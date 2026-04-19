"""
Supabase connection + pgvector queries.
Tables expected in Supabase:
  - jobs (id, title, company, description, raw_skills jsonb, created_at)
  - extracted_skills (id, name, category, seniority, source, embedding vector(768), created_at)
  - users (id, job_id, github_url, resume_text, status, roadmap_md, created_at)
"""
import os
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


# ── Job-level status helpers ────────────────────────────────────────────────

async def upsert_job_status(job_id: str, status: str, extra: dict = None):
    client = get_client()
    payload = {"id": job_id, "status": status, **(extra or {})}
    client.table("users").upsert(payload).execute()


async def get_job_status(job_id: str):
    client = get_client()
    res = client.table("users").select("id, status, created_at").eq("id", job_id).single().execute()
    return res.data


async def get_roadmap(job_id: str):
    client = get_client()
    res = client.table("users").select("roadmap_md").eq("id", job_id).single().execute()
    return res.data


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
    Calls the Supabase RPC `match_skills` which does:
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
    skills = client.table("extracted_skills").select("id, name, category, seniority, source").execute()
    nodes = [
        {"id": s["id"], "label": s["name"], "group": s["category"]}
        for s in (skills.data or [])
    ]
    # Simple co-occurrence edges: skills that share the same source job post
    edges = []
    return {"nodes": nodes, "edges": edges}
