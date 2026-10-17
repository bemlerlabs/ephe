"""Wave 10 (H4) — the memory store's three measured defects, pinned.

The walkthrough of 2026-10-12 drove the running product and found three defects
in the memory surface (``docs/media/user-walkthrough-2026-10-12/FINDINGS.md``,
§ high, plus the memory page's own notes):

1. **The trash could never fill and its restore was dead UI.** `DELETE
   /api/memory/{id}` answered 200 and the entry was gone for good: `GET
   /api/memory/deleted` and `stats.deleted` stayed 0 under Chroma, while the
   page promised "this is where what Ephe forgot ends up" and offered a restore
   that had nothing to call.
2. **One chat turn stored the same fact twice.** The server's own Q/A capture
   (`source: auto_memory`) plus the model's `memory` tool call
   (`source: agent`) both landed; the twin carried no origin label, because the
   page's label map had no key for it (32 rows, 29 chips).
3. **The capture gate was invisible and rejected short answers.** A two-token
   reply after "Remember this fact: …" was refused by the answer floor while the
   assistant confirmed keeping the fact — a save that never happened.

Each test below fails without the fix it pins.
"""

from __future__ import annotations

import pytest


# Memory stores exercised below.

@pytest.fixture()
def kepta_client(tmp_path, monkeypatch):
    """Kepta as the brain: the store that *does* keep a deleted entry."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_MEMORY_PROVIDER", "kepta")
    monkeypatch.setenv("EPHE_MEMORY_EMBEDDER", "none")
    yield from _client()


@pytest.fixture()
def final_delete_client(tmp_path, monkeypatch):
    """A store whose deletes are final, with the route left intact.

    The walkthrough ran on the retired store, which deleted finally. That backend
    left the product on 2026-10-14, but the rule it exposed is a property of the
    *route* — the route must never offer a restore the active store cannot deliver.
    Whether a store keeps a trash is a capability, so the capability and
    the two facade calls behind it are what this fixture removes.
    """
    import server.routes.memory as memory_routes
    from core.memory import Memory

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_MEMORY_PROVIDER", "kepta")
    monkeypatch.setenv("EPHE_MEMORY_EMBEDDER", "none")
    monkeypatch.setattr(memory_routes, "_TRASH_PROVIDERS", frozenset())
    monkeypatch.setattr(Memory, "list_deleted", lambda self, limit=100: [])

    def _gone(self, doc_id: str) -> None:
        raise KeyError(f"Memory entry '{doc_id}' not found.")

    monkeypatch.setattr(Memory, "restore", _gone)
    yield from _client()


def _client():
    from fastapi.testclient import TestClient

    from core.memory import Memory
    from server.main import create_app
    from server.routes.memory import _get_memory

    _get_memory.cache_clear()
    Memory.reset_scoped_instances()
    with TestClient(create_app()) as c:
        yield c
    _get_memory.cache_clear()
    Memory.reset_scoped_instances()


class _Store:
    """In-memory stand-in with the surface ``maybe_store_turn`` uses."""

    def __init__(self, hits=None):
        self.entries: list[dict] = []
        self.hits = list(hits or [])

    def search(self, query, top_k=15):
        return list(self.hits)

    def store(self, text, metadata=None):
        self.entries.append({
            "id": f"id-{len(self.entries)}",
            "text": text,
            "metadata": {"timestamp": 1_000_000.0 + len(self.entries), **(metadata or {})},
        })
        return self.entries[-1]["id"]

    def count(self):
        return len(self.entries)

    def list_all(self, limit=100):
        return sorted(
            self.entries, key=lambda e: e["metadata"].get("timestamp", 0), reverse=True
        )[:limit]

    def delete(self, doc_id):
        self.entries = [e for e in self.entries if e["id"] != doc_id]


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """Capture on, no kill switch, hermetic config root (the thresholds come
    from the register defaults)."""
    from core import auto_memory

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_MEMORY_ENABLED", "1")
    monkeypatch.delenv("EPHE_MEMORY_MAX_ENTRIES", raising=False)
    mem = _Store()
    monkeypatch.setattr(auto_memory, "_memory_factory", lambda: mem)
    return mem


QUESTION = "How should I build the FastAPI lifespan for the scheduler?"
ANSWER = (
    "Start the scheduler on the event loop inside the lifespan context, because "
    "AsyncIOScheduler needs the same thread that owns the loop to run at all."
)


# 1. the promise of the trash

class TestTheTrashOnlyPromisesWhatTheStoreDoes:
    def test_a_final_delete_store_says_so_in_its_stats(self, final_delete_client):
        """GIVEN  a store that deletes finally (the one the walkthrough ran on)
        WHEN   GET /api/memory/stats
        THEN   it reports that a deleted entry cannot come back — the resting
               `deleted: 0` is only honest next to that answer"""
        stats = final_delete_client.get("/api/memory/stats").json()
        assert stats["provider"] == "kepta"
        assert stats["deleted"] == 0
        assert stats["restore_supported"] is False

    def test_a_store_with_a_trash_says_so_in_its_stats(self, kepta_client):
        """GIVEN  a store that keeps deleted entries
        WHEN   GET /api/memory/stats
        THEN   the capability is true — the flag describes the store, not a fix"""
        stats = kepta_client.get("/api/memory/stats").json()
        assert stats["provider"] == "kepta"
        assert stats["restore_supported"] is True

    def test_the_empty_trash_says_the_store_keeps_nothing(self, final_delete_client):
        """GIVEN  a store that deletes finally
        WHEN   GET /api/memory/deleted
        THEN   the empty list comes with the capability and the reason — the walkthrough
               read the empty list as a quiet trash the page had promised to fill"""
        body = final_delete_client.get("/api/memory/deleted").json()
        assert body["entries"] == [] and body["total"] == 0
        assert body["restore_supported"] is False
        assert "kepta" in body["detail"] and "restore" in body["detail"]

    def test_restoring_under_a_final_delete_store_is_a_conflict(self, final_delete_client):
        """GIVEN  an entry deleted under a store that keeps no trash
        WHEN   POST /api/memory/{id}/restore
        THEN   409 with the reason (the ID is not the problem, the store is) and
               the entry stays gone"""
        doc_id = final_delete_client.post(
            "/api/memory/store", json={"text": "Ein Fakt, der verschwindet"}
        ).json()["id"]
        assert final_delete_client.delete(f"/api/memory/{doc_id}").status_code == 200
        assert final_delete_client.get("/api/memory/deleted").json()["entries"] == []

        r = final_delete_client.post(f"/api/memory/{doc_id}/restore")
        assert r.status_code == 409
        assert "deletes finally" in r.json()["error"]["message"]
        assert final_delete_client.get("/api/memory/list").json()["total"] == 0

    def test_the_trash_still_works_where_a_trash_exists(self, kepta_client):
        """GIVEN  a store that keeps deleted entries (the other half of the claim)
        WHEN   an entry is deleted and listed and restored
        THEN   the trash names it, the capability is true, and the restore works"""
        doc_id = kepta_client.post(
            "/api/memory/store", json={"text": "a fact for the trash"}
        ).json()["id"]
        kepta_client.delete(f"/api/memory/{doc_id}")

        trash = kepta_client.get("/api/memory/deleted").json()
        assert [e["id"] for e in trash["entries"]] == [doc_id]
        assert trash["restore_supported"] is True and trash["detail"] == ""

        assert kepta_client.post(f"/api/memory/{doc_id}/restore").status_code == 200
        assert kepta_client.get("/api/memory/list").json()["total"] == 1

    def test_an_unknown_id_in_a_real_trash_stays_not_found(self, kepta_client):
        """The honest conflict must not swallow the honest 404: with a trash in
        place, an ID nobody ever deleted is still 'not found'."""
        assert kepta_client.post("/api/memory/ghost/restore").status_code == 404


# 2. one turn, one stored fact

class TestOneTurnStoresOneEntry:
    def test_the_twin_of_the_same_turn_is_not_stored_again(self, store):
        """GIVEN  the model's own `memory` tool already stored this turn's fact
               (source "agent", worded out of the same message)
        WHEN   the server's Q/A capture runs after the turn
        THEN   it refuses as a duplicate — the fact is in the store once"""
        from core import auto_memory

        store.hits = [{
            "id": "agent-1",
            "text": "The probe marker for this session is probe08gate and it must survive.",
            "score": 0.71,  # below the dedupe floor: the wording differs
            "metadata": {"source": "agent", "timestamp": 1_000_001.0},
        }]
        res = auto_memory.maybe_store_turn(
            "Remember this for later: my probe marker is probe08gate and it must "
            "survive this session. Confirm that you kept it.",
            "Noted — memory is stored.",
        )
        assert res == {"stored": False, "reason": "duplicate"}
        assert store.entries == []

    def test_a_fact_from_another_topic_does_not_block_the_capture(self, store):
        """The twin check is about *this* message: an unrelated tool-written fact
        must not silence the capture."""
        from core import auto_memory

        store.hits = [{
            "id": "agent-1",
            "text": "The user prefers the Schwarzwald for weekend trips.",
            "score": 0.30,
            "metadata": {"source": "agent", "timestamp": 1_000_001.0},
        }]
        res = auto_memory.maybe_store_turn(QUESTION, ANSWER)
        assert res["stored"] is True
        assert len(store.entries) == 1

    def test_a_corrupt_agent_row_cannot_block_the_capture(self, store):
        """GIVEN  a tool-written row whose text is unusable and whose similarity
               is below the dedupe floor
        WHEN   the capture runs
        THEN   the row is skipped as untrusted: a bad row may cost one check,
               never the fact"""
        from core import auto_memory

        store.hits = [{"id": "agent-1", "text": None, "score": 0.30,
                       "metadata": {"source": "agent"}}]
        res = auto_memory.maybe_store_turn(QUESTION, ANSWER)
        assert res["stored"] is True
        assert len(store.entries) == 1

    def test_every_origin_the_store_can_hold_has_a_label(self, kepta_client):
        """GIVEN  the memory API
        WHEN   GET /api/memory/stats
        THEN   the vocabulary of origins travels with it, `agent` included — the
               key whose absence left the twin unlabelled on the page"""
        sources = kepta_client.get("/api/memory/stats").json()["sources"]
        assert "agent" in sources and sources["agent"].strip()
        assert "auto_memory" in sources and sources["auto_memory"].strip()

    def test_no_entry_reaches_the_store_without_an_origin(self, kepta_client):
        """GIVEN  a caller that writes without metadata, one that writes a blank
               origin and one that imports a body without an origin
        WHEN   the entries are read back
        THEN   every row carries a label — the store cannot hold an unlabelled one"""
        plain = kepta_client.post(
            "/api/memory/store", json={"text": "a fact with no origin"}
        ).json()["id"]
        blank = kepta_client.post(
            "/api/memory/store", json={"text": "a fact with a blank origin", "metadata": {"source": "   "}}
        ).json()["id"]
        assert kepta_client.post(
            "/api/memory/import",
            json={"entries": [{"id": "imported-1", "text": "Ein importierter Fakt", "metadata": {}}]},
        ).status_code == 201

        entries = kepta_client.get("/api/memory/list").json()["entries"]
        assert len(entries) == 3
        by_id = {e["id"]: e for e in entries}
        assert by_id[plain]["metadata"]["source"] == "user"
        assert by_id[blank]["metadata"]["source"] == "user"
        assert all(str(e["metadata"].get("source") or "").strip() for e in entries)


# 3. the gate keeps what was asked

class TestTheCaptureKeepsWhatWasAskedFor:
    def test_an_explicit_request_survives_a_one_token_answer(self, store):
        """GIVEN  the user asks for a fact to be kept and for a one-word
               confirmation ("Reply with the single token OK and nothing else")
        WHEN   the turn is captured
        THEN   the fact is stored — the walkthrough's two-character answer landed
               nowhere while the assistant confirmed keeping it"""
        from core import auto_memory

        res = auto_memory.maybe_store_turn(
            "Reply with the single token OK and nothing else. Remember this fact: "
            "my probe marker is probe08short20261013122321.",
            "OK",
        )
        assert res["stored"] is True
        assert len(store.entries) == 1
        assert "probe08short20261013122321" in store.entries[0]["text"]

    def test_a_short_answer_without_a_request_is_still_refused(self, store):
        """The other half of the same gate: a micro acknowledgement to an ordinary
        question stays out of the store."""
        from core import auto_memory

        res = auto_memory.maybe_store_turn(QUESTION, "ok")
        assert res["stored"] is False
        assert res["reason"] == "too-short"
        assert store.entries == []
