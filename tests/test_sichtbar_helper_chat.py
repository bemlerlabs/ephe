"""Visibility wave: every helper gets its own chat surface.

For that, a helper run has to carry its own unique session id and know which
parent session it came from — otherwise the surface can neither create the chat
nor restore it after a restart, and the way back is missing.

Pins:
1. ``spawn_agent`` writes the helper session id (prefix ``helper-``) and the
   parent session (from the tool session context) into the ledger record.
2. The same id travels along in all three SSE events (started/tool/done) — the
   live surface builds the chat from it without polling the ledger.
3. Two runs get different ids; the display schema ``subagent-N``
   stays unchanged (trajectory, activity labels, existing tests).
4. summaries + the detail endpoint deliver the id, so that clicking a
   history row opens the same chat as a live event.
5. Records without context (older snapshot rows) get a deterministic
   id — never empty, so the surface does not have to guess.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import subagent_history  # noqa: E402
from core.subagent import Subagent  # noqa: E402
from core.tools.subagent_tool import spawn_agent  # noqa: E402
from core.tools.session_ctx import set_current_session  # noqa: E402
from core.model_provider import (  # noqa: E402
    ProviderChatResponse,
    ProviderFunctionCall,
    ProviderMessage,
    ProviderToolCall,
)

PREFIX = subagent_history.HELPER_SESSION_PREFIX


def _msg(content="", tool_calls=None):
    return ProviderChatResponse(message=ProviderMessage(content=content, tool_calls=tool_calls))


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)

    async def chat(self, *, model, messages, stream=False, tools=None, **_):
        return self._responses.pop(0)


@pytest.fixture
def active_model(monkeypatch):
    monkeypatch.setattr(
        "core.model_provider.get_active_provider",
        lambda: SimpleNamespace(model="active-model-x"),
    )
    return "active-model-x"


@pytest.fixture(autouse=True)
def isolated_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    subagent_history.reset_for_test()
    yield tmp_path
    subagent_history.reset_for_test()


@pytest.fixture
def bridge():
    """Catches the SSE bridge (server/routes/chat.py sets the same ContextVar)."""
    from core.tools import subagent_tool

    captured: list[dict] = []
    token = subagent_tool.subagent_emit_var.set(captured.append)
    yield captured
    subagent_tool.subagent_emit_var.reset(token)


def _patch_tool_then_report(monkeypatch):
    """One tool step, then the report — the normal case of a helper."""

    async def fake_execute_tool(name, args, *a, **k):
        return f"result-of-{name}"

    monkeypatch.setattr("core.tools.execute_tool", fake_execute_tool)
    monkeypatch.setattr(
        "core.model_provider.build_provider_client",
        lambda: _FakeClient([
            _msg(tool_calls=[ProviderToolCall(
                function=ProviderFunctionCall(name="web_search", arguments={"query": "q"}))]),
            _msg(content="BERICHT"),
        ]),
    )


def _only_record() -> dict:
    assert len(subagent_history._mem) == 1, list(subagent_history._mem)
    return next(iter(subagent_history._mem.values()))


# 1. the ledger record knows the helper session and the parent

def test_spawn_agent_notiert_helfersitzung_und_mutter(active_model, monkeypatch):
    _patch_tool_then_report(monkeypatch)
    set_current_session("9d2c0d55-parent")

    asyncio.run(spawn_agent("Kurzlabel", "Finde etwas", subagent_type="scout"))

    rec = _only_record()
    assert rec["chat_session_id"].startswith(PREFIX)
    assert len(rec["chat_session_id"]) > len(PREFIX)
    assert rec["parent_session"] == "9d2c0d55-parent"


def test_helfersitzung_ohne_mutter_kontext_bleicht_auf_leere_mutter(active_model, monkeypatch):
    """CLI/paths without a session context ('default') invent no parent session."""
    _patch_tool_then_report(monkeypatch)
    set_current_session("")

    asyncio.run(spawn_agent("d", "t"))

    rec = _only_record()
    assert rec["parent_session"] == ""
    assert rec["chat_session_id"].startswith(PREFIX)


# 2. the identity travels along in the SSE events

def test_alle_drei_events_tragen_helfersitzung(active_model, monkeypatch, bridge):
    _patch_tool_then_report(monkeypatch)

    sub = Subagent(
        agent_id="subagent-7", role="scout", task="find it",
        chat_session_id=f"{PREFIX}abc12345", parent_session="mutter-1",
        on_event=bridge.append,
    )
    asyncio.run(sub.run())

    assert bridge[0]["type"] == "subagent_started"
    assert {e["chat_session_id"] for e in bridge} == {f"{PREFIX}abc12345"}
    assert bridge[0]["parent_session"] == "mutter-1"


def test_spawn_agent_events_tragen_dieselbe_id_wie_der_record(active_model, monkeypatch, bridge):
    _patch_tool_then_report(monkeypatch)
    set_current_session("mutter-2")

    asyncio.run(spawn_agent("d", "t"))

    rec = _only_record()
    assert {e["chat_session_id"] for e in bridge} == {rec["chat_session_id"]}


# 3. Unique id per run, display schema stays

def test_zwei_laeufe_getrennte_sitzung_bei_gleichem_agent_id_schema(active_model, monkeypatch):
    _patch_tool_then_report(monkeypatch)
    set_current_session("mutter-3")

    out1 = asyncio.run(spawn_agent("erste Aufgabe", "t1"))
    out2 = asyncio.run(spawn_agent("zweite Aufgabe", "t2"))

    assert "subagent-" in out1 and "subagent-" in out2
    ids = list(subagent_history._mem)
    assert len({subagent_history._mem[i]["chat_session_id"] for i in ids}) == 2


# 4/5. Reading: summaries, detail, legacy fallback

def test_begin_ohne_kennung_leitet_sie_deterministisch_ab():
    subagent_history.begin("subagent-1", role="r", task="t", description="", model="")
    rec = subagent_history.get("subagent-1")
    assert rec["chat_session_id"] == f"{PREFIX}subagent-1"
    assert rec["parent_session"] == ""


def test_summaries_und_record_fuehren_die_kennung():
    subagent_history.begin(
        "subagent-1", role="r", task="t", description="d", model="m",
        chat_session_id=f"{PREFIX}deadbeef", parent_session="mutter-4",
    )
    assert subagent_history.summaries()["agents"][0]["chat_session_id"] == f"{PREFIX}deadbeef"

    from server.main import create_app

    client = TestClient(create_app())
    listed = client.get("/api/subagents").json()["agents"][0]
    assert listed["chat_session_id"] == f"{PREFIX}deadbeef"
    assert listed["parent_session"] == "mutter-4"

    detail = client.get("/api/subagents/subagent-1").json()
    assert detail["chat_session_id"] == f"{PREFIX}deadbeef"
    assert detail["parent_session"] == "mutter-4"
