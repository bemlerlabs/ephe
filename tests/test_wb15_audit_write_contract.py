"""WB-15: the audit-log write path is fail-open by contract, and not silent.

`core.audit_log.audit_event` must never raise into the tool flow — a full disk
(ENOSPC), an unwritable file or an obstacle standing at the path loses the
entry, and the tool keeps running. The other half of that contract is
observability: a dropped entry has to show up, or "the log went quiet" reads
as "nothing happened" (repudiation). These tests pin both halves.
"""
from __future__ import annotations

import json
import logging
import stat

import pytest

import core.audit_log as audit_log


@pytest.fixture(autouse=True)
def _clean_drop_state():
    """Each test starts with no warning spent and no drop counted."""
    audit_log._dropped = 0
    audit_log._drop_warned = False
    yield


@pytest.fixture
def logfile(tmp_path, monkeypatch):
    """Point the write path at one file under tmp."""
    path = tmp_path / "audit.log"
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", path)
    return path


class _DiskFull:
    """Stands in for the log target; opening it fails like a full disk."""

    def __init__(self, parent):
        self.parent = parent

    def exists(self) -> bool:
        return True

    def chmod(self, mode: int) -> None:
        raise AssertionError("chmod must not run once open() already failed")

    def open(self, mode: str, encoding: str | None = None):
        raise OSError(28, "No space left on device")


class _ChmodDenied:
    """Writes for real, but refuses the 0600 tighten on creation."""

    def __init__(self, real):
        self.parent = real.parent
        self._real = real

    def exists(self) -> bool:
        return False

    def open(self, mode: str, encoding: str | None = None):
        return self._real.open(mode, encoding=encoding)

    def chmod(self, mode: int) -> None:
        raise OSError(13, "Operation not permitted")


class TestNeverRaises:
    """No failure mode of the log may reach the tool flow."""

    def test_target_is_a_directory(self, tmp_path, monkeypatch):
        monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", tmp_path / "is_a_dir")
        (tmp_path / "is_a_dir").mkdir()
        assert audit_log.audit_event("tool_exec", tool="shell") is None

    def test_parent_cannot_be_created(self, tmp_path, monkeypatch):
        obstacle = tmp_path / "afile"
        obstacle.write_text("x", encoding="utf-8")
        monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", obstacle / "audit.log")
        assert audit_log.audit_event("tool_exec", tool="shell") is None

    def test_unwritable_file(self, logfile):
        logfile.write_text("", encoding="utf-8")
        logfile.chmod(stat.S_IRUSR)  # owner keeps read, loses write
        assert audit_log.audit_event("tool_exec", tool="shell") is None

    def test_full_disk(self, tmp_path, monkeypatch):
        monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", _DiskFull(tmp_path))
        assert audit_log.audit_event("tool_exec", tool="shell") is None

    def test_chmod_denied_on_create_is_contained(self, tmp_path, monkeypatch):
        real = tmp_path / "audit.log"
        monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", _ChmodDenied(real))
        assert audit_log.audit_event("tool_exec", tool="shell") is None
        # the entry was written; only the permission tighten was skipped
        assert json.loads(real.read_text(encoding="utf-8").strip())["tool"] == "shell"

    def test_lock_released_after_a_drop(self, tmp_path, monkeypatch):
        broken = tmp_path / "broken"
        broken.mkdir()
        good = tmp_path / "audit.log"
        monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", broken)
        audit_log.audit_event("tool_exec", tool="first")  # dropped
        monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", good)
        audit_log.audit_event("tool_exec", tool="second")  # must still land
        assert json.loads(good.read_text(encoding="utf-8").strip())["tool"] == "second"


class TestDropIsObservable:
    """A silent fail-open log is the repudiation gap; the drop must be visible."""

    def test_first_drop_warns_once(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", tmp_path / "broken")
        (tmp_path / "broken").mkdir()
        with caplog.at_level(logging.WARNING, logger=audit_log.__name__):
            audit_log.audit_event("tool_exec", tool="a")
            audit_log.audit_event("tool_exec", tool="b")
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "dropped" in warnings[0].getMessage()

    def test_no_warning_on_a_clean_write(self, logfile, caplog):
        with caplog.at_level(logging.WARNING, logger=audit_log.__name__):
            audit_log.audit_event("tool_exec", tool="shell")
        assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    def test_dropped_counter_accumulates(self, tmp_path, monkeypatch, caplog):
        monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", tmp_path / "broken")
        (tmp_path / "broken").mkdir()
        with caplog.at_level(logging.WARNING, logger=audit_log.__name__):
            for _ in range(3):
                audit_log.audit_event("tool_exec", tool="shell")
        assert audit_log._dropped == 3
        assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 1


class TestNormalWriteContract:
    """The behaviours a normal append is allowed to rely on."""

    def test_entry_written_and_created_0600(self, logfile):
        audit_log.audit_event("approval", tool="shell", decision="denied")
        entry = json.loads(logfile.read_text(encoding="utf-8").strip())
        assert entry["kind"] == "approval" and entry["decision"] == "denied"
        assert stat.S_IMODE(logfile.stat().st_mode) == 0o600

    def test_an_existing_wider_log_is_tightened_on_the_next_append(self, logfile):
        audit_log.audit_event("tool_exec", tool="shell")
        logfile.chmod(0o644)  # a later actor widens the mode
        audit_log.audit_event("tool_exec", tool="shell")
        assert stat.S_IMODE(logfile.stat().st_mode) == 0o600


class TestTornLineIsNotFatal:
    """A crash mid-append leaves a partial line; reading must survive it."""

    def test_tail_skips_a_partial_last_line(self, logfile):
        logfile.parent.mkdir(parents=True, exist_ok=True)
        good = json.dumps({"ts": "t", "kind": "tool_exec", "tool": "shell"})
        logfile.write_text(good + "\n" + '{"ts": "t2", "kind": "appro', encoding="utf-8")
        entries = audit_log.tail(limit=10)
        assert [e["tool"] for e in entries] == ["shell"]


class TestChain:
    """SC-07: the log carries a hash chain, so an edited or removed line shows."""

    def _three(self, logfile):
        for index in range(3):
            audit_log.audit_event("tool_exec", tool=f"t{index}", status="ok")
        return logfile.read_text().splitlines()

    def test_a_fresh_chain_verifies(self, logfile):
        self._three(logfile)
        assert audit_log.verify_chain(logfile) == []

    def test_an_edited_line_breaks_the_chain(self, logfile):
        lines = self._three(logfile)
        lines[1] = lines[1].replace('"status": "ok"', '"status": "blocked"')
        logfile.write_text("\n".join(lines) + "\n")
        assert any("chain mismatch" in problem for problem in audit_log.verify_chain(logfile))

    def test_a_removed_middle_line_breaks_the_chain(self, logfile):
        lines = self._three(logfile)
        logfile.write_text("\n".join([lines[0], lines[2]]) + "\n")
        assert any("chain mismatch" in problem for problem in audit_log.verify_chain(logfile))

    def test_a_torn_line_is_named(self, logfile):
        lines = self._three(logfile)
        logfile.write_text("\n".join(lines) + '\n{"ts": "2026')
        assert any("not JSON" in problem for problem in audit_log.verify_chain(logfile))

    def test_every_entry_carries_its_predecessor(self, logfile):
        self._three(logfile)
        entries = audit_log.tail(limit=10)
        assert all("prev" in entry for entry in entries)
        assert entries[-1]["prev"] == ""

    def test_a_legacy_prefix_is_not_reported_as_8959_breaks(self, logfile):
        """The owner's log predates the chain. Lines without `prev` promise
        nothing; the first chained line links to the legacy tail."""
        import hashlib

        legacy = json.dumps({"ts": "2026-01-01T00:00:00+00:00", "kind": "tool_exec"})
        logfile.write_text(legacy + "\n", encoding="utf-8")
        audit_log.audit_event("tool_exec", tool="after")

        assert audit_log.verify_chain(logfile) == []

    def test_a_stripped_link_after_the_chain_is_named(self, logfile):
        lines = self._three(logfile)
        entry = json.loads(lines[2])
        entry.pop("prev")
        lines[2] = json.dumps(entry)
        logfile.write_text("\n".join(lines) + "\n", encoding="utf-8")

        assert any(
            "missing chain link" in problem
            for problem in audit_log.verify_chain(logfile)
        )
