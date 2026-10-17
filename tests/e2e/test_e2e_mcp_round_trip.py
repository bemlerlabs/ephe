"""WG-46: an MCP tool call round-trips through the real client and a real server.

The MCP path is reached from the TUI, the CLI and the PWA, but it was only proven
one hop at a time. This module drives the whole round trip through the shipped
code in one process:

    model tool call
      -> the real agent loop (core.chat.chat_with_tools -> core.tools.execute_tool)
      -> the real MCP client (core.tools.mcp_client, JSON-RPC 2.0 over stdio)
      -> a real stdio MCP server (a child process, newline-delimited JSON-RPC)
      -> back out as the tool result, fenced as untrusted data, into the next
         engine call
      -> the final answer.

Only the engine client is faked, at the seam core.chat reads at call time; the
MCP server a test configures is a real child process, not a stub. The HTTP
surface shares the same transport: ``POST /api/mcp/health`` probes the
configured server (initialize + tools/list) over a real child process too.
"""
from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# The MCP registry and the live-client table are module-global, and a stdio
# client owns a child process. Eight workers sharing that state would clobber
# one another, so this module runs on a serial leg and stands down under xdist.
pytestmark = pytest.mark.skipif(
    bool(os.environ.get("PYTEST_XDIST_WORKER")),
    reason="serial leg only: the MCP registry and the stdio child are process-global",
)

TOOL_NAME = "mcp_echo"
ECHO_TEXT = "round-trip-through-the-real-client"
EXPECTED = f"echo:{ECHO_TEXT}"
FINAL_ANSWER = "The MCP server answered."
SESSION_ID = "e2e-mcp-session"

# A real MCP stdio server: newline-delimited JSON-RPC 2.0 on stdin/stdout, no
# SDK, no mock. One tool "echo"; tools/list answers without a session.
_SERVER_SOURCE = r'''
import json
import sys


def _reply(mid, result):
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": mid, "result": result}) + "\n")
    sys.stdout.flush()


def main():
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            continue
        mid = msg.get("id")
        if mid is None:
            continue  # notification (e.g. notifications/initialized): no reply
        method = msg.get("method")
        if method == "initialize":
            _reply(mid, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ephe-e2e-mcp", "version": "1.0.0"},
            })
        elif method == "tools/list":
            _reply(mid, {"tools": [{
                "name": "echo",
                "description": "Echo the given text back.",
                "inputSchema": {
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                },
            }]})
        elif method == "tools/call":
            args = (msg.get("params") or {}).get("arguments") or {}
            _reply(mid, {
                "content": [{"type": "text", "text": "echo:" + str(args.get("text", ""))}],
                "isError": False,
            })
        else:
            _reply(mid, {})


main()
'''


def _write_server(tmp_path: Path) -> Path:
    script = tmp_path / "e2e_mcp_server.py"
    script.write_text(_SERVER_SOURCE, encoding="utf-8")
    return script


def _stdio_spec(script: Path) -> str:
    return "stdio:" + shlex.join([sys.executable, str(script)])


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


class _Engine:
    """A model that calls the MCP tool once, then answers. No network, no LLM."""

    def __init__(self):
        self.calls: list[dict] = []
        self.tool_schemas: list[str] = []
        self._responses = [
            _response(content="", tool_calls=[(TOOL_NAME, {"text": ECHO_TEXT})]),
            _response(content=FINAL_ANSWER, tool_calls=None),
        ]

    async def chat(self, **kwargs):
        # Snapshot the message list: the loop mutates it in place, so keeping the
        # reference would make every recorded call look identical after the fact.
        snapshot = [{**m} for m in kwargs.get("messages", []) if isinstance(m, dict)]
        self.calls.append({**kwargs, "messages": snapshot})
        if kwargs.get("tools"):
            self.tool_schemas = [t.get("function", {}).get("name") for t in kwargs["tools"]]
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


def _tool_messages(engine: _Engine, index: int) -> list[str]:
    """The role=='tool' message bodies the engine saw on call ``index``."""
    return [
        m.get("content", "")
        for m in engine.calls[index]["messages"]
        if m.get("role") == "tool"
    ]


def _wire_fake_engine(monkeypatch, engine: "_Engine") -> None:
    """Replace only the engine client, at the seam core.chat reads at call time."""
    from core.model_provider import DEFAULT_OLLAMA_BASE_URL, ModelProviderConfig

    provider = ModelProviderConfig(
        provider="local_ollama", model="e2e-model", base_url=DEFAULT_OLLAMA_BASE_URL,
        label="E2E", offline_capable=True, requires_internet=False,
    )

    async def _passthrough(p):
        return p

    import core.chat as chat_mod
    import server.routes.chat as route_mod

    monkeypatch.setattr(chat_mod, "build_provider_client", lambda *a, **k: engine)
    monkeypatch.setattr(chat_mod, "get_active_provider", lambda: provider)
    monkeypatch.setattr(chat_mod, "resolve_active_with_failover", _passthrough)
    monkeypatch.setattr(route_mod, "get_active_provider", lambda: provider)


def _run_turn(client) -> list[dict]:
    resp = client.post("/api/chat/stream", json={
        "message": "Echo something through the MCP server.",
        "model": "e2e-model",
        "session_id": SESSION_ID,
        "mode": "agent",
        "autonomous": True,
    })
    assert resp.status_code == 200, resp.text
    return _server_events(resp.text)


@pytest.fixture()
def harness(tmp_path, monkeypatch):
    """The real app plus a real stdio MCP server. Only the engine is replaced."""
    monkeypatch.setenv("EPHE_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    monkeypatch.setenv("EPHE_MCP_SERVERS", _stdio_spec(_write_server(tmp_path)))

    # The approval profile below is written through core.engine_config.CONFIG_DIR, a module
    # constant bound at import — so the env var above alone still sent the write into the
    # user's real ~/.ephe and tests/test_home_isolation.py failed the setup in a full run
    # (the same reason the sibling e2e fixtures patch it; see the `client` fixture in
    # test_e2e_install_chat_tool_artifact.py).
    import core.engine_config as _engine_config

    monkeypatch.setattr(_engine_config, "CONFIG_DIR", tmp_path / "config", raising=False)

    engine = _Engine()
    _wire_fake_engine(monkeypatch, engine)

    # The shipped "session" approval profile plus the explicit autonomous flag:
    # the MCP tool call still passes the real gate (MCP tools are non-safe).
    from core.security_config import save_security_config
    save_security_config(approval_profile="session")

    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as c:
        yield c, engine

    # The MCP registry is module-global and the fixture above only clears the
    # live clients. Reset the namespace this test registered, so a sibling test
    # that never re-syncs does not inherit mcp_echo.
    from core.tools.mcp_client import set_mcp_servers, unregister_mcp_tools

    unregister_mcp_tools()
    set_mcp_servers([])


def test_e2e_mcp_tool_round_trips_through_the_agent_loop(harness):
    """GIVEN a configured stdio MCP server
    WHEN a model turn calls its tool
    THEN the call leaves through the real client to the child process and its
    answer returns fenced into the next engine call."""
    client, engine = harness

    import core.tools.mcp_client as mcp
    registered = mcp.get_mcp_tools()
    assert TOOL_NAME in registered, f"startup did not register the MCP tool: {registered}"

    events = _run_turn(client)

    assert _first(events, type="tool_start", tool=TOOL_NAME) is not None, events
    done = _first(events, type="tool_done", tool=TOOL_NAME)
    assert done is not None, events
    # The value can only come from the child process: the fake engine never
    # supplies it, and the real MCP client carried it back.
    assert done["result"] == EXPECTED, done

    # The result flowed into the next engine call, fenced as untrusted data.
    first_call = _tool_messages(engine, 0)
    second_call = _tool_messages(engine, 1)
    assert first_call == [], f"a tool result existed before the tool ran: {first_call}"
    assert len(second_call) == 1, f"the follow-up did not receive one tool result: {second_call}"
    assert EXPECTED in second_call[0], second_call[0]
    from core.channels.injection_guard import UNTRUSTED_DATA_OPEN
    assert UNTRUSTED_DATA_OPEN in second_call[0], (
        f"MCP output reached the engine unwrapped: {second_call[0]!r}"
    )

    # The MCP tool is on the registry surface (what discovery reads). The array
    # actually offered to the model is the progressive-disclosure core set, so a
    # non-skill turn reaches the MCP tool through the tool_call meta router —
    # hence the direct name is absent from engine.tool_schemas by design.
    from core.tools.registry import get_tool_schemas
    registry_names = {s.get("function", {}).get("name") for s in get_tool_schemas()}
    assert TOOL_NAME in registry_names, f"MCP tool missing from the registry: {sorted(registry_names)}"
    assert "tool_call" in engine.tool_schemas, engine.tool_schemas

    answer = "".join(e.get("data", "") for e in events if e.get("type") == "chunk")
    assert FINAL_ANSWER in answer, f"answer not streamed; events={events}"
    assert _first(events, type="done") is not None, "stream never sent done"


def test_e2e_mcp_health_route_probes_the_child_process(harness):
    """GIVEN a configured stdio MCP server
    WHEN POST /api/mcp/health runs
    THEN it reports the server reachable with the tool count its child listed."""
    client, _engine = harness

    resp = client.post("/api/mcp/health")
    assert resp.status_code == 200, resp.text
    servers = resp.json()["servers"]
    assert len(servers) == 1, servers
    row = servers[0]
    assert row["status"] == "ok", row
    assert row["transport"] == "stdio", row
    assert row["tool_count"] == 1, row
    assert row["error"] is None, row
