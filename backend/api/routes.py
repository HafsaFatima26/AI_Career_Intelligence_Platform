"""
FastAPI API Routes — Sitting 4 update.
Changes vs Sitting 3:
  - /analyze-profile now fully activated:
      reads PDF bytes → extract_text() → create_user_job() → run_workflow()
  - import list updated with create_user_job + extract_text
"""

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from pydantic import BaseModel
from services.dbService import (
    get_job_status,
    get_roadmap,
    get_skill_graph,
    create_user_job,
)
from orchestrator import run_workflow
from utils.pdfParser import extract_text
import uuid


router = APIRouter()
MAX_PDF_SIZE_BYTES = 2 * 1024 * 1024   # 2 MB


class ScrapeRequest(BaseModel):
    job_title: str = "software engineer"


# ── POST /api/analyze-profile ─────────────────────────────────────────────────
# Flow:
#  1. Validate file type + size (sync, before anything hits the DB).
#  2. Extract text from PDF bytes immediately (cheap, <100ms).
#  3. Insert a users row with status="queued" so polling works instantly.
#  4. Fire run_workflow() as a background task and return job_id immediately.


@router.post("/analyze-profile")
async def analyze_profile(
    background_tasks: BackgroundTasks,
    resume: UploadFile = File(...),
    github_url: str = None,
):
    # ── Validation ──
    if not resume.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF resumes are accepted.")

    content = await resume.read()
    if len(content) > MAX_PDF_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Resume PDF must be ≤ 2 MB.")

    # ── Extract text synchronously (fast, in-process) ──
    try:
        resume_text = extract_text(content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # ── Create a DB row immediately so /status/:id works right away ──
    job_id = str(uuid.uuid4())
    await create_user_job(job_id, resume_text, github_url)

    # ── Queue the full agentic workflow ──
    # run_workflow receives bytes (orchestrator handles further processing).
    background_tasks.add_task(run_workflow, job_id, content, github_url)

    return {
        "job_id": job_id,
        "status": "queued",
        "message": "Profile analysis started. Poll /api/status/{job_id} for updates.",
    }


# ── GET /api/status/:job_id ───────────────────────────────────────────────────


@router.get("/status/{job_id}")
async def status(job_id: str):
    row = await get_job_status(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found.")
    return row


# ── GET /api/roadmap/:job_id ──────────────────────────────────────────────────


@router.get("/roadmap/{job_id}")
async def roadmap(job_id: str):
    # Guard: only return roadmap if job is actually done
    status_row = await get_job_status(job_id)
    if not status_row:
        raise HTTPException(status_code=404, detail="Job not found.")
    if status_row.get("status") != "done":
        raise HTTPException(
            status_code=202,
            detail=f"Roadmap not ready yet. Current status: {status_row.get('status')}",
        )
    data = await get_roadmap(job_id)
    if not data or not data.get("roadmap_md"):
        raise HTTPException(status_code=404, detail="Roadmap not available.")
    return data


# ── GET /api/skill-graph ──────────────────────────────────────────────────────


@router.get("/skill-graph")
async def skill_graph():
    return await get_skill_graph()


# ── POST /api/trigger-scrape ──────────────────────────────────────────────────


@router.post("/trigger-scrape")
async def trigger_scrape(body: ScrapeRequest, background_tasks: BackgroundTasks):
    from services.scraperService import scrape_all_jobs, save_jobs_to_db, save_jobs_to_json

    async def run_scrape():
        jobs = await scrape_all_jobs()
        save_jobs_to_json(jobs)
        await save_jobs_to_db(jobs)

    background_tasks.add_task(run_scrape)
    return {"status": "scrape triggered", "message": "Check terminal for progress logs"}


# ── GET /api/jobs (debug) ─────────────────────────────────────────────────────


@router.get("/jobs")
async def list_jobs(limit: int = 20):
    """Returns recently scraped jobs from Supabase for verification."""
    from services.dbService import get_client
    client = get_client()
    res = (
        client.table("jobs")
        .select("id, title, company, source_url")
        .limit(limit)
        .execute()
    )
    return {"count": len(res.data), "jobs": res.data}


# ── POST /api/run-agent (debug) ───────────────────────────────────────────────


@router.post("/run-agent")
async def run_agent(background_tasks: BackgroundTasks):
    """Triggers the Job Market Agent to extract + embed skills from scraped jobs."""
    from agents.jobMarketAgent import run_job_market_agent
    background_tasks.add_task(run_job_market_agent, 50)
    return {"status": "agent started", "message": "Check terminal for progress logs"}
