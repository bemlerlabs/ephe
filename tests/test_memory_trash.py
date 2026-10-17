"""D5 — forgetting is reversible, and supersession points in both directions.

Working backwards from the surface: a memory UI that only knows the leading facts
lies twice. First, a deleted entry vanishes under Kepta without a trace — the user
cannot see what was taken away, and cannot get it back. Second, the descent is only
half visible: the old fact carries `superseded_by`, the new one does not know what
it corrects — "that used to be the case" cannot be told from it.

Both are seam methods, not provider special cases: Chroma deletes hard, so it
reports an empty trash list and a restore that answers with KeyError instead of
pretending that a history exists.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    """Hermetic config root, Kepta as the brain, without ONNX (trash and
    descent are storage questions, not ranking questions)."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_MEMORY_PROVIDER", "kepta")
    monkeypatch.setenv("EPHE_MEMORY_EMBEDDER", "none")
    from core.memory import Memory

    Memory.reset_scoped_instances()
    yield tmp_path
    Memory.reset_scoped_instances()


class TestTrashSeam:
    def test_soft_delete_ist_sichtbar_und_umkehrbar(self, cfg):
        """G: a fact is deleted
        W: list_deleted(), then restore()
        T: it appears in the trash with its deletion timestamp, and afterwards it is
           a leading active entry again"""
        from core.memory import Memory

        mem = Memory()
        doc_id = mem.store("Der Bausatz heißt kepta.db", {"source": "agent"})
        mem.delete(doc_id)
        assert doc_id not in [e["id"] for e in mem.list_all()]

        trash = mem.list_deleted()
        assert [e["id"] for e in trash] == [doc_id]
        assert trash[0]["metadata"]["deleted_at"]

        mem.restore(doc_id)
        assert doc_id in [e["id"] for e in mem.list_all()]
        assert mem.list_deleted() == []

    def test_papierkorb_hat_eine_harte_grenze(self, cfg):
        """The trash is a list a UI renders too: `limit` has to reach the
        provider, otherwise it grows without bound."""
        from core.memory import Memory

        mem = Memory()
        for i in range(4):
            doc_id = mem.store(f"Ablagefach {i}")
            mem.delete(doc_id)
        assert len(mem.list_deleted(limit=2)) == 2

    def test_restore_eines_aktiven_eintrags_ist_keyerror(self, cfg):
        """The trash is the only source for a restore: "restoring" an active ID
        would be a no-op lie about a loss that never happened."""
        from core.memory import Memory

        mem = Memory()
        doc_id = mem.store("Ein Fakt, der nie gelöscht wurde")
        with pytest.raises(KeyError):
            mem.restore(doc_id)

    def test_papierkorb_bleibt_im_scope(self, cfg):
        """W16 still holds after deleting: the memory removed in project A
        must not turn up in project B."""
        from core.memory import Memory

        a = Memory(scope="scope-a")
        doc_id = a.store("Geheimer Fakt aus Projekt A")
        a.delete(doc_id)
        b = Memory(scope="scope-b")
        assert b.list_deleted() == []
        assert b.count() == 0

    def test_typ_und_tags_bleiben_im_papierkorb_erhalten(self, cfg):
        """An entry without metadata context would be unrecognisable in the trash
        — you would restore blind."""
        from core.memory import Memory

        mem = Memory()
        doc_id = mem.store(
            "Regel: vor jedem Refactor Tests laufen lassen",
            memory_type="procedural",
            tags=["workflow"],
        )
        mem.delete(doc_id)
        entry = mem.list_deleted()[0]
        assert entry["metadata"]["type"] == "procedural"
        assert "workflow" in entry["metadata"]["tags"]


class TestPapierkorb:
    def test_the_trash_is_real_rather_than_only_promised(self, cfg, tmp_path):
        """The retired store deleted finally, so the class that stood here pinned a
        route reporting an empty trash it could never fill. One store is left and it
        keeps a trash, so the promise the page makes is now deliverable, and that is
        what has to be pinned."""
        from core.memory import Memory

        mem = Memory(persist_dir=str(tmp_path / "c2"), collection_name="trash2")
        assert mem.provider_kind == "kepta"
        doc_id = mem.store("An entry for the trash")
        mem.delete(doc_id)
        assert [e["id"] for e in mem.list_deleted()] == [doc_id]
        mem.restore(doc_id)
        assert mem.count() == 1
        assert mem.list_deleted() == []


class TestVorwaertsAbstammung:
    def test_neuer_fakt_weiss_was_er_korrigiert(self, cfg):
        """`superseded_by` only points backwards. For "that used to be the case" in
        the UI, the correction itself has to carry the id it came from."""
        from core.memory import Memory

        mem = Memory()
        old = mem.store("Der Gateway läuft auf Port 8765", {"source": "agent"})
        new = mem.store("Der Gateway läuft auf Port 9100", {"source": "agent"}, supersedes=old)
        entry = next(e for e in mem.list_all() if e["id"] == new)
        assert entry["metadata"]["supersedes"] == old

    def test_abgeloester_fakt_traegt_sein_neues_id(self, cfg):
        from core.memory import Memory

        mem = Memory()
        old = mem.store("Der Gateway läuft auf Port 8765")
        new = mem.store("Der Gateway läuft auf Port 9100", supersedes=old)
        row = mem._provider._db.execute(
            "SELECT superseded_by, valid_to FROM memories WHERE id = ?", (old,)
        ).fetchone()
        assert row["superseded_by"] == new and row["valid_to"]

    def test_dedup_ohne_abloesung_setzt_keine_herkunft(self, cfg):
        from core.memory import Memory

        mem = Memory()
        doc_id = mem.store("Erster Fakt über Port 8765")
        entry = next(e for e in mem.list_all() if e["id"] == doc_id)
        assert "supersedes" not in entry["metadata"]

    def test_rueckgabe_des_papierkorbs_ist_aufsteigend_nach_loeschung(self, cfg):
        """What was taken away last sits on top: whoever deleted something just now
        wants exactly that back, without scanning the list."""
        from core.memory import Memory

        mem = Memory()
        first = mem.store("Zuerst gelöscht")
        second = mem.store("Danach gelöscht")
        mem.delete(first)
        mem.delete(second)
        assert [e["id"] for e in mem.list_deleted()] == [second, first]


class TestTrashRoutes:
    """The UI can only restore what it can address: a list path and
    a restore path, both additive to what wave D already delivers."""

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

    def test_geloeschter_eintrag_ist_listbar_und_stellbar(self, client):
        doc_id = client.post(
            "/api/memory/store", json={"text": "Eintrag, das bald gelöscht ist"}
        ).json()["id"]
        assert client.delete(f"/api/memory/{doc_id}").status_code == 200

        r = client.get("/api/memory/deleted")
        assert r.status_code == 200
        assert [e["id"] for e in r.json()["entries"]] == [doc_id]
        assert client.get("/api/memory/list").json()["total"] == 0

        ok = client.post(f"/api/memory/{doc_id}/restore")
        assert ok.status_code == 200
        assert ok.json()["restored"] == doc_id
        assert client.get("/api/memory/list").json()["total"] == 1

    def test_restore_unbekannter_id_ist_404(self, client):
        assert client.post("/api/memory/ghost/restore").status_code == 404

    def test_stats_meldet_den_papierkorb(self, client):
        doc_id = client.post(
            "/api/memory/store", json={"text": "Eintrag für die Statistik"}
        ).json()["id"]
        client.delete(f"/api/memory/{doc_id}")
        stats = client.get("/api/memory/stats").json()
        assert stats["deleted"] == 1 and stats["total"] == 0

    def test_loeschpfad_unkaputtbar(self, client):
        """GET /memory/deleted must not disturb the parameter-swallowing /memory/{doc_id}
        route — and the DELETE path behaves as it did before D5."""
        doc_id = client.post(
            "/api/memory/store", json={"text": "Schlichter Fakt"}
        ).json()["id"]
        assert client.delete(f"/api/memory/{doc_id}").json() == {"deleted": doc_id}
