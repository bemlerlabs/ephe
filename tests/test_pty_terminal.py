"""P1-5 full PTY terminal — backend tests.

Covers: (1) the PtySession mechanics (echo, resize), (2) the WebSocket handshake
incl. the roundtrip, (3) the auth gate in LAN mode (BaseHTTPMiddleware does not
cover the websocket scope → an explicit gate). Needs a real PTY (POSIX);
on platforms without os.openpty the PTY tests are skipped.
"""
import asyncio
import os

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

import server.middleware as middleware
from core.pty_session import (
    PtySession,
    get_pty_session,
    pty_available,
    reset_pty_session,
)
from server.main import create_app

requires_pty = pytest.mark.skipif(not pty_available(), reason="os.openpty unavailable")

MARK = "EPHE_PTY_MARK_9137"


@pytest.fixture
def client():
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _isolate_session():
    """Every test gets a fresh singleton session; no leaking processes."""
    reset_pty_session()
    saved = middleware.LAN_AUTH_TOKEN
    middleware.LAN_AUTH_TOKEN = None
    try:
        yield
    finally:
        middleware.LAN_AUTH_TOKEN = saved
        reset_pty_session()


async def _drain_until(queue: asyncio.Queue, needle: str, timeout: float = 8.0) -> str:
    """Collects output frames until the needle shows up (or the timeout hits)."""
    seen = ""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        try:
            frame = await asyncio.wait_for(queue.get(), timeout=max(0.05, deadline - loop.time()))
        except asyncio.TimeoutError:
            break
        if frame.get("type") == "output":
            seen += frame.get("data", "")
            if needle in seen:
                return seen
        elif frame.get("type") == "exit":
            break
    return seen


@requires_pty
def test_pty_session_echo_roundtrip():
    sess = PtySession()
    assert sess.start() is True
    assert sess.alive
    try:
        async def scenario():
            q = sess.subscribe()
            sess.write(f"echo {MARK}\n".encode())
            out = await _drain_until(q, MARK)
            sess.unsubscribe(q)
            return out

        out = asyncio.run(scenario())
        assert MARK in out
    finally:
        sess.kill()
    assert not sess.alive


@requires_pty
def test_pty_session_resize_sets_winsize():
    sess = PtySession()
    assert sess.start(cols=80, rows=24)
    try:
        # Must not crash, and clamps nonsense values.
        sess.resize(120, 40)
        sess.resize(0, 0)
        assert sess.alive
    finally:
        sess.kill()


@requires_pty
def test_pty_session_scrollback_replays():
    sess = PtySession()
    assert sess.start()
    try:
        async def scenario():
            q = sess.subscribe()
            sess.write(f"echo {MARK}\n".encode())
            await _drain_until(q, MARK)
            sess.unsubscribe(q)

        asyncio.run(scenario())
        assert MARK in sess.scrollback().decode("utf-8", "replace")
    finally:
        sess.kill()


@requires_pty
def test_ws_terminal_echo_roundtrip(client):
    """The full path: connect the WS → send input → receive output."""
    with client.websocket_connect("/api/shell/term") as ws:
        ws.send_json({"type": "input", "data": f"echo {MARK}\n"})
        got = ""
        for _ in range(200):
            frame = ws.receive_json()
            if frame.get("type") == "output":
                got += frame.get("data", "")
                if MARK in got:
                    break
            elif frame.get("type") == "exit":
                break
        assert MARK in got


@requires_pty
def test_ws_terminal_reconnect_replays_scrollback(client):
    """Session continuity: after echo + reconnect the new socket delivers the replay."""
    with client.websocket_connect("/api/shell/term") as ws:
        ws.send_json({"type": "input", "data": f"echo {MARK}\n"})
        for _ in range(200):
            frame = ws.receive_json()
            if frame.get("type") == "output" and MARK in frame.get("data", ""):
                break
    # The session lives on (singleton) → the second connect gets the scrollback.
    assert get_pty_session().alive
    with client.websocket_connect("/api/shell/term") as ws2:
        replay = ""
        for _ in range(50):
            frame = ws2.receive_json()
            if frame.get("type") == "output":
                replay += frame.get("data", "")
                if MARK in replay:
                    break
        assert MARK in replay


def test_ws_terminal_lan_rejects_without_token(client):
    """LAN mode: without ?token= the handshake is rejected (1008, no accept)."""
    middleware.LAN_AUTH_TOKEN = "secret-lan-token"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/shell/term") as ws:
            ws.receive_json()


@requires_pty
def test_ws_terminal_lan_accepts_with_token(client):
    """LAN mode: with a correct ?token= the connection is established."""
    middleware.LAN_AUTH_TOKEN = "secret-lan-token"
    with client.websocket_connect("/api/shell/term?token=secret-lan-token") as ws:
        ws.send_json({"type": "input", "data": f"echo {MARK}\n"})
        got = ""
        for _ in range(200):
            frame = ws.receive_json()
            if frame.get("type") == "output":
                got += frame.get("data", "")
                if MARK in got:
                    break
            elif frame.get("type") == "exit":
                break
        assert MARK in got


def test_ws_terminal_lan_rejects_wrong_token(client):
    middleware.LAN_AUTH_TOKEN = "secret-lan-token"
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/shell/term?token=nope") as ws:
            ws.receive_json()
