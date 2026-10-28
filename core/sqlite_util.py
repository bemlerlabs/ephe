"""Every SQLite connection in the product opens through here.

Parallel helpers write to the same databases (`swarm_state`, the artifact store,
the semantic index, memory). Without WAL a reader blocks a writer, and without a
busy timeout the second writer raises `database is locked` instead of waiting a
few milliseconds. One helper, so a new store cannot forget the three pragmas.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

BUSY_TIMEOUT_MS = 5000


def apply_pragmas(conn: sqlite3.Connection, *, readonly: bool = False) -> sqlite3.Connection:
    """WAL and NORMAL for writers; the timeout for both.

    A read-only handle cannot switch the journal mode — that writes the database
    header — so it keeps whatever the file already carries and only gains the
    wait.
    """
    try:
        if not readonly:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    except sqlite3.DatabaseError:
        # A corrupt file must reach the caller's own recovery path instead of
        # dying here; the pragmas reapply on the next healthy connection.
        pass
    return conn


def connect(
    path: str | Path,
    *,
    check_same_thread: bool = True,
    readonly: bool = False,
    timeout: float = 5.0,
) -> sqlite3.Connection:
    target = str(path)
    if readonly:
        conn = sqlite3.connect(f"file:{target}?mode=ro", uri=True, timeout=timeout)
        return apply_pragmas(conn, readonly=True)
    conn = sqlite3.connect(target, check_same_thread=check_same_thread, timeout=timeout)
    return apply_pragmas(conn)
