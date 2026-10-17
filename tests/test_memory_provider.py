"""D2 — Memory provider seam: one facade, one brain.

The contract is the headline: `core/memory.py` stays the API that the four
consumers (chat, auto_memory, state_tools, /api/memory) already use. A provider
may not invent behaviour, it may only store it differently.
That is why this file tests parity, not novelty.

Since 2026-10-14 there is one local brain, `kepta` — the retired vector store left
the product with advisories that no release closed. Two rules survived
the move. Anyone passing persist_dir or collection_name still gets exactly the store
they named: the path is where the Kepta file lands, the collection name is its scope.
A retired store on disk is recognised and named, never opened: the brain stays Kepta
and the one-time read is offered offline.
"""

from __future__ import annotations

import json

import pytest


@pytest.fixture()
def cfg(tmp_path, monkeypatch):
    """Hermetic config root + no embedder (loading ONNX here would be noise)."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("EPHE_MEMORY_PROVIDER", raising=False)
    monkeypatch.setenv("EPHE_MEMORY_EMBEDDER", "none")
    from core.memory import Memory

    Memory.reset_scoped_instances()
    yield tmp_path
    Memory.reset_scoped_instances()


def _kind(mem) -> str:
    return mem.provider_kind


def _plant_retired_store(cfg):
    """A filled folder where the retired store used to write, for this workspace."""
    from core.memory import workspace_memory_dir

    directory = workspace_memory_dir()
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "chroma.sqlite3").write_bytes(b"retired")
    return directory


class TestSelection:
    def test_frische_Installation_bekommt_kepta(self, cfg):
        """G: empty device folder, nothing configured
        W: Memory()
        T: kepta — and the decision sits visibly as a record, not as a guess"""
        from core.memory import Memory
        from core.memory_provider import read_provider_record

        mem = Memory()
        assert _kind(mem) == "kepta"
        rec = read_provider_record()
        assert rec and rec["provider"] == "kepta"
        assert rec["reason"]

    def test_benannter_speicher_ist_der_benannte_speicher(self, cfg):
        """G: a caller names a path and a collection
        W: Memory(persist_dir=…, collection_name=…)
        T: kepta, whose file lands at that path under that scope — the legacy
           vocabulary still names a store exactly, it just names a Kepta one"""
        from core.memory import Memory
        from core.memory_provider import kepta_db_path

        mem = Memory(persist_dir=str(cfg / "c1"), collection_name="explicit")
        assert _kind(mem) == "kepta"
        assert mem.migrate_to_kepta()["scope"] == "explicit"
        mem.store("Ein benannter Fakt")
        assert mem.count() == 1
        assert kepta_db_path("explicit", str(cfg / "c1")).exists(), (
            "the named path is where the file has to land, or a caller cannot isolate a store"
        )
        assert not (cfg / "c1" / "chroma.sqlite3").exists()

    def test_altbestand_wird_erkannt_und_benannt_nicht_geoeffnet(self, cfg):
        """G: the workspace holds data of the retired store
        W: Memory()
        T: kepta, and the decision record says so — a user in production must not
           have the memory swapped out from under them, and the store that would
           receive the swap does not exist any more"""
        from core.memory import Memory
        from core.memory_provider import read_provider_record

        planted = _plant_retired_store(cfg)
        assert planted.is_dir()
        assert _kind(Memory()) == "kepta"
        rec = read_provider_record()
        assert rec and rec["provider"] == "kepta"
        assert rec["reason"] == "existing-data", rec

    def test_alte_provider_datei_mit_entferntem_namen_wird_ignoriert(self, cfg):
        """G: ~/.ephe/memory/provider.json still names the retired provider
        W: Memory()
        T: kepta — an existing installation upgrades instead of dying on a name
           that left the product"""
        from core.memory import Memory
        from core.memory_provider import provider_record_path, read_provider_record

        path = provider_record_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"provider": "chroma", "reason": "settings",
                                    "decided_at": 0, "schema": 1}), encoding="utf-8")
        assert read_provider_record() is None, "a name outside VALID_PROVIDERS is not a record"
        assert _kind(Memory()) == "kepta"

    def test_der_entfernte_name_kann_nicht_mehr_geschrieben_werden(self, cfg):
        """The route's Literal and this writer have to agree: an unusable name must
        fail loudly instead of being persisted and then ignored on every read."""
        from core.memory_provider import VALID_PROVIDERS, write_provider_record

        assert "chroma" not in VALID_PROVIDERS
        with pytest.raises(ValueError):
            write_provider_record("chroma", reason="test")

    def test_env_gewinnt_gegen_record(self, cfg, monkeypatch):
        from core.memory import Memory
        from core.memory_provider import write_provider_record

        write_provider_record("kepta-bridge", reason="test")
        monkeypatch.setenv("EPHE_MEMORY_PROVIDER", "kepta")
        Memory.reset_scoped_instances()
        assert _kind(Memory()) == "kepta"

    def test_unbekannter_env_wert_ist_sichtbar_und_faellt_auf_regel_zurueck(self, cfg, monkeypatch):
        monkeypatch.setenv("EPHE_MEMORY_PROVIDER", "quatsch")
        from core.memory import Memory

        assert _kind(Memory()) == "kepta"


class TestFacadeParity:
    def test_gleiche_api_ueber_jeden_weg(self, cfg):
        """The slice criterion: store/search/list_all/delete/update/count/clear
        deliver identical shapes and identical errors, whether the store was
        resolved from the workspace or named by the caller."""
        from core.memory import Memory

        paths = {
            "workspace": {},
            "named": {"persist_dir": str(cfg / "c2"), "collection_name": "named"},
        }
        for label, kwargs in paths.items():
            Memory.reset_scoped_instances()
            mem = Memory(**kwargs)
            doc_id = mem.store("Der API-Gateway läuft auf Port 8765", {"source": "manual"})
            assert mem.count() == 1, label

            hits = mem.search("API-Gateway 8765", top_k=3)
            assert set(hits[0]) >= {"id", "text", "metadata", "score"}, label
            assert hits[0]["id"] == doc_id, label
            assert 0.0 < hits[0]["score"] <= 1.0, label

            rows = mem.list_all(limit=10)
            assert rows[0]["id"] == doc_id and rows[0]["metadata"]["source"] == "manual", label

            mem.update(doc_id, "Der API-Gateway läuft auf Port 9000")
            assert "9000" in next(e["text"] for e in mem.list_all() if e["id"] == doc_id), label

            injection = mem.get_context_injection("API-Gateway Port")
            assert "9000" in injection, label

            mem.delete(doc_id)
            assert mem.count() == 0, label
            with pytest.raises(KeyError):
                mem.delete(doc_id)
            mem.store("   ")
            assert mem.count() == 0, label
            with pytest.raises(ValueError):
                mem.update("ffffffffffffffff", "  ")

            mem.store("Vor dem Leeren")
            mem.clear()
            assert mem.count() == 0, label
            assert mem.collection_name.startswith("kepta_"), label

    def test_search_auf_leerem_speicher_ist_leer_nicht_null(self, cfg, monkeypatch):
        from core.memory import Memory

        monkeypatch.setenv("EPHE_MEMORY_PROVIDER", "kepta")
        Memory.reset_scoped_instances()
        mem = Memory()
        assert mem.search("irgendwas") == []
        assert mem.get_context_injection("irgendwas") == ""
        assert mem.list_all() == []

    def test_singleton_pro_workspace_unchaengt(self, cfg, monkeypatch):
        from core.memory import Memory

        monkeypatch.setenv("EPHE_MEMORY_PROVIDER", "kepta")
        assert Memory() is Memory()
        assert Memory(persist_dir=str(cfg / "x")) is not Memory()


class TestMigration:
    def test_der_import_laeuft_offline_und_die_antwort_nennt_den_befehl(self, cfg):
        """G: a retired store on disk
        W: migrate_chroma_to_kepta()
        T: no in-process copy — the report names the one command that does it, and
           `imported` is 0 because this process cannot read the source at all. A
           caller must not read that 0 as "the store was empty"."""
        from core.memory_provider import migrate_chroma_to_kepta

        _plant_retired_store(cfg)
        report = migrate_chroma_to_kepta(dry_run=False, embedder=None)
        assert report["moved_in_process"] is False
        assert report["imported"] == 0
        assert report["provider_target"] == "kepta"
        assert "scripts/import_legacy_store.py" in report["command"]
        assert report["command"].startswith("uv run --with")
        assert report["source_dir"] in report["command"], (
            "the command has to name the folder it reads, or it reads the wrong one"
        )

    def test_kein_lauf_legt_die_zieldatei_an(self, cfg):
        from core.memory_provider import kepta_db_path, migrate_chroma_to_kepta

        _plant_retired_store(cfg)
        report = migrate_chroma_to_kepta(dry_run=True, embedder=None)
        assert not kepta_db_path(report["scope"]).exists(), (
            "the report is a statement, not a copy — nothing may be written"
        )


class TestProviderRoutes:
    @pytest.fixture()
    def client(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        monkeypatch.setenv("EPHE_MEMORY_EMBEDDER", "none")
        monkeypatch.delenv("EPHE_MEMORY_DIR", raising=False)
        monkeypatch.delenv("EPHE_MEMORY_PROVIDER", raising=False)
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

    def test_stats_melden_provider_ohne_bestaehende_felder_zu_nderen(self, client):
        body = client.get("/api/memory/stats").json()
        assert body["total"] == 0
        assert body["provider"] == "kepta"
        assert body["scope"].startswith("kepta_")
        assert body["vector_leg"] is False

    def test_die_einstellung_nimmt_keinen_namen_an_der_das_produkt_verlassen_hat(self, client):
        r = client.put("/api/memory/provider", json={"provider": "chroma"})
        assert r.status_code == 422, (
            "the route's Literal has to reject the retired name: writing it would persist a "
            "choice every later read silently ignores"
        )
        r2 = client.put("/api/memory/provider", json={"provider": "kepta"})
        assert r2.status_code == 200
        assert client.get("/api/memory/stats").json()["provider"] == "kepta"

    def test_unbekannter_provider_wird_abgelehnt_statt_geraten(self, client):
        assert client.put("/api/memory/provider", json={"provider": "postgres"}).status_code == 422

    def test_migrate_route_nennt_den_offline_befehl(self, client):
        """The dry run shows what would move — and this process moves nothing."""
        from core.engine_config import workspace_hash
        from core.memory_provider import kepta_db_path

        r = client.post("/api/memory/migrate", json={"dry_run": True})
        assert r.status_code == 200
        report = r.json()
        assert report["moved_in_process"] is False
        assert report["imported"] == 0
        assert "scripts/import_legacy_store.py" in report["command"]
        assert not kepta_db_path(workspace_hash()).exists(), (
            "a dry run may not even create the target file"
        )
