"""S20/C1: one content-free line says how a stream ended.

The 18:38 turn proved the client can lose a stream without the server learning
why. These tests pin the transport line the route now writes on every close:
the six fields the diagnosis needs, none of the turn's content, and no effect on
the five-phase projection the surface reads.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

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


def _rows(cfg: Path) -> list[dict]:
    runs = sorted((cfg / "run").glob("*.jsonl"))
    assert runs, "no ledger file for the turn"
    return ledger.read_run(runs[-1].stem)


def test_the_close_line_carries_the_six_fields_and_no_content(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    ledger.start("run-close")
    ledger.record_stream_close(
        close_code="client_gone",
        last_frame_type="tool_start",
        elapsed_ms=111_600,
        last_heartbeat_ms=4_200,
        provider="openai_compatible",
        cancelled=True,
    )

    rows = ledger.read_run("run-close")
    close = next(r for r in rows if r["kind"] == "stream_closed")
    assert close["close_code"] == "client_gone"
    assert close["last_frame_type"] == "tool_start"
    assert close["elapsed_ms"] == 111_600
    assert close["last_heartbeat_ms"] == 4_200
    assert close["provider"] == "openai_compatible"
    assert close["cancelled"] is True
    assert "msg" not in close and "text" not in close and "data" not in close


def test_the_transport_line_stays_out_of_the_phase_projection(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    ledger.start("run-projection")
    ledger.finish("complete")
    ledger.record_stream_close(
        close_code="stream_end",
        last_frame_type="done",
        elapsed_ms=1_000,
        last_heartbeat_ms=500,
        provider="local_ollama",
        cancelled=False,
    )

    snap = ledger.snapshot("run-projection")
    assert snap["phases"]["Next"]["kind"] == "run_finished", snap
    assert snap["phases"]["Next"]["finish_reason"] == "complete", snap


def test_a_completed_stream_writes_one_stream_end_line(client, tmp_path):
    async def answer(**kwargs):
        kwargs["on_token"]("the answer")
        return "the answer"

    with patch("server.routes.chat.chat_with_tools", new=AsyncMock(side_effect=answer)):
        with patch(
            "server.routes.chat.reflect",
            new=AsyncMock(return_value=MagicMock(needs_revision=False, reason="ok")),
        ):
            response = client.post(
                "/api/chat/stream",
                json={"model": "gemma4:12b", "history": [], "message": "PROMPT-SENTINEL-41b2"},
            )
    assert response.status_code == 200

    rows = _rows(tmp_path / "cfg")
    closes = [r for r in rows if r["kind"] == "stream_closed"]
    assert len(closes) == 1, closes
    close = closes[0]
    assert close["close_code"] == "stream_end", close
    assert close["cancelled"] is False, close
    assert close["provider"], close
    assert "PROMPT-SENTINEL-41b2" not in json.dumps(close)
