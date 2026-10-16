"""R30 — Session sync: PWA sessions mirrored to the server so FTS5 sees them.

The documented search gap: the browser kept sessions in IndexedDB only, so
GET /api/search could never find PWA conversation content. Sync closes it:
the client pushes sessions; the server mirrors them into the session store
under a `pwa-` namespace, which the existing mtime-driven FTS5 indexer picks
up automatically.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def stack(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Hermetic session store + search db; TestClient with lifespans."""
    import core.multi_session as ms

    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    monkeypatch.setattr(ms, "SESSIONS_DIR", sessions_dir)
    monkeypatch.setenv("EPHE_SEARCH_DB", str(tmp_path / "search.db"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma_db"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "user_profile.json"))
    import core.engine_config as engine_config

    monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path / "config")

    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as client:
        yield client, sessions_dir


def _payload() -> dict:
    return {
        "sessions": [
            {
                "id": "abc123",
                "title": "Kaffee-Rezepte",
                "messages": [
                    {"role": "user", "content": "Wie mach ich Cold Brew Kaffee genau?", "timestamp": 1},
                    {"role": "assistant", "content": "16 Stunden kalt extrahiert mit grobem Mahlgut.", "timestamp": 2},
                ],
            },
            {
                "id": "def456",
                "title": "Router Debug",
                "messages": [
                    {"role": "user", "content": "Der WLAN Repeater wirft packet loss auf port 5.", "timestamp": 1},
                ],
            },
        ]
    }


class TestSessionSyncRoute:
    def test_sync_writes_mirror_files(self, stack):
        client, sessions_dir = stack
        resp = client.post("/api/sessions/sync", json=_payload())
        assert resp.status_code == 200
        body = resp.json()
        assert body["stored_sessions"] == 2
        mirror = sessions_dir / "pwa-abc123.json"
        assert mirror.exists()
        data = json.loads(mirror.read_text(encoding="utf-8"))
        assert data[0]["content"].startswith("Wie mach ich Cold Brew")

    def test_synced_content_is_searchable(self, stack):
        client, _ = stack
        client.post("/api/sessions/sync", json=_payload())
        resp = client.get("/api/search?q=Mahlgut")
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert any("Mahlgut" in r["content"] for r in results)
        hit = next(r for r in results if "Mahlgut" in r["content"])
        assert hit["session_id"] == "pwa-abc123"
        assert hit["session_title"] == "Kaffee-Rezepte"

    def test_resync_is_idempotent(self, stack):
        client, _ = stack
        client.post("/api/sessions/sync", json=_payload())
        first = client.get("/api/search?q=Mahlgut").json()["total"]
        client.post("/api/sessions/sync", json=_payload())
        second = client.get("/api/search?q=Mahlgut").json()["total"]
        assert first == second == 1

    def test_deleted_sessions_leave_the_index(self, stack):
        client, sessions_dir = stack
        client.post("/api/sessions/sync", json=_payload())
        assert client.get("/api/search?q=Mahlgut").json()["total"] == 1
        resp = client.post("/api/sessions/sync", json={"sessions": [], "deleted": ["abc123"]})
        assert resp.status_code == 200
        assert not (sessions_dir / "pwa-abc123.json").exists()
        assert client.get("/api/search?q=Mahlgut").json()["total"] == 0
        # the untouched session survives
        assert client.get("/api/search?q=Repeater").json()["total"] == 1

    def test_oversized_batches_are_rejected(self, stack):
        client, _ = stack
        big = {"sessions": [{"id": f"s{i}", "title": "t", "messages": [{"role": "user", "content": "hallo welt"}]} for i in range(100)]}
        assert client.post("/api/sessions/sync", json=big).status_code == 413
        fat = {"sessions": [{"id": "x", "title": "t", "messages": [{"role": "user", "content": "x" * 100_000}]}]}
        assert client.post("/api/sessions/sync", json=fat).status_code == 413

    def test_path_traversal_in_ids_is_refused(self, stack):
        client, _ = stack
        evil = {"sessions": [{"id": "../../etc/passwd", "title": "t", "messages": [{"role": "user", "content": "hi"}]}]}
        resp = client.post("/api/sessions/sync", json=evil)
        assert resp.status_code == 200  # dropped, not stored
        assert resp.json()["stored_sessions"] == 0

    def test_mode_round_trips_through_the_mirror(self, stack):
        # P4: the composer mode has to survive the server mirror round trip, so a
        # fresh browser (empty IndexedDB) reconstructs the chosen mode
        # instead of falling back to 'ask'.
        client, _ = stack
        payload = {
            "sessions": [
                {
                    "id": "m0de1",
                    "title": "Modus-Test",
                    "mode": "full-access",
                    "messages": [{"role": "user", "content": "hi", "timestamp": 1}],
                }
            ]
        }
        assert client.post("/api/sessions/sync", json=payload).json()["stored_sessions"] == 1
        restored = client.get("/api/sessions/restore", params={"limit": 50}).json()["sessions"]
        m = next((s for s in restored if s["id"] == "m0de1"), None)
        assert m is not None
        assert m.get("mode") == "full-access"

    def test_parent_id_round_trips_through_the_mirror(self, stack):
        # Session tree (#9): a fork carries parentId. The mirror is the durable
        # per-device store — without parent_id in the round trip the tree comes
        # back flat after a reload (empty IndexedDB) and the fork chip
        # disappears.
        client, _ = stack
        payload = {
            "sessions": [
                {
                    "id": "parent1",
                    "title": "Mutter",
                    "messages": [{"role": "user", "content": "hi", "timestamp": 1}],
                },
                {
                    "id": "child1",
                    "title": "Mutter · #1",
                    "parent_id": "parent1",
                    "messages": [{"role": "user", "content": "hi", "timestamp": 1}],
                },
            ]
        }
        assert client.post("/api/sessions/sync", json=payload).json()["stored_sessions"] == 2
        restored = client.get("/api/sessions/restore", params={"limit": 50}).json()["sessions"]
        by_id = {s["id"]: s for s in restored}
        assert by_id["child1"].get("parent_id") == "parent1"
        # a session without a fork must get no parent_id field (no dirt)
        assert "parent_id" not in by_id["parent1"]

    def test_parent_id_reaches_registry_without_title_or_mode(self, stack):
        # The gate must trigger registration on parent_id alone: a fork inherits
        # the prefixed title, but a sync carrying only the parent_id field (e.g. a
        # read fix) may not be silently discarded.
        client, sessions_dir = stack
        payload = {
            "sessions": [
                {"id": "p", "title": "P", "messages": [{"role": "user", "content": "hi", "timestamp": 1}]},
                {"id": "c", "title": "", "parent_id": "p", "messages": []},
            ]
        }
        assert client.post("/api/sessions/sync", json=payload).json()["stored_sessions"] == 2
        reg = json.loads((sessions_dir / "registry.json").read_text(encoding="utf-8"))
        entry = next(e for e in reg["sessions"] if e["id"] == "pwa-c")
        assert entry.get("parent_id") == "p"

    def test_mode_none_when_omitted(self, stack):
        client, _ = stack
        payload = {"sessions": [{"id": "m0de2", "title": "T", "messages": [{"role": "user", "content": "hi", "timestamp": 1}]}]}
        client.post("/api/sessions/sync", json=payload)
        restored = client.get("/api/sessions/restore", params={"limit": 50}).json()["sessions"]
        m = next((s for s in restored if s["id"] == "m0de2"), None)
        assert m is not None and "mode" not in m

    def test_message_ids_are_mirrored(self, stack):
        # Measured 2026-10-13: 298 of 298 mirrored rows carried no id, so restore.ts keyed
        # its virtual list with `undefined`. The mirror now writes the reader's id.
        client, sessions_dir = stack
        assert client.post("/api/sessions/sync", json=_payload()).json()["stored_sessions"] == 2
        rows = json.loads((sessions_dir / "pwa-abc123.json").read_text(encoding="utf-8"))
        assert [r["id"] for r in rows] == ["restored:abc123:0:1", "restored:abc123:1:2"]

    def test_client_sent_message_id_is_preserved(self, stack):
        client, sessions_dir = stack
        payload = {
            "sessions": [
                {
                    "id": "keep1",
                    "title": "T",
                    "messages": [
                        {"role": "user", "content": "hi", "timestamp": 5, "id": "client-uuid-1"}
                    ],
                }
            ]
        }
        assert client.post("/api/sessions/sync", json=payload).json()["stored_sessions"] == 1
        rows = json.loads((sessions_dir / "pwa-keep1.json").read_text(encoding="utf-8"))
        assert rows[0]["id"] == "client-uuid-1"

    def test_restore_carries_the_message_ids(self, stack):
        # The consumer the id exists for: restore-on-empty serves the very rows the PWA
        # keys its virtual list with, so each carries an id before restore.ts sees it.
        client, _ = stack
        client.post("/api/sessions/sync", json=_payload())
        restored = client.get("/api/sessions/restore").json()["sessions"]
        sess = next(s for s in restored if s["id"] == "abc123")
        assert all(isinstance(m.get("id"), str) and m["id"] for m in sess["messages"])
