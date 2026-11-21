"""W8 — the engine's return value is an answer, not a leftover.

Two paths, both measured on the same turn: (1) a tool run without a closing sentence
was waved through as a success by the exemption "tools count as content",
(2) `_emit_final_answer` hands back the text as its return value without streaming it
— the value was thrown away and the surface stayed empty.

Here the real route runs against an engine that only returns.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    import server.routes.chat as chat_route
    from server.main import create_app

    monkeypatch.setattr(chat_route, "_ensure_engine_ready", lambda *a, **k: None)
    return TestClient(create_app())


def _sse(body: str) -> list[dict]:
    out = []
    for line in body.splitlines():
        if line.startswith("data: "):
            try:
                out.append(json.loads(line[6:]))
            except json.JSONDecodeError:
                continue
    return out


def _stub_engine(monkeypatch, *, chunks, returned):
    import server.routes.chat as chat_route

    async def fake(**kwargs):
        on_chunk = kwargs.get("on_chunk")
        for chunk in chunks:
            if on_chunk:
                on_chunk(chunk)
        return returned

    monkeypatch.setattr(chat_route, "chat_with_tools", fake)


def test_given_engine_that_only_returns_then_the_answer_reaches_the_stream(client, monkeypatch):
    _stub_engine(monkeypatch, chunks=[], returned="Fertig. Drei Dateien liegen in der Werkbank.")
    response = client.post(
        "/api/chat/stream",
        json={"message": "Mach drei Dateien", "session_id": "w8", "model": "stub"},
    )
    assert response.status_code == 200, response.text
    events = _sse(response.text)
    joined = "".join(str(e.get("data", "")) for e in events if e.get("type") == "chunk")
    assert "Drei Dateien" in joined, "der Rückgabewert versickert weiter"
    assert not [e for e in events if e.get("type") == "error"], "ein Turn mit Inhalt ist nicht stumm"


def test_given_tool_run_without_final_answer_then_the_honest_frame_names_it(client, monkeypatch):
    import server.routes.chat as chat_route

    async def fake(**kwargs):
        on_tool_done = kwargs.get("on_tool_done")
        if on_tool_done:
            on_tool_done("create_pdf", "ok")
        return ""

    monkeypatch.setattr(chat_route, "chat_with_tools", fake)
    response = client.post(
        "/api/chat/stream",
        json={"message": "Mach eine Datei", "session_id": "w8b", "model": "stub"},
    )
    assert response.status_code == 200, response.text
    errors = [e for e in _sse(response.text) if e.get("type") == "error"]
    assert errors, "ein Lauf ohne Schlusswort darf kein Erfolg sein"
    assert "Werkzeug" in errors[0]["msg"] or "Werkbank" in errors[0]["msg"]
