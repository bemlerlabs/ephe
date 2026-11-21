"""J4 parity round: scheduler — relative one-shots (delay_minutes) + max_runs limit.
Hermetic: react_loop and both job/result files are mocked or redirected."""
from __future__ import annotations

import json
import os

import pytest


@pytest.fixture()
def iso_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_SCHEDULE_JOBS", str(tmp_path / "jobs.json"))
    monkeypatch.setenv("EPHE_SCHEDULE_RESULTS", str(tmp_path / "results.json"))
    # A job that runs has to name a model, and since 2026-10-11 the scheduler names no
    # model of its own (`chosen_model()` refuses). The tag here is invented fixture data,
    # the same as the fake react_loop below.
    monkeypatch.setenv("EPHE_MODEL", "j4-fake:1b")
    return tmp_path


@pytest.fixture()
def fake_react(monkeypatch):
    import core.react as react_module

    async def fake(question, model=None, context=None, **kwargs):
        return f"FAKE::{question}"

    monkeypatch.setattr(react_module, "react_loop", fake)
    return fake


class TestRelativeOneshots:
    @pytest.mark.asyncio
    async def test_delay_minutes_creates_oneshot_with_next_run(self, iso_dirs):
        from core.scheduler import EpheScheduler

        sched = EpheScheduler()
        sched.start()
        try:
            job_id = sched.add_job("j4-rel", delay_minutes=2)
            listing = sched.list_jobs()
            job = next(j for j in listing if j["id"] == job_id)
            assert job["cron"] == "once"
            assert job["next_run"] is not None
        finally:
            sched.stop()

    async def test_oneshot_fires_within_delay(self, iso_dirs, fake_react):
        from core.scheduler import EpheScheduler

        sched = EpheScheduler()
        sched.start()
        try:
            sched.add_job("j4-fire", delay_minutes=0.05)  # 3 s
            import asyncio

            await asyncio.sleep(4)
            results = sched.get_results(limit=5)
            assert any("FAKE::j4-fire" in str(r.get("result", "")) for r in results)
        finally:
            sched.stop()

    async def test_max_runs_counts_in_results_and_removes_job(
        self, iso_dirs, fake_react
    ):
        from core.scheduler import EpheScheduler

        sched = EpheScheduler()
        sched.start()
        try:
            job_id = sched.add_job("j4-cap", cron_expr="* * * * *", max_runs=2)
            await sched.run_job_now(job_id)
            await sched.run_job_now(job_id)
            runs = [r for r in sched.get_results(limit=50) if r["job_id"] == job_id]
            assert len(runs) == 2
            assert job_id not in {j["id"] for j in sched.list_jobs()}
            # Cap reached → job is removed, the third run reports an honest KeyError
            with pytest.raises(KeyError):
                await sched.run_job_now(job_id)
        finally:
            sched.stop()

    @pytest.mark.asyncio
    async def test_persist_roundtrip_oneshot(self, iso_dirs, tmp_path):
        from core.scheduler import EpheScheduler

        sched = EpheScheduler()
        sched.start()
        try:
            job_id = sched.add_job("j4-persist", delay_minutes=3, max_runs=1)
            data = json.loads((tmp_path / "jobs.json").read_text(encoding="utf-8"))
            entry = next(j for j in data if j["id"] == job_id)
            assert entry["cron"] == "once"
            assert entry["run_date"]  # ISO field used by restore
            assert entry["max_runs"] == 1
        finally:
            sched.stop()

    @pytest.mark.asyncio
    async def test_restart_restores_oneshot_job(self, iso_dirs, fake_react):
        """Regression: a restart has to pick up persisted one-shots again.

        _load_persisted_jobs() recomputes the remaining time from run_date; a typo
        there (totalseconds instead of total_seconds) raises and gets swallowed by
        except — the job would be gone without a trace after the restart.
        """
        from core.scheduler import EpheScheduler

        first = EpheScheduler()
        first.start()
        try:
            job_id = first.add_job("j4-restart", delay_minutes=5, max_runs=1)
        finally:
            first.stop()

        second = EpheScheduler()
        second.start()
        try:
            restored = {j["id"] for j in second.list_jobs()}
            assert job_id in restored
            job = next(j for j in second.list_jobs() if j["id"] == job_id)
            assert job["cron"] == "once"
            assert job["next_run"] is not None
        finally:
            second.stop()

    @pytest.mark.asyncio
    async def test_cron_preset_path_unchanged(self, iso_dirs):
        from core.scheduler import EpheScheduler

        sched = EpheScheduler()
        sched.start()
        try:
            job_id = sched.add_job("j4-cron", cron_expr="0 8 * * *")
            job = next(j for j in sched.list_jobs() if j["id"] == job_id)
            assert job["cron"] == "0 8 * * *"
        finally:
            sched.stop()


class TestRouteIntegration:
    def test_route_accepts_delay_minutes(self, iso_dirs):
        from fastapi.testclient import TestClient
        from server.main import create_app

        with TestClient(create_app()) as client:
            resp = client.post(
                "/api/schedule",
                json={"task": "j4-route", "delay_minutes": 2},
            )
            assert resp.status_code == 200
            assert resp.json()["job_id"]

    def test_route_requires_cron_or_delay(self, iso_dirs):
        from fastapi.testclient import TestClient
        from server.main import create_app

        with TestClient(create_app()) as client:
            resp = client.post("/api/schedule", json={"task": "j4-leer"})
            assert resp.status_code == 422
