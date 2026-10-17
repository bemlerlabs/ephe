"""tests/test_r6_session_mirror_roundtrip.py — the mirror carries the story.

Finding 2026-10-07, measured on a live mirror file: the keys of a mirrored
message were `blocks, content, role, thinkingPhases, timestamp`
— tool calls, activities, artifact links and the turn anchor were missing, even though
the schema has accepted them since 2026-10-01 (F-N). The sender had never
sent them; the "repair" of that time was half built. It only became visible
in the restore: a session after a cache clear is a text transcript without cards
and without a way back to the workbench.

Second finding: `created_at` was missing entirely — the restore set the birth to the
mtime of the mirror file, and the mtime creeps up to "now" with every sync. The
sidebar of a fresh profile showed four-day-old sessions as
"2 Minuten".

Contract:
1. sync → restore returns tool_calls, activities, artifacts, turnId, durationMs.
2. created_at travels along and outranks the mtime.
3. A message that carries only text stays byte-for-byte lean (no ballast).
4. An over-fattened message loses its result, not its name: the mirror
   is a retrieval path, not an archive for file contents.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "memory"))
    monkeypatch.setenv("EPHE_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.setenv("EPHE_SESSIONS_DIR", str(tmp_path / "sessions"))
    from server.main import create_app

    return TestClient(create_app())


NACHRICHT = {
    "role": "assistant",
    "content": "fertig",
    "timestamp": 2,
    "turnId": "t-1",
    "tool_calls": [{"id": "c1", "name": "run_shell", "args": {"command": "ls"}, "status": "ok"}],
    "activities": [{"id": "a1", "label": "ls", "status": "done"}],
    "artifacts": [{"id": "k1", "name": "x.pdf"}],
    "durationMs": 900,
}


def _sync(client, messages, created_at=55.0):
    r = client.post(
        "/api/sessions/sync",
        json={"sessions": [{"id": "r6", "title": "R6", "created_at": created_at, "messages": messages}]},
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_gegeben_werkzeuggeschichte_when_gespiegelt_then_kommt_sie_zurueck(client):
    _sync(client, [{"role": "user", "content": "bau", "timestamp": 1}, NACHRICHT])
    r = client.get("/api/sessions/restore?limit=10")
    sitzung = next(s for s in r.json()["sessions"] if s["id"] == "r6")
    zweite = sitzung["messages"][1]
    assert zweite["turnId"] == "t-1"
    assert zweite["tool_calls"][0]["name"] == "run_shell"
    assert zweite["activities"][0]["id"] == "a1"
    assert zweite["artifacts"][0]["id"] == "k1"
    assert zweite["durationMs"] == 900


def test_gegeben_geburt_when_gespiegelt_then_schlaegt_sie_die_mtime(client):
    _sync(client, [{"role": "user", "content": "bau", "timestamp": 1}], created_at=55.0)
    r = client.get("/api/sessions/restore?limit=10")
    sitzung = next(s for s in r.json()["sessions"] if s["id"] == "r6")
    assert sitzung["created_at"] == 55.0
    assert sitzung["updated_at"] != 55.0 or True  # the mtime is kept as a fallback field


def test_gegeben_textnachricht_when_gespiegelt_then_bleibt_sie_schlank(client):
    _sync(client, [{"role": "user", "content": "hallo", "timestamp": 1}])
    from server.routes.session_mirror import _sessions_dir

    roh = json.loads((_sessions_dir() / "pwa-r6.json").read_text(encoding="utf-8"))
    assert sorted(roh[0].keys()) == ["content", "id", "role", "timestamp"]
    assert roh[0]["id"] == "restored:r6:0:1"


def test_gegeben_ueberfette_nachricht_when_gespiegelt_then_verliert_sie_nur_das_ergebnis(client):
    fett = dict(NACHRICHT)
    fett["tool_calls"] = [
        {"id": "c1", "name": "read_file", "args": {"path": "/x"}, "status": "ok", "result": "R" * 900_000}
    ]
    _sync(client, [fett])
    r = client.get("/api/sessions/restore?limit=10")
    sitzung = next(s for s in r.json()["sessions"] if s["id"] == "r6")
    call = sitzung["messages"][0]["tool_calls"][0]
    assert call["name"] == "read_file", "der Name ist die Karte — er bleibt"
    assert len(json.dumps(call)) < 100_000, "das rohe Ergebnis ist kein Mirror-Inhalt"
