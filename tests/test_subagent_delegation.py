"""R36-S: subagent delegation (spawn_agent → core/subagent.Subagent).

Pins:
1. The model follows the ACTIVE provider (no Ollama hardcode).
2. Events: subagent_started / subagent_tool / subagent_done over the bridge.
3. Read-only whitelist: a foreign tool does NOT run in execute_tool; the model
   gets a rejection note.
4. Closing status: ok / timeout / step_limit; the report in the spawn_agent header.
5. The event bridge may raise without killing the helper.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.subagent import SUBAGENT_TOOL_WHITELIST, Subagent  # noqa: E402
from core.model_provider import ProviderChatResponse, ProviderFunctionCall, ProviderMessage, ProviderToolCall  # noqa: E402


def _msg(content="", tool_calls=None):
    return ProviderChatResponse(message=ProviderMessage(content=content, tool_calls=tool_calls))


class _FakeClient:
    """Scripted chat(): pops one response per call."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def chat(self, *, model, messages, stream=False, tools=None, **_):
        assert stream is False
        self.calls.append({"model": model, "messages": list(messages), "tools": tools})
        return self._responses.pop(0)


@pytest.fixture
def active_model(monkeypatch):
    monkeypatch.setattr(
        "core.model_provider.get_active_provider",
        lambda: SimpleNamespace(model="active-model-x"),
    )
    return "active-model-x"


def _patch_tools(monkeypatch, executed=None):
    async def fake_execute_tool(name, args, *a, **k):
        if executed is not None:
            executed.append((name, args))
        return f"result-of-{name}"

    monkeypatch.setattr("core.tools.execute_tool", fake_execute_tool)


def test_given_no_explicit_model_when_spawned_then_active_engine_model_is_used(active_model):
    sub = Subagent(agent_id="a1", role="researcher", task="do x")
    assert sub.model == "active-model-x"


def test_given_explicit_model_when_spawned_then_it_wins():
    sub = Subagent(agent_id="a1", role="r", task="t", model="pinned")
    assert sub.model == "pinned"


def test_given_tool_call_then_final_when_run_then_events_and_report(active_model, monkeypatch):
    executed: list[tuple] = []
    _patch_tools(monkeypatch, executed)
    client = _FakeClient([
        _msg(tool_calls=[ProviderToolCall(function=ProviderFunctionCall(name="web_search", arguments={"query": "q"}))]),
        _msg(content="Final report text"),
    ])
    monkeypatch.setattr("core.model_provider.build_provider_client", lambda: client)

    events: list[dict] = []
    sub = Subagent(agent_id="a1", role="researcher", task="find it", on_event=events.append)
    result = asyncio.run(sub.run())

    types = [e["type"] for e in events]
    assert types[0] == "subagent_started" and types[-1] == "subagent_done"
    assert "subagent_tool" in types
    assert result.status == "ok"
    assert result.report == "Final report text"
    assert executed == [("web_search", {"query": "q"})]
    # the tool result lands back in the history as role:tool:
    tool_msgs = [m for m in client.calls[-1]["messages"]
                 if isinstance(m, dict) and m.get("role") == "tool"]
    assert any("result-of-web_search" in m["content"] for m in tool_msgs)
    assert events[-1]["status"] == "ok" and events[-1]["agent_id"] == "a1"


def test_given_off_whitelist_tool_when_run_then_execute_tool_not_called(active_model, monkeypatch):
    executed: list[tuple] = []
    _patch_tools(monkeypatch, executed)
    client = _FakeClient([
        _msg(tool_calls=[ProviderToolCall(function=ProviderFunctionCall(name="write_file", arguments={"path": "x"}))]),
        _msg(content="done"),
    ])
    monkeypatch.setattr("core.model_provider.build_provider_client", lambda: client)

    sub = Subagent(agent_id="a2", role="r", task="t")
    result = asyncio.run(sub.run())

    assert result.status == "ok" and executed == []
    sub_names = {c["function"].name for c in ()}  # noqa: F841 — readability
    assert "write_file" not in SUBAGENT_TOOL_WHITELIST


def test_given_always_tool_calls_when_run_then_step_limit(active_model, monkeypatch):
    _patch_tools(monkeypatch)
    loop_call = ProviderToolCall(function=ProviderFunctionCall(name="get_datetime", arguments={}))
    client = _FakeClient([_msg(tool_calls=[loop_call])] * 4)
    monkeypatch.setattr("core.model_provider.build_provider_client", lambda: client)
    monkeypatch.setattr("core.subagent.SUBAGENT_MAX_ITERATIONS", 2)

    sub = Subagent(agent_id="a3", role="r", task="t")
    result = asyncio.run(sub.run())
    assert result.status == "step_limit"
    assert "step limit" in result.report


def test_given_slow_engine_when_run_then_timeout(active_model, monkeypatch):
    class SlowClient:
        async def chat(self, **_):
            await asyncio.sleep(10)
            return _msg(content="never")

    monkeypatch.setattr("core.model_provider.build_provider_client", lambda: SlowClient())
    monkeypatch.setattr("core.subagent.SUBAGENT_TIMEOUT", 0.05)

    sub = Subagent(agent_id="a4", role="r", task="t")
    result = asyncio.run(sub.run())
    assert result.status == "timeout"
    assert "timeout" in result.report


def test_given_raising_bridge_when_run_then_helper_survives(active_model, monkeypatch):
    _patch_tools(monkeypatch)
    client = _FakeClient([_msg(content="ok report")])
    monkeypatch.setattr("core.model_provider.build_provider_client", lambda: client)

    def _boom(_event):
        raise RuntimeError("sse hiccup")

    sub = Subagent(agent_id="a5", role="r", task="t", on_event=_boom)
    result = asyncio.run(sub.run())
    assert result.status == "ok" and result.report == "ok report"


def test_given_engine_error_when_run_then_error_status(active_model, monkeypatch):
    class ExplodingClient:
        async def chat(self, **_):
            raise RuntimeError("engine gone")

    monkeypatch.setattr("core.model_provider.build_provider_client", lambda: ExplodingClient())
    sub = Subagent(agent_id="a6", role="r", task="t")
    result = asyncio.run(sub.run())
    assert result.status == "error"
    assert "subagent error" in result.report


def test_given_whitelisted_schemas_when_built_then_only_whitelist_returned(monkeypatch):
    import core.tools.registry as registry

    schemas = [
        {"type": "function", "function": {"name": "web_search"}},
        {"type": "function", "function": {"name": "write_file"}},
        {"type": "function", "function": {"name": "read_file"}},
    ]
    monkeypatch.setattr(registry, "get_tool_schemas", lambda: schemas)
    from core.subagent import _whitelisted_schemas

    out = asyncio.run(_whitelisted_schemas())
    names = {s["function"]["name"] for s in out}
    assert names == {"web_search", "read_file"}
    assert "write_file" not in names


def test_given_spawn_agent_when_run_then_header_and_role_and_bridge_events(monkeypatch):
    """spawn_agent sequences the agent ids, defaults the role and streams
    events over the ContextVar bridge (server/routes/chat.py sets it)."""
    from core.tools import subagent_tool

    async def fake_run(self):
        self._emit({"type": "subagent_started", "agent_id": self.agent_id})
        return SimpleNamespace(agent_id=self.agent_id, role=self.role, task=self.task,
                               report="THE REPORT", status="ok", tool_calls=[{"tool": "web_search"}])

    monkeypatch.setattr("core.subagent.Subagent.run", fake_run)

    captured: list[dict] = []
    token = subagent_tool.subagent_emit_var.set(captured.append)
    try:
        out = asyncio.run(subagent_tool.spawn_agent(
            "Research HTTP timeouts", "Find authoritative numbers", subagent_type="researcher"))
        assert out.startswith("Subagent subagent-")
        assert "role: researcher" in out
        assert out.endswith("THE REPORT")
        assert any(e["type"] == "subagent_started" for e in captured)
        out2 = asyncio.run(subagent_tool.spawn_agent("Second", "task"))
        assert "role: general-purpose" in out2
        first_id = int(out.split("subagent-")[1].split(" ")[0])
        second_id = int(out2.split("subagent-")[1].split(" ")[0])
        assert second_id == first_id + 1
    finally:
        subagent_tool.subagent_emit_var.reset(token)


def test_given_no_bridge_when_run_then_events_dropped_silently(monkeypatch):
    """Without a bridge set (CLI/tests) spawn_agent still runs through."""
    from core.tools import subagent_tool

    async def fake_run(self):
        return SimpleNamespace(agent_id=self.agent_id, role=self.role, task=self.task,
                               report="r", status="ok", tool_calls=[])

    monkeypatch.setattr("core.subagent.Subagent.run", fake_run)
    assert subagent_tool.subagent_emit_var.get() is None
    out = asyncio.run(subagent_tool.spawn_agent("desc", "prompt"))
    assert "status 'ok'" in out
