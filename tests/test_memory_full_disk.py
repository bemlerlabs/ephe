"""Quality gate: the memory write path when the disk is full.

Observed, not mocked. On a 2 MB HFS volume (a RAM disk, macOS, 2026-10-11) the
Kepta write path stored 30 facts and then raised ``sqlite3.OperationalError:
database or disk is full`` — SQLITE_FULL, the error the kernel hands SQLite when
``write()`` returns ENOSPC. The same error, on the same provider code path, is
reproducible without a mount by capping the database with ``PRAGMA
max_page_count``: SQLite then refuses to grow the file and returns the identical
SQLITE_FULL. That is the seam these tests use, so the failure is real — the
provider's own INSERT/commit — while the suite stays hermetic.

What a full disk must not do: leave a half-written fact (a torn row, an orphan
chunk), corrupt the file, or brick the brain for the rest of the process. And the
production caller (``core.auto_memory.maybe_store_turn``) must turn the failure
into an honest ``error:`` verdict — never a crash, never a silent success.

``supersede`` is the one write that spans two statements. The class docstring
below marks the hole it had.
"""
from __future__ import annotations

import sqlite3

import pytest

import core.auto_memory as am
from core.memory import Memory
from core.memory_kepta import KeptaProvider

GOOD_Q = "How should I build the FastAPI lifespan for the scheduler?"
GOOD_A = (
    "Start the scheduler directly on the event loop inside the lifespan "
    "context, never in a worker thread. AsyncIOScheduler needs a running loop "
    "in the calling thread, otherwise the failure is swallowed silently and the "
    "job never runs."
)

FULL = "database or disk is full"


def _force_full(provider: KeptaProvider) -> None:
    """Cap the database at its current size: the next growth is SQLITE_FULL."""
    pages = provider._db.execute("PRAGMA page_count").fetchone()[0]
    provider._db.execute(f"PRAGMA max_page_count = {pages}")


def _lift_the_cap(provider: KeptaProvider, pages: int = 1_000_000) -> None:
    provider._db.execute(f"PRAGMA max_page_count = {pages}")


def _orphan_chunks(provider: KeptaProvider) -> int:
    return int(
        provider._db.execute(
            "SELECT COUNT(*) FROM chunks c LEFT JOIN memories m ON c.memory_id = m.id "
            "WHERE m.id IS NULL"
        ).fetchone()[0]
    )


def _fill_until_full(store_call, tries: int = 500) -> sqlite3.OperationalError:
    """Writes until the capped database reports SQLITE_FULL; returns the error."""
    for i in range(tries):
        try:
            store_call(i)
        except sqlite3.OperationalError as exc:
            assert FULL in str(exc), f"expected SQLITE_FULL, got {exc!r}"
            return exc
    raise AssertionError("the capped database never reported SQLITE_FULL")


class _CommitGate:
    """The connection, but the Nth ``commit`` meets a full disk.

    Used for the two-statement write (``supersede``): this is the fault that only
    appears when the disk fills *between* the two statements, which no single
    capped database can place.
    """

    def __init__(self, conn: sqlite3.Connection, fail_on: int) -> None:
        self._conn = conn
        self._fail_on = fail_on
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1
        if self.commits == self._fail_on:
            raise sqlite3.OperationalError(FULL)
        self._conn.commit()

    def __getattr__(self, name):  # delegate execute / close / row_factory / ...
        return getattr(self._conn, name)


@pytest.fixture()
def kepta(tmp_path):
    prov = KeptaProvider(db_path=str(tmp_path / "kepta.db"), scope="full", embedder=None)
    prov.store("The API gateway listens on port 9100.", {"source": "seed"})
    try:
        yield prov
    finally:
        prov.close()


@pytest.fixture()
def facade(monkeypatch):
    # A named path means Chroma by contract, so Kepta is selected by name and its
    # db lands under the hermetic EPHE_CONFIG_DIR the suite already provides.
    monkeypatch.setenv("EPHE_MEMORY_EMBEDDER", "none")
    mem = Memory(provider="kepta", scope="full")
    try:
        yield mem
    finally:
        mem.close()
        Memory.reset_scoped_instances()


class TestStoreUnderAFullDisk:
    def test_a_full_disk_raises_sqlite_full(self, kepta):
        """GIVEN a database the OS will not let grow
        WHEN a fact is written
        THEN SQLite refuses with the kernel's own full-disk error."""
        _force_full(kepta)
        with pytest.raises(sqlite3.OperationalError) as err:
            for i in range(500):
                kepta.store(f"fact {i} " + "x" * 300, {"source": "t"})
        assert FULL in str(err.value)

    def test_a_failed_write_leaves_no_partial_row(self, kepta):
        """GIVEN the disk fills mid-write
        WHEN the write fails
        THEN the fact is all there or not at all — no torn row, no orphan chunk."""
        _force_full(kepta)
        last = kepta.count()
        raised = False
        for i in range(500):
            try:
                kepta.store(f"fact {i} " + "x" * 300, {"source": "t"})
                last = kepta.count()
            except sqlite3.OperationalError:
                raised = True
                break
        assert raised, "the capped database never filled"
        assert kepta.count() == last  # the failing store rolled back
        assert _orphan_chunks(kepta) == 0  # ... including its chunks

    def test_the_file_survives_the_episode(self, kepta):
        """GIVEN the disk filled and a write failed
        WHEN the file is checked
        THEN the file is intact and never half-written."""
        _force_full(kepta)
        _fill_until_full(lambda i: kepta.store(f"fact {i} " + "x" * 300, {"source": "t"}))
        assert kepta._db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

    def test_space_again_means_writes_again(self, kepta):
        """GIVEN a full disk that freed up
        WHEN the same connection writes
        THEN it works — the failure did not brick the brain."""
        _force_full(kepta)
        _fill_until_full(lambda i: kepta.store(f"fact {i} " + "x" * 300, {"source": "t"}))
        _lift_the_cap(kepta)
        before = kepta.count()
        kepta.store("A fact stored once the disk has room again.", {"source": "t"})
        assert kepta.count() == before + 1


class TestThroughTheFacadeAndTheCaller:
    def test_the_facade_surfaces_the_full_disk(self, facade):
        """GIVEN a full disk under the facade
        WHEN a fact is stored
        THEN the error reaches the caller unchanged (the facade does not swallow)."""
        _force_full(facade._provider)
        with pytest.raises(sqlite3.OperationalError) as err:
            for i in range(500):
                facade.store(f"fact {i} " + "y" * 300, {"source": "t"})
        assert FULL in str(err.value)

    def test_maybe_store_turn_answers_error_never_crashes(self, facade, monkeypatch):
        """GIVEN the disk is full
        WHEN the auto-memory caller stores a turn
        THEN it returns an honest `error:` verdict — the chat stream must not die."""
        monkeypatch.setattr(am, "_memory_factory", lambda: facade)
        monkeypatch.setenv("EPHE_MEMORY_ENABLED", "1")
        _force_full(facade._provider)
        _fill_until_full(lambda i: facade.store(f"fact {i} " + "z" * 300, {"source": "t"}))

        verdict = am.maybe_store_turn(GOOD_Q, GOOD_A)

        assert verdict["stored"] is False
        assert verdict["reason"].startswith("error:")
        assert FULL in verdict["reason"]


class TestSupersedeIsOneTransaction:
    """Hole: ``supersede`` wrote the new fact and marked the old one in two
    separate commits. A disk that filled between them left the new fact
    persisted and the old fact unmarked — a correction that half-applied: two
    active facts, the descent one-sided. It commits once now, so the whole
    correction lands or none of it does."""

    def test_no_commit_point_leaves_a_half_correction(self, tmp_path):
        """GIVEN the disk fills at commit point N (N = 1, 2, 3)
        WHEN a fact is superseded
        THEN the new fact is applied exactly when the old one is marked — never
        one without the other."""
        for fail_on in (1, 2, 3):
            db = tmp_path / f"gate{fail_on}.db"
            prov = KeptaProvider(db_path=str(db), scope="full", embedder=None)
            old = prov.store("The gateway listens on port 9000.", {"source": "t"})
            before = prov.count()
            prov._db = _CommitGate(prov._db, fail_on=fail_on)
            try:
                prov.supersede(old, "The gateway listens on port 9100.", {"source": "t"})
            except sqlite3.OperationalError:
                pass
            prov._db._conn.close()

            # Read the file: only what committed is on disk.
            fresh = sqlite3.connect(str(db))
            fresh.row_factory = sqlite3.Row
            try:
                count = fresh.execute("SELECT COUNT(*) k FROM memories").fetchone()["k"]
                mark = fresh.execute(
                    "SELECT superseded_by FROM memories WHERE id = ?", (old,)
                ).fetchone()
            finally:
                fresh.close()

            applied = count == before + 1
            marked = mark["superseded_by"] is not None
            assert applied == marked, (
                f"fail_on={fail_on}: new fact applied={applied}, old marked={marked} — torn"
            )

    def test_the_correction_links_both_ways_when_there_is_room(self, kepta):
        """GIVEN a disk with room
        WHEN a fact is superseded
        THEN the old one points at the new one and both are queryable."""
        old = kepta.store("The gateway listens on port 9000.", {"source": "t"})
        new = kepta.supersede(old, "The gateway listens on port 9100.", {"source": "t"})
        assert new != old
        row = kepta._db.execute(
            "SELECT superseded_by, valid_to FROM memories WHERE id = ?", (old,)
        ).fetchone()
        assert row["superseded_by"] == new
        assert row["valid_to"] is not None
