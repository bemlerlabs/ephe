"""Deploy-check regression: the background scheduler must actually run.

Root cause found during the pre-deployment audit (2026-09-06): the lifespan
started EpheScheduler via ``asyncio.to_thread`` so ``AsyncIOScheduler.start()``
ran in a worker thread WITHOUT a running event loop, failed silently (broad
``except: pass``), and every scheduled job stayed pending forever —
``next_run`` stayed null and jobs never fired. A live 1-minute cron job
confirmed the bug against the real server.

These tests pin the corrected behavior: the scheduler starts on the event
loop, created jobs get a real ``next_run``, and user-facing strings are
English (app default language rule).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

EVERY_MINUTE = "* * * * *"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import os

    os.environ["EPHE_MEMORY_DIR"] = os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
    os.environ["EPHE_PROFILE_PATH"] = os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
    # Isolated engine.json per test — NEVER touch the real user config.
    import core.engine_config as engine_config

    monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path / "config")

    from server.main import create_app

    # ``with`` runs the lifespan — required: it starts the scheduler on the
    # TestClient's event loop (the very code path that used to be broken).
    with TestClient(create_app()) as c:
        yield c


class TestSchedulerRuntime:
    def test_lifespan_starts_scheduler_on_event_loop(self, client):
        from core.scheduler import ephe_scheduler

        scheduler = ephe_scheduler._ensure_scheduler()
        assert scheduler.running is True

    def test_start_is_idempotent_while_running(self, client):
        from core.scheduler import ephe_scheduler

        # Second start on a running scheduler must be a no-op, not an
        # apscheduler "already running" error.
        ephe_scheduler.start()
        assert ephe_scheduler._ensure_scheduler().running is True

    def test_created_job_gets_a_real_next_run(self, client):
        resp = client.post(
            "/api/schedule",
            json={"task": "zz-deploy-check runtime", "cron": EVERY_MINUTE},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["job_id"]
        # The scheduler is running → apscheduler computed the next fire time.
        assert body["message"].startswith("Job '")
        assert "Next run:" in body["message"]
        assert "unknown" not in body["message"]

        listing = client.get("/api/schedule").json()["jobs"]
        job = next(j for j in listing if j["id"] == body["job_id"])
        assert job["cron"] == EVERY_MINUTE
        assert job["next_run"] is not None

        assert client.delete(f"/api/schedule/{body['job_id']}").status_code == 200

    def test_invalid_cron_returns_422_with_english_detail(self, client):
        resp = client.post(
            "/api/schedule",
            json={"task": "zz-deploy-check bad", "cron": "99"},
        )
        assert resp.status_code == 422
        assert str(resp.json()["error"]["message"]).startswith("Invalid cron expression")

    def test_missing_job_delete_is_404_english(self, client):
        resp = client.delete("/api/schedule/ephe_job_missing")
        assert resp.status_code == 404
        assert "not found" in str(resp.json()["error"]["message"])
