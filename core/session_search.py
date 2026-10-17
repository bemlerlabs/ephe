"""Ephe — session_search: full-text search across all sessions (R25).

SQLite FTS5 (stdlib sqlite3, no new dependency) over the message files
in ``~/.ephe/sessions/``. The index is **incremental and mtime-driven**:
per search it checks only once (cheaply) which session files changed since
the last index run; unchanged ones are not touched.

The index is derived data, so the rebuild path is explicit and self-healing
(`rebuild_index`, or implicitly on a format-version bump / a corrupt DB):
a session file that cannot be parsed has its stale rows dropped and its
fingerprint recorded, so it is not re-read on every search. The registry is
an index input too (a title is read from it), so a registry change refreshes
the affected rows rather than waiting for a rename to look like a rebuild.

Entry point in the UI: command palette with the prefix ``inhalt:…`` (R25).  # language-gate: ignore (quoted palette prefix string — a literal this document describes, not prose)

Honest limits (documented in docs/LATENCY_BUDGETS.md):
- The index run itself does NOT count toward the search budget (it is
  O(changed sessions), typically 0 files).
- FTS5 syntax explosion characters (parentheses, binary operators without an
  operand) get quoted as a phrase fallback — the search never crashes.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

# FTS5 syntax: only queries made of so-called safe tokens go raw into MATCH;
# everything else is quoted as a phrase.
_SAFE_TOKEN_RE = re.compile(r"[\wäöüßÄÖÜ]+", re.UNICODE)

# Bump when the indexed content, the FTS5 column layout, or the tokenizer changes.
# A mismatch in ``index_meta`` forces a full rebuild on the next connect, so an
# unchanged session file can never keep serving rows built by an older format.
_INDEX_FORMAT_VERSION = 2

_SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    session_id UNINDEXED,
    role UNINDEXED,
    content,
    title
);
CREATE TABLE IF NOT EXISTS indexed_files (
    filename TEXT PRIMARY KEY,
    mtime REAL,
    size INTEGER
);
CREATE TABLE IF NOT EXISTS index_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _db_path() -> Path:
    return Path(
        os.environ.get("EPHE_SEARCH_DB")
        or Path.home() / ".ephe" / "search.db"
    )


def _sessions_dir(sessions_dir: Path | None = None) -> Path:
    if sessions_dir is not None:
        return sessions_dir
    import core.multi_session as ms

    return ms.SESSIONS_DIR


def _ensure_format(conn: sqlite3.Connection) -> None:
    """Full-rebuild trigger: drop every row when the stored format version differs.

    ``indexed_files`` is cleared alongside the rows, so unchanged session files are
    re-indexed after a format change.
    """
    row = conn.execute("SELECT value FROM index_meta WHERE key = 'format_version'").fetchone()
    stored = int(row[0]) if row and str(row[0]).isdigit() else 0
    if stored == _INDEX_FORMAT_VERSION:
        return
    conn.execute("DELETE FROM messages_fts")
    conn.execute("DELETE FROM indexed_files")
    conn.execute(
        "INSERT OR REPLACE INTO index_meta (key, value) VALUES ('format_version', ?)",
        (str(_INDEX_FORMAT_VERSION),),
    )
    conn.commit()


def _open_index(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.executescript(_SCHEMA)
    _ensure_format(conn)
    return conn


def _connect(db: Path | None = None) -> sqlite3.Connection:
    path = db or _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = _open_index(path)
    except sqlite3.DatabaseError:
        # Corrupt or foreign file → the index is derived data, so rebuild it empty.
        path.unlink(missing_ok=True)
        conn = _open_index(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return conn


def _fts_query(query: str) -> str:
    """Raw query for safe tokens, otherwise phrase-quoted (no crash)."""
    q = (query or "").strip()
    if not q:
        return ""
    tokens = _SAFE_TOKEN_RE.findall(q)
    if not tokens:
        return ""
    reconstructed = " ".join(tokens)
    if reconstructed == q:
        # Only words (+ spaces) → FTS5 standard query (implicit AND)
        return q
    return '"{}"'.format(q.replace('"', '""'))


def _session_title(sdir: Path, sid: str) -> str:
    try:
        reg = json.loads((sdir / "registry.json").read_text(encoding="utf-8"))
        for entry in reg.get("sessions", []):
            if entry.get("id") == sid:
                return str(entry.get("title", ""))
    except (OSError, json.JSONDecodeError):
        pass
    return ""


def _registry_fingerprint(sdir: Path) -> str:
    """Fingerprint of the registry file, or "" when it is absent.

    ``title`` is derived from the registry, so the registry is an index input
    exactly like the session files are.
    """
    try:
        st = (sdir / "registry.json").stat()
    except OSError:
        return ""
    return f"{st.st_mtime!r}:{st.st_size}"


def _refresh_on_registry_change(conn: sqlite3.Connection, sdir: Path) -> None:
    """Force a re-index when the registry changed since the last run.

    A rename touches only ``registry.json``; the session file keeps its
    (mtime, size), so the incremental run would skip it and the live index would
    keep serving the old title while a fresh ``rebuild_index`` served the new
    one. Marking every fingerprint stale (``mtime = -1``) re-indexes the files
    whose title is read from the registry, without dropping the filenames: an
    entry whose file was deleted in the meantime is still dropped by
    ``_drop_stale``.
    """
    current = _registry_fingerprint(sdir)
    row = conn.execute(
        "SELECT value FROM index_meta WHERE key = 'registry_fingerprint'"
    ).fetchone()
    stored = row[0] if row else None
    if stored == current:
        return
    conn.execute("UPDATE indexed_files SET mtime = -1")
    conn.execute(
        "INSERT OR REPLACE INTO index_meta (key, value) VALUES ('registry_fingerprint', ?)",
        (current,),
    )
    conn.commit()


def _record_fingerprint(conn: sqlite3.Connection, name: str, stat: os.stat_result) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO indexed_files (filename, mtime, size) VALUES (?, ?, ?)",
        (name, stat.st_mtime, stat.st_size),
    )


def _index_file(conn: sqlite3.Connection, path: Path, sdir: Path, stat: os.stat_result) -> bool:
    """(Re)index one session file. True when indexed, False when it could not be parsed.

    An unreadable file still gets its fingerprint recorded (so an unchanged broken file
    is not re-read on every search) and its stale rows removed.
    """
    sid = path.stem
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        data = None

    conn.execute("DELETE FROM messages_fts WHERE session_id = ?", (sid,))
    if not isinstance(data, list):
        _record_fingerprint(conn, path.name, stat)
        return False

    title = _session_title(sdir, sid)
    for msg in data:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role")
        content = msg.get("content")
        if role not in ("user", "assistant", "system") or not isinstance(content, str):
            continue
        conn.execute(
            "INSERT INTO messages_fts (session_id, role, content, title) VALUES (?, ?, ?, ?)",
            (sid, role, content, title),
        )
    _record_fingerprint(conn, path.name, stat)
    return True


def _drop_stale(conn: sqlite3.Connection, seen: set[str]) -> None:
    stale = [name for (name,) in conn.execute("SELECT filename FROM indexed_files") if name not in seen]
    for name in stale:
        conn.execute("DELETE FROM messages_fts WHERE session_id = ?", (name.removesuffix(".json"),))
        conn.execute("DELETE FROM indexed_files WHERE filename = ?", (name,))


def index_sessions(sessions_dir: Path | None = None, db: Path | None = None) -> int:
    """Incremental index run. Return: number of sessions indexed or re-indexed."""
    sdir = _sessions_dir(sessions_dir)
    conn = _connect(db)
    try:
        _refresh_on_registry_change(conn, sdir)
        files = sorted(p for p in sdir.glob("*.json") if p.name not in {"registry.json", "default.json"})
        now_indexed = 0
        seen: set[str] = set()
        for path in files:
            stat = path.stat()
            seen.add(path.name)
            row = conn.execute(
                "SELECT mtime, size FROM indexed_files WHERE filename = ?", (path.name,)
            ).fetchone()
            if row and abs(row[0] - stat.st_mtime) < 1e-6 and row[1] == stat.st_size:
                continue  # unchanged (also covers a recorded-but-unparseable file)
            if _index_file(conn, path, sdir, stat):
                now_indexed += 1
        _drop_stale(conn, seen)
        conn.commit()
        return now_indexed
    finally:
        conn.close()


def search_messages(
    query: str,
    limit: int = 20,
    sessions_dir: Path | None = None,
    db: Path | None = None,
) -> list[dict[str, Any]]:
    """Full-text search over messages + session titles (FTS5 snippets)."""
    q = _fts_query(query)
    if not q:
        return []
    index_sessions(sessions_dir, db)  # mtime increment: typically 0 new files
    conn = _connect(db)
    try:
        rows = conn.execute(
            """
            SELECT session_id, role,
                   snippet(messages_fts, 2, '‹', '›', '…', 12) AS snip,
                   content, title
            FROM messages_fts
            WHERE messages_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (q, max(1, min(int(limit), 100))),
        ).fetchall()
    except sqlite3.OperationalError:
        return []  # corrupt/narrow DB → honest empty answer
    finally:
        conn.close()

    out: list[dict[str, Any]] = []
    for sid, role, snip, content, title in rows:
        out.append(
            {
                "session_id": sid,
                "session_title": title or sid,
                "role": role,
                "snippet": snip,
                "content": content,
                "updated_at": "",
            }
        )
    return out


def clear_index(db: Path | None = None) -> None:
    conn = _connect(db)
    try:
        conn.execute("DELETE FROM messages_fts")
        conn.execute("DELETE FROM indexed_files")
        conn.commit()
    finally:
        conn.close()


def rebuild_index(sessions_dir: Path | None = None, db: Path | None = None) -> int:
    """Full rebuild: drop every row and re-index all session files from scratch.

    Return: number of sessions indexed. This is the explicit form of what a format
    bump does implicitly; both leave ``indexed_files`` empty first, so unchanged
    files are re-indexed rather than skipped.
    """
    clear_index(db)
    return index_sessions(sessions_dir, db)


def drop_session(session_id: str, db: Path | None = None) -> None:
    """Remove one session from the index (used when its file is deleted)."""
    conn = _connect(db)
    try:
        conn.execute("DELETE FROM messages_fts WHERE session_id = ?", (session_id,))
        conn.execute("DELETE FROM indexed_files WHERE filename = ?", (f"{session_id}.json",))
        conn.commit()
    finally:
        conn.close()


__all__ = [
    "clear_index",
    "drop_session",
    "index_sessions",
    "rebuild_index",
    "search_messages",
]
