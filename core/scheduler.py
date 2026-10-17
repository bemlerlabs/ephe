"""
Ephe – Background Job Scheduler
core/scheduler.py

APScheduler integration for asynchronous background jobs.
Use /schedule in chat to define recurring tasks.
"""
from __future__ import annotations

import os

import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from core.scheduler_config import (history_keep, history_rows, max_parallel_jobs,
                         misfire_grace_seconds)

logger = logging.getLogger(__name__)


def _jobs_file() -> Path:
    """Jobs persistence path, resolved lazily so tests can redirect it via env."""
    return Path(
        os.environ.get("EPHE_SCHEDULE_JOBS", str(Path.home() / ".ephe" / "scheduled_jobs.json"))
    )


def _results_file() -> Path:
    """Run-history path, resolved lazily so tests can redirect it via env."""
    return Path(
        os.environ.get("EPHE_SCHEDULE_RESULTS", str(Path.home() / ".ephe" / "schedule_results.json"))
    )

# Registry for live results (in-memory, per server session)
_job_results: list[dict] = []

# R19: curated automation templates (offline) — presets for the panel.
SCHEDULE_PRESETS: list[dict] = [
    {
        "id": "daily-standup",
        "title": "Daily Standup Summary",
        "task": "Create a short standup summary: what is planned today, open items and blockers you know from memory.",
        "cron": "0 8 * * 1-5",
    },
    {
        "id": "inbox-triage",
        "title": "Inbox Triage",
        "task": "Summarize the most important open to-dos and notes for the workspace and propose priorities.",
        "cron": "0 9 * * 1-5",
    },
    {
        "id": "project-digest",
        "title": "Project Digest",
        "task": "Analyze the workspace project and summarize progress, risks and next steps.",
        "cron": "0 17 * * 5",
    },
    {
        "id": "news-digest",
        "title": "AI News Digest",
        "task": "Research the most important AI news of the last 24 hours and summarize them briefly.",
        "cron": "0 7 * * *",
    },
    {
        "id": "weekly-review",
        "title": "Weekly Review",
        "task": "Weekly review: what was done, learnings, and the focus for next week — as a compact summary.",
        "cron": "0 18 * * 5",
    },
]


class EpheScheduler:
    def __init__(self):
        self._scheduler = None
        self._on_result_callback: Callable[[dict], None] | None = None

    def _ensure_scheduler(self):
        if self._scheduler is None:
            from apscheduler.schedulers.asyncio import AsyncIOScheduler

            # P1-2: the AsyncIO executor is the right choice — it puts coroutines
            # (_run_task) as tasks on the running loop and non-coroutine
            # callbacks into the loop's default thread pool (run_in_executor).
            # JSON persistence additionally goes via asyncio.to_thread (see _run_task),
            # so the loop stays free for SSE/REST.
            self._scheduler = AsyncIOScheduler()
        return self._scheduler

    def start(self):
        """Start the scheduler on the CURRENT thread's event loop.

        MUST be called from the asyncio event-loop thread (async lifespan),
        never via a worker thread: AsyncIOScheduler needs a running loop in
        the calling thread, otherwise jobs queue as pending forever and never
        fire. Idempotent: a second call on a running scheduler is a no-op.
        """
        scheduler = self._ensure_scheduler()
        if getattr(scheduler, "running", False):
            return
        scheduler.start()
        self._load_persisted_jobs()
        _load_results()
        logger.info("EpheScheduler started.")

    def stop(self):
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)

    def set_result_callback(self, cb: Callable[[dict], None]):
        """Callback invoked by the SSE bridge on new job results."""
        self._on_result_callback = cb

    def list_jobs(self) -> list[dict]:
        # Field parity with the frontend (api.ts expects task/cron).
        jobs = []
        scheduler = self._ensure_scheduler()
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.date import DateTrigger
        for job in scheduler.get_jobs():
            cron_str = ""
            if isinstance(job.trigger, CronTrigger):
                fields = {f.name: str(f) for f in job.trigger.fields}
                cron_str = (
                    f"{fields.get('minute','*')} {fields.get('hour','*')} "
                    f"{fields.get('day','*')} {fields.get('month','*')} "
                    f"{fields.get('day_of_week','*')}"
                )
            elif isinstance(job.trigger, DateTrigger):
                # J4: relative one-shot → short label + exact next run
                cron_str = "once"
            args = list(job.args or [])
            task = args[0] if args else job.name
            entry = {
                "id": job.id,
                "task": task,
                "cron": cron_str,
                # getattr + default: next_run_time RAISES on a never-started
                # scheduler (TestClient without lifespan).
                "next_run": str(job.next_run_time) if getattr(job, "next_run_time", None) else None,
            }
            if len(args) > 2 and args[2] is not None:
                entry["max_runs"] = args[2]
            jobs.append(entry)
        return jobs

    async def run_job_now(self, job_id: str) -> dict:
        """R19: run a job manually (rerun) — result like scheduled runs."""
        scheduler = self._ensure_scheduler()
        job = scheduler.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        args = list(job.args or [])
        task = args[0] if args else job.name
        max_runs = args[2] if len(args) > 2 else None
        await self._run_task(task, job_id, max_runs)
        return _job_results[-1]

    def remove_job(self, job_id: str) -> bool:
        try:
            scheduler = self._ensure_scheduler()
            scheduler.remove_job(job_id)
            self._persist_jobs()
            return True
        except Exception:
            return False

    def add_job(
        self,
        task_description: str,
        cron_expr: str | None = None,
        job_id: str | None = None,
        delay_minutes: float | None = None,
        max_runs: int | None = None,
    ) -> str:
        """
        Add a new background job (J4 parity: relative one-shots + run cap).

        Args:
            task_description: What Ephe should do on every trigger (natural language).
            cron_expr:        Cron string: "minute hour day_of_month month day_of_week"
                              Example: "0 8 * * *" = daily at 8am
            job_id:           Optional. Auto-generated if empty.
            delay_minutes:  Relative one-shot: fire once after N minutes from now
                              (DateTrigger). Takes precedence over cron_expr.
            max_runs:       Optional cap — after N executed runs the job is removed.
        Returns:
            The created job_id.
        """
        import uuid
        if not job_id:
            job_id = f"ephe_job_{uuid.uuid4().hex[:8]}"

        timezone_name = os.environ.get("EPHE_TIMEZONE", "Europe/Berlin")
        if delay_minutes is not None:
            from apscheduler.triggers.date import DateTrigger
            from datetime import timedelta

            run_date = datetime.now(timezone.utc) + timedelta(minutes=float(delay_minutes))
            trigger = DateTrigger(run_date=run_date, timezone=timezone_name)
            schedule_note = f"once in {delay_minutes} min"
        else:
            if not cron_expr:
                raise ValueError(
                    "Provide a cron expression ('min hour dom month dow') or delay_minutes."
                )
            parts = cron_expr.strip().split()
            if len(parts) != 5:
                raise ValueError(f"Invalid cron expression: '{cron_expr}'. Expected: 'min hour dom month dow'")

            minute, hour, day, month, day_of_week = parts
            from apscheduler.triggers.cron import CronTrigger
            trigger = CronTrigger(
                minute=minute,
                hour=hour,
                day=day,
                month=month,
                day_of_week=day_of_week,
                timezone=timezone_name,
            )
            schedule_note = f"cron({cron_expr})"

        scheduler = self._ensure_scheduler()
        scheduler.add_job(
            func=self._run_task,
            trigger=trigger,
            id=job_id,
            name=task_description[:80],
            args=[task_description, job_id, max_runs],
            replace_existing=True,
            misfire_grace_time=misfire_grace_seconds(),
            max_instances=max_parallel_jobs(),
        )

        self._persist_jobs()
        logger.info(f"Job '{job_id}' scheduled: '{task_description}' @ {schedule_note}")
        return job_id

    async def _run_task(
        self, task_description: str, job_id: str, max_runs: int | None = None
    ):
        """Run a scheduled task and persist the result.

        max_runs (J4): after N entries for this job in the results history
        the job is removed from the scheduler (one-shot caps, as in the reference).
        """
        from core.react import react_loop  # lazy import to avoid circular

        logger.info(f"Job '{job_id}' executing: {task_description[:60]}…")
        start_ts = datetime.now(timezone.utc).isoformat()
        result = ""
        error = None

        try:
            from core.model_provider import chosen_model

            result = await react_loop(
                question=task_description,
                model=chosen_model("a scheduled job"),
                context=[],
                # n1-memory: a job has no chat session, so its turn is keyed to the
                # job itself — the provenance trail names which job ran it instead
                # of answering the empty-session default.
                session_id=f"sched-{job_id}",
            )
        except Exception as exc:
            error = str(exc)
            logger.error(f"Job '{job_id}' failed: {exc}")

        entry = {
            "job_id": job_id,
            "task": task_description,
            "executed_at": start_ts,
            "result": result or "",
            "error": error,
        }
        _job_results.append(entry)

        keep = history_keep()
        while len(_job_results) > keep:
            _job_results.pop(0)
        # P1-2: file I/O out of the loop — the event loop stays free for SSE/REST.
        await asyncio.to_thread(_persist_results)

        # J4: max_runs limit — the count in the results history decides (the
        # results file is the truth behind the caps, like the reference).
        if isinstance(max_runs, int) and max_runs > 0:
            runs = sum(1 for e in _job_results if e.get("job_id") == job_id)
            if runs >= max_runs:
                try:
                    self._ensure_scheduler().remove_job(job_id)
                except Exception:
                    pass
                await asyncio.to_thread(self._persist_jobs)

        # Notify SSE bridge if connected
        if self._on_result_callback:
            try:
                self._on_result_callback(entry)
            except Exception:
                pass

    def get_results(self, limit: int | None = None) -> list[dict]:
        rows = history_rows() if limit is None else limit
        return list(reversed(_job_results[-rows:]))

    # Persistence
    def _persist_jobs(self):
        jobs_path = _jobs_file()
        jobs_path.parent.mkdir(parents=True, exist_ok=True)
        jobs_data = []
        scheduler = self._ensure_scheduler()
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.date import DateTrigger
        for job in scheduler.get_jobs():
            trigger = job.trigger
            args = list(job.args or [])
            max_runs = args[2] if len(args) > 2 else None
            if isinstance(trigger, CronTrigger):
                fields = {f.name: str(f) for f in trigger.fields}
                cron_str = (
                    f"{fields.get('minute','*')} "
                    f"{fields.get('hour','*')} "
                    f"{fields.get('day','*')} "
                    f"{fields.get('month','*')} "
                    f"{fields.get('day_of_week','*')}"
                )
                entry = {
                    "id": job.id,
                    "name": job.name,
                    "cron": cron_str,
                }
            elif isinstance(trigger, DateTrigger):
                # J4: persist the one-shot with its absolute run date + cap
                entry = {
                    "id": job.id,
                    "name": job.name,
                    "cron": "once",
                    "run_date": trigger.run_date.isoformat(),
                }
            else:
                continue
            if max_runs is not None:
                entry["max_runs"] = max_runs
            jobs_data.append(entry)
        jobs_path.write_text(json.dumps(jobs_data, indent=2, ensure_ascii=False))

    def _load_persisted_jobs(self):
        jobs_path = _jobs_file()
        if not jobs_path.exists():
            return
        try:
            jobs_data = json.loads(jobs_path.read_text())
            for jd in jobs_data:
                max_runs = jd.get("max_runs")
                if jd.get("cron") == "once" and jd.get("run_date"):
                    # J4: one-shot restore — remaining time from the absolute date
                    run_date = datetime.fromisoformat(jd["run_date"])
                    remaining = (run_date - datetime.now(timezone.utc)).total_seconds() / 60.0
                    self.add_job(
                        task_description=jd["name"],
                        job_id=jd["id"],
                        delay_minutes=max(0.01, remaining),
                        max_runs=max_runs,
                    )
                    continue
                self.add_job(
                    task_description=jd["name"],
                    cron_expr=jd["cron"],
                    job_id=jd["id"],
                    max_runs=max_runs,
                )
            logger.info(f"{len(jobs_data)} persisted jobs restored.")
        except Exception as exc:
            logger.warning(f"Could not load persisted jobs: {exc}")


def _persist_results():
    try:
        results_path = _results_file()
        results_path.parent.mkdir(parents=True, exist_ok=True)
        results_path.write_text(
            json.dumps(_job_results[-history_keep():], ensure_ascii=False, indent=1)
        )
    except Exception as exc:
        logger.warning(f"Could not save run history: {exc}")


def _load_results():
    results_path = _results_file()
    if not results_path.exists():
        return
    try:
        data = json.loads(results_path.read_text())
        if isinstance(data, list):
            _job_results.extend(data[-history_keep():])
            logger.info(f"{len(_job_results)} run-history entries restored.")
    except Exception as exc:
        logger.warning(f"Could not load run history: {exc}")


# Singleton
ephe_scheduler = EpheScheduler()
