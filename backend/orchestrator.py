"""
LangGraph Orchestrator — State machine connecting all agents.
State shape:
  {
    job_id: str,
    resume_bytes: bytes,
    github_url: str | None,
    resume_text: str,
    user_skills: list,
    market_skills: list,
    gap_report: dict,
    final_roadmap: str,
  }
Full graph wiring happens in Sitting 7.
"""
from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional
from services.dbService import upsert_job_status


class WorkflowState(TypedDict):
    job_id: str
    resume_bytes: bytes
    github_url: Optional[str]
    resume_text: str
    user_skills: list
    market_skills: list
    gap_report: dict
    final_roadmap: str


async def run_workflow(job_id: str, resume_bytes: bytes, github_url: str | None):
    """Background task entry point – called by /analyze-profile."""
    await upsert_job_status(job_id, "profiling")
    state: WorkflowState = {
        "job_id": job_id,
        "resume_bytes": resume_bytes,
        "github_url": github_url,
        "resume_text": "",
        "user_skills": [],
        "market_skills": [],
        "gap_report": {},
        "final_roadmap": "",
    }
    # TODO (Sitting 7): wire LangGraph nodes.
    # Placeholder: mark as pending.
    await upsert_job_status(job_id, "pending_full_implementation")
    print(f"[Orchestrator] job {job_id} scaffolded. Full graph in Sitting 7.")
