"""
Supabase connection + pgvector queries.
Tables expected in Supabase:
  - jobs            (id, title, company, description, raw_skills jsonb, created_at)
  - extracted_skills(id, skill, category, seniority, source, frequency,
                      embedding vector(768), created_at)
  - users           (id, job_id text, github_url text, resume_text text,
                      user_skills jsonb, status text, roadmap_md text, created_at)

Sitting 4 additions:
  - create_user_job(job_id, resume_text, github_url)
  - update_user_skills(job_id, skills)
"""
import os
import json
from supabase import create_client, Client
from typing import Optional


_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_KEY"]
        _client = create_client(url, key)
    return _client


async def init_db():
    """Called at startup – lightweight connectivity check."""
    try:
        client = get_client()
        client.table("users").select("id").limit(1).execute()
        print("✅  Supabase connected successfully.")
    except Exception as e:
        print(f"⚠️  Supabase connection warning: {e}")


# ── User / Job-level helpers (Sitting 4) ────────────────────────────────────


async def create_user_job(job_id: str, resume_text: str, github_url: str | None = None):
    """
    Inserts a new row into the users table when a profile analysis job starts.
    Called immediately after job_id is generated, before the background task runs.
    """
    client = get_client()
    payload = {
        "id": job_id,
        "resume_text": resume_text,
        "github_url": github_url,
        "status": "queued",
        "user_skills": json.dumps([]),
        "roadmap_md": None,
    }
    client.table("users").insert(payload).execute()
    print(f"[dbService] Created user job row: {job_id}")


async def update_user_skills(job_id: str, skills: list[dict]):
    """
    Persists the extracted user_skills list (as JSONB) into the users table.
    Called by the Profiling Agent after both resume + GitHub parsing are done.
    """
    client = get_client()
    client.table("users").update({
        "user_skills": json.dumps(skills),
    }).eq("id", job_id).execute()
    print(f"[dbService] Stored {len(skills)} user skills for job {job_id}")


# ── Job-level status helpers ────────────────────────────────────────────────


async def upsert_job_status(job_id: str, status: str, extra: dict = None):
    client = get_client()
    payload = {"id": job_id, "status": status, **(extra or {})}
    client.table("users").upsert(payload).execute()


async def get_job_status(job_id: str):
    """
    Returns the status row for a job, or None if not found.
    Uses maybe_single() so no exception is raised on zero rows.
    """
    client = get_client()
    try:
        res = (
            client.table("users")
            .select("id, status")          # removed created_at – may not exist
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )
        # ── DEBUG (remove after fix confirmed) ──────────────────────────────
        print(f"[DEBUG get_job_status] job_id={job_id!r}")
        print(f"[DEBUG get_job_status] res.data={res.data!r}")
        # ────────────────────────────────────────────────────────────────────
        return res.data
    except Exception as exc:
        print(f"[DEBUG get_job_status] EXCEPTION type={type(exc).__name__} msg={exc}")
        return None


async def get_roadmap(job_id: str):
    """
    Returns the roadmap_md for a job, or None if not found.
    Uses maybe_single() so no exception is raised on zero rows.
    """
    client = get_client()
    try:
        res = (
            client.table("users")
            .select("roadmap_md")
            .eq("id", job_id)
            .maybe_single()
            .execute()
        )
        return res.data  # None if no row matched
    except Exception as exc:
        print(f"[dbService] get_roadmap error for {job_id}: {exc}")
        return None


# ── Skill helpers ────────────────────────────────────────────────────────────


async def upsert_skill(name: str, category: str, seniority: str, source: str, embedding: list):
    client = get_client()
    payload = {
        "name": name,
        "category": category,
        "seniority": seniority,
        "source": source,
        "embedding": embedding,
    }
    client.table("extracted_skills").upsert(payload, on_conflict="name,source").execute()


async def similarity_search(query_embedding: list, top_k: int = 20) -> list:
    """
    Calls the Supabase RPC `match_skills` which performs cosine similarity search:
      SELECT * FROM extracted_skills
      ORDER BY embedding <=> query_embedding
      LIMIT top_k;
    """
    client = get_client()
    res = client.rpc(
        "match_skills",
        {"query_embedding": query_embedding, "match_count": top_k},
    ).execute()
    return res.data or []


async def get_skill_graph():
    client = get_client()
    res = (
        client.table("extracted_skills")
        .select("id, skill, category, seniority, frequency")
        .order("frequency", desc=True)
        .limit(100)
        .execute()
    )
    skills = res.data
    nodes = [
        {
            "id": s["id"],
            "label": s["skill"],
            "category": s["category"],
            "seniority": s["seniority"],
            "frequency": s["frequency"],
        }
        for s in skills
    ]
    edges = []
    for i, a in enumerate(skills):
        for b in skills[i + 1:]:
            if a["category"] == b["category"]:
                edges.append({"source": a["id"], "target": b["id"], "weight": 1})
    return {"nodes": nodes, "edges": edges}


# ── Raw job helpers ──────────────────────────────────────────────────────────


async def insert_jobs(jobs: list[dict]):
    client = get_client()
    if jobs:
        client.table("jobs").upsert(jobs, on_conflict="source_url").execute()
