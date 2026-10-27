"""D2 — Kepta core port: SQLite/FTS5 memory with three retrieval legs.

Ported from /work/kepta src/core/{store,engine}.ts (MIT): schema,
RRF fusion (k=60), Oblivion retention, supersede-not-delete, recordAccess.
Ephe extensions: scope enforcement (Kepta does not enforce it) and the
metadata column for Ephe's free-form dict (source/priority/hits).

The tests run against a scripted fake embedder — no ONNX download, and above
all: each of the three legs is tested IN ISOLATION, otherwise BM25 hides a
broken vector path (and the other way round).
"""

from __future__ import annotations

import hashlib
import json
import math
import time

import pytest


DAY = 86400.0
_DIMS = 64


def make_embedder(vectors: dict[str, list[float]] | None = None):
    """Word-hash embedder, optionally overridden by explicit table entries.

    md5 on purpose instead of hash(): Python's string hash is salted per
    process, so a ranking test would change between runs. The vectors are
    L2-normalised like chroma's all-MiniLM — the cosine computation in the
    provider should see the same values as in production.
    """
    table = {k.strip().lower(): v for k, v in (vectors or {}).items()}

    def embed(texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for t in texts:
            key = t.strip().lower()
            if key in table:
                out.append(list(table[key]))
                continue
            dims = [0.0] * _DIMS
            for word in key.replace("\n", " ").split(" "):
                if not word:
                    continue
                h = int.from_bytes(hashlib.md5(word.encode()).digest()[:4], "big") % _DIMS
                dims[h] += 1.0
            n = math.sqrt(sum(d * d for d in dims)) or 1.0
            out.append([d / n for d in dims])
        return out

    return embed


@pytest.fixture()
def kp(tmp_path):
    from core.memory_kepta import KeptaProvider

    p = KeptaProvider(
        db_path=str(tmp_path / "kepta.db"),
        scope="wspace0f4fc0524e42",
        embedder=make_embedder(),
        embed_model="fake-hash-16",
    )
    yield p
    p.close()


class TestStoreAndRead:
    def test_store_gibt_stabile_16_hex_id(self, kp):
        doc_id = kp.store("Der API-Gateway läuft auf Port 8765", {"source": "chat"})
        assert len(doc_id) == 16
        assert int(doc_id, 16) >= 0
        assert kp.list_all()[0]["id"] == doc_id

    def test_whitespace_store_ist_noop_wie_bisher(self, kp):
        assert kp.store("   ") is None or kp.store("   ") == ""
        assert kp.count() == 0

    def test_metadata_ueberlebt_roundtrip(self, kp):
        doc_id = kp.store(
            "Nutzer bevorzugt Schwarzwald-Urlaub",
            {"source": "auto_memory", "priority": "high", "session_id": "s-1"},
        )
        row = next(e for e in kp.list_all() if e["id"] == doc_id)
        assert row["metadata"]["source"] == "auto_memory"
        assert row["metadata"]["priority"] == "high"
        assert row["metadata"]["session_id"] == "s-1"
        assert isinstance(row["metadata"]["timestamp"], float)

    def test_list_all_neueste_zuerst(self, kp):
        kp.store("ältester Fakt")
        time.sleep(0.01)
        kp.store("neuester Fakt")
        texts = [e["text"] for e in kp.list_all()]
        assert texts[0] == "neuester Fakt"

    def test_persistiert_neueroeffnung(self, tmp_path):
        from core.memory_kepta import KeptaProvider

        db = str(tmp_path / "persist.db")
        a = KeptaProvider(db_path=db, scope="s", embedder=make_embedder())
        a.store("Eintrag überlebt Prozessgrenze")
        a.close()
        b = KeptaProvider(db_path=db, scope="s", embedder=make_embedder())
        assert b.count() == 1
        assert b.search("Eintrag Prozessgrenze")[0]["text"].startswith("Eintrag")
        b.close()


class TestThreeLeges:
    def test_leg1_lexikalisch_ohne_embedding_modell(self, tmp_path):
        """Without an embedder retrieval must not die — BM25 is always there offline."""
        from core.memory_kepta import KeptaProvider

        p = KeptaProvider(db_path=str(tmp_path / "lex.db"), scope="s", embedder=None)
        p.store("Der Beamer im Besprechungszimmer hat ein defektes HDMI-Kabel")
        hits = p.search("HDMI-Kabel defekt")
        assert hits, "FTS5-Leg muss auch ohne Vektor-Leg treffen"
        assert p.stats()["vector_leg"] is False
        p.close()

    def test_leg2_vektor_ohne_woerterueberschneidung(self, kp):
        q = "gruenes Kaktusbeet"
        target = "Der Dienst antwortet auf dem Standard-Gateway"
        # Fake embedder: query and target are near-identical but share no word.
        kp._embedder = make_embedder(
            {
                q: [1.0] + [0.0] * (_DIMS - 1),
                target: [0.99, 0.1] + [0.0] * (_DIMS - 2),
            }
        )
        kp.store(target)
        kp.store("Der Nutzer isst gern Pfannkuchen am Sonntagmorgen")
        hits = kp.search(q, top_k=1)
        assert hits[0]["text"] == target

    def test_leg3_entity_ohne_texttreffer(self, kp):
        kp.store("Er beriet den Hof drei Jahr(zehnt) lang.", entities=["Gandalf"])
        hits = kp.search("gandalf")
        assert hits, "Entity-Leg muss einen reinen Namens-Query bedienen"
        assert hits[0]["text"].startswith("Er beriet")

    def test_rrf_zwei_leges_schlagen_eine(self, kp):
        kp.store("Der API-Gateway läuft auf Port 8765", entities=["Gateway"])
        kp.store("Ein Pfannkuchen-Rezept aus Omas Küche", entities=["Gateway"])
        hits = kp.search("Gateway Port 8765 API")
        assert hits[0]["text"].startswith("Der API-Gateway")

    def test_score_normiert_und_fallend(self, kp):
        """The score stays in (0,1] so get_context_injection() (threshold 0.3)
        does not filter away the whole memory — the quietest risk in this port."""
        kp.store("Der API-Gateway läuft auf Port 8765")
        kp.store("Der API-Gateway läuft auf Port 8765 und braucht einen Restart")
        hits = kp.search("API-Gateway Port 8765", top_k=5)
        scores = [h["score"] for h in hits]
        assert all(0.0 < s <= 1.0 for s in scores)
        assert scores == sorted(scores, reverse=True)
        assert max(scores) >= 0.3, "Top-Treffer muss den Injection-Threshold überleben"


class TestRetentionAndAccess:
    def test_retention_faktor_an_kepta_konstanten(self):
        from core.memory_kepta_schema import retention_factor

        # FLOOR + (1-FLOOR) * exp(-days / ((utility + min(access,10) + 0.1) * T_DAYS))
        floor, t_days = 0.2, 90.0
        for utility, access, days in ((0.5, 0, 0), (0.5, 3, 90), (0.9, 12, 400)):
            expected = floor + (1 - floor) * math.exp(
                -days / ((utility + min(access, 10) + 0.1) * t_days)
            )
            assert retention_factor(utility, access, days) == pytest.approx(expected)

    def test_retention_hat_floor_und_vergiessen_ist_monoton(self):
        from core.memory_kepta_schema import retention_factor

        assert retention_factor(0.5, 0, 0) == pytest.approx(1.0)
        assert retention_factor(0.5, 0, 10_000) == pytest.approx(0.2, abs=1e-3)
        assert retention_factor(0.5, 9, 10_000) > retention_factor(0.5, 0, 10_000)

    def test_recordAccess_hebt_hits_und_last_seen(self, kp):
        doc_id = kp.store("Der API-Gateway läuft auf Port 8765")
        before = kp.count_access(doc_id)
        kp.search("API-Gateway Port 8765")
        assert kp.count_access(doc_id) == before + 1
        row = next(e for e in kp.list_all() if e["id"] == doc_id)
        assert row["metadata"]["hits"] == before + 1

    def test_alter_eintrag_verliert_gegen_frischen(self, kp):
        fresh = kp.store("Der API-Gateway läuft auf Port 8765")
        old = kp.store("Der API-Gateway lief auf Port 8765")
        kp._db.execute(
            "UPDATE memories SET created_at = ?, last_access_at = ? WHERE id = ?",
            (time.time() - 700 * DAY, time.time() - 700 * DAY, old),
        )
        kp._db.commit()
        hits = kp.search("API-Gateway Port 8765")
        ids = [h["id"] for h in hits]
        assert ids.index(fresh) < ids.index(old)


class TestSupersedeAndSoftDelete:
    def test_supersede_behaelt_historie_und_ist_untten(self, kp):
        a = kp.store("Das Gateway läuft auf Port 8765")
        b = kp.store("Das Gateway läuft auf Port 9000")
        kp.supersede(a, "Das Gateway läuft auf Port 9000")
        hits = kp.search("Gateway Port")
        ids = [h["id"] for h in hits]
        assert b in ids
        row = kp._db.execute("SELECT superseded_by FROM memories WHERE id = ?", (a,)).fetchone()
        assert row["superseded_by"] == b
        assert ids.index(b) <= ids.index(a), "ersetzt darf nicht über dem Ersatz liegen"

    def test_supersede_auf_unbekannt_id_schluesselt(self, kp):
        with pytest.raises(KeyError):
            kp.supersede("deadbeefdeadbeef", "neuer Text")

    def test_delete_ist_soft_und_unknown_rauscht(self, kp):
        doc_id = kp.store("Eintrag, der verschwinden soll")
        kp.delete(doc_id)
        assert kp.count() == 0
        assert kp.search("Eintrag verschwinden") == []
        assert kp.list_all() == []
        assert kp.deleted_count() == 1
        row = kp._db.execute(
            "SELECT deleted_at FROM memories WHERE id = ?", (doc_id,)
        ).fetchone()
        assert row and row["deleted_at"], "soft delete muss auditierbar bleiben"
        with pytest.raises(KeyError):
            kp.delete(doc_id)

    def test_update_wahrt_id_metadata_und_reembeddet(self, kp):
        doc_id = kp.store("Das Gateway läuft auf Port 8765", {"source": "manual"})
        kp.update(doc_id, "Das Gateway läuft auf Port 9000")
        row = next(e for e in kp.list_all() if e["id"] == doc_id)
        assert row["metadata"]["source"] == "manual"
        assert row["metadata"]["updated_at"]
        assert "9000" in row["text"]

    def test_update_validiert_wie_die_route(self, kp):
        doc_id = kp.store("Bestehender Fakt")
        with pytest.raises(ValueError):
            kp.update(doc_id, "   ")
        with pytest.raises(KeyError):
            kp.update("ffffffffffffffff", "text")

    def test_near_duplicate_merged_statt_pollutiert(self, kp):
        a = kp.store("Der Nutzer mag Schwarzwaldwanderungen")
        b = kp.store("Der Nutzer mag Schwarzwaldwanderungen")
        assert b == a, "der Überlebende ist die ID des bestehenden Eintrags"
        assert kp.count() == 1
        row = next(e for e in kp.list_all() if e["id"] == a)
        assert row["metadata"]["hits"] >= 2
        assert row["metadata"]["last_seen"]

    def test_priority_louder_gewinnt_beim_merge(self, kp):
        a = kp.store("Der Nutzer mag Schwarzwaldwanderungen", {"priority": "high"})
        kp.store("Der Nutzer mag Schwarzwaldwanderungen", {"priority": "low"})
        row = next(e for e in kp.list_all() if e["id"] == a)
        assert row["metadata"]["priority"] == "high"


class TestScopeEnforcement:
    def test_scope_isoliert_zwei_Workspaces_in_einer_Datei(self, tmp_path):
        """Kepta does not enforce scope — Ephe has to, otherwise project A leaks
        into project B (W16 contract)."""
        from core.memory_kepta import KeptaProvider

        db = str(tmp_path / "shared.db")
        a = KeptaProvider(db_path=db, scope="alpha00000000000", embedder=make_embedder())
        b = KeptaProvider(db_path=db, scope="beta000000000000", embedder=make_embedder())
        a.store("Das Deploy-Token für Alpha ist pineapple-42")
        assert b.count() == 0
        assert b.search("Deploy-Token Alpha pineapple") == []
        assert a.count() == 1
        a.close()
        b.close()

    def test_clear_leer_scope_nicht_andere(self, tmp_path):
        from core.memory_kepta import KeptaProvider

        db = str(tmp_path / "shared2.db")
        a = KeptaProvider(db_path=db, scope="alpha", embedder=make_embedder())
        b = KeptaProvider(db_path=db, scope="beta", embedder=make_embedder())
        a.store("Alpha-Fakt")
        b.store("Beta-Fakt")
        a.clear()
        assert a.count() == 0
        assert b.count() == 1
        a.close()
        b.close()


class TestSchema:
    def test_schema_version_und_meta_tabelle(self, kp):
        row = kp._db.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        assert int(row["value"]) == 2

    def test_fts_ist_external_content_und_konsistent(self, kp):
        doc_id = kp.store("Der Beamer im Besprechungszimmer ist defekt")
        assert kp._db.execute(
            "SELECT content FROM memories_fts WHERE rowid = "
            "(SELECT rid FROM memories WHERE id = ?)",
            (doc_id,),
        ).fetchone()
        kp.update(doc_id, "Der Beamer im Besprechungszimmer braucht eine neue Lampe")
        hits = kp.search("Beamer neue Lampe")
        assert hits and "Lampe" in hits[0]["text"]
        kp.delete(doc_id)
        assert kp.search("Besprechungszimmer neue Lampe") == []

    def test_tags_und_typ_sind_persistiert(self, kp):
        doc_id = kp.store(
            "Deploy: erst migrate, dann restart",
            {"source": "agent"},
            memory_type="procedural",
            tags=["deploy", "runbook"],
        )
        row = kp._db.execute(
            "SELECT type, tags FROM memories WHERE id = ?", (doc_id,)
        ).fetchone()
        assert row["type"] == "procedural"
        assert json.loads(row["tags"]) == ["deploy", "runbook"]

    def test_unbekannter_typ_wird_semantisch(self, kp):
        doc_id = kp.store("Ein Fakt", memory_type="quatsch")
        row = kp._db.execute("SELECT type FROM memories WHERE id = ?", (doc_id,)).fetchone()
        assert row["type"] == "semantic"


class TestFtsLimitBinding:
    def test_leg_fts_binds_the_limit_instead_of_pasting_it_into_the_sql(self):
        """Given a query that reaches FTS5, when leg_fts runs, then LIMIT is a
        bound parameter — an interpolated integer would sit next to text the
        caller controlled, and SQLite would silently accept the string."""
        import sqlite3

        from core.memory_kepta_ranking import LEG_LIMIT, leg_fts

        class RecordingConnection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple]] = []

            def execute(self, sql, params=()):
                self.calls.append((sql, tuple(params)))
                raise sqlite3.OperationalError("no such table: memories_fts")

        db = RecordingConnection()
        assert leg_fts(db, "scope-a", "alpha beta", {}, fts_enabled=True) == []

        sql, params = db.calls[0]
        assert "LIMIT ?" in sql
        assert f"LIMIT {LEG_LIMIT}" not in sql
        assert params == ('"alpha" OR "beta"', "scope-a", LEG_LIMIT)
