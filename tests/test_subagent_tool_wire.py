"""◑ Ephe · TDD — a subagent tool result names the call it answers on the wire.

A live iterative-team run on the owner's Spark engine showed both members die
after their first tool call: the loop appended a ``role="tool"`` message with no
``tool_call_id``, and the OpenAI-compatible converter refuses an orphaned result
(TL-1). The helper must name the same id the assistant block registered, on the
executed result and on the denial alike.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import core.model_provider as provider  # noqa: E402
from core.subagent import Subagent  # noqa: E402

# Every provider name is read off the module object when it is needed, never bound at
# import: a sibling test reloads core.model_provider, which mints a second
# ProviderMessage in the same dict, and a class held from before that reload is an
# instance the reloaded converter no longer recognises. See tests/test_order_independence_pin.py.


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    from core import subagent_history

    subagent_history.reset_for_test()
    yield
    subagent_history.reset_for_test()


@pytest.fixture(autouse=True)
def active_model(monkeypatch):
    monkeypatch.setattr(
        "core.model_provider.get_active_provider",
        lambda: SimpleNamespace(model="active-model-x"),
    )


def _tool_call(call_id: str, name: str, **args):
    return provider.ProviderChatResponse(
        message=provider.ProviderMessage(
            content="",
            tool_calls=[
                provider.ProviderToolCall(
                    function=provider.ProviderFunctionCall(name=name, arguments=args), id=call_id
                )
            ],
        )
    )


def _final(text: str):
    return provider.ProviderChatResponse(message=provider.ProviderMessage(content=text))


class _WireClient:
    """Every request passes through the real OpenAI-compatible converter."""

    def __init__(self, responses):
        self._responses = list(responses)
        self._wire = provider.OpenAICompatibleAsyncClient(base_url="http://localhost")
        self.converted: list[list[dict]] = []

    async def chat(self, *, model, messages, tools=None, stream=False, **_):
        self.converted.append(self._wire._convert_messages(messages))
        return self._responses.pop(0)


def _run(client, monkeypatch, *, allowed_tools):
    monkeypatch.setattr(provider, "build_provider_client", lambda: client)
    sub = Subagent(agent_id="sub-wire", role="helper", task="t", allowed_tools=allowed_tools)
    return asyncio.run(sub.run())


def _tool_messages(client, request_index=1):
    return [m for m in client.converted[request_index] if m["role"] == "tool"]


def test_an_executed_tool_result_names_its_call(monkeypatch):
    """GIVEN a whitelisted read call WHEN the helper answers it
    THEN the second request carries a tool message naming the call id."""
    client = _WireClient([_tool_call("call_abc", "read_file", path="/nonexistent"), _final("done")])
    result = _run(client, monkeypatch, allowed_tools=["read_file"])
    assert result.status == "ok"
    assert result.report == "done"
    tools = _tool_messages(client)
    assert tools and tools[0]["tool_call_id"] == "call_abc"


def test_a_denied_tool_result_also_names_its_call(monkeypatch):
    """GIVEN a call outside the whitelist WHEN the helper denies it
    THEN the denial still names the call so the wire stays valid."""
    client = _WireClient([_tool_call("call_den", "write_file", path="/x", content="y"), _final("done")])
    result = _run(client, monkeypatch, allowed_tools=["read_file"])
    assert result.status == "ok"
    tools = _tool_messages(client)
    assert tools and tools[0]["tool_call_id"] == "call_den"


def test_an_empty_call_id_falls_back_to_the_wire_index(monkeypatch):
    """GIVEN an engine that sends no call id WHEN the helper answers
    THEN the result names the positional id the converter registered."""
    client = _WireClient([_tool_call("", "read_file", path="/nonexistent"), _final("done")])
    result = _run(client, monkeypatch, allowed_tools=["read_file"])
    assert result.status == "ok"
    tools = _tool_messages(client)
    assert tools and tools[0]["tool_call_id"] == "call_0"