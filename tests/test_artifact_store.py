"""tests/test_artifact_store.py — R17 Artifact Hub: persistent library.

Given/When/Then. By default the DB lives under ~/.ephe/artifacts.db
(gitignored-local per release bar); tests redirect it via monkeypatch.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from core import artifact_store
from core import artifact_workbench as workbench


@pytest.fixture(autouse=True)
def store_db(tmp_path, monkeypatch):
    db = tmp_path / "artifacts.db"
    monkeypatch.setattr(artifact_store, "ARTIFACTS_DB", db)
    return db


def _file(tmp_path, name, content=b"x"):
    p = tmp_path / name
    p.write_bytes(content)
    return str(p)


class TestRegister:
    def test_given_new_artifact_when_registered_then_row_is_complete(self, tmp_path):
        row = artifact_store.register_artifact(
            path=_file(tmp_path, "brief.pdf"), kind="pdf", session_id="s1", topic="Kurzbriefing"
        )
        assert row["name"] == "brief.pdf"
        assert row["kind"] == "pdf"
        assert row["session_id"] == "s1"
        assert row["topic"] == "Kurzbriefing"
        assert row["version"] == 1
        assert row["root_id"] == row["id"]
        assert row["size"] == 1

    def test_given_same_name_same_session_when_registered_then_version_bumps_same_root(self, tmp_path):
        gen = tmp_path / "gen"
        gen.mkdir()
        report = gen / "report.pdf"
        report.write_bytes(b"a")
        first = artifact_store.register_artifact(path=str(report), kind="pdf", session_id="s1", topic="Report")
        report.write_bytes(b"b")  # Regenerating overwrites the same path/name
        second = artifact_store.register_artifact(path=str(report), kind="pdf", session_id="s1", topic="Report")
        assert second["version"] == 2
        assert second["root_id"] == first["root_id"]
        # Other session = its own version line
        other = artifact_store.register_artifact(path=_file(tmp_path, "v3", b"c"), kind="pdf", session_id="s2", topic="Report")
        assert other["version"] == 1 and other["root_id"] != first["root_id"]

    def test_given_same_name_other_kind_when_registered_then_separate_line(self, tmp_path):
        """brief.svg ≠ brief.pdf — versioning follows name+kind, not name alone."""
        a = artifact_store.register_artifact(path=_file(tmp_path, "mixed", b"a"), kind="svg", session_id="s1")
        b = artifact_store.register_artifact(path=_file(tmp_path, "mixed", b"b"), kind="pdf", session_id="s1")
        assert a["version"] == 1 and b["version"] == 1


class TestListSearch:
    def test_given_several_artifacts_when_listed_then_newest_first(self, tmp_path):
        artifact_store.register_artifact(path=_file(tmp_path, "a.pdf"), kind="pdf", session_id="s1")
        artifact_store.register_artifact(path=_file(tmp_path, "b.svg"), kind="svg", session_id="s1")
        rows = artifact_store.list_artifacts()
        assert [r["name"] for r in rows] == ["b.svg", "a.pdf"]

    def test_given_query_when_searched_then_matches_name_and_topic(self, tmp_path):
        artifact_store.register_artifact(path=_file(tmp_path, "q3-report.pdf"), kind="pdf", session_id="s1", topic="Umsatz Q3")
        artifact_store.register_artifact(path=_file(tmp_path, "pic.png"), kind="png", session_id="s1")
        assert len(artifact_store.list_artifacts(q="q3")) == 1
        assert len(artifact_store.list_artifacts(q="umsatz")) == 1  # Topic, case-insensitive
        assert len(artifact_store.list_artifacts(kind="png")) == 1
        assert len(artifact_store.list_artifacts(favorite=True)) == 0

    def test_given_favorite_filter_when_listed_then_only_favorites(self, tmp_path):
        row = artifact_store.register_artifact(path=_file(tmp_path, "f.pdf"), kind="pdf", session_id="s1")
        artifact_store.set_favorite(row["id"], True)
        rows = artifact_store.list_artifacts(favorite=True)
        assert len(rows) == 1 and rows[0]["id"] == row["id"]

    def test_given_tags_when_set_then_roundtrip_as_list(self, tmp_path):
        row = artifact_store.register_artifact(path=_file(tmp_path, "t.pdf"), kind="pdf", session_id="s1")
        artifact_store.set_tags(row["id"], ["board", "q3"])
        tags = json.loads(artifact_store.list_artifacts()[0]["tags"])
        assert tags == ["board", "q3"]


class TestVersionsAndDelete:
    def test_given_version_line_when_queried_then_oldest_first(self, tmp_path):
        # Regenerate line: same (name, kind, session), new path/content
        gen = tmp_path / "gen1"
        gen.mkdir()
        p1 = gen / "report.pdf"
        p1.write_bytes(b"a")
        first = artifact_store.register_artifact(path=str(p1), kind="pdf", session_id="s1")
        p2 = gen / "report_v2.pdf"
        p2.write_bytes(b"b")
        second = artifact_store.register_artifact(path=str(p2), kind="pdf", session_id="s1", topic="same-name")
        # Force the same name: the second run really does overwrite the same name
        import shutil
        shutil.move(str(p2), str(gen / "report.pdf"))
        second = artifact_store.register_artifact(path=str(gen / "report.pdf"), kind="pdf", session_id="s1")
        versions = artifact_store.get_versions(first["root_id"])
        assert [v["version"] for v in versions] == [1, 2]
        assert versions[-1]["id"] == second["id"]

    def test_given_delete_without_file_flag_when_deleted_then_file_survives(self, tmp_path):
        path = _file(tmp_path, "keep.pdf")
        row = artifact_store.register_artifact(path=path, kind="pdf", session_id="s1")
        artifact_store.delete_artifact(row["id"])
        assert artifact_store.list_artifacts() == []
        import pathlib

        assert pathlib.Path(path).exists()

    def test_given_delete_inside_allowed_root_when_flag_set_then_file_removed(self, tmp_path, monkeypatch):
        import pathlib

        import core.tools.base as base

        monkeypatch.setattr(base, "_get_allowed_roots", lambda: [tmp_path])
        path = _file(tmp_path, "gone.pdf")
        row = artifact_store.register_artifact(path=path, kind="pdf", session_id="s1")
        removed = artifact_store.delete_artifact(row["id"], delete_file=True)
        assert removed is True
        assert not pathlib.Path(path).exists()

    def test_given_delete_outside_allowed_roots_when_flag_set_then_refused(self, tmp_path, monkeypatch):
        import core.tools.base as base

        monkeypatch.setattr(base, "_get_allowed_roots", lambda: [tmp_path / "elsewhere"])
        path = _file(tmp_path, "protected.pdf")
        row = artifact_store.register_artifact(path=path, kind="pdf", session_id="s1")
        removed = artifact_store.delete_artifact(row["id"], delete_file=True)
        assert removed is False, "THEN: Datei-Löschung außerhalb der Roots wird verweigert"
        assert artifact_store.list_artifacts() == [], "THEN: der DB-Eintrag ist trotzdem weg"

    def test_given_corrupt_db_when_accessed_then_recovers(self, store_db):
        store_db.write_bytes(b"not a sqlite database at all")
        assert artifact_store.list_artifacts() == []
        row = artifact_store.register_artifact(path="/tmp/x.pdf", kind="pdf", session_id="s1")
        assert row["name"] == "x.pdf"


class TestIdentityAndRetention:
    """A0 + the owner's deadline rule (2026-10-06): 30 days, and before any delete
    stands an answer, never a background branch."""

    @pytest.fixture
    def bench(self, tmp_path, monkeypatch):
        """The workbench sits in tmp per test — workbench_dir follows EPHE_CONFIG_DIR."""
        root = tmp_path / "ephe-home"
        (root / "artifacts" / "s1").mkdir(parents=True)
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(root))
        return root / "artifacts"

    def _age(self, artifact_id: str, days: int) -> None:
        """Simulated day jump: move the deadline into the past without waiting."""
        past = workbench.iso(datetime.now(timezone.utc) - timedelta(days=days))
        artifact_store._write(
            "UPDATE artifacts SET expires_at = ? WHERE id = ?", (past, artifact_id)
        )

    def test_given_old_database_when_opened_then_new_columns_migrate_and_rows_survive(self, store_db, tmp_path):
        conn = sqlite3.connect(store_db)
        conn.executescript(
            "CREATE TABLE artifacts (id TEXT PRIMARY KEY, root_id TEXT NOT NULL, version INTEGER DEFAULT 1, "
            "session_id TEXT DEFAULT '', name TEXT NOT NULL, path TEXT NOT NULL, kind TEXT DEFAULT 'file', "
            "size INTEGER DEFAULT 0, topic TEXT DEFAULT '', created_at TEXT NOT NULL, favorite INTEGER DEFAULT 0, "
            "tags TEXT DEFAULT '[]');"
        )
        conn.execute(
            "INSERT INTO artifacts (id, root_id, name, path, kind, created_at) VALUES "
            "('alt','alt','alt.pdf','/tmp/alt.pdf','pdf','2026-01-01T00:00:00+00:00')"
        )
        conn.commit()
        conn.close()

        rows = artifact_store.list_artifacts()
        assert [r["id"] for r in rows] == ["alt"]
        assert rows[0]["expires_at"] is None, "ein Eintrag von vor der Frist läuft nie ab"
        assert rows[0]["keep"] is False and rows[0]["content_hash"] == ""

    def test_given_file_in_workbench_when_registered_then_it_carries_a_deadline(self, bench):
        p = bench / "s1" / "brief.pdf"
        p.write_bytes(b"x")
        row = artifact_store.register_artifact(path=str(p), kind="pdf", session_id="s1")
        assert row["expires_at"] is not None
        assert row["origin_path"] == str(p)
        assert row["content_hash"].startswith("sha256:")

    def test_given_file_in_user_folder_when_registered_then_ephe_sets_no_deadline(self, tmp_path):
        """The disk belongs to the user. A deadline that could delete there is
        not tidying up, it is an access."""
        row = artifact_store.register_artifact(path=_file(tmp_path, "down.pdf"), kind="pdf", session_id="s1")
        assert row["expires_at"] is None
        assert workbench.expiry_due() == []

    def test_given_workbench_copy_past_its_deadline_when_asked_then_it_is_due(self, bench):
        p = bench / "s1" / "alt.pdf"
        p.write_bytes(b"payload")
        row = artifact_store.register_artifact(path=str(p), kind="pdf", session_id="s1")
        assert workbench.expiry_due() == []
        self._age(row["id"], 31)
        due = workbench.expiry_due()
        assert [d["id"] for d in due] == [row["id"]]

    def test_given_due_copy_when_answered_keep_then_nothing_is_due_and_the_file_stays(self, bench):
        p = bench / "s1" / "keepme.pdf"
        p.write_bytes(b"payload")
        row = artifact_store.register_artifact(path=str(p), kind="pdf", session_id="s1")
        self._age(row["id"], 31)
        result = workbench.answer_expiry([row["id"]], "keep")
        assert result["kept"] == [row["id"]]
        assert workbench.expiry_due() == []
        assert p.exists()
        assert artifact_store.get_artifact(row["id"])["keep"] is True

    def test_given_due_copies_when_answered_delete_then_rows_and_bytes_are_gone(self, bench, monkeypatch):
        import core.tools.base as base

        monkeypatch.setattr(base, "_get_allowed_roots", lambda: [bench.parent])
        paths = []
        for name in ("a.pdf", "b.pdf"):
            p = bench / "s1" / name
            p.write_bytes(b"payload")
            paths.append(p)
            row = artifact_store.register_artifact(path=str(p), kind="pdf", session_id="s1")
            self._age(row["id"], 31)
        ids = [artifact_store.list_artifacts()[i]["id"] for i in range(2)]
        result = workbench.answer_expiry(ids, "delete")
        assert sorted(result["deleted"]) == sorted(ids), "mehrere auf eine Antwort"
        assert not any(p.exists() for p in paths)
        assert artifact_store.list_artifacts() == []

    def test_given_adopted_copy_when_expiry_deletes_then_the_users_copy_survives(self, bench, monkeypatch):
        """A4s adoption in a single test: the adopted file never disappears —
        at most the redundant workbench copy gets deleted."""
        import core.tools.base as base

        target = bench.parent / "platte"
        target.mkdir()
        monkeypatch.setattr(base, "_get_allowed_roots", lambda: [bench.parent])
        p = bench / "s1" / "deck.pdf"
        p.write_bytes(b"payload")
        adopted = target / "deck.pdf"
        adopted.write_bytes(b"payload")
        row = artifact_store.register_artifact(path=str(p), kind="pdf", session_id="s1")
        workbench.set_adopted(row["id"], str(adopted))
        self._age(row["id"], 31)
        workbench.answer_expiry([row["id"]], "delete")
        assert adopted.exists()
        assert not p.exists()

    def test_given_unanswered_artifact_when_expiry_runs_then_it_never_deletes_on_its_own(self, bench):
        """There is no delete branch without an answer. The deadline alone changes
        nothing about the file — not even after 300 days."""
        p = bench / "s1" / "wait.pdf"
        p.write_bytes(b"payload")
        row = artifact_store.register_artifact(path=str(p), kind="pdf", session_id="s1")
        self._age(row["id"], 300)
        assert len(workbench.expiry_due()) == 1
        assert p.exists()
        assert artifact_store.get_artifact(row["id"]) is not None

    def test_given_favorited_or_unexpiring_id_when_answered_then_respected(self, bench, tmp_path):
        p = bench / "s1" / "fav.pdf"
        p.write_bytes(b"x")
        fav = artifact_store.register_artifact(path=str(p), kind="pdf", session_id="s1")
        artifact_store.set_favorite(fav["id"], True)
        self._age(fav["id"], 31)
        assert workbench.expiry_due() == [], "ein Stern ist auch ein Schutz gegen die Frist"
        outside = artifact_store.register_artifact(path=_file(tmp_path, "andere.pdf"), kind="pdf", session_id="s2")
        result = workbench.answer_expiry([outside["id"]], "keep")
        assert result["skipped"] == [outside["id"]], "ohne Frist keine Frage"

    def test_given_unknown_action_when_answered_then_value_error(self, tmp_path):
        with pytest.raises(ValueError):
            workbench.answer_expiry(["x"], "trash")

    def test_given_artifact_when_targeted_by_id_then_path_is_checked_and_returned(self, tmp_path, monkeypatch):
        import core.tools.base as base

        monkeypatch.setattr(base, "_get_allowed_roots", lambda: [tmp_path])
        row = artifact_store.register_artifact(path=_file(tmp_path, "ziel.pdf", b"bytes"), kind="pdf", session_id="s1")
        assert workbench.artifact_target(row["id"]) == (tmp_path / "ziel.pdf").resolve()
        assert workbench.artifact_target("nie-registriert") is None

    def test_given_path_outside_allowed_roots_when_targeted_then_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr("core.tools.base._get_allowed_roots", lambda: [tmp_path / "andere"])
        row = artifact_store.register_artifact(path=_file(tmp_path, "fremd.pdf"), kind="pdf", session_id="s1")
        assert workbench.artifact_target(row["id"]) is None

    def test_given_view_when_marked_then_the_row_remembers_it(self, tmp_path):
        row = artifact_store.register_artifact(path=_file(tmp_path, "v.pdf"), kind="pdf", session_id="s1")
        assert row["viewed_at"] is None
        workbench.mark_viewed(row["id"])
        assert artifact_store.get_artifact(row["id"])["viewed_at"]

    def test_given_corrupt_database_when_recovered_then_the_unreadable_file_survives(self, store_db):
        """§5.1-4: a reset that also took the index was bearable as long as the
        file lay with the user. With workbench copies it is data loss."""
        store_db.write_bytes(b"not a sqlite database at all")
        assert artifact_store.list_artifacts() == []
        kept = [p.name for p in store_db.parent.iterdir()]
        assert any("unusable" in name for name in kept), kept

    def test_given_provenance_keys_when_registered_then_they_roundtrip(self, tmp_path):
        row = artifact_store.register_artifact(
            path=_file(tmp_path, "prov.pdf"), kind="pdf", session_id="s1",
            call_id="call-7", args_hash="aabbccddeeff0011",
        )
        back = artifact_store.get_artifact(row["id"])
        assert (back["call_id"], back["args_hash"]) == ("call-7", "aabbccddeeff0011")


class TestSearchPerformance:
    def test_given_1000_artifacts_when_searched_then_under_50ms(self, store_db):
        """R17-Acceptance: search < 50 ms at 1k artifacts (measured, not
        claimed). Bulk insert via executemany for setup speed."""
        import time

        base = time.time()
        rows = []
        for i in range(1000):
            created = datetime.fromtimestamp(base - i, tz=timezone.utc).isoformat(timespec="seconds")
            rows.append((f"id{i}", f"root{i}", 1, f"s{i % 10}", f"report-{i}.pdf",
                         f"/tmp/report-{i}.pdf", "pdf", 10, f"Topic {i}", created, 0, "[]"))
        conn = sqlite3.connect(store_db)
        conn.executescript(artifact_store._SCHEMA)
        conn.executemany(
            "INSERT INTO artifacts (id, root_id, version, session_id, name, path, kind, size, topic, created_at, favorite, tags) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.commit()
        conn.close()

        artifact_store.list_artifacts()  # warm-up
        start = time.perf_counter()
        result = artifact_store.list_artifacts(q="report-9")
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert len(result) >= 1
        assert elapsed_ms < 50, f"THEN: Suche dauerte {elapsed_ms:.1f} ms (Limit 50 ms)"
