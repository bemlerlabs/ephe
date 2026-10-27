"""P4-D: persistent subagent history + REST read (the gates of the wave).

Pins:
1. Registry lifecycle begin → tool_call* → finish: full record fields,
   newest-first order, summaries capped (not the whole task text).
2. Subagent.run() fills the history with: status, duration_ms, tool_calls
   (incl. ms), report, transcript — role/task/model from begin.
3. Persistence: finish writes ~/.ephe/subagent_history.json; after a reset
   (restart simulation) the record is back from the snapshot.
4. REST: GET /api/subagents returns {"agents": […]}; detail 200/404.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import subagent_history  # noqa: E402
from core.subagent import Subagent  # noqa: E402
from core.model_provider import (  # noqa: E402
    ProviderChatResponse,
    ProviderFunctionCall,
    ProviderMessage,
    ProviderToolCall,
)


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


# 1. Registry lifecycle

def test_begin_tool_finish_pro_full_record(isolated_registry):
    subagent_history.begin("subagent-1", role="scout", task="find x",
                           description="Kurzlabel", model="m1")
    subagent_history.tool_call("subagent-1", "read_file", '{"path":"a"}', 12)
    subagent_history.tool_call("subagent-1", "web_search", '{"q":"x"}', 34)
    subagent_history.finish("subagent-1", status="ok", report="Fertig.",
                            duration_ms=125, transcript=[{"role": "tool", "text": "r"}])

    rec = subagent_history.get("subagent-1")
    assert rec is not None
    assert rec["status"] == "ok"
    assert rec["role"] == "scout" and rec["task"] == "find x"
    assert rec["description"] == "Kurzlabel" and rec["model"] == "m1"
    assert rec["duration_ms"] == 125
    assert rec["tool_calls"] == [
        {"tool": "read_file", "args_preview": '{"path":"a"}', "ms": 12, "gate": ""},
        {"tool": "web_search", "args_preview": '{"q":"x"}', "ms": 34, "gate": ""},
    ]
    assert rec["report"] == "Fertig."
    assert rec["transcript"] == [{"role": "tool", "text": "r"}]


def test_summaries_neueste_zuerst_und_compact(isolated_registry):
    subagent_history.begin("a-old", role="r", task="t" * 200, description="", model="")
    subagent_history.finish("a-old", status="ok", report="", duration_ms=1, transcript=[])
    subagent_history.begin("a-new", role="r", task="neu", description="", model="")

    out = subagent_history.summaries()["agents"]
    assert [s["agent_id"] for s in out] == ["a-new", "a-old"]  # started_ts, insertion-stabil
    assert out[0]["status"] == "running" and out[1]["status"] == "ok"
    assert out[1]["task"] == "t" * 120  # capped for the overview
    assert out[1]["tool_count"] == 0


def test_unknown_id_liefert_none(isolated_registry):
    assert subagent_history.get("nope") is None


# 2. Subagent.run() fills the history

def test_run_füllt_history_mit_timings_und_transcript(active_model, monkeypatch, isolated_registry):
    async def fake_execute_tool(name, args, *a, **k):
        return f"result-of-{name}"

    monkeypatch.setattr("core.tools.execute_tool", fake_execute_tool)
    client = _FakeClient([
        _msg(tool_calls=[ProviderToolCall(function=ProviderFunctionCall(name="web_search", arguments={"query": "q"}))]),
        _msg(content="Final report text"),
    ])
    monkeypatch.setattr("core.model_provider.build_provider_client", lambda: client)

    sub = Subagent(agent_id="sub-hist-1", role="researcher", task="find it")
    result = asyncio.run(sub.run())
    assert result.status == "ok"

    rec = subagent_history.get("sub-hist-1")
    assert rec is not None
    assert rec["status"] == "ok" and rec["report"] == "Final report text"
    assert rec["role"] == "researcher" and rec["model"] == "active-model-x"
    assert rec["duration_ms"] is not None and rec["duration_ms"] >= 0
    assert rec["tool_calls"][0]["tool"] == "web_search"
    assert isinstance(rec["tool_calls"][0]["ms"], int)
    # about 4 entries: user, assistant(tc), tool, assistant(final) — never an empty role
    roles = [t["role"] for t in rec["transcript"]]
    assert roles[0] == "user" and "tool" in roles
    assert all(roles) and "assistant" in roles


def test_run_timeout_pfad_erhält_error_record(active_model, monkeypatch, isolated_registry):
    class SlowClient:
        async def chat(self, **_):
            import asyncio as aio

            await aio.sleep(0.2)
            return _msg(content="never")

    monkeypatch.setattr("core.model_provider.build_provider_client", lambda: SlowClient())
    sub = Subagent(agent_id="sub-hist-2", role="r", task="t", timeout=0.01)
    result = asyncio.run(sub.run())

    rec = subagent_history.get("sub-hist-2")
    assert rec is not None
    assert rec["status"] == "timeout" and rec["duration_ms"] >= 0


def test_cancellation_finishes_the_record(active_model, monkeypatch, isolated_registry):
    """Given a helper the parent cancelled; Then its record stops claiming to run."""

    class HangingClient:
        async def chat(self, **_):
            await asyncio.sleep(30)
            return _msg(content="never")

    monkeypatch.setattr("core.model_provider.build_provider_client", lambda: HangingClient())
    sub = Subagent(agent_id="sub-hist-cancel", role="r", task="t", timeout=60)

    async def drive() -> None:
        task = asyncio.create_task(sub.run())
        for _ in range(200):
            if subagent_history.get("sub-hist-cancel") is not None:
                break
            await asyncio.sleep(0.005)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(drive())

    rec = subagent_history.get("sub-hist-cancel")
    assert rec is not None
    assert rec["status"] == "interrupted"


# 3. Persistence / restart

def test_finish_persistiert_und_neustart_lädt_snapshot(isolated_registry):
    subagent_history.begin("sub-p", role="r", task="t", description="d", model="m")
    subagent_history.finish("sub-p", status="ok", report="R", duration_ms=7, transcript=[])
    snapshot = isolated_registry / "subagent_history.json"
    assert snapshot.is_file()

    # Restart simulation: the in-process registry is empty, the file stays — both
    # access paths load the snapshot back lazily.
    subagent_history.reset_for_test()
    rec = subagent_history.summaries()["agents"]
    assert [s["agent_id"] for s in rec] == ["sub-p"]
    assert subagent_history.get("sub-p")["report"] == "R"


def test_a_snapshot_that_says_running_reloads_as_interrupted(isolated_registry):
    """Given a record persisted as running; Then the restart proves it was not.

    The file only outlives the process that wrote it, so a reloaded "running"
    record is a helper whose task died with that process. Read back as running it
    was shown as live work on the fleet board the next day.
    """
    snapshot = isolated_registry / "subagent_history.json"
    snapshot.write_text(
        json.dumps(
            [
                {
                    "agent_id": "subagent-ghost",
                    "role": "general-purpose",
                    "description": "",
                    "task": "",
                    "model": "",
                    "status": "running",
                    "started_ts": time.time() - 86400,
                    "finished_ts": None,
                    "duration_ms": None,
                    "report": "",
                    "tool_calls": [],
                    "transcript": [],
                }
            ]
        ),
        encoding="utf-8",
    )

    subagent_history.reset_for_test()
    out = subagent_history.summaries()["agents"]
    assert [s["agent_id"] for s in out] == ["subagent-ghost"]
    assert out[0]["status"] == "interrupted"


# 4. REST endpoints

def _client(tmp_path):
    from server.main import create_app

    return TestClient(create_app())


def test_rest_list_und_detail_404(isolated_registry):
    subagent_history.begin("sub-r", role="scout", task="t", description="d", model="m")
    subagent_history.finish("sub-r", status="ok", report="R!", duration_ms=3, transcript=[])

    with _client(isolated_registry) as client:
        lst = client.get("/api/subagents")
        assert lst.status_code == 200
        assert [a["agent_id"] for a in lst.json()["agents"]] == ["sub-r"]

        detail = client.get("/api/subagents/sub-r")
        assert detail.status_code == 200
        assert detail.json()["report"] == "R!"

        missing = client.get("/api/subagents/nope")
        assert missing.status_code == 404
