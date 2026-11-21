"""W7-13: the session index rebuild is deterministic — a freshly built index equals the live one.

Derived data must not drift. After any sequence of session operations (a message
save, a title rename, a delete) the index a running process kept up to date has to
hold the same rows a from-scratch rebuild would produce, byte for byte. The live
path is exercised through the incremental ``index_sessions``; the fresh path through
``rebuild_index`` into a second database, so the comparison cannot pass by comparing
one file against itself.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

import core.multi_session as ms
from core.session_search import index_sessions, rebuild_index, search_messages


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "sessions"
    d.mkdir(parents=True)
    monkeypatch.setattr(ms, "SESSIONS_DIR", d)
    monkeypatch.setattr(ms, "REGISTRY_FILE", d / "registry.json")
    monkeypatch.setenv("EPHE_SEARCH_DB", str(tmp_path / "live.db"))
    return d


def _seed(title: str, turns: list[tuple[str, str]]) -> str:
    sid = ms.create_session(title)["id"]
    msgs = []
    for user, assistant in turns:
        msgs.append({"role": "user", "content": user})
        msgs.append({"role": "assistant", "content": assistant})
    ms.save_messages(sid, msgs)  # type: ignore[arg-type]
    return sid


def _dump(db: Path) -> tuple[list[tuple], list[tuple]]:
    """Index content (rows + fingerprints) in a stable order, for equality tests."""
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT session_id, role, content, title FROM messages_fts "
            "ORDER BY session_id, role, content, title"
        ).fetchall()
        files = conn.execute(
            "SELECT filename, size, round(mtime, 6) FROM indexed_files ORDER BY filename"
        ).fetchall()
    finally:
        conn.close()
    return rows, files


def _live_db() -> Path:
    return Path(os.environ["EPHE_SEARCH_DB"])


def test_fresh_rebuild_equals_live_index(tmp_path: Path) -> None:
    """A rebuild after a full operation sequence reproduces the live index exactly."""
    a = _seed("Alpha", [("Frage A", "The ALPHAWORT is here")])
    _seed("Beta", [("Frage B", "The BETAWORT is here")])
    _seed("Gamma", [("Frage C", "The GAMMAWORT is here")])
    index_sessions()  # live build

    ms.save_messages(  # a message save changes the session file
        a,
        [{"role": "user", "content": "The ALPHAWORT is here"},
         {"role": "assistant", "content": "appended"}],  # type: ignore[arg-type]
    )
    index_sessions()

    ms.rename_session(a, "Alpha Zwei")  # a registry-only change
    index_sessions()

    first = ms.create_session("Beta")["id"]
    ms.delete_session(first)  # its row was dropped after this exact id
    ms.create_session("Delta")  # an empty session (no messages, fingerprint only)
    index_sessions()

    fresh = tmp_path / "fresh.db"
    rebuild_index(ms.SESSIONS_DIR, fresh)

    live_rows, live_files = _dump(_live_db())
    assert live_rows, "the comparison must not be vacuous"
    assert _dump(_live_db()) == _dump(fresh)


def test_rebuild_is_deterministic(tmp_path: Path) -> None:
    """Two rebuilds of the same session folder produce identical indexes."""
    _seed("Alpha", [("q", "The ALPHAWORT is here")])
    _seed("Beta", [("q", "The BETAWORT is here")])

    one = tmp_path / "one.db"
    two = tmp_path / "two.db"
    rebuild_index(ms.SESSIONS_DIR, one)
    rebuild_index(ms.SESSIONS_DIR, two)

    assert _dump(one)[0], "the comparison must not be vacuous"
    assert _dump(one) == _dump(two)


def test_rename_refreshes_the_live_index_without_a_file_change() -> None:
    """A rename is a registry input: the live index must show the new title at once."""
    sid = _seed("Alpha", [("q", "The ALPHAWORT is here")])
    index_sessions()
    session_file = Path(ms.SESSIONS_DIR) / f"{sid}.json"
    before = session_file.stat().st_mtime

    ms.rename_session(sid, "Alpha Zwei")
    # The rename must leave the session file untouched, so the refresh below can
    # only come from the registry rather than from a file-fingerprint change.
    assert session_file.stat().st_mtime == before

    hits = search_messages("ALPHAWORT")
    assert hits and hits[0]["session_title"] == "Alpha Zwei"
    assert index_sessions() == 0  # the refresh settles: no perpetual re-index


def test_registry_refresh_still_drops_a_deleted_session() -> None:
    """The stale-marking refresh keeps the filenames, so a removed file is still dropped."""
    a = _seed("Alpha", [("q", "The ALPHAWORT is here")])
    b = _seed("Beta", [("q", "The BETAWORT is here")])
    index_sessions()
    assert search_messages("BETAWORT")

    (Path(ms.SESSIONS_DIR) / f"{b}.json").unlink()  # the file is gone, the registry still lists it
    ms.rename_session(a, "Alpha Zwei")  # forces the registry refresh pass
    index_sessions()

    assert search_messages("BETAWORT") == []
    conn = sqlite3.connect(str(_live_db()))
    try:
        left = conn.execute(
            "SELECT COUNT(*) FROM indexed_files WHERE filename = ?", (f"{b}.json",)
        ).fetchone()[0]
    finally:
        conn.close()
    assert left == 0
