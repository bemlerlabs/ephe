"""Quality gate: what a memory write says when it closes on a full disk.

The mechanics are the wave-3 gate's (``tests/test_memory_full_disk``): no torn row,
no orphan chunk, the file intact, the brain alive, and the facade does not swallow
the provider's error. This file pins the other half — the closure a person or a
surface actually reads.

A bare ``database or disk is full`` says what did not happen and stops. That is the
half-refusal ``tests/test_refusal_messages_actionable`` forbids everywhere else: it
costs the reader the round trip back to the surface to find out what to do. So the
write closes fail-closed — nothing lands — with a stable ``code`` a surface
translates and one line naming the move (free the memory volume, then retry), while
staying the provider's own error class so nothing that caught it before stops
catching it.

The refusal is held to the same marker set as the other refusal families, and the
full-disk seam is the wave-3 gate's, imported rather than forked.
"""
from __future__ import annotations

import errno
import re
import sqlite3
from pathlib import Path

import pytest

import core.auto_memory as am
from core.memory import (
    MEMORY_WRITE_REFUSALS,
    Memory,
    MemoryWriteRefused,
    is_full_disk,
)
from tests.test_memory_full_disk import FULL, GOOD_A, GOOD_Q, _fill_until_full, _force_full
from tests.test_refusal_messages_actionable import (
    NEXT_STEP_EN,
    SURFACE_EN,
    _names_a_next_step,
)

STABLE_CODE = re.compile(r"[a-z][a-z0-9_]*")


def _refusal(code: str = "memory_disk_full") -> MemoryWriteRefused:
    return MemoryWriteRefused(code, error=FULL, volume="/home/anna/.ephe/memory")


class TestTheRefusalItself:
    def test_every_code_names_a_next_step(self):
        """A registry entry without a move fails the same way a dead end does."""
        assert MEMORY_WRITE_REFUSALS, "the memory write carries no coded refusal"
        for code in MEMORY_WRITE_REFUSALS:
            exc = _refusal(code)
            assert exc.code == code
            assert exc.next_step
            assert _names_a_next_step(str(exc), NEXT_STEP_EN, SURFACE_EN), (code, str(exc))

    def test_the_codes_are_stable_identifiers(self):
        for code in MEMORY_WRITE_REFUSALS:
            assert STABLE_CODE.fullmatch(code), code

    def test_a_code_outside_the_registry_is_refused(self):
        with pytest.raises(KeyError):
            MemoryWriteRefused("memory_on_fire", error=FULL, volume="/x")

    def test_the_message_still_carries_the_driver_own_sentence(self):
        assert FULL in str(_refusal())

    def test_only_a_full_disk_is_dressed_as_one(self):
        assert is_full_disk(sqlite3.OperationalError(FULL))
        assert is_full_disk(OSError(errno.ENOSPC, "no space left on device"))
        assert not is_full_disk(sqlite3.OperationalError("no such table: memories"))
        assert not is_full_disk(OSError(errno.EACCES, "permission denied"))


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


class TestTheFacadeWritePath:
    def test_the_refusal_names_the_move_and_keeps_the_provider_class(self, facade):
        """GIVEN a full disk under the facade
        WHEN a fact is stored
        THEN the failure names the move and carries a code, and is still the
        provider's own error class — the facade does not swallow it."""
        _force_full(facade._provider)
        err = _fill_until_full(
            lambda i: facade.store(f"fact {i} " + "y" * 300, {"source": "t"})
        )
        assert isinstance(err, MemoryWriteRefused)
        assert isinstance(err, sqlite3.OperationalError)
        assert isinstance(err, OSError)
        assert err.code == "memory_disk_full"
        assert _names_a_next_step(str(err), NEXT_STEP_EN, SURFACE_EN), str(err)
        assert FULL in str(err)

    def test_the_move_names_the_folder_the_store_lives_on(self, facade):
        """GIVEN a full disk under the facade
        WHEN the write refuses
        THEN the move points at the folder to clear — the path, not a vague "disk"."""
        _force_full(facade._provider)
        err = _fill_until_full(
            lambda i: facade.store(f"fact {i} " + "y" * 300, {"source": "t"})
        )
        assert err.volume == str(Path(facade._provider._db_path).parent)
        assert err.volume in str(err)

    def test_the_refused_write_leaves_no_partial_record(self, facade):
        """GIVEN the disk fills mid-write
        WHEN the coded refusal closes the write
        THEN no trace of the fact is on disk: no row, no chunk."""
        _force_full(facade._provider)
        before = facade.count()
        err = None
        for i in range(500):
            try:
                facade.store(f"fact {i} " + "y" * 300, {"source": "t"})
                before = facade.count()
            except sqlite3.OperationalError as exc:
                err = exc
                break
        assert isinstance(err, MemoryWriteRefused)
        assert facade.count() == before
        orphans = facade._provider._db.execute(
            "SELECT COUNT(*) FROM chunks c LEFT JOIN memories m ON c.memory_id = m.id "
            "WHERE m.id IS NULL"
        ).fetchone()[0]
        assert orphans == 0


class TestTheProductionCaller:
    def test_the_auto_memory_verdict_carries_the_named_next_step(self, facade, monkeypatch):
        """GIVEN the disk is full
        WHEN the auto-memory caller stores a turn
        THEN its honest ``error:`` verdict names the move too — the reader of the
        verdict does not have to go find it."""
        monkeypatch.setattr(am, "_memory_factory", lambda: facade)
        monkeypatch.setenv("EPHE_MEMORY_ENABLED", "1")
        _force_full(facade._provider)
        _fill_until_full(lambda i: facade.store(f"fact {i} " + "z" * 300, {"source": "t"}))

        verdict = am.maybe_store_turn(GOOD_Q, GOOD_A)

        assert verdict["stored"] is False
        assert verdict["reason"].startswith("error:")
        assert _names_a_next_step(verdict["reason"], NEXT_STEP_EN, SURFACE_EN), verdict["reason"]
        assert FULL in verdict["reason"]
