"""
Ephe – Scheduler REST API
server/routes/schedule.py

Endpoints:
  POST /api/schedule          → Create a job
  GET  /api/schedule          → List all jobs
  DELETE /api/schedule/{id}   → Remove a job
  GET  /api/schedule/results  → Recent job results
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.scheduler import ephe_scheduler

router = APIRouter(tags=["Schedule"])


class ScheduleCreateRequest(BaseModel):
    task: str                              # Task description in natural language
    cron: str | None = None                # "0 8 * * *" = daily at 8am
    delay_minutes: float | None = None     # J4: relative one-shot (N minutes from now)
    max_runs: int | None = None            # J4: optional run cap, then job is removed


class ScheduleCreateResponse(BaseModel):
    job_id: str
    message: str


@router.post("/schedule", response_model=ScheduleCreateResponse)
def create_schedule(req: ScheduleCreateRequest) -> ScheduleCreateResponse:
    """Create a background job — cron (recurring) or delay_minutes (relative one-shot)."""
    if req.cron is None and req.delay_minutes is None:
        raise HTTPException(
            status_code=422,
            detail="Provide a cron expression ('min hour dom month dow') or delay_minutes.",
        )
    try:
        job_id = ephe_scheduler.add_job(
            task_description=req.task,
            cron_expr=req.cron,
            delay_minutes=req.delay_minutes,
            max_runs=req.max_runs,
        )
        return ScheduleCreateResponse(
            job_id=job_id,
            message=f"Job '{job_id}' scheduled. Next run: {_next_run(job_id)}",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/schedule")
def list_schedules():
    """List all active jobs."""
    return {"jobs": ephe_scheduler.list_jobs()}


@router.get("/schedule/results")
def get_results(limit: int | None = None):
    """Return the last N job results (newest first).

    I7-3: with no limit given, `cron.history_rows` from the register applies — the
    number the user sees in the Cronjobs area decides, not this endpoint."""
    return {"results": ephe_scheduler.get_results(limit=limit)}


@router.delete("/schedule/{job_id}")
def delete_schedule(job_id: str):
    """Delete a job; an unknown id answers 404, never a silent no-op."""
    removed = ephe_scheduler.remove_job(job_id)
    if not removed:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return {"status": "deleted", "job_id": job_id}


# Helper

def _next_run(job_id: str) -> str:
    for j in ephe_scheduler.list_jobs():
        if j["id"] == job_id:
            return j["next_run"] or "unknown"
    return "unknown"


# R19: Automation presets + manual rerun

@router.get("/schedule/presets")
async def list_schedule_presets() -> dict:
    """Curated offline automation presets (no network)."""
    from core.scheduler import SCHEDULE_PRESETS

    return {"presets": SCHEDULE_PRESETS}


@router.post("/schedule/{job_id}/run")
async def run_schedule_job(job_id: str) -> dict:
    """Run a job immediately (rerun) — the result lands in the history."""
    from core.scheduler import ephe_scheduler

    try:
        entry = await ephe_scheduler.run_job_now(job_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return entry
