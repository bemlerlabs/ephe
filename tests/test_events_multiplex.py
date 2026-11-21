"""L1 — the multiplex stream carries the fleet and the cell in one response."""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.routes import events  # noqa: E402


class FakeRequest:
    """Disconnects after the frames a test asked for."""

    def __init__(self, disconnect_after: int = 3) -> None:
        self.calls = 0
        self.disconnect_after = disconnect_after

    async def is_disconnected(self) -> bool:
        self.calls += 1
        return self.calls > self.disconnect_after


def take_frames(count: int, session: str | None = "s1") -> list[str]:
    async def run() -> list[str]:
        gen = events._frames(FakeRequest(disconnect_after=count), session)
        try:
            return [await anext(gen) for _ in range(count)]
        finally:
            await gen.aclose()

    return asyncio.run(run())


def test_the_stream_opens_with_hello_then_a_full_snapshot(monkeypatch):
    monkeypatch.setattr(events, "fleet_payload", lambda: {"workspaces": [], "runs": []})
    monkeypatch.setattr(events, "cell_life", lambda session: {"alive": False, "session": session})

    frames = take_frames(3)

    assert ": connected" in frames[0]
    assert "event: hello" in frames[1]
    assert '"session": "s1"' in frames[1]
    assert "event: multiplex" in frames[2]
    assert '"fleet"' in frames[2]
    assert '"cell"' in frames[2]
    assert '"session":"s1"' in frames[2]


def test_a_snapshot_without_a_session_carries_no_cell(monkeypatch):
    monkeypatch.setattr(events, "fleet_payload", lambda: {"workspaces": [], "runs": []})
    frames = take_frames(3, session=None)
    assert '"cell":null' in frames[2]


def test_the_snapshot_keeps_the_fleet_shape_of_the_route(monkeypatch):
    monkeypatch.setattr(events, "fleet_payload", lambda: {"workspaces": [{"id": "t"}], "runs": []})
    monkeypatch.setattr(events, "cell_life", lambda session: {"alive": False})
    snap = events._snapshot("s1", read_fleet=True)
    assert snap["fleet"]["workspaces"] == [{"id": "t"}]
    assert snap["cell"] == {"alive": False}


def test_the_stream_cap_refuses_instead_of_unbounded_readers(monkeypatch):
    monkeypatch.setattr(events, "_active", events.MAX_STREAMS)
    app = FastAPI()
    app.include_router(events.router, prefix="/api")
    response = TestClient(app).get("/api/events/multiplex")
    assert response.status_code == 503
    assert events._active == events.MAX_STREAMS


def test_a_writer_wakes_every_open_stream():
    """L1: notify() reaches each stream's own event, not a shared one."""
    from core import live_state

    async def scenario() -> None:
        first, second = asyncio.Event(), asyncio.Event()
        events._WAITERS.update({first, second})
        try:
            live_state.notify()
            assert first.is_set() and second.is_set()
        finally:
            events._WAITERS.difference_update({first, second})

    asyncio.run(scenario())


def test_a_finished_stream_leaves_no_waiter_behind():
    assert not events._WAITERS


def test_a_new_cell_notifies_the_live_state():
    from core import live_state
    from core.ephemeral_cell import create_cell, forget

    calls: list[int] = []
    unsubscribe = live_state.subscribe(lambda: calls.append(1))
    try:
        before = len(calls)
        create_cell("wake-test")
        assert len(calls) > before
    finally:
        unsubscribe()
        forget("wake-test")
