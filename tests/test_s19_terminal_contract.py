"""S19: a failed turn ends with one coded frame and one ledger terminal line.

Given/When/Then. The 18:38 turn carried a producer that finished after a tool
result while the client lost the last frames; the ledger then held two terminal
lines, `run_finished cancelled` and `done complete`. These tests pin the two
contracts the route owes the surface:

* a failure after a tool result reaches the client as exactly one `error` frame
  with a `reason_code`, followed by `done`;
* the ledger closes once, and its terminal line names the failure.

No network: the tool loop and the reflection pass are replaced.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from core.chat_stream import OllamaNotReachableError
from core.run import ledger


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma_db"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "user_profile.json"))
    monkeypatch.setenv("EPHE_CORRECTIONS_PATH", str(tmp_path / "corrections.md"))
    monkeypatch.setenv("EPHE_FEEDBACK_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_SKILLS_DIR", str(tmp_path / "skills"))
    from server.main import create_app

    return TestClient(create_app())


def _sse(client: TestClient, body: dict) -> list[dict]:
    with patch(
        "server.routes.chat.reflect",
        new=AsyncMock(return_value=MagicMock(needs_revision=False, reason="ok")),
    ):
        with client.stream(
            "POST", "/api/chat/stream", json={"model": "gemma4:12b", "history": [], **body}
        ) as response:
            assert response.status_code == 200
            text = "".join(response.iter_text())
    events: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            events.append(json.loads(line[5:].strip()))
    return events


class TestTheStreamContract:
    def test_a_provider_failure_after_a_tool_result_ends_with_one_coded_frame(self, client):
        async def failing_loop(**kwargs):
            kwargs["on_tool_start"]("web_search", {"query": "probe"}, "c-1")
            kwargs["on_tool_done"]("web_search", "[1] a result", "c-1")
            raise OllamaNotReachableError()

        with patch("server.routes.chat.chat_with_tools", new=AsyncMock(side_effect=failing_loop)):
            events = _sse(client, {"message": "look this up"})

        errors = [e for e in events if e.get("type") == "error"]
        assert len(errors) == 1, events
        # No code without a renderable sentence (test_stream_4xx_provider_body).
        assert "reason_code" not in errors[0], errors[0]
        assert events[-1].get("type") == "done", events[-1]

        runs = sorted((tmp_run_dir := __import__("pathlib").Path(__import__("os").environ["EPHE_CONFIG_DIR"]) / "run").glob("*.jsonl"))
        assert runs, "no ledger file for the turn"
        rows = ledger.read_run(runs[-1].stem)
        terminal = [r for r in rows if r["kind"] in ("done", "run_finished")]
        assert len(terminal) == 1, terminal
        assert terminal[0]["finish_reason"] == "error", terminal[0]


class TestTheLedgerContract:
    def test_a_cancelled_run_keeps_one_terminal_line(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        ledger.start("run-cancel")
        ledger.finish("cancelled")
        # The producer keeps going and emits its own done after the disconnect.
        ledger.record_event({"type": "done"})
        ledger.finish("complete")

        rows = ledger.read_run("run-cancel")
        terminals = [r for r in rows if r["kind"] in ("done", "run_finished")]
        assert [t["finish_reason"] for t in terminals] == ["cancelled"], terminals

    def test_an_error_frame_makes_the_terminal_line_an_error(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        ledger.start("run-error")
        ledger.record_event(
            {"type": "error", "reason_code": "engine_unreachable", "msg": "provider went away"}
        )
        ledger.record_event({"type": "done"})

        rows = ledger.read_run("run-error")
        done = next(r for r in rows if r["kind"] == "done")
        assert done["finish_reason"] == "error", done
        assert done["failure_class"] == "engine_unreachable", done
