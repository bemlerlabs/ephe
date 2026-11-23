"""I7-3 — the schedule dials reach the scheduler.

Four values were literals in the code (misfire 3600 s, history 50, view 20,
the `max_instances` APScheduler default 1), while the Cronjobs section showed
none of them. The check targets the effect, not the call.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, ROOT)

from core.settings_schema import save_deep_settings, validate_sections  # noqa: E402


def _set(**fields) -> None:
    assert save_deep_settings(validate_sections({"cron": fields}))


@pytest.fixture
def cron_home(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
    import core.engine_config as ec

    monkeypatch.setattr(ec, "CONFIG_DIR", cfg, raising=False)
    return cfg


def test_misfire_grace_and_parallelism_reach_the_job(cron_home) -> None:
    from core import scheduler as sc

    captured: dict = {}
    fake = MagicMock()
    fake.add_job.side_effect = lambda **kw: captured.update(kw)

    sched = sc.EpheScheduler()
    sched._ensure_scheduler = lambda: fake  # type: ignore[method-assign]

    sched.add_job("Test Aufgabe", cron_expr="0 8 * * *")
    assert captured["misfire_grace_time"] == 3600  # the default is 60 minutes
    assert captured["max_instances"] == 1  # the APScheduler default, unchanged

    _set(**{"cron.misfire_grace_minutes": 5, "cron.max_parallel_jobs": 4})
    captured.clear()
    sched.add_job("Test Aufgabe 2", cron_expr="0 9 * * *")
    assert captured["misfire_grace_time"] == 300
    assert captured["max_instances"] == 4

    # The register's 0 is not a value APScheduler accepts for this keyword — `job.py`
    # validates None or a positive integer, and until 2026-11-18 the raise it threw was
    # swallowed by the restore loop, which came up with an empty schedule.
    _set(**{"cron.misfire_grace_minutes": 0})
    captured.clear()
    sched.add_job("Test Aufgabe 3", cron_expr="0 10 * * *")
    assert captured["misfire_grace_time"] == 1


def test_history_size_and_view_read_the_setting(cron_home) -> None:
    from core import scheduler as sc

    assert sc.history_keep() == 50
    assert sc.history_rows() == 20
    _set(**{"cron.history_keep": 12, "cron.history_rows": 7})
    assert sc.history_keep() == 12
    assert sc.history_rows() == 7

    sched = sc.EpheScheduler()
    saved = list(sc._job_results)
    try:
        sc._job_results.clear()
        sc._job_results.extend(
            {"job_id": f"j{i}", "executed_at": str(i), "task": "t", "result": "ok", "error": None}
            for i in range(30)
        )
        assert len(sched.get_results()) == 7, "the view follows the slider"
        assert len(sched.get_results(limit=3)) == 3, "an explicit number wins"
    finally:
        sc._job_results.clear()
        sc._job_results.extend(saved)


def test_cron_bounds_ship_in_the_payload(cron_home) -> None:
    from core.settings_schema import deep_view

    entries = {f["key"]: f for s in deep_view() for f in s["fields"]}
    for key in (
        "cron.misfire_grace_minutes",
        "cron.history_keep",
        "cron.history_rows",
        "cron.max_parallel_jobs",
    ):
        entry = entries[key]
        assert entry["type"] == "number" and entry["step"] == 1, key
        assert entry["min"] <= entry["default"] <= entry["max"], key
        assert entry["hint"] and entry["hintEn"], key
    with pytest.raises(ValueError):
        validate_sections({"cron": {"cron.max_parallel_jobs": 99}})


def test_route_without_a_limit_uses_the_setting(cron_home) -> None:
    from fastapi.testclient import TestClient

    from server.main import app

    _set(**{"cron.history_rows": 6})
    client = TestClient(app)
    _set(**{"cron.history_rows": 6})  # environment isolation after the import
    body = client.get("/api/schedule/results").json()
    assert len(body["results"]) <= 6


# The catch-up window at the seam where it is decided.
# `test_misfire_grace_and_parallelism_reach_the_job` above proves the dial reaches the
# `add_job` call. That is not where the product promise lives: APScheduler honours
# `misfire_grace_time` in its executor (`executors/base.py`, `EVENT_JOB_MISSED`) for a
# run_time it was given in the past, and the restore path hands it no past run_time at
# all — it rewrote a late one-shot into `delay_minutes=0.01`, so every appointment that
# passed during a downtime ran on restart no matter what the dial said. These cases drive
# a restart against a jobs file whose `run_date` has moved.

import asyncio  # noqa: E402
import json  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

import pytest  # noqa: E402


@pytest.fixture
def schedule_home(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_SCHEDULE_JOBS", str(tmp_path / "jobs.json"))
    monkeypatch.setenv("EPHE_SCHEDULE_RESULTS", str(tmp_path / "results.json"))
    # A restored one-shot inside its window fires a fraction of a second after the
    # restart, so the turn needs a stand-in: no model is chosen for a real turn here.
    monkeypatch.setenv("EPHE_MODEL", "cron-window-fake:1b")
    import core.react as react_module

    async def fake(question, model=None, context=None, **kwargs):
        return f"FAKE::{question}"

    monkeypatch.setattr(react_module, "react_loop", fake)
    return tmp_path


def _late_oneshot(home: Path, job_id: str, minutes_from_now: float) -> None:
    """The jobs file as `_persist_jobs` writes it, with the one-shot's date moved."""
    run_date = datetime.now(timezone.utc) + timedelta(minutes=minutes_from_now)
    (home / "jobs.json").write_text(
        json.dumps(
            [
                {
                    "id": job_id,
                    "name": "late report",
                    "cron": "once",
                    "run_date": run_date.isoformat(),
                    "max_runs": 1,
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )


async def _restart_and_wait(home: Path, job_id: str) -> tuple[dict | None, list[dict]]:
    """The restart, then what the scheduler holds and what the job produced.

    A late one-shot that was restored starts 0.6 s after the start, so the wait is what
    tells a lapsed run apart from one that ran and left the list on its own: only a run
    leaves a row in the result history.
    """
    from core.scheduler import EpheScheduler

    sched = EpheScheduler()
    sched.start()
    try:
        await asyncio.sleep(1.2)
        job = next((j for j in sched.list_jobs() if j["id"] == job_id), None)
        runs = [r for r in sched.get_results(limit=50) if r.get("job_id") == job_id]
        return job, runs
    finally:
        sched.stop()


class TestCatchUpWindow:
    @pytest.mark.asyncio
    async def test_a_run_missed_inside_the_window_is_taken(self, cron_home, schedule_home) -> None:
        _set(**{"cron.misfire_grace_minutes": 60})
        _late_oneshot(schedule_home, "in-window", -10)
        job, runs = await _restart_and_wait(schedule_home, "in-window")
        assert job is not None or runs, "a 10 minute late one-shot must still start"

    @pytest.mark.asyncio
    async def test_a_run_missed_past_the_window_lapses(self, cron_home, schedule_home) -> None:
        _set(**{"cron.misfire_grace_minutes": 60})
        _late_oneshot(schedule_home, "past-window", -180)
        job, runs = await _restart_and_wait(schedule_home, "past-window")
        assert job is None and runs == [], "past the window the run does not stand and does not run"
        stored = json.loads((schedule_home / "jobs.json").read_text(encoding="utf-8"))
        assert stored == [], "a lapsed one-shot has to leave the store, not return on every start"

    @pytest.mark.asyncio
    async def test_zero_never_catches_up(self, cron_home, schedule_home) -> None:
        _set(**{"cron.misfire_grace_minutes": 0})
        _late_oneshot(schedule_home, "zero-grace", -1)
        job, runs = await _restart_and_wait(schedule_home, "zero-grace")
        assert job is None and runs == [], "0 catches up nothing — this run included"

    @pytest.mark.asyncio
    async def test_a_run_not_yet_due_keeps_its_time(self, cron_home, schedule_home) -> None:
        _set(**{"cron.misfire_grace_minutes": 60})
        _late_oneshot(schedule_home, "still-ahead", 5)
        job, runs = await _restart_and_wait(schedule_home, "still-ahead")
        assert job is not None and job["next_run"] is not None
        assert runs == [], "five minutes ahead is not now"

    @pytest.mark.asyncio
    async def test_zero_still_restores_what_is_not_late(self, cron_home, schedule_home) -> None:
        """0 means never catch up; it does not mean losing the schedule.

        Three entries, one restart: the daily job and the future one-shot have to come
        back, only the one minute late one-shot lapses. Before the grace went through
        `misfire_grace_setting()` and the restore went entry by entry, the refused 0
        raised on the first add and every job in the file was gone.
        """
        _set(**{"cron.misfire_grace_minutes": 0})
        ahead = datetime.now(timezone.utc) + timedelta(minutes=5)
        (schedule_home / "jobs.json").write_text(
            json.dumps(
                [
                    {"id": "daily", "name": "daily brief", "cron": "0 8 * * *"},
                    {"id": "ahead", "name": "ahead", "cron": "once",
                     "run_date": ahead.isoformat(), "max_runs": 1},
                    {"id": "late", "name": "late", "cron": "once",
                     "run_date": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
                     "max_runs": 1},
                ],
                indent=2,
            ),
            encoding="utf-8",
        )
        from core.scheduler import EpheScheduler

        sched = EpheScheduler()
        sched.start()
        try:
            restored = {j["id"] for j in sched.list_jobs()}
        finally:
            sched.stop()
        assert {"daily", "ahead"} <= restored
        assert "late" not in restored

    @pytest.mark.asyncio
    async def test_one_unusable_entry_does_not_cost_the_rest(self, cron_home, schedule_home) -> None:
        """A stored value the scheduler refuses fails that entry alone; the rest of the
        file still comes back."""
        _set(**{"cron.misfire_grace_minutes": 60})
        (schedule_home / "jobs.json").write_text(
            json.dumps(
                [
                    {"id": "broken", "name": "broken", "cron": "not a cron expression at all"},
                    {"id": "good", "name": "good", "cron": "30 6 * * *"},
                ],
                indent=2,
            ),
            encoding="utf-8",
        )
        from core.scheduler import EpheScheduler

        sched = EpheScheduler()
        sched.start()
        try:
            restored = {j["id"] for j in sched.list_jobs()}
        finally:
            sched.stop()
        assert "good" in restored
        assert "broken" not in restored
