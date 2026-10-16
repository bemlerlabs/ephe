"""R25: full-text search over sessions (SQLite FTS5) across messages + session titles.

Budget: a search over 1k+ messages stays under 50 ms (p95) — see docs/LATENCY_BUDGETS.md.
The index is incremental (mtime-based), hermetic through the EPHE_SEARCH_DB env.

The budgets in this file are measured in the serial timing segment: CI run 37974211156
(2026-10-09) lost the route's 200 ms budget at 324.7 ms inside the `-n auto` leg while the
same response body asserted green. `test_search_budget_1000_messages_under_50ms_p95` runs in
that segment by node id, and the route budget moved to tests/test_wall_clock_budgets.py, so
what stays here is the shape of `elapsed_ms`. See tests/test_timing_assertion_guard.py.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path

import pytest

import core.multi_session as ms
from core.session_search import (
    _INDEX_FORMAT_VERSION,
    clear_index,
    drop_session,
    index_sessions,
    rebuild_index,
    search_messages,
)


@pytest.fixture(autouse=True)
def _tmp_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "sessions"
    d.mkdir(parents=True)
    monkeypatch.setattr(ms, "SESSIONS_DIR", d)
    monkeypatch.setattr(ms, "REGISTRY_FILE", d / "registry.json")
    monkeypatch.setenv("EPHE_SEARCH_DB", str(tmp_path / "search.db"))
    return d


def _seed_session(title: str, turns: list[tuple[str, str]]) -> str:
    sid = ms.create_session(title)["id"]
    msgs = []
    for user, assistant in turns:
        msgs.append({"role": "user", "content": user})
        msgs.append({"role": "assistant", "content": assistant})
    ms.save_messages(sid, msgs)  # type: ignore[arg-type]
    return sid


# Index + search


def test_index_and_search_finds_content_with_session_title() -> None:
    sid = _seed_session(
        "Black Forest Planung",
        [("What about the API-Key?", "The API-Key lives in the keyring."),
         ("Noch was?", "Nein, sonst nichts.")],
    )
    _seed_session("Küche", [("Rezept?", "Käsespätzle.")])

    indexed = index_sessions()
    assert indexed >= 2

    hits = search_messages("API-Key")
    assert hits, "Treffer erwartet"
    top = hits[0]
    assert top["session_id"] == sid
    assert top["session_title"] == "Black Forest Planung"
    assert top["role"] == "user"
    assert "API-Key" in top["snippet"].replace("<mark>", "").replace("</mark>", "")


def test_search_is_case_insensitive_and_role_covered() -> None:
    _seed_session("a", [("Frage", "Der SCHWARZWALD ist grün.")])
    index_sessions()
    hits = search_messages("schwarzwald")
    assert any(h["role"] == "assistant" for h in hits)


def test_search_includes_session_title_words() -> None:
    _seed_session("Steuererklärung 2026", [("Was war das?", "Dokumente.")])
    index_sessions()
    hits = search_messages("Steuererklärung")
    assert hits  # the session title is searched too


def test_incremental_reindex_on_mtime_change() -> None:
    sid = _seed_session("t", [("a", "b")])
    index_sessions()
    assert search_messages("neuwort") == []

    time.sleep(0.02)
    msgs = [{"role": "user", "content": "the NEUWORT is here"}]
    ms.save_messages(sid, msgs)
    index_sessions()
    hits = search_messages("NEUWORT")
    assert len(hits) == 1


def test_deleted_session_disappears_from_index() -> None:
    sid = _seed_session("t", [("x", "SUCHWORT")])
    index_sessions()
    assert search_messages("SUCHWORT")
    ms.delete_session(sid)
    index_sessions()
    assert search_messages("SUCHWORT") == []


def test_empty_and_malformed_queries_are_graceful() -> None:
    _seed_session("t", [("a", "b")])
    index_sessions()
    assert search_messages("") == []
    assert search_messages("   ") == []
    # FTS5 syntax explosion characters → no crash, phrase fallback
    assert isinstance(search_messages('neun:( "odd'), list)
    assert isinstance(search_messages("a AND OR NOT ("), list)


def test_result_shape_is_stable() -> None:
    _seed_session("Titel", [("Frage X", "Antwort Y")])
    index_sessions()
    hits = search_messages("Frage")
    assert hits
    assert set(hits[0]) == {
        "session_id",
        "session_title",
        "role",
        "snippet",
        "content",
        "updated_at",
    }


# Latency budget (roadmap: 1k messages < 50 ms)


def test_search_budget_1000_messages_under_50ms_p95() -> None:
    """Serial timing segment only: deselected from the `-n auto` leg by node id."""
    turns = [
        (f"Frage Nummer {i} about Projekte", f"Antwort Nummer {i} with plenty of detail.")
        for i in range(500)  # 1000 messages
    ]
    _seed_session("Budget-Session", turns)
    index_sessions()

    samples: list[float] = []
    for i in range(20):
        start = time.perf_counter()
        search_messages(f"Projekte Nummer {i % 100}")
        samples.append((time.perf_counter() - start) * 1000)
    samples.sort()
    p95 = samples[int(len(samples) * 0.95) - 1]
    assert p95 < 50, f"search too slow: p95={p95:.1f} ms over 1000 messages"


def test_clear_index_resets_everything() -> None:
    _seed_session("t", [("a", "b")])
    index_sessions()
    clear_index()
    # Direct DB check (search_messages would re-index self-healing on its own)
    conn = sqlite3.connect(os.environ["EPHE_SEARCH_DB"])
    count = conn.execute("SELECT COUNT(*) FROM messages_fts").fetchone()[0]
    conn.close()
    assert count == 0


# Index rebuild path


def test_corrupt_search_db_is_rebuilt_not_fatal() -> None:
    """A corrupt index file is derived data: it is dropped and rebuilt, never fatal."""
    sid = _seed_session("Rettung", [("Frage", "The RETTUNGSWORT is here.")])
    Path(os.environ["EPHE_SEARCH_DB"]).write_bytes(b"not a sqlite file")

    hits = search_messages("RETTUNGSWORT")  # must not raise on the broken DB
    assert any(h["session_id"] == sid for h in hits)


def test_format_version_bump_forces_full_rebuild() -> None:
    """A stale index from an older format must be rebuilt even though no file changed."""
    sid = _seed_session("Format", [("Frage", "The FORMATWORT is here.")])
    index_sessions()

    # A stale index: rows gone, fingerprints kept, so the mtime-driven incremental
    # run would skip the (unchanged) file forever. Only the version mismatch rebuilds.
    conn = sqlite3.connect(os.environ["EPHE_SEARCH_DB"])
    conn.execute("DELETE FROM messages_fts")
    conn.execute("UPDATE index_meta SET value = '1' WHERE key = 'format_version'")
    conn.commit()
    conn.close()

    hits = search_messages("FORMATWORT")
    assert any(h["session_id"] == sid for h in hits)

    # Negative control: at the current format version the same wipe is NOT recovered
    # incrementally — the version bump is what triggers the rebuild.
    conn = sqlite3.connect(os.environ["EPHE_SEARCH_DB"])
    assert conn.execute(
        "SELECT value FROM index_meta WHERE key = 'format_version'"
    ).fetchone()[0] == str(_INDEX_FORMAT_VERSION)
    conn.execute("DELETE FROM messages_fts")
    conn.commit()
    conn.close()
    assert search_messages("FORMATWORT") == []


def test_unparseable_session_file_drops_stale_rows_and_is_recorded() -> None:
    """A file that turns malformed loses its rows and is not re-read every search."""
    sid = _seed_session("Kaputt", [("Frage", "The ALTWORT is here.")])
    index_sessions()
    assert search_messages("ALTWORT")

    path = Path(ms.SESSIONS_DIR) / f"{sid}.json"
    time.sleep(0.02)
    path.write_text("{ kaputt", encoding="utf-8")

    assert index_sessions() == 0  # nothing indexable in this run
    assert search_messages("ALTWORT") == []  # the stale rows are gone
    assert index_sessions() == 0  # recorded → an unchanged broken file is skipped

    conn = sqlite3.connect(os.environ["EPHE_SEARCH_DB"])
    recorded = conn.execute(
        "SELECT 1 FROM indexed_files WHERE filename = ?", (f"{sid}.json",)
    ).fetchone()
    conn.close()
    assert recorded is not None  # the fingerprint is what stops the re-read


def test_rebuild_index_reindexes_unchanged_files() -> None:
    """rebuild_index() re-indexes files the incremental run would skip."""
    sid = _seed_session("Rebuild", [("Frage", "The REBUILDWORT is here.")])
    index_sessions()
    assert index_sessions() == 0  # steady state: nothing changed

    assert rebuild_index() >= 1  # full rebuild despite no file change
    assert any(h["session_id"] == sid for h in search_messages("REBUILDWORT"))
    assert index_sessions() == 0  # idempotent: back to the no-op steady state


def test_drop_session_removes_rows_and_fingerprint() -> None:
    """The per-session maintenance path clears both tables (used when a file is deleted)."""
    sid = _seed_session("Weg", [("Frage", "The WEGWORT is here.")])
    index_sessions()
    assert search_messages("WEGWORT")

    drop_session(sid)
    # Direct DB check: search_messages would re-index the still-present file.
    conn = sqlite3.connect(os.environ["EPHE_SEARCH_DB"])
    rows = conn.execute(
        "SELECT COUNT(*) FROM messages_fts WHERE session_id = ?", (sid,)
    ).fetchone()[0]
    files = conn.execute(
        "SELECT COUNT(*) FROM indexed_files WHERE filename = ?", (f"{sid}.json",)
    ).fetchone()[0]
    conn.close()
    assert rows == 0
    assert files == 0


# Route


def test_search_route_returns_results_and_elapsed_field(client_factory) -> None:
    from fastapi.testclient import TestClient

    _seed_session("Route-Session", [("The GEHEIMWORT is here", "Antwort")])
    from server.main import create_app

    with client_factory() as c:
        resp = c.get("/api/search", params={"q": "GEHEIMWORT"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1
        assert body["results"][0]["session_title"] == "Route-Session"
        # The route always reports its own duration. The 200 ms budget on this field is a
        # wall-clock measurement and lives in tests/test_wall_clock_budgets.py.
        assert isinstance(body["elapsed_ms"], (int, float))
        assert body["elapsed_ms"] >= 0


def test_search_route_validates_query(client_factory) -> None:
    from server.main import create_app

    with client_factory() as c:
        assert c.get("/api/search", params={"q": ""}).status_code == 422


@pytest.fixture()
def client_factory(tmp_path, monkeypatch):
    import os

    os.environ["EPHE_MEMORY_DIR"] = os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
    os.environ["EPHE_PROFILE_PATH"] = os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
    os.environ["EPHE_CORRECTIONS_PATH"] = os.environ["EPHE_CORRECTIONS_PATH"] = str(tmp_path / "corrections.md")
    os.environ["EPHE_FEEDBACK_DIR"] = os.environ["EPHE_FEEDBACK_DIR"] = str(tmp_path)
    os.environ["EPHE_SKILLS_DIR"] = os.environ["EPHE_SKILLS_DIR"] = str(tmp_path / "skills")

    from contextlib import contextmanager

    @contextmanager
    def _factory():
        from fastapi.testclient import TestClient
        from server.main import create_app

        with TestClient(create_app()) as c:
            yield c

    return _factory
