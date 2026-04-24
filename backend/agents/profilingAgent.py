"""
Sitting 4 — User Profiling Agent
Responsibilities:
  1. parse_resume(resume_text) → list[dict]   — Groq LLaMA-3.3-70b, strict JSON
  2. parse_github(github_url)  → list[dict]   — GitHub API /repos, extract languages+topics
  3. profile_user(state)       → WorkflowState — LangGraph node entry point
"""

import os
import re
import json
import httpx
from groq import AsyncGroq

GROQ_MODEL = "llama-3.3-70b-versatile"

# Schema injected into every prompt so the LLM is forced into structure.
SKILL_JSON_SCHEMA = """
Return ONLY a JSON array. No markdown, no explanation, no trailing text.
Each element must match this exact schema:
[
  {
    "skill": "<concise skill name, e.g. Python, FastAPI, Docker>",
    "category": "<one of: Language | Framework | Tool | Cloud | Database | Concept | Soft Skill>",
    "seniority": "<one of: Junior | Mid | Senior | Any>"
  }
]
"""

RESUME_PROMPT_TEMPLATE = """
You are an expert technical recruiter. Extract every technical and soft skill
mentioned in the following resume text.

Rules:
- Normalise skill names (e.g. "node.js" → "Node.js", "postgres" → "PostgreSQL").
- Do NOT include job titles, company names, or education degrees as skills.
- Assign seniority based on context clues (years of experience, role level).
  If unclear, use "Any".
- Deduplicate: if the same skill appears multiple times, include it once.
- Maximum 40 skills.

{schema}

Resume:
\"\"\"
{resume_text}
\"\"\"
"""

GITHUB_PROMPT_TEMPLATE = """
You are an expert technical recruiter. Based on the following list of GitHub
repository metadata (languages + topics), infer the developer's skill set.

Rules:
- Convert raw language names to proper skill entries (e.g. "Jupyter Notebook" → "Python").
- Map topics to skills where sensible (e.g. "machine-learning" → "Machine Learning").
- Skip generic/irrelevant topics (e.g. "awesome", "hacktoberfest").
- Assign seniority as "Any" unless there are clear signals otherwise.
- Deduplicate and cap at 30 skills.

{schema}

Repository metadata (JSON):
{repos_json}
"""


def _extract_username(github_url: str) -> str | None:
    """Extracts username from various GitHub URL formats."""
    url = github_url.rstrip("/")
    match = re.search(r"github\.com/([\w\-\.]+)", url)
    return match.group(1) if match else None


def _parse_json_response(raw: str) -> list[dict]:
    """Strips markdown fences and parses JSON array from LLM output."""
    # Remove ```json ... ``` or ``` ... ``` wrappers
    cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"```\s*$", "", cleaned.strip(), flags=re.MULTILINE)
    data = json.loads(cleaned.strip())
    if not isinstance(data, list):
        raise ValueError("LLM did not return a JSON array.")
    validated = []
    valid_cats = {"Language", "Framework", "Tool", "Cloud", "Database", "Concept", "Soft Skill"}
    valid_sen  = {"Junior", "Mid", "Senior", "Any"}
    for item in data:
        if not isinstance(item, dict):
            continue
        skill    = str(item.get("skill", "")).strip()
        category = str(item.get("category", "Concept")).strip()
        seniority= str(item.get("seniority", "Any")).strip()
        if not skill:
            continue
        if category not in valid_cats:
            category = "Concept"
        if seniority not in valid_sen:
            seniority = "Any"
        validated.append({"skill": skill, "category": category, "seniority": seniority})
    return validated


async def parse_resume(resume_text: str) -> list[dict]:
    """
    Sends resume text to Groq LLaMA-3.3-70b and returns extracted skills.
    Raises ValueError on LLM or parse failure.
    """
    client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
    prompt = RESUME_PROMPT_TEMPLATE.format(
        schema=SKILL_JSON_SCHEMA,
        resume_text=resume_text[:6000],   # guard against token overflow
    )
    response = await client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=2048,
    )
    raw = response.choices[0].message.content
    skills = _parse_json_response(raw)
    print(f"[ProfilingAgent] Resume parsed → {len(skills)} skills extracted.")
    return skills


async def parse_github(github_url: str) -> list[dict]:
    """
    Hits the GitHub REST API to fetch repos for a user, then calls Groq to
    extract skills from languages + topics.  Returns [] gracefully on failure.
    """
    username = _extract_username(github_url)
    if not username:
        print(f"[ProfilingAgent] Could not parse username from: {github_url}")
        return []

    headers = {"Accept": "application/vnd.github.v3+json"}
    gh_token = os.environ.get("GITHUB_TOKEN")
    if gh_token:
        headers["Authorization"] = f"Bearer {gh_token}"

    async with httpx.AsyncClient(timeout=15.0) as http:
        try:
            resp = await http.get(
                f"https://api.github.com/users/{username}/repos",
                params={"per_page": 30, "sort": "pushed"},
                headers=headers,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                print(f"[ProfilingAgent] GitHub user not found: {username}")
            else:
                print(f"[ProfilingAgent] GitHub API error {exc.response.status_code}: {exc}")
            return []
        except Exception as exc:
            print(f"[ProfilingAgent] GitHub fetch failed: {exc}")
            return []

    repos = resp.json()
    # Summarise to a compact payload (avoid sending massive JSON to Groq)
    repo_summary = [
        {
            "name": r.get("name", ""),
            "language": r.get("language"),
            "topics": r.get("topics", []),
            "description": (r.get("description") or "")[:120],
        }
        for r in repos
        if not r.get("fork", False)          # skip forks
    ][:25]

    if not repo_summary:
        print(f"[ProfilingAgent] No original repos found for {username}.")
        return []

    client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
    prompt = GITHUB_PROMPT_TEMPLATE.format(
        schema=SKILL_JSON_SCHEMA,
        repos_json=json.dumps(repo_summary, indent=2),
    )
    response = await client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=1024,
    )
    raw = response.choices[0].message.content
    try:
        skills = _parse_json_response(raw)
        print(f"[ProfilingAgent] GitHub parsed → {len(skills)} skills extracted for {username}.")
        return skills
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"[ProfilingAgent] Could not parse GitHub LLM response: {exc}")
        return []


def _merge_skills(resume_skills: list[dict], github_skills: list[dict]) -> list[dict]:
    """
    Merges two skill lists, deduplicating on skill name (case-insensitive).
    Resume skills take precedence for seniority/category on conflict.
    """
    seen: dict[str, dict] = {}
    for s in resume_skills:
        key = s["skill"].lower()
        seen[key] = s
    for s in github_skills:
        key = s["skill"].lower()
        if key not in seen:
            seen[key] = s
    return list(seen.values())


async def profile_user(state: dict) -> dict:
    """
    LangGraph node — called by orchestrator.
    Reads  : state["resume_text"], state["github_url"], state["job_id"]
    Writes : state["user_skills"]
    Updates: Supabase users row status → 'profiling' then 'gap_analysis'
    """
    from services.dbService import upsert_job_status, update_user_skills

    job_id      = state["job_id"]
    resume_text = state.get("resume_text", "")
    github_url  = state.get("github_url")

    await upsert_job_status(job_id, "profiling")

    # 1. Parse resume
    resume_skills: list[dict] = []
    if resume_text.strip():
        try:
            resume_skills = await parse_resume(resume_text)
        except Exception as exc:
            print(f"[ProfilingAgent] Resume parse error for {job_id}: {exc}")

    # 2. Optionally parse GitHub
    github_skills: list[dict] = []
    if github_url:
        github_skills = await parse_github(github_url)

    # 3. Merge
    user_skills = _merge_skills(resume_skills, github_skills)

    # 4. Persist to Supabase
    await update_user_skills(job_id, user_skills)
    await upsert_job_status(job_id, "gap_analysis")

    print(f"[ProfilingAgent] job {job_id} → {len(user_skills)} total user skills stored.")
    return {**state, "user_skills": user_skills}
