"""R44 (P2): the session-sync mirror carries the turn chronology.

The PWA sends blocks/thinkingPhases along; the pwa-<id> JSON in the session file
has to carry the same fields so that a later deep-load (context assembler,
export) can reconstruct the order of the tool/thinking lines — the FTS index
itself stays on role/content (the proven index shape).
"""
from __future__ import annotations

import json

import pytest

from server.routes.session_mirror import SessionSyncRequest, sync_sessions


def _payload(tmp_path):
    return json.loads((tmp_path / "pwa-s1.json").read_text(encoding="utf-8"))


async def test_sync_mirrors_chronology(tmp_path, monkeypatch):
    import core.multi_session as ms

    monkeypatch.setattr(ms, "SESSIONS_DIR", tmp_path)
    req = SessionSyncRequest.model_validate({
        "sessions": [{
            "id": "s1",
            "title": "Takt",
            "messages": [{
                "role": "assistant",
                "content": "Antwort",
                "timestamp": 1,
                "blocks": [
                    {"kind": "thinking", "index": 0},
                    {"kind": "tool", "callId": "c1"},
                    {"kind": "text", "text": "Antwort"},
                ],
                "thinkingPhases": [{"start": 1, "end": 2, "text": "P"}],
            }],
        }],
        "deleted": [],
    })
    res = await sync_sessions(req)
    assert res["stored_sessions"] == 1
    rows = _payload(tmp_path)
    assert rows[0]["blocks"][0]["kind"] == "thinking"
    assert rows[0]["thinkingPhases"][0]["text"] == "P"


async def test_sync_legacy_without_chronology_unchanged(tmp_path, monkeypatch):
    import core.multi_session as ms

    monkeypatch.setattr(ms, "SESSIONS_DIR", tmp_path)
    req = SessionSyncRequest.model_validate({
        "sessions": [{
            "id": "s1",
            "title": "Legacy",
            "messages": [{"role": "user", "content": "Frage", "timestamp": 2}],
        }],
        "deleted": [],
    })
    await sync_sessions(req)
    rows = _payload(tmp_path)
    assert set(rows[0].keys()) == {"role", "content", "timestamp", "id"}
    assert rows[0]["id"] == "restored:s1:0:2"


async def test_load_messages_passes_chronology(tmp_path, monkeypatch):
    import core.multi_session as ms

    monkeypatch.setattr(ms, "SESSIONS_DIR", tmp_path)
    (tmp_path / "s3.json").write_text(json.dumps([{
        "role": "assistant",
        "content": "A",
        "timestamp": 3,
        "blocks": [{"kind": "text", "text": "A"}],
        "thinkingPhases": [{"start": 1, "end": 2, "text": "P"}],
    }]), encoding="utf-8")
    msgs = ms.load_messages("s3")
    assert msgs[0]["blocks"][0]["kind"] == "text"
    assert msgs[0]["thinkingPhases"][0]["end"] == 2
    # Legacy rows without a chronology stay 3-field (no index drift)
    (tmp_path / "s4.json").write_text(json.dumps([{
        "role": "user", "content": "F", "timestamp": 4,
    }]), encoding="utf-8")
    legacy = ms.load_messages("s4")
    assert "blocks" not in legacy[0]


async def test_sync_mirrors_activities_artifacts_duration(tmp_path, monkeypatch):
    """Finding 2026-10-01 (F-N): activities/artifacts/durationMs/thinking/error
    must not silently drop on the mirror roundtrip — after a restore without
    IndexedDB the replay bar and the deliverable line were simply gone."""
    import core.multi_session as ms

    monkeypatch.setattr(ms, "SESSIONS_DIR", tmp_path)
    req = SessionSyncRequest.model_validate({
        "sessions": [{
            "id": "s-fn",
            "title": "Deliverables",
            "messages": [{
                "role": "assistant",
                "content": "Fertig",
                "timestamp": 3,
                "thinking": {"start": 1, "end": 2},
                "durationMs": 20000,
                "activities": [{"kind": "tool", "name": "write", "status": "done"}],
                "artifacts": [{"id": "a1", "filename": "document.md", "title": "Liste"}],
                "turnId": "t-42",
                "error": None,
            }],
        }],
        "deleted": [],
    })
    res = await sync_sessions(req)
    assert res["stored_sessions"] == 1
    rows = json.loads((tmp_path / "pwa-s-fn.json").read_text(encoding="utf-8"))
    assert rows[0]["activities"][0]["name"] == "write"
    assert rows[0]["artifacts"][0]["filename"] == "document.md"
    assert rows[0]["durationMs"] == 20000
    assert rows[0]["thinking"]["end"] == 2
    # R4 (A3): the same class of break for the turn id. Without it the
    # backwards link workbench → job dead-ends after a restore without IndexedDB.
    assert rows[0]["turnId"] == "t-42"
