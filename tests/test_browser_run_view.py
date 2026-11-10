"""The watchable run: a frame names its audit row, and a hold is read before the next act.

A picture with no row is unproven. A hand-back is the next tool result, so the
action the model asked for does not run. The act route answers with a mode and
carries no frame.
"""
from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    from core.browser_run_view import reset_run_view

    reset_run_view()
    monkeypatch.setattr("core.browser_run_view._HOLD_BUDGET_S", 0.2)
    yield
    reset_run_view()


def test_a_frame_with_no_row_carries_a_null_audit():
    from core.browser_run_view import frame_audit

    assert frame_audit("default") == {"audit": None}


def test_a_browser_exec_row_is_what_the_frame_may_name():
    from core.audit_log import audit_event
    from core.browser_run_view import public_binding, stamp_browser_exec

    detail = (
        'STEP_EVIDENCE:{"step":"browser_go","verdict":"observed","url":"https://example.com/",'
        '"title":"Example","delta":{"url_changed":1,"nodes":2}}'
    )
    arguments = {"url": "https://example.com/"}
    audit_event(
        "tool_exec",
        tool="browser_go",
        args=arguments,
        status="ok",
        decision="ok",
        detail=detail,
    )
    stamp_browser_exec("browser_go", arguments, detail)
    binding = public_binding("default")
    assert binding is not None
    assert binding["kind"] == "tool_exec"
    assert binding["tool"] == "browser_go"
    assert binding["verdict"] == "observed"
    assert binding["delta"] == {"url_changed": 1, "nodes": 2}
    assert binding["ts"]
    assert "args" not in binding


def test_a_tool_with_no_page_does_not_bind_a_frame():
    from core.audit_log import audit_event
    from core.browser_run_view import public_binding, stamp_browser_exec

    audit_event("tool_exec", tool="web_search", args={"query": "ephe"}, status="ok", detail="hits")
    stamp_browser_exec("web_search", {"query": "ephe"}, "hits")
    assert public_binding("default") is None


def test_parse_act_refuses_a_page_field_and_a_bool_coordinate():
    from core.browser_run_view import parse_act

    with pytest.raises(ValueError):
        parse_act({"kind": "click", "x": 1, "y": 2, "url": "https://example.com/"})
    with pytest.raises(ValueError):
        parse_act({"kind": "click", "x": True, "y": 2})
    assert parse_act({"kind": "press", "key": "Enter"}) == {"kind": "press", "key": "Enter"}


@pytest.mark.asyncio
async def test_pause_holds_the_action_until_resume():
    from core.browser_run_view import gate_action, pause, resume

    assert pause("s")
    pending = asyncio.create_task(gate_action("s"))
    await asyncio.sleep(0.05)
    assert pending.done() is False
    assert resume("s")
    assert await pending is None


@pytest.mark.asyncio
async def test_a_handback_note_is_the_action_result():
    from core.browser_run_view import finish_takeover, gate_action

    finish_takeover("s", "STEP_EVIDENCE:held")
    assert await gate_action("s") == "STEP_EVIDENCE:held"
    assert await gate_action("s") is None


@pytest.mark.asyncio
async def test_the_next_tool_returns_the_note_and_does_not_run(monkeypatch):
    from core.browser_run_view import finish_takeover
    from core.tools import registry

    finish_takeover("default", "STEP_EVIDENCE:held")
    called = {"ran": False}

    async def _fake(**_kwargs):
        called["ran"] = True
        return "ran"

    monkeypatch.setitem(registry.TOOL_MAP, "browser_go", _fake)
    result = await registry._execute_tool_core("browser_go", {"url": "https://example.com/"})
    assert result == "STEP_EVIDENCE:held"
    assert called["ran"] is False


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    from server.main import create_app

    return create_app()


class _Manager:
    def __init__(self) -> None:
        self.sessions = {"run-1"}
        self.acted: list[dict] = []

    def has_session(self, session: str) -> bool:
        return session in self.sessions

    async def read_signature(self, session: str) -> dict:
        return {"url": "https://example.com/", "nodes": 1}

    async def reconcile_hold(self, session: str, before: dict | None) -> str:
        return (
            'STEP_EVIDENCE:{"step":"user_hold","verdict":"observed","url":"https://example.com/",'
            '"title":"Example","delta":{"url_changed":1}}'
        )

    async def apply_user_act(self, session: str, act: dict) -> None:
        self.acted.append(act)


def test_hold_and_act_stay_on_the_machine_and_name_the_row(app, monkeypatch):
    manager = _Manager()
    monkeypatch.setattr("core.browser.browser_manager", manager)
    client = TestClient(app)

    missing = client.post("/api/browser/watch/ghost/hold", json={"action": "pause"})
    assert missing.status_code == 404
    assert missing.json()["error"]["reason_code"] == "browser_session_unknown"

    paused = client.post("/api/browser/watch/run-1/hold", json={"action": "pause"})
    assert paused.status_code == 200
    assert paused.json() == {"session": "run-1", "mode": "paused"}
    assert "jpeg" not in paused.text

    taken = client.post("/api/browser/watch/run-1/hold", json={"action": "takeover"})
    assert taken.status_code == 200
    assert taken.json()["mode"] == "takeover"

    acted = client.post("/api/browser/watch/run-1/act", json={"kind": "click", "x": 10, "y": 12})
    assert acted.status_code == 200
    assert acted.json() == {"session": "run-1", "acted": "click"}
    assert manager.acted == [{"kind": "click", "x": 10, "y": 12}]
    assert "jpeg" not in acted.text

    back = client.post("/api/browser/watch/run-1/hold", json={"action": "handback"})
    body = back.json()
    assert back.status_code == 200
    assert body["mode"] == "running"
    evidence = json.loads(body["evidence"].split("STEP_EVIDENCE:", 1)[1])
    assert evidence["verdict"] == "observed"
    assert "jpeg" not in back.text

    from core.browser_run_view import public_binding

    binding = public_binding("run-1")
    assert binding is not None
    assert binding["tool"] == "user_hold"
    assert binding["verdict"] == "observed"


def test_an_act_outside_takeover_is_refused(app, monkeypatch):
    monkeypatch.setattr("core.browser.browser_manager", _Manager())
    response = TestClient(app).post(
        "/api/browser/watch/run-1/act",
        json={"kind": "click", "x": 1, "y": 1},
    )
    assert response.status_code == 400
    assert response.json()["error"]["reason_code"] == "invalid_request"


def test_the_watch_route_does_not_open_an_outbound_client():
    import inspect

    import server.routes.browser_watch as watch

    source = inspect.getsource(watch)
    assert "httpx" not in source
    assert "urllib" not in source
