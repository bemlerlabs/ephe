"""QD-016 C1: the deck's frames actually leave the orchestrator.

The cards are built from activity lines, and those lines only exist when the
orchestrator hands its bridge to every agent. Before this test the bridge was
dropped at agent construction, so a `/swarm` run showed a deck stuck at its
first phase: no roster, no model, no done stamp.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from core.swarm_state import SwarmStateStore
from core.swarm_v2 import SwarmAgent, SwarmOrchestrator, _make_envelope


@pytest.fixture()
def events() -> list[dict]:
    return []


def _orchestrator(subtasks: list[str], sink: list[dict]) -> SwarmOrchestrator:
    store = SwarmStateStore()
    orch = SwarmOrchestrator(
        task="Deck test", model="qwen-test", state_store=store, on_event=sink.append
    )
    orch.swarm_id = store.create_session("Deck test")
    orch._run_manager = AsyncMock(
        return_value={
            "count": len(subtasks),
            "role": "researcher",
            "subtasks": subtasks,
            "task_type": "general",
        }
    )
    orch._synthesize = AsyncMock(return_value="merged answer")
    return orch


def _fake_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(self: SwarmAgent):
        await asyncio.sleep(0)
        return _make_envelope(self.agent_id, f"result:{self.agent_id}", run_id=self.run_id)

    monkeypatch.setattr(SwarmAgent, "run", fake_run)


@pytest.mark.asyncio
async def test_the_roster_names_every_agent_with_its_model_and_task_hash(
    monkeypatch: pytest.MonkeyPatch, events: list[dict]
) -> None:
    _fake_runs(monkeypatch)
    orch = _orchestrator(["a", "b"], events)

    await orch.run()

    created = [e for e in events if e["type"] == "swarm_created"]
    assert len(created) == 1
    roster = created[0]["agents"]
    assert [row["role"] for row in roster] == ["researcher", "researcher"]
    assert all(row["model"] == "qwen-test" for row in roster)
    assert all(len(row["task_spec_hash"]) == 12 for row in roster)
    assert roster[0]["task_spec_hash"] != roster[1]["task_spec_hash"]
    assert created[0]["model"] == "qwen-test"


@pytest.mark.asyncio
async def test_each_agent_opens_and_closes_its_card(
    monkeypatch: pytest.MonkeyPatch, events: list[dict]
) -> None:
    _fake_runs(monkeypatch)
    orch = _orchestrator(["a", "b"], events)

    await orch.run()

    started = [e for e in events if e["type"] == "swarm_agent_started"]
    done = [e for e in events if e["type"] == "swarm_agent_done"]
    assert len(started) == 2 and len(done) == 2
    assert all(e["model"] == "qwen-test" for e in started)
    assert all(e["swarm_id"] == orch.swarm_id for e in started)
    assert {e["status"] for e in done} == {"done"}
    assert all(e["summary"].startswith("result:") for e in done)


@pytest.mark.asyncio
async def test_a_failing_agent_closes_its_card_as_error(
    monkeypatch: pytest.MonkeyPatch, events: list[dict]
) -> None:
    async def broken_run(self: SwarmAgent):
        raise RuntimeError("agent exploded")

    monkeypatch.setattr(SwarmAgent, "run", broken_run)
    orch = _orchestrator(["a"], events)

    await orch.run()

    done = [e for e in events if e["type"] == "swarm_agent_done"]
    assert done and done[0]["status"] == "error"
    assert done[0]["summary"] == ""
