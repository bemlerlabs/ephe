"""D4a: Kepta-Bridge — a provider that lives inside a running Kepta.

Ephe's own memory is local (Chroma | Kepta-Core). But whoever already runs a
Kepta instance — shared across several agents, with its own UI — should be able
to attach Ephe to it instead of fattening a second brain. The bridge is
therefore a provider like the others: same contract, same scope column,
same extras as wave D5.

What the bridge is NOT: a silent third default. It only takes effect for whoever
chooses it explicitly by name and URL; without a URL a fail-closed applies that states
what is missing — no guessing `localhost`, no falling back to the local brain.
"""
from __future__ import annotations

import pytest

from core.memory_kepta_bridge import KeptaBridgeProvider, bridge_url_from_env


class FakeKepta:
    """Fake instance: records requests and returns the API answers of server.ts."""

    def __init__(self):
        self.calls: list[tuple[str, str, dict | None]] = []
        self.records: dict[str, dict] = {}
        self._seq = 0
        self.storage_info = {"dbPath": "/tmp/kepta.db", "count": 2, "trashed": 1, "embeddings": {}}

    def __call__(self, method: str, path: str, body=None, params=None):
        url = path + ("?" + "&".join(f"{k}={v}" for k, v in (params or {}).items()) if params else "")
        self.calls.append((method, url, body))
        if path == "/api/memories" and method == "POST":
            self._seq += 1
            rec = {"id": f"m{self._seq}", "userId": "local", "deletedAt": None, **body}
            rec.setdefault("title", "")
            rec.setdefault("content", "")
            if body.get("id"):  # patch path of the single create/update route
                self.records[body["id"]].update({k: v for k, v in body.items() if k != "id"})
                return {"memory": self.records[body["id"]]}
            self.records[rec["id"]] = rec
            return {"memory": rec}
        if path == "/api/memories" and method == "GET":
            trashed = (params or {}).get("trash") == "1"
            return [r for r in self.records.values() if bool(r.get("deletedAt")) == trashed]
        if path == "/api/memories/search":
            q = (params or {}).get("q", "")
            hits = [r for r in self.records.values() if q.lower() in str(r.get("content", "")).lower()]
            return {"query": q, "count": len(hits), "total": len(hits), "memories": hits}
        if path.startswith("/api/memories/") and path.endswith("/restore") and method == "POST":
            rid = path.split("/")[3]
            if rid not in self.records or not self.records[rid].get("deletedAt"):
                return None  # 404
            self.records[rid]["deletedAt"] = None
            return {"ok": True, "memory": self.records[rid]}
        if path.startswith("/api/memories/") and method == "DELETE":
            rid = path.split("/")[3]
            if rid in self.records:
                self.records[rid]["deletedAt"] = 1_790_000_000
                return {"ok": True, "permanent": False}
            return {"ok": False, "permanent": False}
        if path == "/api/storage-info":
            return self.storage_info
        raise AssertionError(f"unerwarteter Request: {method} {url}")


@pytest.fixture
def kepta():
    return FakeKepta()


@pytest.fixture
def bridge(kepta):
    return KeptaBridgeProvider("http://memory.internal:3000", scope="ws-42", transport=kepta)


class TestKeinStillerDefault:
    def test_without_url_there_is_no_bridge_and_it_says_so(self, monkeypatch):
        monkeypatch.delenv("EPHE_MEMORY_KEPTA_URL", raising=False)
        assert bridge_url_from_env() is None
        with pytest.raises(RuntimeError) as exc:
            KeptaBridgeProvider(None, scope="ws-42")
        assert "EPHE_MEMORY_KEPTA_URL" in str(exc.value)

    def test_every_read_and_write_carries_the_scope(self, bridge, kepta):
        bridge.store("Der Deploy-Server läuft auf Port 8765")
        assert kepta.calls[0][2]["scope"] == "ws-42"


class TestSchreiben:
    def test_store_sends_content_type_tags_and_returns_the_remote_id(self, bridge, kepta):
        new_id = bridge.store(
            "Regel: vor jedem Refactor die Tests laufen lassen",
            {"source": "agent"},
            memory_type="procedural",
            tags=["workflow"],
            confidence=0.9,
        )
        method, url, body = kepta.calls[0]
        assert (method, url) == ("POST", "/api/memories")
        assert body["content"].startswith("Regel:")
        assert body["type"] == "procedural"
        assert body["tags"] == ["workflow"]
        assert body["confidence"] == 0.9
        assert new_id == "m1"

    def test_supersede_creates_the_correction_and_marks_the_old_fact(self, bridge, kepta):
        bridge.store("Der API-Gateway läuft auf Port 8765")
        new_id = bridge.supersede("m1", "Der API-Gateway läuft auf Port 9100")
        assert new_id == "m2"
        assert kepta.calls[-1][2] == {"id": "m1", "supersededBy": "m2"}

    def test_update_patches_in_place_under_the_same_id(self, bridge, kepta):
        bridge.store("Tippfehler mit deppfehler")
        out = bridge.update("m1", "Tippfehler mit Fehler")
        assert kepta.calls[-1][2]["id"] == "m1"
        assert "deppfehler" not in kepta.records["m1"]["content"]
        assert out is True or out == "m1"


class TestLesen:
    def test_search_returns_real_document_ids(self, bridge, kepta):
        bridge.store("Der Deploy-Server läuft auf Port 8765")
        hits = bridge.search("Port")
        assert hits[0]["id"] == "m1"
        assert "8765" in hits[0]["text"]
        assert hits[0]["score"] > 0

    def test_list_and_trash_read_the_two_faces_of_the_same_route(self, bridge, kepta):
        bridge.store("Aktiver Fakt")
        bridge.store("Weggeworfener Fakt")
        bridge.delete("m2")
        assert [e["text"] for e in bridge.list_all()] == ["Aktiver Fakt"]
        deleted = bridge.list_deleted()
        assert [e["id"] for e in deleted] == ["m2"]
        # D5 contract: `deleted_at` lives in the metadata so the UI can state the moment.
        assert deleted[0]["metadata"]["deleted_at"] == 1_790_000_000

    def test_restore_brings_the_entry_back(self, bridge, kepta):
        bridge.store("Weggeworfener Fakt")
        bridge.delete("m1")
        bridge.restore("m1")
        assert kepta.records["m1"]["deletedAt"] is None
        assert [e["id"] for e in bridge.list_all()] == ["m1"]

    def test_restoring_something_that_is_not_deleted_is_a_key_error(self, bridge):
        with pytest.raises(KeyError):
            bridge.restore("m404")

    def test_stats_and_count_come_from_the_storage_route(self, bridge, kepta):
        assert bridge.count() == 2
        assert bridge.stats()["deleted"] == 1
        assert bridge.name == "kepta-bridge"


class TestGrenzen:
    def test_clearing_a_shared_brain_is_refused_not_faked(self, bridge):
        # "Memory leeren" on a shared instance is an instruction to everyone —
        # there is no route for it, and a silent no-op would be the lie.
        with pytest.raises(RuntimeError) as exc:
            bridge.clear()
        assert "clear" in str(exc.value).lower()

    def test_an_unreachable_instance_fails_closed_with_a_hint(self, kepta):
        def down(*_a, **_k):
            raise OSError("connection refused")

        b = KeptaBridgeProvider("http://memory.internal:3000", scope="ws-42", transport=down)
        with pytest.raises(RuntimeError) as exc:
            b.list_all()
        assert "memory.internal:3000" in str(exc.value)

    def test_close_is_not_a_leak(self, bridge):
        assert bridge.close() is None


class TestAuswahl:
    def test_the_bridge_is_never_the_recognized_default(self, monkeypatch):
        from core.memory_provider import KEPTA, resolve_provider

        monkeypatch.delenv("EPHE_MEMORY_PROVIDER", raising=False)
        monkeypatch.delenv("EPHE_MEMORY_KEPTA_URL", raising=False)
        provider, _reason = resolve_provider(record=None)
        assert provider != "kepta-bridge"
        assert provider in {KEPTA, "chroma"}

    def test_env_picks_it_when_named_explicitly(self, monkeypatch):
        from core.memory_provider import resolve_provider

        monkeypatch.setenv("EPHE_MEMORY_PROVIDER", "kepta-bridge")
        monkeypatch.setenv("EPHE_MEMORY_KEPTA_URL", "http://memory.internal:3000")
        assert resolve_provider(record={})[0] == "kepta-bridge"

    def test_opening_through_the_factory_wires_the_url_from_env(self, monkeypatch):
        from core import memory_provider

        monkeypatch.setenv("EPHE_MEMORY_KEPTA_URL", "http://memory.internal:3000")
        provider = memory_provider.open_provider("kepta-bridge", scope="ws-42")
        assert provider.name == "kepta-bridge"
