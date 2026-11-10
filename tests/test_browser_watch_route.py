"""W2-88 — the watch channel: a name is not a licence, and a frame is the payload.

`server/routes/browser_watch.py` is the first HTTP route that reads a browser the agent is
running. `tests/test_browser_watch.py` pins the bus and the engine hand above it; this file
pins the three things only the route decides, each of them found by running it:

  * **a watch never opens a browser.** The session name arrives over the wire. A route that
    created the context on demand would hand any reachable caller a way to spawn browsers
    without limit, so the answer to an unknown name is a coded 404 and no engine call.
  * **the blocking read leaves the event loop.** `Queue.get` parks the thread that calls it,
    and on the loop that is the same thread the CDP callback needs to deliver the frame — the
    cast then looks dead while its own reader is what stopped it. That is invisible in a
    behavioural test, so this pins the thread the read happens on.
  * **the cast stops with the last reader.** A measured cast costs real CPU; a pane that was
    closed must not leave it running. The stop is scheduled rather than awaited, because the
    server cancels the task this cleanup runs inside.
"""
from __future__ import annotations

import asyncio
import json
import threading

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    from server.main import create_app

    return create_app()


class _Manager:
    """The manager surface the route touches, with every call recorded."""

    def __init__(self, sessions=(), refusal: str = "") -> None:
        self.sessions = set(sessions)
        self.refusal = refusal
        self.started: list[str] = []
        self.stopped: list[str] = []

    def has_session(self, session: str) -> bool:
        return session in self.sessions

    async def start_watch(self, session: str) -> str:
        self.started.append(session)
        return self.refusal

    async def stop_watch(self, session: str) -> None:
        self.stopped.append(session)


def _patch(monkeypatch, manager: _Manager) -> None:
    """The route reads the manager inside the call, so the module attribute is the seam."""
    monkeypatch.setattr("core.browser.browser_manager", manager)


def _events(chunks: list[str]) -> list[tuple[str, dict]]:
    """`event: <name>\\ndata: <json>\\n\\n` back into pairs, in the order they were sent."""
    out: list[tuple[str, dict]] = []
    name = ""
    for chunk in chunks:
        for line in chunk.splitlines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                out.append((name, json.loads(line[len("data: ") :])))
    return out


# The two refusals, through the running app.


def test_an_unknown_session_is_refused_before_the_engine_is_asked(app, monkeypatch):
    manager = _Manager(sessions=())
    _patch(monkeypatch, manager)

    response = TestClient(app).get("/api/browser/watch/ghost")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["reason_code"] == "browser_session_unknown"
    assert error["reason_params"] == {"session": "ghost"}
    assert error["message"].startswith("no browser session 'ghost'")
    assert manager.started == [], "the watch opened a browser context that did not exist"


def test_a_cast_that_will_not_start_carries_the_engines_own_reason(app, monkeypatch):
    manager = _Manager(sessions={"run-7"}, refusal="watch_unavailable: TimeoutError")
    _patch(monkeypatch, manager)

    response = TestClient(app).get("/api/browser/watch/run-7")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["reason_code"] == "browser_watch_unavailable"
    # The reason is the engine's word, not the channel's prefix: a reader who is told
    # "watch_unavailable" learns nothing they did not already see.
    assert error["reason_params"] == {"reason": "TimeoutError"}
    assert manager.stopped == [], "a cast that never started has nothing to stop"


# The stream itself, driven on the generator the route returns.


async def _drive(manager: _Manager, session: str, want: int, ping: float):
    """Open the stream, take `want` events, close it, and hand back what was sent.

    The generator is driven here rather than through HTTP because the cleanup below the
    stream has to be observed at a known moment: closing the response is what runs it, and a
    test that waits for a server-side cancellation waits for something this file does not own.
    """
    from server.routes import browser_watch

    manager.sessions.add(session)
    original = browser_watch._PING_SECONDS
    browser_watch._PING_SECONDS = ping
    try:
        response = await browser_watch.get_browser_watch(session)
        stream = response.body_iterator
        chunks = [await stream.__anext__() for _ in range(want)]
        await stream.aclose()
        for _ in range(50):
            if manager.stopped:
                break
            await asyncio.sleep(0.01)
        return _events(chunks)
    finally:
        browser_watch._PING_SECONDS = original


def test_the_stream_opens_with_its_state_and_hands_the_frame_already_on_screen(monkeypatch):
    from core import browser_frames

    session = "watch-route-seeded"
    bus = browser_frames.bus_for(session)
    bus.publish({"jpeg": "aGVsbG8=", "viewport_width": 1280, "viewport_height": 800})
    manager = _Manager()
    _patch(monkeypatch, manager)

    events = asyncio.run(_drive(manager, session, want=2, ping=0.01))

    assert events[0] == ("status", {"state": "casting", "session": session})
    name, frame = events[1]
    assert name == "frame"
    assert frame["jpeg"] == "aGVsbG8="
    # The two coordinate spaces the pane needs to place an overlay, both named as measured.
    assert frame["viewport_width"] == 1280 and frame["viewport_height"] == 800
    assert manager.started == [session]


def test_a_still_page_says_so_by_age_instead_of_leaving_the_pane_silent(monkeypatch):
    session = "watch-route-still"
    manager = _Manager()
    _patch(monkeypatch, manager)

    events = asyncio.run(_drive(manager, session, want=3, ping=0.2))

    names = [name for name, _ in events]
    assert names == ["status", "keepalive", "keepalive"]
    ages = [payload["since_frame_s"] for _, payload in events[1:]]
    assert ages == [0.2, 0.4], ages


def test_the_blocking_read_runs_off_the_event_loop(monkeypatch):
    from core import browser_frames

    seen: list[str] = []
    real_get = browser_frames.FrameSubscription.get

    def recorder(self, timeout=None):  # noqa: ANN001 — the same shape, with a note taken
        seen.append(threading.current_thread().name)
        return real_get(self, timeout)

    monkeypatch.setattr(browser_frames.FrameSubscription, "get", recorder)
    session = "watch-route-thread"
    manager = _Manager()
    _patch(monkeypatch, manager)

    asyncio.run(_drive(manager, session, want=2, ping=0.01))

    assert seen, "the route never read the bus"
    assert "MainThread" not in seen[0], seen
    assert manager.stopped == [session]


def test_the_cast_stops_when_the_last_reader_leaves(monkeypatch):
    """The stop survives the cancellation this cleanup runs inside because it is scheduled.

    An `await` here raises `CancelledError` before the engine is told to stop, which is the
    difference between a pane that closed and a cast that keeps costing a core.
    """
    session = "watch-route-stops"
    manager = _Manager()
    _patch(monkeypatch, manager)

    events = asyncio.run(_drive(manager, session, want=1, ping=0.01))

    assert events[0][0] == "status"
    assert manager.stopped == [session]


def test_a_reader_that_leaves_detaches_and_the_next_one_still_sees_the_page(monkeypatch):
    """No leaked subscriber, and a second watch is served the frame already on screen.

    A reader left on the bus would keep the count above zero, and the count is what decides
    whether the cast stops — so a leak is a cast that never ends. The late joiner case is the
    one a second tab hits, and it has to hold through the route as well as through the bus.
    """
    from core import browser_frames

    session = "watch-route-rejoin"
    bus = browser_frames.bus_for(session)
    bus.publish({"jpeg": "x"})
    manager = _Manager()
    _patch(monkeypatch, manager)

    asyncio.run(_drive(manager, session, want=2, ping=0.01))
    assert bus.stats()["subscribers"] == 0, "a closed stream left its reader on the bus"

    second = asyncio.run(_drive(manager, session, want=2, ping=0.01))
    assert [name for name, _ in second] == ["status", "frame"], second
    assert second[1][1]["jpeg"] == "x"
def test_the_production_manager_answers_what_the_route_calls() -> None:
    """The route's dependency list, checked against the class it really imports.

    Every case above drives a fake manager, and that is exactly what hides a method the
    production class does not have: the fake answers 404 while the real route raises
    `AttributeError` and the reader gets a 500. Measured on 2026-11-05, this pair was
    committed apart — the caller landed in `ed64a3ed` and `has_session` stayed in the
    working tree — and only a checkout of the commit shows it. So the three names the
    route reaches for are asserted here on the real class, with the shape each needs:
    `has_session` synchronous because the guard runs before any await, the two cast calls
    coroutines because they talk to the engine.
    """
    import inspect

    from core.browser import PlaywrightBrowserManager

    for name in ("has_session", "start_watch", "stop_watch"):
        member = getattr(PlaywrightBrowserManager, name, None)
        assert callable(member), f"the route calls {name}, the manager has no such method"

    assert not inspect.iscoroutinefunction(PlaywrightBrowserManager.has_session)
    assert inspect.iscoroutinefunction(PlaywrightBrowserManager.start_watch)
    assert inspect.iscoroutinefunction(PlaywrightBrowserManager.stop_watch)

    signature = inspect.signature(PlaywrightBrowserManager.has_session)
    assert signature.parameters["session"].default == "default"
