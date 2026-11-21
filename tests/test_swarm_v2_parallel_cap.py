"""Concurrency cap of one swarm wave (`swarm_max_parallel`).

GIVEN a wave of N agents whose run() sleeps long enough to overlap
WHEN the orchestrator executes the wave
THEN at most `swarm_max_parallel` agents run at the same time, the rest queue
     cleanly, every envelope arrives, and the order matches the subtasks.

The cap is a generation option (core/engine_config.py): env
EPHE_SWARM_MAX_PARALLEL > engine.json generation block > default 8.
Before this cap, every spawned agent started at once (asyncio.create_task)
no matter how many there were — MAX_SWARM_AGENTS bounded the count only.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from core import engine_config, swarm_v2
from core.swarm_state import SwarmPhase, SwarmStateStore
from core.swarm_v2 import SwarmAgent, SwarmOrchestrator, _make_envelope

#: Long enough that a whole wave piles up inside run() when nothing bounds it.
HOLD_SECONDS = 0.05


class _Probe:
    """Counts agents that are inside run() at the same time."""

    def __init__(self, hold: float = HOLD_SECONDS) -> None:
        self.hold = hold
        self.active = 0
        self.max_active = 0
        self.started: list[str] = []
        self.finished: list[str] = []


def _install_fake_run(monkeypatch: pytest.MonkeyPatch, probe: _Probe) -> None:
    """Replaces SwarmAgent.run() with a slow, concurrency-counting stand-in."""

    async def fake_run(self: SwarmAgent) -> swarm_v2.SwarmEnvelope:
        probe.active += 1
        probe.max_active = max(probe.max_active, probe.active)
        probe.started.append(self.agent_id)
        try:
            await asyncio.sleep(probe.hold)
        finally:
            probe.active -= 1
            probe.finished.append(self.agent_id)
        return _make_envelope(
            self.agent_id, f"result:{self.agent_id}", run_id=self.run_id
        )

    monkeypatch.setattr(SwarmAgent, "run", fake_run)


def _spawn_wave(subtasks: list[str]) -> SwarmOrchestrator:
    """Orchestrator whose manager spawns exactly `subtasks` — no model needed."""
    store = SwarmStateStore()
    orch = SwarmOrchestrator(task="Wave test", model="test-model", state_store=store)
    orch.swarm_id = store.create_session("Wave test")
    orch._run_manager = AsyncMock(
        return_value={
            "count": len(subtasks),
            "role": "researcher",
            "subtasks": subtasks,
        }
    )
    orch._synthesize = AsyncMock(return_value="FINAL")
    return orch


def _envelopes(result: swarm_v2.SwarmV2Result) -> list[swarm_v2.SwarmEnvelope]:
    """The wave's envelopes, narrowed.

    `result.envelopes` also carries the str/None seam the merge tolerates, so a
    status/run_id read has to name the envelope it expects.
    """
    return [e for e in result.envelopes if isinstance(e, swarm_v2.SwarmEnvelope)]


# The cap bounds the wave


async def test_wave_runs_at_most_cap(empty_ephe_home, monkeypatch: pytest.MonkeyPatch):
    """GIVEN cap 2 WHEN 6 agents run THEN measured max concurrency is 2 and all arrive."""
    monkeypatch.setenv("EPHE_SWARM_MAX_PARALLEL", "2")
    probe = _Probe()
    _install_fake_run(monkeypatch, probe)
    orch = _spawn_wave([f"Sub {i}" for i in range(6)])

    result = await orch._execute_pipeline()

    assert probe.max_active == 2
    assert len(probe.started) == 6
    assert sorted(probe.finished) == sorted(probe.started)
    assert len(result.envelopes) == 6
    assert [env.status for env in _envelopes(result)] == ["ok"] * 6
    # queue order preserved: envelope i belongs to subtask i
    assert [env.run_id for env in _envelopes(result)] == [
        f"{orch.swarm_id}:{i}" for i in range(6)
    ]


async def test_cap_one_serialises_the_wave(
    empty_ephe_home, monkeypatch: pytest.MonkeyPatch
):
    """GIVEN cap 1 WHEN 3 agents run THEN they run one after another, none dropped."""
    monkeypatch.setenv("EPHE_SWARM_MAX_PARALLEL", "1")
    probe = _Probe()
    _install_fake_run(monkeypatch, probe)
    orch = _spawn_wave(["A", "B", "C"])

    result = await orch._execute_pipeline()

    assert probe.max_active == 1
    assert len(result.envelopes) == 3
    assert all(env.status == "ok" for env in _envelopes(result))


async def test_default_cap_runs_a_full_wave(
    empty_ephe_home, monkeypatch: pytest.MonkeyPatch
):
    """GIVEN nothing configured WHEN MAX_SWARM_AGENTS agents run THEN all start together."""
    monkeypatch.delenv("EPHE_SWARM_MAX_PARALLEL", raising=False)
    probe = _Probe()
    _install_fake_run(monkeypatch, probe)
    orch = _spawn_wave([f"Sub {i}" for i in range(swarm_v2.MAX_SWARM_AGENTS)])

    result = await orch._execute_pipeline()

    assert probe.max_active == swarm_v2.MAX_SWARM_AGENTS
    assert len(result.envelopes) == swarm_v2.MAX_SWARM_AGENTS


async def test_cap_comes_from_engine_json(
    empty_ephe_home, monkeypatch: pytest.MonkeyPatch
):
    """GIVEN the generation block in engine.json WHEN the wave runs THEN its cap applies."""
    monkeypatch.delenv("EPHE_SWARM_MAX_PARALLEL", raising=False)
    (Path(empty_ephe_home) / "engine.json").write_text(
        json.dumps(
            {
                "provider": "local_ollama",
                "model": "test-model",
                "generation": {"swarm_max_parallel": 2},
            }
        ),
        encoding="utf-8",
    )
    probe = _Probe()
    _install_fake_run(monkeypatch, probe)
    orch = _spawn_wave([f"Sub {i}" for i in range(5)])

    result = await orch._execute_pipeline()

    assert probe.max_active == 2
    assert len(result.envelopes) == 5


# The option itself: bounds, env key, resolver


def test_option_is_registered_with_expected_bounds():
    """GIVEN the generation registry THEN swarm_max_parallel = (8, 1, None)."""
    assert engine_config.GENERATION_BOUNDS["swarm_max_parallel"] == (8, 1, None)
    assert (
        engine_config.GENERATION_ENV_KEYS["swarm_max_parallel"]
        == "EPHE_SWARM_MAX_PARALLEL"
    )


def test_write_path_validates_the_option(empty_ephe_home):
    """GIVEN a settings payload THEN the option is bounded like every other key."""
    assert engine_config.validate_generation({"swarm_max_parallel": 2}) == {
        "swarm_max_parallel": 2
    }
    with pytest.raises(ValueError):
        engine_config.validate_generation(
            {"swarm_max_parallel": 0}
        )  # below the low bound


def test_resolver_defaults_clamps_and_survives_junk(
    empty_ephe_home, monkeypatch: pytest.MonkeyPatch
):
    """GIVEN unset / out-of-range / non-numeric config THEN the cap is sane."""
    monkeypatch.delenv("EPHE_SWARM_MAX_PARALLEL", raising=False)
    assert swarm_v2.resolve_swarm_max_parallel() == 8

    monkeypatch.setenv("EPHE_SWARM_MAX_PARALLEL", "0")
    assert swarm_v2.resolve_swarm_max_parallel() == 1  # low bound, never 0 slots

    monkeypatch.setenv("EPHE_SWARM_MAX_PARALLEL", "nonsense")
    assert swarm_v2.resolve_swarm_max_parallel() == 8  # invalid → default


def test_resolver_trims_a_cap_wider_than_the_spawn_ceiling(
    empty_ephe_home, monkeypatch: pytest.MonkeyPatch
):
    """GIVEN a cap above the spawn ceiling WHEN resolved THEN it is trimmed to
    MAX_SWARM_AGENTS, so the semaphore never outruns the wave."""
    monkeypatch.setenv("EPHE_SWARM_MAX_PARALLEL", "1000")
    assert swarm_v2.resolve_swarm_max_parallel() == swarm_v2.MAX_SWARM_AGENTS


# The cap when a child fails, is cancelled or leaves no result


async def test_cap_holds_when_an_agent_crashes(
    empty_ephe_home, monkeypatch: pytest.MonkeyPatch
):
    """GIVEN cap 2 and one agent that raises WHEN the wave runs THEN the cap still
    bounds it, the slot is freed and every queued agent still gets through."""
    monkeypatch.setenv("EPHE_SWARM_MAX_PARALLEL", "2")
    active = 0
    max_active = 0
    finished: list[str] = []

    async def fake_run(self: SwarmAgent) -> swarm_v2.SwarmEnvelope:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        try:
            await asyncio.sleep(HOLD_SECONDS)
            if self.subtask == "Sub 3":
                raise RuntimeError("boom")
        finally:
            active -= 1
            finished.append(self.subtask)
        return _make_envelope(
            self.agent_id, f"result:{self.subtask}", run_id=self.run_id
        )

    monkeypatch.setattr(SwarmAgent, "run", fake_run)
    orch = _spawn_wave([f"Sub {i}" for i in range(6)])

    result = await orch._execute_pipeline()

    assert max_active == 2
    assert len(finished) == 6
    statuses = [env.status for env in _envelopes(result)]
    assert statuses.count("ok") == 5
    assert statuses.count("error") == 1


async def test_cancelled_child_becomes_an_error_gap(
    empty_ephe_home, monkeypatch: pytest.MonkeyPatch
):
    """GIVEN one agent raises CancelledError (a BaseException) WHEN the wave runs
    THEN the wave still merges: that child is an explicit error gap, the others
    arrive, and the order still matches the subtasks."""
    monkeypatch.setenv("EPHE_SWARM_MAX_PARALLEL", "3")

    async def fake_run(self: SwarmAgent) -> swarm_v2.SwarmEnvelope:
        if self.subtask == "B":
            raise asyncio.CancelledError()
        return _make_envelope(
            self.agent_id, f"result:{self.subtask}", run_id=self.run_id
        )

    monkeypatch.setattr(SwarmAgent, "run", fake_run)
    orch = _spawn_wave(["A", "B", "C"])

    result = await orch._execute_pipeline()

    assert [env.status for env in _envelopes(result)] == ["ok", "error", "ok"]
    assert "CancelledError" in _envelopes(result)[1].summary
    assert result.agent_results[0].startswith("result:A")
    assert "[Gap: status=error]" in result.agent_results[1]
    assert result.agent_results[2].startswith("result:C")


async def test_unexpected_result_becomes_an_error_gap(
    empty_ephe_home, monkeypatch: pytest.MonkeyPatch
):
    """GIVEN an agent returns something that is neither envelope nor text WHEN
    the wave merges THEN it lands as an error gap, never as an AttributeError
    that loses the whole wave's answer."""
    monkeypatch.setenv("EPHE_SWARM_MAX_PARALLEL", "2")

    async def fake_run(self: SwarmAgent):
        if self.subtask == "B":
            return 42
        return _make_envelope(self.agent_id, "done", run_id=self.run_id)

    monkeypatch.setattr(SwarmAgent, "run", fake_run)
    orch = _spawn_wave(["A", "B"])

    result = await orch._execute_pipeline()

    assert len(result.envelopes) == 2
    assert _envelopes(result)[0].status == "ok"
    assert _envelopes(result)[1].status == "error"
    assert result.agent_results[1].startswith("[agent error:")


async def test_agent_without_a_result_is_an_explicit_gap(
    empty_ephe_home, monkeypatch: pytest.MonkeyPatch
):
    """GIVEN an agent leaves no result WHEN the wave merges THEN the gap is named
    here instead of silently dropped."""
    monkeypatch.setenv("EPHE_SWARM_MAX_PARALLEL", "3")

    async def fake_run(self: SwarmAgent):
        if self.subtask == "B":
            return None
        return _make_envelope(self.agent_id, self.subtask, run_id=self.run_id)

    monkeypatch.setattr(SwarmAgent, "run", fake_run)
    orch = _spawn_wave(["A", "B", "C"])

    result = await orch._execute_pipeline()

    assert len(result.envelopes) == 3
    assert result.envelopes[1] is None
    assert len(result.agent_results) == 3
    assert result.agent_results[1].startswith("[")
    assert result.agent_results[0] != result.agent_results[1]


async def test_cancel_mid_wave_marks_error_and_unwinds_children(
    empty_ephe_home, monkeypatch: pytest.MonkeyPatch
):
    """GIVEN cap 1 and a wave in flight WHEN the pipeline is cancelled THEN the
    running child unwinds, the queued ones never start, the CancelledError
    propagates, and the session is ERROR instead of stuck in EXECUTING."""
    monkeypatch.setenv("EPHE_SWARM_MAX_PARALLEL", "1")
    started = asyncio.Event()
    unwound: list[str] = []

    async def fake_run(self: SwarmAgent):
        started.set()
        try:
            await asyncio.sleep(5)
        finally:
            unwound.append(self.subtask)
        return _make_envelope(self.agent_id, "late", run_id=self.run_id)

    monkeypatch.setattr(SwarmAgent, "run", fake_run)
    orch = _spawn_wave(["A", "B", "C"])

    task = asyncio.create_task(orch._execute_pipeline())
    await asyncio.wait_for(started.wait(), timeout=5)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert unwound == ["A"]
    session = orch.state.get_session(orch.swarm_id)
    assert session is not None
    assert session.phase is SwarmPhase.ERROR
