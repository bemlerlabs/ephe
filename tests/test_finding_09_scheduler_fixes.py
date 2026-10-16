"""
tests/test_finding_09_scheduler_fixes.py

Finding 9: Scheduler had model=None bug and hardcoded "Europe/Berlin" timezone.
Fix: model from env var, timezone from env var with fallback.

Given-When-Then Tests:
  1. GIVEN EPHE_TIMEZONE=Asia/Tokyo WHEN add_job() THEN CronTrigger uses Tokyo
  2. GIVEN default env WHEN add_job() THEN CronTrigger uses Europe/Berlin (fallback)
  3. GIVEN EPHE_MODEL=llama3.3 WHEN _run_task() THEN react_loop gets llama3.3
  4. GIVEN no model env WHEN _run_task() THEN the job records "No model chosen" and
     calls nothing (the gemma4:12b fallback this list used to pin went with #94)
"""
import os
from unittest.mock import patch, AsyncMock, MagicMock

import pytest

from core.scheduler import EpheScheduler


# Test 1: GIVEN Tokyo timezone WHEN add_job THEN CronTrigger uses Tokyo

def test_given_tokyo_tz_when_add_job_then_uses_tokyo(monkeypatch):
    """GIVEN EPHE_TIMEZONE=Asia/Tokyo WHEN add_job() THEN trigger uses Tokyo."""
    monkeypatch.setenv("EPHE_TIMEZONE", "Asia/Tokyo")

    scheduler = EpheScheduler()
    scheduler._scheduler = MagicMock()
    scheduler._scheduler.get_jobs.return_value = []

    with patch("core.scheduler._jobs_file", return_value=MagicMock()):
        scheduler.add_job("test task", "0 8 * * *", "test_id")

    call_args = scheduler._scheduler.add_job.call_args
    trigger = call_args.kwargs.get("trigger") or call_args[1].get("trigger")
    assert str(trigger.timezone) == "Asia/Tokyo"


# Test 2: GIVEN no timezone env WHEN add_job THEN uses Berlin fallback

def test_given_no_tz_env_when_add_job_then_uses_berlin(monkeypatch):
    """GIVEN no EPHE_TIMEZONE set WHEN add_job() THEN uses Europe/Berlin."""
    monkeypatch.delenv("EPHE_TIMEZONE", raising=False)

    scheduler = EpheScheduler()
    scheduler._scheduler = MagicMock()
    scheduler._scheduler.get_jobs.return_value = []

    with patch("core.scheduler._jobs_file", return_value=MagicMock()):
        scheduler.add_job("test task", "0 8 * * *", "test_id")

    call_args = scheduler._scheduler.add_job.call_args
    trigger = call_args.kwargs.get("trigger") or call_args[1].get("trigger")
    assert str(trigger.timezone) == "Europe/Berlin"


# Test 3: GIVEN custom model WHEN _run_task THEN passes model to react_loop

@pytest.mark.asyncio
async def test_given_custom_model_when_run_task_then_passes_to_react(monkeypatch):
    """GIVEN EPHE_MODEL=llama3.3 WHEN _run_task() THEN react_loop receives llama3.3."""
    monkeypatch.setenv("EPHE_MODEL", "llama3.3")

    scheduler = EpheScheduler()
    captured_model = []
    captured_provenance = []

    async def fake_react_loop(question, model, context, **kwargs):
        captured_model.append(model)
        captured_provenance.append(kwargs.get("session_id"))
        return "test result"

    with patch("core.react.react_loop", side_effect=fake_react_loop):
        await scheduler._run_task("test task", "test_id")

    assert captured_model[0] == "llama3.3"
    # n1-memory: the job's turn carries a provenance session id.
    assert captured_provenance[0] == "sched-test_id"


# Test 4: GIVEN no model env WHEN _run_task THEN the job refuses and names the absence

@pytest.mark.asyncio
async def test_given_no_model_env_when_run_task_then_the_job_refuses(monkeypatch, tmp_path):
    """GIVEN no EPHE_MODEL and no chosen engine WHEN _run_task() runs
    THEN react_loop is never reached and the recorded error says no model was chosen.

    This test used to pin the opposite: `react_loop gets gemma4:12b (fallback)`, a model
    the user never picked and, on this machine, never had. The scheduler now goes through
    `core.model_provider.chosen_model()` (owner decision 2026-10-11)."""
    monkeypatch.setenv("EPHE_SCHEDULE_RESULTS", str(tmp_path / "results.json"))
    monkeypatch.delenv("EPHE_MODEL", raising=False)
    monkeypatch.delenv("EPHE_MODEL_PROVIDER", raising=False)

    scheduler = EpheScheduler()
    captured_model = []

    async def fake_react_loop(question, model, context, **kwargs):
        captured_model.append(model)
        return "test result"

    with patch("core.react.react_loop", side_effect=fake_react_loop):
        await scheduler._run_task("test task", "test_id")

    assert captured_model == []
    recorded = scheduler.get_results(limit=3)
    assert any("No model chosen" in str(entry.get("error")) for entry in recorded), recorded
