"""W3-62 e2e: a full local turn runs with the network switched off.

The README's offline-first line says the core product works locally once an
engine is chosen. This module makes that line fail loudly: every outbound
connection is fenced at the socket layer, so ``connect`` and
``create_connection`` raise and the target is recorded. With the fence armed,
the shipped app (FastAPI route, agent loop, approval gate, tool, session
mirror) still runs a whole turn, because the engine is the only part faked and
it is served in-process.

Three checks: a turn completes with zero connection attempts, a turn with no
engine ends on the actionable offline message, and the fence really refuses a
public address.
"""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

TOOL_NAME = "create_svg"
ARTIFACT_FILENAME = "offline-proof.svg"
SVG_BODY = '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><rect width="40" height="40" fill="red"/></svg>'
FINAL_ANSWER = "Saved the red square as offline-proof.svg."
MODEL = "offline-e2e-model"
SESSION_ID = "w3-62-offline"
MIRRORED_ID = f"rest-{SESSION_ID}"

_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost", "0.0.0.0"})


class _OfflineFence:
    """Records every outbound connection attempt and refuses it.

    The fence is what makes the turn run with the network off; a passing turn
    proves the product did not need a socket.
    """

    def __init__(self) -> None:
        self.attempts: list[tuple[str, object]] = []

    def arm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        fence = self

        def refused_connect(self, address):
            fence.attempts.append(("connect", address))
            raise OSError("offline fence: outbound connect refused")

        def refused_connect_ex(self, address):
            fence.attempts.append(("connect_ex", address))
            return 111  # ECONNREFUSED

        def refused_create_connection(address, *args, **kwargs):
            fence.attempts.append(("create_connection", address))
            raise OSError("offline fence: outbound connect refused")

        monkeypatch.setattr(socket.socket, "connect", refused_connect)
        monkeypatch.setattr(socket.socket, "connect_ex", refused_connect_ex)
        monkeypatch.setattr(socket, "create_connection", refused_create_connection)

    def off_loopback(self) -> list[tuple[str, object]]:
        """Attempts whose host is neither loopback nor a bare local name."""
        out = []
        for kind, address in self.attempts:
            host = address[0] if isinstance(address, tuple) and address else address
            if host not in _LOOPBACK:
                out.append((kind, address))
        return out


def _response(content: str = "", tool_calls=None):
    from core.model_provider import (
        ProviderChatResponse, ProviderFunctionCall, ProviderMessage, ProviderToolCall,
    )

    calls = None
    if tool_calls:
        calls = [
            ProviderToolCall(function=ProviderFunctionCall(name=name, arguments=args))
            for name, args in tool_calls
        ]
    return ProviderChatResponse(message=ProviderMessage(content=content, tool_calls=calls))


class _ScriptedEngine:
    """One tool call, then a final answer, from a fixed script."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._responses = [
            _response("", [(TOOL_NAME, {"svg_code": SVG_BODY, "filename": ARTIFACT_FILENAME})]),
            _response(FINAL_ANSWER),
        ]

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        return self._responses[idx]

    async def aclose(self):
        return None


def _server_events(body: str) -> list[dict]:
    events: list[dict] = []
    for line in body.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload:
            events.append(json.loads(payload))
    return events


def _first(events: list[dict], **match) -> dict | None:
    return next((e for e in events if all(e.get(k) == v for k, v in match.items())), None)


def _point_engine_at_local(monkeypatch, engine) -> None:
    """Send every provider lookup to the local endpoint; ``engine`` fakes the client.

    ``engine=None`` leaves the client real, so the shipped ollama client targets
    the local endpoint and the fence refuses the connection.
    """
    from core.model_provider import DEFAULT_OLLAMA_BASE_URL, ModelProviderConfig

    provider = ModelProviderConfig(
        provider="local_ollama", model=MODEL, base_url=DEFAULT_OLLAMA_BASE_URL,
        label="Offline E2E", offline_capable=True, requires_internet=False,
    )

    async def _passthrough(p):
        return p

    import core.chat as chat_mod
    import core.react as react_mod
    import server.routes.chat as route_mod

    monkeypatch.setattr(chat_mod, "get_active_provider", lambda: provider)
    monkeypatch.setattr(chat_mod, "resolve_active_with_failover", _passthrough)
    monkeypatch.setattr(route_mod, "get_active_provider", lambda: provider)
    # reflect() builds its own client out of core.react's namespace, so a seam
    # left open there reaches localhost:11434 on every turn.
    if engine is not None:
        monkeypatch.setattr(chat_mod, "build_provider_client", lambda *a, **k: engine)
        monkeypatch.setattr(react_mod, "build_provider_client", lambda *a, **k: engine)


def _run_turn(client) -> list[dict]:
    """One real SSE turn; returns the parsed server events."""
    resp = client.post("/api/chat/stream", json={
        "message": "Draw a red square and save it as an SVG.",
        "model": MODEL,
        "session_id": SESSION_ID,
        "mode": "agent",
        "autonomous": True,
    })
    assert resp.status_code == 200, resp.text
    return _server_events(resp.text)


@pytest.fixture()
def offline_home(tmp_path, monkeypatch):
    """A throwaway home: sessions, workbench, profile, artifacts and security config."""
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
    sessions = tmp_path / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EPHE_SESSIONS_DIR", str(sessions))

    import core.multi_session as multi_session
    import core.artifact_store as artifact_store
    import core.security_config as security

    monkeypatch.setattr(multi_session, "SESSIONS_DIR", sessions)
    monkeypatch.setattr(artifact_store, "ARTIFACTS_DB", tmp_path / "artifacts.db")
    monkeypatch.setattr(security, "security_config_path", lambda: tmp_path / "security.json")
    # The shipped "session" profile frees the local write; the real gate still runs.
    security.save_security_config(approval_profile="session")
    return tmp_path


def test_a_turn_runs_offline_with_every_socket_refused(offline_home, monkeypatch):
    """GIVEN the fence armed and one engine faked
    WHEN a full turn is posted
    THEN chat and tool complete, the turn is mirrored, and nothing was attempted."""
    fence = _OfflineFence()
    fence.arm(monkeypatch)
    _point_engine_at_local(monkeypatch, _ScriptedEngine())

    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as client:
        events = _run_turn(client)

    answer = "".join(e.get("data", "") for e in events if e.get("type") == "chunk")
    assert FINAL_ANSWER in answer, f"answer not streamed; events={events}"
    assert _first(events, type="done") is not None, events

    assert _first(events, type="tool_start", tool=TOOL_NAME) is not None, events
    assert _first(events, type="tool_done", tool=TOOL_NAME) is not None, events

    file_result = _first(events, type="file_result", file_type="svg")
    assert file_result and file_result.get("id"), events
    out_path = Path(file_result["path"])
    assert out_path.is_file(), f"tool reported {out_path}, nothing there"
    assert SVG_BODY in out_path.read_text(encoding="utf-8")

    from core import multi_session

    mirrored = multi_session.load_messages(MIRRORED_ID)
    roles = [m["role"] for m in mirrored]
    assert "user" in roles and "assistant" in roles, f"turn not mirrored: {mirrored}"
    assert mirrored[-1]["content"] == FINAL_ANSWER, mirrored

    assert fence.attempts == [], f"the turn reached for the network: {fence.attempts}"


def test_a_turn_with_no_engine_ends_on_the_offline_message(offline_home, monkeypatch):
    """GIVEN the local engine unreachable and the fence armed
    WHEN a turn is posted
    THEN the stream closes cleanly on the actionable offline message, and every
    attempt it made stayed on this machine."""
    fence = _OfflineFence()
    fence.arm(monkeypatch)
    _point_engine_at_local(monkeypatch, engine=None)

    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as client:
        events = _run_turn(client)

    error = _first(events, type="error")
    assert error is not None, f"no error event; events={events}"
    assert "not reachable" in error["msg"].lower(), error
    assert _first(events, type="done") is not None, f"stream never closed: {events}"
    assert fence.off_loopback() == [], (
        f"the offline path reached a host outside this machine: {fence.off_loopback()}"
    )


def test_the_fence_refuses_a_real_outbound_connection(monkeypatch):
    """GIVEN the fence armed
    WHEN a public address is dialled
    THEN the call is refused and the target recorded."""
    fence = _OfflineFence()
    fence.arm(monkeypatch)

    with pytest.raises(OSError):
        socket.create_connection(("example.com", 443))
    assert fence.attempts == [("create_connection", ("example.com", 443))]
