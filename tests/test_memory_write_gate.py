"""D3 — the write gate: a correction is its own kind of write.

Working Backwards from the user experience: someone who tells the agent "no, I
moved away long ago" does not want both addresses left in the context afterwards
— and also does not want the old address to be *forgotten*. Both are the case
today: `memory(replace)` deletes on a handshake and `add` writes a second fact.

The gate puts the intent into the schema, not into a model heuristic.
`Memory.store(..., supersedes=<id>)` on the live Kepta store writes
`superseded_by` and `valid_to`. The old fact stays queryable and falls back
in the ranking. The call returns the id of the leading entry.
The `chromadb==1.5.9` pin is the retired importer command. This suite does
not open that store.
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    """Hermetic config root, Kepta as the brain, no ONNX (a vector leg would be
    noise here — the gate is a write decision, not a ranking question)."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_MEMORY_PROVIDER", "kepta")
    monkeypatch.setenv("EPHE_MEMORY_EMBEDDER", "none")
    from core.memory import Memory

    Memory.reset_scoped_instances()
    yield tmp_path
    Memory.reset_scoped_instances()


def _row(mem, doc_id: str):
    return mem._provider._db.execute(
        "SELECT superseded_by, valid_to, deleted_at FROM memories WHERE id = ?", (doc_id,)
    ).fetchone()


class TestSupersedeGate:
    def test_a_correction_links_instead_of_forgetting(self, cfg):
        """G: a fact exists
        W: the same write with supersedes=<id>
        T: the old entry is superseded (superseded_by, valid_to), not deleted,
           and the new one leads"""
        from core.memory import Memory

        mem = Memory()
        old = mem.store("Der API-Gateway läuft auf Port 8765", {"source": "agent"})
        new = mem.store(
            "Der API-Gateway läuft auf Port 9100", {"source": "agent"}, supersedes=old
        )
        assert new and new != old
        row = _row(mem, old)
        assert row["superseded_by"] == new
        assert row["valid_to"]
        assert row["deleted_at"] is None
        assert old in [e["id"] for e in mem.list_all()]

    def test_identical_text_does_not_supersede_itself(self, cfg):
        """The duplicate course runs *before* the supersession: identical text is
        the same fact, so no descent event. Otherwise the correction would mark a
        fact as superseded by itself."""
        from core.memory import Memory

        mem = Memory()
        old = mem.store("Der Gateway lauscht auf Port 8765", {"source": "agent"})
        same = mem.store("Der Gateway lauscht auf Port 8765", {"source": "agent"}, supersedes=old)
        assert same == old
        assert _row(mem, old)["superseded_by"] is None

    def test_a_retired_fact_ranks_below_its_successor(self, cfg):
        from core.memory import Memory

        mem = Memory()
        a = mem.store("Der Gateway lauscht auf Port 8765", {"source": "agent"})
        b = mem.store("Der Gateway lauscht auf Port 9100", {"source": "agent"}, supersedes=a)
        hits = {h["id"]: h["score"] for h in mem.search("Gateway lauscht Port")}
        assert b in hits and a in hits
        assert hits[b] > hits[a]

    def test_an_unknown_id_raises_key_error(self, cfg):
        from core.memory import Memory

        mem = Memory()
        with pytest.raises(KeyError):
            mem.store("Irgendein Fakt", supersedes="ghost")

    def test_an_empty_correction_moves_nothing(self, cfg):
        from core.memory import Memory

        mem = Memory()
        old = mem.store("Ein Fakt bleibt unangetastet")
        assert mem.store("   ", supersedes=old) == ""
        assert _row(mem, old)["superseded_by"] is None

    def test_type_and_tags_reach_the_provider(self, cfg):
        from core.memory import Memory

        mem = Memory()
        doc_id = mem.store(
            "Reihenfolge: erst Test, dann Implementierung",
            {"source": "agent"},
            memory_type="procedural",
            tags=["workflow"],
        )
        entry = next(e for e in mem.list_all() if e["id"] == doc_id)
        assert entry["metadata"]["type"] == "procedural"
        assert "workflow" in entry["metadata"]["tags"]


class TestNamedStoreReachesTheSameGate:
    """The retired store *replaced* a superseded text; Kepta links it instead
    (`superseded_by`, the row stays queryable — see TestSupersedeGate). The class
    that used to stand here pinned the replacement, which is vendor behaviour and
    left with the backend on 2026-10-14. What still has to hold is that the named
    store — the legacy vocabulary, `persist_dir` + `collection_name` — reaches the
    same gate as the workspace path, so it does not become a second code path.
    """

    def test_supersede_works_on_a_named_scope(self, cfg, tmp_path):
        from core.memory import Memory

        mem = Memory(persist_dir=str(tmp_path / "c"), collection_name="gate")
        assert mem.provider_kind == "kepta"
        old = mem.store("Alte Adresse: Freiburg", {"source": "agent"})
        new = mem.store("Neue Adresse: Berlin", {"source": "agent"}, supersedes=old)
        assert new and new != old

        row = mem._provider._db.execute(
            "SELECT superseded_by, valid_to, deleted_at FROM memories WHERE id = ?", (old,)
        ).fetchone()
        assert row["superseded_by"] == new and row["valid_to"] and row["deleted_at"] is None
        leading = [e["text"] for e in mem.list_all() if e["metadata"].get("superseded_by") is None]
        assert "Neue Adresse: Berlin" in leading

    def test_an_unknown_id_raises_key_error_in_a_named_scope(self, cfg, tmp_path):
        from core.memory import Memory

        mem = Memory(persist_dir=str(tmp_path / "c2"), collection_name="gate2")
        with pytest.raises(KeyError):
            mem.store("Text", supersedes="ghost")


class TestMemoryTool:
    def _call(self, **kwargs) -> str:
        from core.tools.state_tools import memory

        return asyncio.run(memory(**kwargs))

    def test_replace_becomes_provenance(self, cfg):
        from core.memory import Memory

        mem = Memory()
        old = mem.store("Unser Deployment läuft auf Port 8765", {"source": "agent"})
        out = self._call(
            action="replace", target="memory",
            old_text="8765", content="Unser Deployment läuft auf Port 9100",
        )
        assert "replaced" in out
        row = _row(mem, old)
        assert row["superseded_by"] and row["deleted_at"] is None

    def test_the_list_shows_only_leading_facts(self, cfg):
        from core.memory import Memory

        mem = Memory()
        old = mem.store("Belegbare Aussage 8765", {"source": "agent"})
        self._call(action="replace", target="memory", old_text="8765", content="Aussage 9100")
        listing = self._call(action="list", target="memory")
        assert "9100" in listing and "8765" not in listing
        assert old in [e["id"] for e in mem.list_all()], "die Historie bleibt erhalten"

    def test_add_without_a_type_stays_semantic(self, cfg):
        from core.memory import Memory

        out = self._call(action="add", target="memory", content="Die DB heißt kepta.db")
        assert "stored" in out
        entry = Memory().list_all()[0]
        assert entry["metadata"]["type"] == "semantic"
        assert entry["metadata"]["source"] == "agent"

    def test_add_with_a_procedural_type(self, cfg):
        from core.memory import Memory

        out = self._call(
            action="add", target="memory",
            content="Erst Test schreiben, dann implementieren",
            memory_type="procedural",
        )
        assert "stored" in out
        assert Memory().list_all()[0]["metadata"]["type"] == "procedural"

    def test_an_unknown_type_still_stores_the_entry(self, cfg):
        """A typo in the type field must not cost a fact: Kepta caps it to
        semantic and the write goes through."""
        from core.memory import Memory

        self._call(action="add", target="memory", content="Ein Fakt", memory_type="vibes")
        assert Memory().list_all()[0]["metadata"]["type"] == "semantic"

    def test_remove_is_a_soft_delete(self, cfg):
        from core.memory import Memory

        mem = Memory()
        doc_id = mem.store("Eintrag, der verschwinden soll")
        out = self._call(action="remove", target="memory", old_text="verschwinden")
        assert "removed" in out
        assert doc_id not in [e["id"] for e in mem.list_all()]
        assert mem.provider_stats()["deleted"] == 1

    def test_the_schema_advertises_the_write_kinds(self):
        """The model can only write deliberately what the schema states."""
        from core.tools.registry import get_tool_schemas

        tool = next(
            t["function"] for t in get_tool_schemas() if t["function"]["name"] == "memory"
        )
        props = tool["parameters"]["properties"]
        assert props["memory_type"]["enum"] == ["semantic", "episodic", "procedural"]
        assert "supersedes" in props
        assert "supersede" in tool["description"].lower()


class TestWriteRoutes:
    """/memory/store gets the same intent as the tool — the UI writes too, after
    all. Every new field is additive: a body like before wave D still just
    stores."""

    @pytest.fixture()
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("EPHE_MEMORY_PROVIDER", "kepta")
        monkeypatch.setenv("EPHE_MEMORY_EMBEDDER", "none")
        from core.memory import Memory
        from server.routes.memory import _get_memory

        _get_memory.cache_clear()
        Memory.reset_scoped_instances()
        from fastapi.testclient import TestClient
        from server.main import create_app

        with TestClient(create_app()) as c:
            yield c
        _get_memory.cache_clear()
        Memory.reset_scoped_instances()

    def test_type_and_tags_pass_through_the_api(self, client):
        r = client.post(
            "/api/memory/store",
            json={"text": "Deploy: erst Migration, dann Rollout", "memory_type": "procedural",
                  "tags": ["runbook"]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["stored"] is True and body["id"]
        entry = next(e for e in client.get("/api/memory/list").json()["entries"]
                     if e["id"] == body["id"])
        assert entry["metadata"]["type"] == "procedural"
        assert "runbook" in entry["metadata"]["tags"]

    def test_supersedes_passes_through_the_api(self, client):
        old = client.post("/api/memory/store", json={"text": "Port 8765 ist der Gateway"}).json()["id"]
        r = client.post(
            "/api/memory/store",
            json={"text": "Port 9100 ist der Gateway", "supersedes": old},
        )
        assert r.status_code == 200
        assert r.json()["id"] != old

    def test_an_unknown_supersedes_is_404(self, client):
        r = client.post("/api/memory/store", json={"text": "Ein Fakt", "supersedes": "ghost"})
        assert r.status_code == 404

    def test_the_legacy_payload_shape_still_works(self, client):
        r = client.post("/api/memory/store", json={"text": "Nur Text, wie vor Welle D"})
        assert r.status_code == 200 and r.json()["stored"] is True
