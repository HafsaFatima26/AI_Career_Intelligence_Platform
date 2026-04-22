"""
Job Market Agent — Sitting 3
1. Reads raw job descriptions from Supabase `jobs` table
2. Sends each to Groq (llama-3.3-70b) with strict JSON schema prompt
3. Extracts structured skills: [{skill, category, seniority}]
4. Embeds each skill name via Gemini text-embedding-004 (768-dim)
5. Saves skill + frequency count + embedding to `extracted_skills` table
"""
import json
import asyncio
import os
from typing import List, Dict
from groq import Groq
from services.embeddingService import embed_batch
from services.dbService import get_client


# ── Groq setup ────────────────────────────────────────────────────────────────
def get_groq_client() -> Groq:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY is not set. Add it to your .env file.")
    return Groq(api_key=api_key)


# ── Skill extraction prompt ───────────────────────────────────────────────────
EXTRACTION_PROMPT = """You are a technical recruiter AI. Extract ONLY technical skills from the job description below.

Return STRICTLY valid JSON — no markdown, no explanation, just the JSON array.

Schema:
[
  {{"skill": "string", "category": "Language|Framework|Tool|Cloud|Database|Concept|Soft", "seniority": "Junior|Mid|Senior|Any"}}
]

Rules:
- Max 15 skills per job
- Only technical/hard skills (no "communication", "teamwork" etc.)
- Normalize skill names (e.g. "ML" → "Machine Learning", "JS" → "JavaScript")
- If unsure of seniority, use "Any"

Job Description:
{description}"""


# ── Extract skills from one job ───────────────────────────────────────────────
async def extract_skills_from_job(client: Groq, job: Dict) -> List[Dict]:
    """Calls Groq to extract structured skills from one job description."""
    description = job.get("description", "")[:2000]  # cap tokens
    if not description or len(description) < 50:
        return []

    prompt = EXTRACTION_PROMPT.format(description=description)
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1024,
        )
        raw = response.choices[0].message.content.strip()

        # Strip markdown code fences if model wraps in ```json
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        skills = json.loads(raw)
        if not isinstance(skills, list):
            return []

        # Attach job_id to each skill
        for s in skills:
            s["job_id"] = job.get("id")
        return skills

    except (json.JSONDecodeError, Exception) as e:
        print(f"  ⚠️  Skill extraction failed for job {job.get('id', '?')}: {e}")
        return []


# ── Aggregate skill frequencies ───────────────────────────────────────────────
def aggregate_skills(all_skills: List[Dict]) -> List[Dict]:
    """
    Deduplicates skills by name and counts frequency.
    Returns: [{skill, category, seniority, frequency}]
    """
    freq_map: Dict[str, Dict] = {}
    for s in all_skills:
        name = s.get("skill", "").strip()
        if not name:
            continue
        key = name.lower()
        if key not in freq_map:
            freq_map[key] = {
                "skill": name,
                "category": s.get("category", "Tool"),
                "seniority": s.get("seniority", "Any"),
                "frequency": 1,
            }
        else:
            freq_map[key]["frequency"] += 1

    # Sort by frequency descending
    return sorted(freq_map.values(), key=lambda x: x["frequency"], reverse=True)


# ── Save skills + embeddings to Supabase ─────────────────────────────────────
async def save_skills_with_embeddings(aggregated: List[Dict]) -> int:
    """Embeds skill names in batch and upserts into extracted_skills table."""
    db = get_client()
    if not aggregated:
        return 0

    print(f"🔢  Embedding {len(aggregated)} unique skills via Gemini text-embedding-004...")
    skill_names = [s["skill"] for s in aggregated]

    # Batch embed all skill names at once
    embeddings = embed_batch(skill_names)

    rows = []
    for skill, embedding in zip(aggregated, embeddings):
        rows.append({
            "skill": skill["skill"],
            "category": skill["category"],
            "seniority": skill["seniority"],
            "frequency": skill["frequency"],
            "embedding": embedding,  # 768-dim vector
        })

    # Upsert in chunks of 10 (vectors are large)
    saved = 0
    for i in range(0, len(rows), 10):
        chunk = rows[i:i + 10]
        try:
            db.table("extracted_skills").upsert(
                chunk, on_conflict="skill"
            ).execute()
            saved += len(chunk)
            print(f"  💾  Saved skills {i + 1}–{i + len(chunk)}")
        except Exception as e:
            print(f"  ⚠️  DB error: {e}")

    return saved


# ── Main agent entry point ────────────────────────────────────────────────────
async def run_job_market_agent(limit: int = 50):
    """
    Full pipeline:
    1. Fetch jobs from Supabase
    2. Extract skills via Groq (llama-3.3-70b)
    3. Aggregate frequencies
    4. Embed via Gemini text-embedding-004 + save to extracted_skills
    """
    print("\n🤖  Job Market Agent starting...")
    db = get_client()
    groq_client = get_groq_client()

    # Fetch jobs
    res = db.table("jobs") \
        .select("id, title, company, description") \
        .limit(limit) \
        .execute()

    jobs = res.data
    if not jobs:
        print("⚠️  No jobs found in DB. Run /api/trigger-scrape first.")
        return 0

    print(f"📋  Processing {len(jobs)} jobs...")

    all_skills = []
    for i, job in enumerate(jobs):
        print(f"  [{i + 1}/{len(jobs)}] {job['title'][:50]} @ {job['company'][:30]}")
        skills = await extract_skills_from_job(groq_client, job)
        all_skills.extend(skills)
        # Small delay to respect Groq free tier rate limits
        if (i + 1) % 10 == 0:
            print("  ⏳  Brief pause...")
            await asyncio.sleep(2)

    print(f"\n📊  Raw skills extracted: {len(all_skills)}")

    # Aggregate frequencies
    aggregated = aggregate_skills(all_skills)
    print(f"📊  Unique skills after dedup: {len(aggregated)}")
    print(f"🏆  Top 10 market skills:")
    for s in aggregated[:10]:
        print(f"     {s['frequency']:3d}x  {s['skill']} ({s['category']})")

    # Embed + save
    saved = await save_skills_with_embeddings(aggregated)
    print(f"\n✅  Job Market Agent complete. {saved} skills saved to Supabase.")
    return saved
