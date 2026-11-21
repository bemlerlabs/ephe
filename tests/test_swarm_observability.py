"""Wave observability: counters + events for one running swarm wave.

GIVEN a wave of N agents that runs under the `swarm_max_parallel` cap
WHEN the orchestrator executes the wave
THEN it keeps live counters (queued / active / started / finished / by_status)
     that never report more active agents than the cap, emits a `swarm_wave`
     snapshot on the event bridge at every transition, and carries the final
     snapshot in the `swarm_done` event and in the result.

The counters are the read model over the semaphore bound; the `swarm_wave`
events are its live wire form. Cap resolution itself is covered by
tests/test_swarm_v2_parallel_cap.py.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from core.swarm_state import SwarmStateStore
from core.swarm_v2 import (
    SwarmAgent,
    SwarmEnvelope,
    SwarmOrchestrator,
    WaveCounters,
    _make_envelope,
    _wave_status,
)

HOLD_SECONDS = 0.02


class _Collector:
    """Records the on-event bridge plus a concurrency probe under run()."""

    def __init__(self, statuses: dict[str, str] | None = None) -> None:
        self.events: list[dict] = []
        self.statuses = statuses or {}
        self.active = 0
        self.max_active = 0
        self.max_active_in_events = 0

    def emit(self, event: dict) -> None:
        # Snapshot is copied: later mutations must not rewrite recorded history.
        self.events.append(dict(event))
        if event.get("type") == "swarm_wave":
            self.max_active_in_events = max(
                self.max_active_in_events, int(event.get("active", 0))
            )

    def wave_events(self, transition: str | None = None) -> list[dict]:
        rows = [e for e in self.events if e.get("type") == "swarm_wave"]
        if transition is not None:
            rows = [e for e in rows if e.get("transition") == transition]
        return rows


def _install_fake_run(collector: _Collector):
    """Slow, concurrency-counting stand-in for SwarmAgent.run()."""

    async def fake_run(self: SwarmAgent) -> SwarmEnvelope:
        collector.active += 1
        collector.max_active = max(collector.max_active, collector.active)
        try:
            await asyncio.sleep(HOLD_SECONDS)
        finally:
            collector.active -= 1
        return _make_envelope(
            self.agent_id,
            f"result:{self.agent_id}",
            status=collector.statuses.get(self.agent_id, "ok"),
            run_id=self.run_id,
        )

    return fake_run


def _spawn_wave(subtasks: list[str], collector: _Collector) -> SwarmOrchestrator:
    store = SwarmStateStore()
    orch = SwarmOrchestrator(
        task="Wave test", model="test-model", state_store=store, on_event=collector.emit
    )
    orch.swarm_id = store.create_session("Wave test")
    orch._run_manager = AsyncMock(
        return_value={"count": len(subtasks), "role": "researcher", "subtasks": subtasks}
    )
    orch._synthesize = AsyncMock(return_value="FINAL")
    return orch


# Counters track the bound


async def test_peak_active_never_exceeds_the_cap(
    empty_ephe_home, monkeypatch: pytest.MonkeyPatch
):
    """GIVEN cap 2 WHEN 6 agents run THEN measured and reported active peak is 2."""
    monkeypatch.setenv("EPHE_SWARM_MAX_PARALLEL", "2")
    collector = _Collector()
    monkeypatch.setattr(SwarmAgent, "run", _install_fake_run(collector))
    orch = _spawn_wave([f"Sub {i}" for i in range(6)], collector)

    result = await orch._execute_pipeline()

    assert collector.max_active == 2
    assert collector.max_active_in_events == 2
    assert result.counters["cap"] == 2
    assert result.counters["total"] == 6


async def test_final_counters_close_the_wave(
    empty_ephe_home, monkeypatch: pytest.MonkeyPatch
):
    """GIVEN a finished wave THEN queued drains, active is 0, every status bucketed."""
    monkeypatch.setenv("EPHE_SWARM_MAX_PARALLEL", "2")
    collector = _Collector()
    monkeypatch.setattr(SwarmAgent, "run", _install_fake_run(collector))
    orch = _spawn_wave([f"Sub {i}" for i in range(5)], collector)

    result = await orch._execute_pipeline()

    counters = result.counters
    assert counters["queued"] == 0
    assert counters["active"] == 0
    assert counters["started"] == 5
    assert counters["finished"] == 5
    assert counters["by_status"] == {"ok": 5}


async def test_start_event_shows_a_full_queue(
    empty_ephe_home, monkeypatch: pytest.MonkeyPatch
):
    """GIVEN a wave THEN the first snapshot has all agents queued and none active."""
    monkeypatch.setenv("EPHE_SWARM_MAX_PARALLEL", "2")
    collector = _Collector()
    monkeypatch.setattr(SwarmAgent, "run", _install_fake_run(collector))
    orch = _spawn_wave([f"Sub {i}" for i in range(4)], collector)

    await orch._execute_pipeline()

    first = collector.wave_events("start")[0]
    assert first["total"] == 4
    assert first["queued"] == 4
    assert first["active"] == 0
    assert first["started"] == 0
    assert first["swarm_id"] == orch.swarm_id


# Events on the bridge


async def test_wave_events_cover_every_transition(
    empty_ephe_home, monkeypatch: pytest.MonkeyPatch
):
    """GIVEN 3 agents THEN each start/finish emits one swarm_wave with its id."""
    monkeypatch.setenv("EPHE_SWARM_MAX_PARALLEL", "2")
    collector = _Collector()
    monkeypatch.setattr(SwarmAgent, "run", _install_fake_run(collector))
    orch = _spawn_wave(["A", "B", "C"], collector)

    await orch._execute_pipeline()

    started = collector.wave_events("started")
    finished = collector.wave_events("finished")
    assert len(started) == 3
    assert len(finished) == 3
    assert {e["agent_id"] for e in started} == {e["agent_id"] for e in finished}
    # started snapshots climb to the cap, finished snapshots drain it
    assert max(e["active"] for e in started) == 2
    assert finished[-1]["active"] == 0
    assert finished[-1]["finished"] == 3


async def test_swarm_done_event_carries_the_counters(
    empty_ephe_home, monkeypatch: pytest.MonkeyPatch
):
    """GIVEN a finished wave THEN swarm_done repeats the final snapshot."""
    collector = _Collector()
    monkeypatch.setattr(SwarmAgent, "run", _install_fake_run(collector))
    orch = _spawn_wave(["A", "B"], collector)

    result = await orch._execute_pipeline()

    done = [e for e in collector.events if e.get("type") == "swarm_done"]
    assert len(done) == 1
    assert done[0]["counters"] == result.counters
    assert done[0]["counters"]["finished"] == 2


# Failure paths land in their buckets


async def test_statuses_are_bucketed(
    empty_ephe_home, monkeypatch: pytest.MonkeyPatch
):
    """GIVEN mixed terminal statuses THEN each is counted under its own bucket."""
    collector = _Collector()
    orch = _spawn_wave(["A", "B", "C"], collector)

    async def fake_run(self: SwarmAgent) -> SwarmEnvelope:
        bucket = {"A": "ok", "B": "step_limit", "C": "timeout"}[self.subtask]
        return _make_envelope(self.agent_id, self.subtask, status=bucket, run_id=self.run_id)

    monkeypatch.setattr(SwarmAgent, "run", fake_run)

    result = await orch._execute_pipeline()

    assert result.counters["by_status"] == {"ok": 1, "step_limit": 1, "timeout": 1}
    assert result.counters["finished"] == 3


async def test_crashing_agent_is_bucketed_as_error(
    empty_ephe_home, monkeypatch: pytest.MonkeyPatch
):
    """GIVEN one run() raises THEN it counts as error and never leaks an active slot."""
    collector = _Collector()

    async def fake_run(self: SwarmAgent) -> SwarmEnvelope:
        if self.subtask == "boom":
            raise RuntimeError("agent exploded")
        return _make_envelope(self.agent_id, self.subtask, run_id=self.run_id)

    monkeypatch.setattr(SwarmAgent, "run", fake_run)
    orch = _spawn_wave(["ok", "boom"], collector)

    result = await orch._execute_pipeline()

    assert result.counters["finished"] == 2
    assert result.counters["active"] == 0
    assert result.counters["by_status"] == {"ok": 1, "error": 1}


# Counters before the wave + the pure unit


def test_snapshot_is_empty_before_a_wave():
    """GIVEN a fresh orchestrator THEN no counters exist yet."""
    orch = SwarmOrchestrator(task="t", model="m", state_store=SwarmStateStore())
    assert orch.wave is None
    assert orch.wave_snapshot() == {}


def test_wave_counters_unit_behaviour():
    """GIVEN counters THEN queued drains on start and statuses land in buckets."""
    counters = WaveCounters(total=4, cap=2)
    assert counters.snapshot() == {
        "total": 4,
        "cap": 2,
        "queued": 4,
        "active": 0,
        "started": 0,
        "finished": 0,
        "by_status": {},
        # N24 R1: the gate's figure rides the same snapshot — N tools skipped.
        "skipped_for_approval": 0,
    }
    counters.record_start()
    counters.record_start()
    assert (counters.active, counters.started, counters.queued) == (2, 2, 2)
    counters.record_finish("ok")
    assert (counters.active, counters.finished, counters.by_status) == (1, 1, {"ok": 1})
    counters.record_finish("weird_status")
    assert counters.by_status == {"ok": 1, "error": 1}  # unknown → error
    counters.record_finish(SwarmEnvelope(agent_id="x", status="step_limit"))
    assert counters.by_status["step_limit"] == 1
    assert counters.active == 0  # never goes negative


def test_wave_status_normalises_inputs():
    """GIVEN envelope / str / None THEN status resolves to a known bucket."""
    assert _wave_status(SwarmEnvelope(agent_id="a", status="ok")) == "ok"
    assert _wave_status("timeout") == "timeout"
    assert _wave_status("") == "ok"
    assert _wave_status(None) == "ok"
    assert _wave_status("garbage") == "error"
