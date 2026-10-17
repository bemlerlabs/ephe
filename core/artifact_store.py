"""Ephe – artifact_store: the persistent artifact library (R17) and the workbench (R4).

Artifacts used to be derived only from message activities — deleting a session
took them along. The store makes them independent of the session: SQLite under
~/.ephe/artifacts.db (a local DB, gitignored-local per the release bar).

Registration happens in the chat stream as soon as a FILE marker (PDF_FILE:, PNG_FILE:,
… → file_result event) reports a real artifact. Versioning: the same
(name, kind, session_id) line → version++ under a shared root_id (regenerate
builds v2/v3 on top of it). The file itself stays where it is — the store only references;
since A0 the surface addresses the artifacts by their **id**
(`GET /artifacts/{id}/file`), no longer by path.

Birthplace, byte target and deadline (RETENTION_DAYS, expiry_due, answer_expiry)
are core.artifact_workbench — this index keeps their columns and rows.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from core.artifact_workbench import artifact_target, content_hash, iso, now_iso, schedule_for

# Env override (deployment/tests), otherwise ~/.ephe/artifacts.db — pattern like
# EPHE_AUDIO_DIR. Tests may additionally monkeypatch the module attribute.
def _default_db() -> Path:
    """The index lives with the workbench. An EPHE_CONFIG_DIR that only moved the
    birthplace and left the library in the real ~/.ephe was the bug behind this
    sentence: a redirect test wrote a row into the real DB."""
    return Path(os.environ.get("EPHE_CONFIG_DIR") or str(Path.home() / ".ephe")) / "artifacts.db"


ARTIFACTS_DB = Path(os.environ.get("EPHE_ARTIFACTS_DB") or _default_db())

_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    root_id TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    session_id TEXT NOT NULL DEFAULT '',
    name TEXT NOT NULL,
    path TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'file',
    size INTEGER NOT NULL DEFAULT 0,
    topic TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    favorite INTEGER NOT NULL DEFAULT 0,
    tags TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_artifacts_created ON artifacts(created_at);
CREATE INDEX IF NOT EXISTS idx_artifacts_session ON artifacts(session_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_root ON artifacts(root_id);
"""

# A0: identity instead of path. origin_path = where the file was born, adopted_path
# = where the user adopted it to, content_hash = the same byte string,
# turn_id/call_id/args_hash = the provenance chain (A3), viewed_at = last view.
# keep/expires_at/expiry_answered_at = the deadline and its question.
_NEW_COLUMNS = {
    "origin_path": "TEXT NOT NULL DEFAULT ''",
    "adopted_path": "TEXT NOT NULL DEFAULT ''",
    "adopted_hash": "TEXT NOT NULL DEFAULT ''",
    "content_hash": "TEXT NOT NULL DEFAULT ''",
    "viewed_at": "TEXT",
    "turn_id": "TEXT NOT NULL DEFAULT ''",
    "call_id": "TEXT NOT NULL DEFAULT ''",
    "args_hash": "TEXT NOT NULL DEFAULT ''",
    "keep": "INTEGER NOT NULL DEFAULT 0",
    "expires_at": "TEXT",
    "expiry_answered_at": "TEXT",
}

_COLS = (
    "id, root_id, version, session_id, name, path, kind, size, topic, created_at, "
    "favorite, tags, origin_path, adopted_path, adopted_hash, content_hash, viewed_at, turn_id, "
    "call_id, args_hash, keep, expires_at, expiry_answered_at"
)


def _connect() -> sqlite3.Connection:
    ARTIFACTS_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(ARTIFACTS_DB, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    _ensure_columns(conn)


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Idempotent migration: columns an older index does not have yet.

    No DROP, no conversion — an old artifacts.db stays readable and gets its deadline
    fields added empty. The index on expires_at may only be created afterwards,
    otherwise it fails on a table from before A0.
    """
    have = {r[1] for r in conn.execute("PRAGMA table_info(artifacts)")}
    for name, decl in _NEW_COLUMNS.items():
        if name not in have:
            conn.execute(f"ALTER TABLE artifacts ADD COLUMN {name} {decl}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_artifacts_expires ON artifacts(expires_at)")
    conn.commit()


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["favorite"] = bool(d["favorite"])
    d["keep"] = bool(d.get("keep"))
    return d


def _fresh_db() -> sqlite3.Connection:
    """With a corrupt DB: put the file **aside**, do not destroy it.

    This used to be an unlink, justified by artifacts being only references. Since the
    workbench that is no longer true: for a copy under ~/.ephe/artifacts the index is
    the only pointer. The unreadable file therefore stays where it is and can be
    restored.
    """
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    aside = ARTIFACTS_DB.with_name(f"{ARTIFACTS_DB.name}.unusable-{stamp}")
    try:
        ARTIFACTS_DB.replace(aside)
    except OSError:
        try:
            ARTIFACTS_DB.unlink()
        except OSError:
            pass
    conn = _connect()
    _init(conn)
    return conn


def _read(query: str, params: tuple = ()) -> list[sqlite3.Row]:
    """Read access. On a corrupt DB: create the file anew and retry once
    (artifacts are references, not irreplaceable content)."""
    try:
        conn = _connect()
    except Exception:
        return []
    try:
        _init(conn)
        return conn.execute(query, params).fetchall()
    except sqlite3.DatabaseError:
        try:
            conn2 = _fresh_db()
            return conn2.execute(query, params).fetchall()
        except Exception:
            return []
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _write(query: str, params: tuple = ()) -> None:
    """Write access — errors are NOT swallowed (the callers decide whether a store
    error may disturb the stream/call; register_artifact catches)."""
    conn = _connect()
    try:
        _init(conn)
        conn.execute(query, params)
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass


def register_artifact(
    path: str,
    kind: str,
    session_id: str = "",
    topic: str = "",
    *,
    turn_id: str = "",
    call_id: str = "",
    args_hash: str = "",
) -> dict | None:
    """Registers a real artifact. Versioned per (name, kind, session).

    Returns:
        The new row — or None when the DB is unusable (the stream must
        never die on the registration).
    """
    p = Path(path)
    name = p.name
    size = p.stat().st_size if p.exists() else 0
    now_dt = datetime.now(timezone.utc)
    now = iso(now_dt)
    expires_at = schedule_for(p, now_dt)
    rows = _read(
        "SELECT id, root_id, MAX(version) AS max_version FROM artifacts "
        "WHERE name = ? AND kind = ? AND session_id = ? LIMIT 1",
        (name, kind, session_id),
    )
    try:
        if rows and rows[0]["root_id"]:
            root_id = rows[0]["root_id"]
            version = int(rows[0]["max_version"] or 1) + 1
            art_id = uuid.uuid4().hex
        else:
            art_id = uuid.uuid4().hex
            root_id = art_id  # v1 is the root of the version line
            version = 1
        fields = {
            "id": art_id, "root_id": root_id, "version": version, "session_id": session_id,
            "name": name, "path": str(p), "kind": kind, "size": size, "topic": topic,
            "created_at": now, "favorite": False, "tags": [],
            "origin_path": str(p), "adopted_path": "", "adopted_hash": "", "content_hash": content_hash(p),
            "viewed_at": None, "turn_id": turn_id, "call_id": call_id,
            "args_hash": args_hash, "keep": False, "expires_at": expires_at,
            "expiry_answered_at": None,
        }
        row = dict(fields, favorite=0, keep=0, tags="[]")
        _write(
            "INSERT INTO artifacts (" + ", ".join(row) + ") "
            "VALUES (" + ", ".join("?" * len(row)) + ")",
            tuple(row.values()),
        )
        return fields
    except Exception:
        # The stream must not die on the registration — but without this
        # line a schema error stays invisible: a missing column shows itself
        # only when writing, and 59 tests were the only signal.
        logging.getLogger("ephe").exception("artifact registration failed for %s", path)
        return None


def list_artifacts(
    q: str = "",
    kind: str = "",
    session_id: str = "",
    favorite: bool | None = None,
    turn_id: str = "",
    limit: int = 200,
) -> list[dict]:
    sql = f"SELECT {_COLS} FROM artifacts WHERE 1=1"
    params: list = []
    if q.strip():
        sql += " AND (name LIKE ? OR topic LIKE ?)"
        like = f"%{q.strip()}%"
        params += [like, like]
    if kind:
        sql += " AND kind = ?"
        params.append(kind)
    if session_id:
        sql += " AND session_id = ?"
        params.append(session_id)
    if favorite is not None:
        sql += " AND favorite = ?"
        params.append(1 if favorite else 0)
    if turn_id:
        # A3 backwards: which files did exactly this assignment give birth to?
        sql += " AND turn_id = ?"
        params.append(turn_id)
    sql += " ORDER BY created_at DESC, rowid DESC LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    return [_row_to_dict(r) for r in _read(sql, tuple(params))]


def get_artifact(artifact_id: str) -> dict | None:
    rows = _read(f"SELECT {_COLS} FROM artifacts WHERE id = ?", (artifact_id,))
    return _row_to_dict(rows[0]) if rows else None


def get_versions(root_id: str) -> list[dict]:
    rows = _read(
        f"SELECT {_COLS} FROM artifacts WHERE root_id = ? ORDER BY version ASC, created_at ASC",
        (root_id,),
    )
    return [_row_to_dict(r) for r in rows]


def stats() -> dict:
    """The number the storage page shows in its header: over ALL rows, not over
    the first page slice.

    `expiring_*` counts only what the deadline actually touches (not pinned,
    not kept, with a date) — `next_expiry` is the earliest day on which a
    **question** is due. It is no deletion, and no caller may pretend
    it is one.
    """
    kind_rows = _read(
        "SELECT kind, COUNT(*) AS n, SUM(size) AS bytes FROM artifacts GROUP BY kind ORDER BY n DESC"
    )
    totals = _read(
        "SELECT COUNT(*) AS n, SUM(size) AS bytes FROM artifacts"
    )
    # Only what the deadline has REACHED — a card born tomorrow and asked
    # in 30 days is no upcoming question.
    due = _read(
        "SELECT COUNT(*) AS n, SUM(size) AS bytes, MIN(expires_at) AS at FROM artifacts "
        "WHERE keep = 0 AND favorite = 0 AND expires_at IS NOT NULL AND expires_at <= ?",
        (now_iso(),),
    )
    t = totals[0] if totals else None
    h = due[0] if due else None
    return {
        "count": int(t["n"] or 0) if t else 0,
        "bytes": int(t["bytes"] or 0) if t else 0,
        "by_kind": [
            {"kind": r["kind"], "count": int(r["n"] or 0), "bytes": int(r["bytes"] or 0)}
            for r in kind_rows
        ],
        "expiring_count": int(h["n"] or 0) if h else 0,
        "expiring_bytes": int(h["bytes"] or 0) if h else 0,
        "next_expiry": h["at"] if h else None,
    }


def set_favorite(artifact_id: str, favorite: bool) -> bool:
    _write("UPDATE artifacts SET favorite = ? WHERE id = ?", (1 if favorite else 0, artifact_id))
    return True


def set_tags(artifact_id: str, tags: list[str]) -> bool:
    clean = sorted({str(t).strip() for t in tags if str(t).strip()})[:20]
    _write("UPDATE artifacts SET tags = ? WHERE id = ?", (json.dumps(clean), artifact_id))
    return True


def delete_artifact(artifact_id: str, delete_file: bool = False) -> bool:
    """Removes the entry; delete_file deletes the file ONLY inside the allowed
    roots (core.tools.base) — otherwise it stays where it is (False).

    Order: the file first, then the row. The other way round would leave a file
    without a pointer behind — bytes nobody can find any more.
    """
    target = artifact_target(artifact_id) if delete_file else None
    if delete_file and target is not None:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            return False
    _write("DELETE FROM artifacts WHERE id = ?", (artifact_id,))
    return target is not None
