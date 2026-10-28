"""L3: every SQLite connection waits instead of failing, and writers use WAL."""
from __future__ import annotations

import sqlite3

import pytest

from core import sqlite_util


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "store.db"
    conn = sqlite_util.connect(path)
    conn.execute("CREATE TABLE t (v INTEGER)")
    conn.commit()
    conn.close()
    return path


def test_a_writer_gets_wal_normal_and_a_five_second_wait(db):
    conn = sqlite_util.connect(db)
    try:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
    finally:
        conn.close()


def test_a_read_only_handle_keeps_the_file_mode_and_still_waits(db):
    conn = sqlite_util.connect(db, readonly=True)
    try:
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0
    finally:
        conn.close()


def test_a_second_writer_waits_instead_of_raising(db):
    import threading
    import time

    first = sqlite_util.connect(db)
    second = sqlite_util.connect(db, check_same_thread=False)
    outcome: list[str] = []
    first.execute("BEGIN IMMEDIATE")
    first.execute("INSERT INTO t VALUES (1)")

    def write_second() -> None:
        try:
            second.execute("BEGIN IMMEDIATE")
            second.execute("INSERT INTO t VALUES (2)")
            second.commit()
            outcome.append("written")
        except sqlite3.OperationalError as exc:  # the defect this helper prevents
            outcome.append(f"raised: {exc}")

    worker = threading.Thread(target=write_second)
    worker.start()
    # The first writer commits while the second is waiting on the lock.
    time.sleep(0.3)
    first.commit()
    worker.join(timeout=10)
    try:
        assert outcome == ["written"]
        assert first.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 2
    finally:
        first.close()
        second.close()


def test_the_helper_names_the_pragmas_it_applies():
    assert sqlite_util.BUSY_TIMEOUT_MS == 5000
    assert sqlite3.sqlite_version
