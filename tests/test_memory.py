"""
◑ Ephe – the core.memory store (Phase 2 TDD)
tests/test_memory.py

RULE: tests written BEFORE implementation.
Every test has to be RED until core/memory.py is complete.

Given / When / Then – strictly.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.memory import Memory


class TestMemoryStore:

    @pytest.fixture
    def mem(self, tmp_path, monkeypatch):
        """Fresh Memory instance for each test."""
        # Empty config root: otherwise _migrate_from_legacy migrates the real
        # ~/.ephe/memory into the tmp collection and count()/search() are no
        # longer empty (test isolation).
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        return Memory(persist_dir=str(tmp_path / "chroma_test"))

    def test_store_creates_no_exception(self, mem):
        """
        GIVEN  empty Memory instance
        WHEN   mem.store("Ich bin Python-Entwickler") is called
        THEN   no exception
        AND    mem.count() > 0
        """
        mem.store("Ich bin Python-Entwickler", metadata={"source": "test"})
        assert mem.count() > 0

    def test_search_returns_relevant_result(self, mem):
        """
        GIVEN  stored text: "Ich bin Python-Entwickler und mag asyncio"  # language-gate: ignore (the fixture sentence the search is run against)
        WHEN   mem.search("Programmiersprache Python") is called
        THEN   the result is a list with >=1 entries
        AND    the top result contains "Python"
        """
        mem.store("Ich bin Python-Entwickler und mag asyncio")
        results = mem.search("Programmiersprache Python", top_k=3)

        assert isinstance(results, list)
        assert len(results) >= 1
        assert any("Python" in r["text"] for r in results)

    def test_search_on_empty_db_returns_empty_list(self, mem):
        """
        GIVEN  empty memory database
        WHEN   mem.search("irgendwas") is called
        THEN   the result is an empty list (no crash)
        """
        results = mem.search("irgendwas")
        assert results == []

    def test_clear_removes_all_entries(self, mem):
        """
        GIVEN  several stored entries
        WHEN   mem.clear() is called, then mem.search()
        THEN   the result is an empty list
        AND    mem.count() == 0
        """
        mem.store("Eintrag 1")
        mem.store("Eintrag 2")
        assert mem.count() > 0

        mem.clear()

        assert mem.count() == 0
        assert mem.search("Eintrag") == []

    def test_store_multiple_entries(self, mem):
        """
        GIVEN  3 different texts are stored
        WHEN   mem.count() is called
        THEN   the result is 3
        """
        mem.store("Python ist eine Programmiersprache")
        mem.store("Rust ist schnell und sicher")
        mem.store("JavaScript läuft im Browser")

        assert mem.count() == 3

    def test_search_returns_at_most_top_k(self, mem):
        """
        GIVEN  5 similar entries stored
        WHEN   mem.search(query, top_k=2) is called
        THEN   the result contains <=2 entries
        """
        for i in range(5):
            mem.store(f"Eintrag Nummer {i} über Python und KI")

        results = mem.search("Python KI", top_k=2)
        assert len(results) <= 2

    def test_each_result_has_required_keys(self, mem):
        """
        GIVEN  stored entry with text and metadata
        WHEN   mem.search() is called
        THEN   every result has the keys: text, metadata, score
        """
        mem.store("Test-Eintrag", metadata={"session": "abc"})
        results = mem.search("Test", top_k=1)

        assert len(results) >= 1
        for r in results:
            assert "text" in r
            assert "metadata" in r
            assert "score" in r


class TestWorkspaceScopedClear:
    """Regression: clear() has to delete the workspace-scoped collection.

    The no-arg path names the collection via workspace_collection_name()
    (ephe_memory_{hash}); clear() must not blindly delete COLLECTION_NAME
    (ephe_memory) — otherwise "clear memory" stays a silent no-op for real
    workspace data (or crashes with a NotFoundError).
    """

    @pytest.fixture
    def scoped_mem(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
        monkeypatch.setenv("EPHE_WORKSPACE", str(tmp_path / "ws-a"))
        Memory.reset_scoped_instances()
        return Memory()

    def test_collection_is_workspace_scoped(self, scoped_mem):
        """GIVEN no-arg Memory THEN the collection name is scoped, not the constant."""
        from core.memory import workspace_hash_local

        # Wave D: the facade holds the provider, no longer the client object. The
        # invariant under test is the scope itself, so two workspaces cannot end up
        # in one store whatever the backend names it.
        assert scoped_mem._provider.scope == workspace_hash_local()
        assert workspace_hash_local() in scoped_mem._provider.name
        assert scoped_mem._provider.name != Memory.COLLECTION_NAME

    def test_clear_removes_all_scoped_entries(self, scoped_mem):
        """GIVEN scoped entries WHEN clear() THEN count()==0 and search()==[]."""
        scoped_mem.store("Workspace-Geheimnis 1")
        scoped_mem.store("Workspace-Geheimnis 2")
        assert scoped_mem.count() > 0

        scoped_mem.clear()

        assert scoped_mem.count() == 0
        assert scoped_mem.search("Workspace") == []


class TestSearchCarriesId:
    """Regression R40: search() returned no document ID. The UI therefore had
    to invent synthetic IDs that came up empty when deleting/editing
    (DELETE /api/memory/{id} -> 404)."""

    @pytest.fixture
    def mem(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        return Memory(persist_dir=str(tmp_path / "chroma_test"))

    def test_search_result_includes_the_document_id(self, mem):
        mem.store("Der Herd wird nach 20 Minuten abgeschaltet", metadata={"source": "test"})
        hits = mem.search("Herd abschalten")

        assert len(hits) >= 1
        assert hits[0]["id"], "Suchtreffer muss eine echte Document-ID tragen"
        listed = mem.list_all()
        assert hits[0]["id"] in {e["id"] for e in listed}

    def test_id_survives_delete_roundtrip(self, mem):
        mem.store("Eintrag A zum Löschen über die Suche")
        doc_id = mem.search("Eintrag A")[0]["id"]

        mem.delete(doc_id)

        assert mem.search("Eintrag A") == []


class TestMemoryUpdate:
    """R40: correct entries instead of deleting and re-creating them."""

    @pytest.fixture
    def mem(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        return Memory(persist_dir=str(tmp_path / "chroma_update"))

    def test_update_replaces_text_and_keeps_id(self, mem):
        mem.store("Python 3.9 ist die Version")
        doc_id = mem.list_all()[0]["id"]

        mem.update(doc_id, "Python 3.13 ist die Version")

        entries = mem.list_all()
        assert [e["id"] for e in entries] == [doc_id]
        assert entries[0]["text"] == "Python 3.13 ist die Version"

    def test_update_reembeds_so_search_follows_the_new_text(self, mem):
        mem.store("Der Server läuft auf Port 8000")
        doc_id = mem.list_all()[0]["id"]

        mem.update(doc_id, "Der Server läuft auf Port 9999")

        hits = mem.search("Port 9999")
        assert hits and "9999" in hits[0]["text"]
        assert not [h for h in mem.search("Port 8000") if "8000" in h["text"]]

    def test_update_preserves_metadata_and_stamps_updated_at(self, mem):
        mem.store("Alte Notiz", metadata={"source": "compaction", "priority": "high"})
        before = mem.list_all()[0]["metadata"]
        doc_id = mem.list_all()[0]["id"]

        mem.update(doc_id, "Neue Notiz")

        after = mem.list_all()[0]["metadata"]
        assert after["source"] == "compaction"
        assert after["priority"] == "high"
        assert after["timestamp"] == before["timestamp"]
        assert after["updated_at"] >= before["timestamp"]

    def test_update_unknown_id_raises_keyerror(self, mem):
        with pytest.raises(KeyError):
            mem.update("ghost-id", "Text")

    @pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
    def test_update_rejects_blank_text_without_touching_the_entry(self, mem, blank):
        mem.store("Wertvoller Bestand")
        doc_id = mem.list_all()[0]["id"]

        with pytest.raises(ValueError):
            mem.update(doc_id, blank)

        assert mem.list_all()[0]["text"] == "Wertvoller Bestand"

    def test_collection_name_exposes_the_active_scope(self, mem):
        """The UI needs the real name, which may be workspace-scoped; the
        constant alone cannot label the displayed stock correctly."""
        assert mem.collection_name == mem._provider.name
        assert mem.collection_name != Memory.COLLECTION_NAME
        assert mem._provider.scope in mem.collection_name
