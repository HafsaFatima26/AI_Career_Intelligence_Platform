"""
LangGraph Orchestrator — Sitting 4 update.

State shape:
  {
    job_id:        str,
    resume_bytes:  bytes,
    github_url:    str | None,
    resume_text:   str,
    user_skills:   list,
    market_skills: list,
    gap_report:    dict,
    final_roadmap: str,
  }

Sitting 4: run_workflow now calls the Profiling Agent (parse_resume + parse_github).
Full LangGraph node graph wiring in Sitting 7.
"""

from typing import TypedDict, Optional
from services.dbService import upsert_job_status
from utils.pdfParser import extract_text


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
    """
    Background task entry point — called by POST /api/analyze-profile.

    Sitting 4 implements:
      - PDF text extraction from bytes
      - Profiling Agent (resume + optional GitHub parsing)

    Sitting 5 will add: Gap Analysis Agent
    Sitting 6 will add: Strategist Agent
    Sitting 7 will wire everything into a proper LangGraph StateGraph.
    """
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

    try:
        # ── Step 1: Extract text from PDF bytes ──────────────────────────────
        await upsert_job_status(job_id, "extracting_text")
        try:
            resume_text = extract_text(resume_bytes)
            state["resume_text"] = resume_text
            print(f"[Orchestrator] job {job_id} — PDF extracted ({len(resume_text)} chars)")
        except ValueError as exc:
            await upsert_job_status(job_id, "error", {"error_message": str(exc)})
            print(f"[Orchestrator] PDF extraction failed for {job_id}: {exc}")
            return

        # ── Step 2: Profiling Agent ───────────────────────────────────────────
        from agents.profilingAgent import profile_user
        state = await profile_user(state)
        # profile_user sets status → "profiling" then → "gap_analysis" and
        # persists user_skills to Supabase internally.

        # ── Steps 3-5: Stubs (Sittings 5, 6, 7) ─────────────────────────────
        # Gap Analysis Agent  → Sitting 5
        # Strategist Agent    → Sitting 6
        # Full LangGraph wiring → Sitting 7

        await upsert_job_status(job_id, "pending_gap_analysis")
        print(
            f"[Orchestrator] job {job_id} — Profiling done. "
            f"{len(state['user_skills'])} user skills stored. "
            f"Awaiting Gap Analysis (Sitting 5)."
        )

    except Exception as exc:
        await upsert_job_status(job_id, "error", {"error_message": str(exc)})
        print(f"[Orchestrator] Unhandled error for job {job_id}: {exc}")
        raise
