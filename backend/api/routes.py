from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from services.dbService import get_job_status, get_roadmap, get_skill_graph
from orchestrator import run_workflow
import uuid, os

router = APIRouter()
MAX_PDF_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB


class ScrapeRequest(BaseModel):
    job_title: str = "software engineer"


@router.post("/analyze-profile")
async def analyze_profile(
    background_tasks: BackgroundTasks,
    resume: UploadFile = File(...),
    github_url: str = None,
):
    if not resume.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF resumes accepted.")

    content = await resume.read()
    if len(content) > MAX_PDF_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="PDF must be ≤ 2 MB.")

    job_id = str(uuid.uuid4())
    background_tasks.add_task(run_workflow, job_id, content, github_url)
    return {"job_id": job_id, "status": "queued"}


@router.get("/status/{job_id}")
async def status(job_id: str):
    row = await get_job_status(job_id)
    if not row:
        raise HTTPException(status_code=404, detail="Job not found.")
    return row


@router.get("/roadmap/{job_id}")
async def roadmap(job_id: str):
    data = await get_roadmap(job_id)
    if not data:
        raise HTTPException(status_code=404, detail="Roadmap not ready yet.")
    return data


@router.get("/skill-graph")
async def skill_graph():
    return await get_skill_graph()


@router.post("/trigger-scrape")
async def trigger_scrape(body: ScrapeRequest, background_tasks: BackgroundTasks):
    from agents.jobMarketAgent import scrape_and_embed
    background_tasks.add_task(scrape_and_embed, body.job_title)
    return {"status": "scrape triggered", "job_title": body.job_title}
