"""`ephe doctor` and the device folder's stale entries.

The folder holds what the product declared plus what hands and old releases left. The
doctor names the leftovers, and `--fix` moves the recognised ones under the folder's own
trash — a repair that stays reversible, because a hand that wrote a backup meant it.
"""

from __future__ import annotations

import os
from pathlib import Path

from core import persistence
import ephe_cli


def _mode(path: Path) -> int:
    return path.stat().st_mode & 0o777


def _recognisable_leftovers() -> list[str]:
    return [
        "engine.json.bak-20261028T201820Z",
        "engine.json.qwen-backup",
        "engine.key.pre-openrouter",
        "creator-staging",
    ]


def _untouched_entries() -> list[str]:
    # The pem is a private key; the rest are declared product state or unrelated names
    # that share a prefix with a debris shape without matching it.
    return [
        "first-party.private.pem",
        "engine.json",
        "engine.json.random",
        "sessions",
        "trash",
    ]


class TestDebrisRecognition:
    def test_given_a_known_leftover_when_named_then_it_is_debris(self):
        for name in _recognisable_leftovers():
            assert ephe_cli._is_doctor_debris(name), name

    def test_given_a_key_or_a_declared_name_when_named_then_it_is_never_debris(self):
        for name in _untouched_entries():
            assert not ephe_cli._is_doctor_debris(name), name


class TestDebrisRepair:
    def test_given_debris_and_a_private_key_when_repaired_then_only_debris_moves(self, tmp_path):
        for name in _recognisable_leftovers():
            (tmp_path / name).write_text("bytes", encoding="utf-8")
        (tmp_path / "first-party.private.pem").write_text("secret", encoding="utf-8")

        ok, detail = ephe_cli._repair_device_debris(folder=tmp_path)

        assert ok, detail
        for name in _recognisable_leftovers():
            assert not (tmp_path / name).exists(), name
        assert (tmp_path / "first-party.private.pem").read_text(encoding="utf-8") == "secret"
        trash_runs = list((tmp_path / "trash").iterdir())
        assert len(trash_runs) == 1
        moved = sorted(p.name for p in trash_runs[0].iterdir())
        assert moved == sorted(_recognisable_leftovers())

    def test_given_a_folder_without_debris_when_repaired_then_it_says_so(self, tmp_path):
        (tmp_path / "engine.json").write_text("{}", encoding="utf-8")

        ok, detail = ephe_cli._repair_device_debris(folder=tmp_path)

        assert ok
        assert "no recognisable debris" in detail
        assert not (tmp_path / "trash").exists()

    def test_given_the_same_folder_when_repaired_twice_then_the_second_run_is_quiet(self, tmp_path):
        (tmp_path / "engine.json.qwen-backup").write_text("bytes", encoding="utf-8")

        ephe_cli._repair_device_debris(folder=tmp_path)
        ok, detail = ephe_cli._repair_device_debris(folder=tmp_path)

        assert ok and "no recognisable debris" in detail

    def test_given_one_file_held_when_repaired_then_the_partial_move_is_reported(self, tmp_path, monkeypatch):
        (tmp_path / "engine.json.qwen-backup").write_text("bytes", encoding="utf-8")
        (tmp_path / "engine.key.pre-openrouter").write_text("bytes", encoding="utf-8")
        real_move = persistence.shutil.move

        def hold_one(src, dst):
            if "qwen" in str(src):
                raise OSError("held by another process")
            return real_move(src, dst)

        monkeypatch.setattr(persistence.shutil, "move", hold_one)

        ok, detail = ephe_cli._repair_device_debris(folder=tmp_path)

        assert not ok
        assert "1 stayed" in detail
        assert (tmp_path / "engine.json.qwen-backup").exists()
        assert not (tmp_path / "engine.key.pre-openrouter").exists()

    def test_given_every_move_failing_when_repaired_then_it_names_the_refusal(self, tmp_path, monkeypatch):
        (tmp_path / "engine.json.qwen-backup").write_text("bytes", encoding="utf-8")

        def refuse(src, dst):
            raise OSError("held by another process")

        monkeypatch.setattr(persistence.shutil, "move", refuse)

        ok, detail = ephe_cli._repair_device_debris(folder=tmp_path)

        assert not ok
        assert "could not move any" in detail


class TestDeviceStateLine:
    def test_given_debris_and_an_unknown_name_when_read_then_the_line_separates_them(self, tmp_path, monkeypatch):
        from core import persistence

        (tmp_path / "engine.json.q1b-backup").write_text("bytes", encoding="utf-8")
        (tmp_path / "sessions").mkdir()
        (tmp_path / "mystery").write_text("bytes", encoding="utf-8")
        monkeypatch.setattr(persistence, "root", lambda: tmp_path)

        line = ephe_cli._doctor_device_state()

        assert "1 unnamed (mystery)" in line
        assert "1 stale" in line
        assert "ephe doctor --fix" in line


class TestDeclarations:
    def test_given_the_product_files_the_folder_actually_holds_when_declared_then_none_is_unnamed(self):
        from core import persistence

        declared = persistence.declared_names()
        for name in ("creator", "creator-consent.json", "plugin-locks", "trash"):
            assert name in declared, name


class TestMoveToTrash:
    """The one mechanic both `doctor --fix` and `ephe device --clear` move entries with."""

    def test_given_a_named_leftover_when_moved_then_the_bytes_survive_under_the_run(self, tmp_path):
        (tmp_path / "loose").write_text("contents", encoding="utf-8")

        result = persistence.move_to_trash(tmp_path, names=["loose"], dry_run=False, stamp="RUN")

        assert result["moved"] == ["loose"]
        assert not (tmp_path / "loose").exists()
        assert (tmp_path / "trash" / "RUN" / "loose").read_text(encoding="utf-8") == "contents"

    def test_given_a_dry_run_when_named_then_nothing_moves_and_the_answer_says_where(self, tmp_path):
        (tmp_path / "loose").write_text("contents", encoding="utf-8")

        result = persistence.move_to_trash(tmp_path, names=["loose"], stamp="RUN")

        assert result["would_move"] == ["loose"] and result["moved"] == []
        assert (tmp_path / "loose").exists(), "the dry run moved"
        assert not (tmp_path / "trash").exists(), "the dry run created a folder"
        assert result["trash"] == str(tmp_path / "trash" / "RUN")

    def test_given_a_declared_name_when_named_then_the_move_is_refused(self, tmp_path):
        """`forget()` owns the declared rows; a name typed at this verb does not move them."""
        (tmp_path / "sessions").mkdir()

        result = persistence.move_to_trash(tmp_path, names=["sessions"], dry_run=False)

        assert result["refused"] == ["sessions"] and result["moved"] == []
        assert (tmp_path / "sessions").is_dir()

    def test_given_a_name_with_a_separator_when_named_then_it_is_refused_unread(self, tmp_path):
        for name in ("sessions/one.json", "../outside", "a\\b", "", ".", "..", "~/keys"):
            result = persistence.move_to_trash(tmp_path, names=[name], dry_run=False)
            assert result["refused"] == [name], name
            assert result["missing"] == [], "a refused name was also looked for on disk"

    def test_given_a_name_the_folder_does_not_hold_when_named_then_it_is_reported_absent(self, tmp_path):
        result = persistence.move_to_trash(tmp_path, names=["never-there"], dry_run=False)

        assert result["missing"] == ["never-there"]
        assert result["trash"] is None, "an empty run announced a folder it never made"

    def test_given_a_moved_entry_when_it_landed_then_the_folder_reads_it_private(self, tmp_path):
        """Trash is content the doctor row reads, so an entry may not arrive at 644.

        `shutil.move` keeps the source's mode; the file below is written the way another
        tool writes one, and the move has to bring it to the modes the device promises.
        """
        loose = tmp_path / "loose"
        loose.write_text("contents", encoding="utf-8")
        os.chmod(loose, 0o644)
        nested = tmp_path / "loose-dir"
        (nested / "deep").mkdir(parents=True)
        (nested / "deep" / "inner.txt").write_text("x", encoding="utf-8")
        os.chmod(nested / "deep" / "inner.txt", 0o644)

        persistence.move_to_trash(tmp_path, names=["loose", "loose-dir"], dry_run=False, stamp="RUN")

        run = tmp_path / "trash" / "RUN"
        assert _mode(run) == 0o700 and _mode(run.parent) == 0o700
        assert _mode(run / "loose") == 0o600
        assert _mode(run / "loose-dir" / "deep" / "inner.txt") == 0o600

    def test_given_a_mode_that_cannot_be_set_when_moving_then_the_entry_still_moves(self, tmp_path, monkeypatch):
        """A refusal to chmod is the doctor row's to report, not a reason to leave the file."""
        (tmp_path / "loose").write_text("contents", encoding="utf-8")
        real_chmod = os.chmod

        def refuse(path, mode, *args, **kwargs):
            if str(path).endswith("loose"):
                raise OSError("not yours")
            return real_chmod(path, mode, *args, **kwargs)

        monkeypatch.setattr(persistence.os, "chmod", refuse)
        result = persistence.move_to_trash(tmp_path, names=["loose"], dry_run=False, stamp="RUN")

        assert result["moved"] == ["loose"]
        assert (tmp_path / "trash" / "RUN" / "loose").exists()

    def test_given_a_private_key_when_unnamed_then_only_a_named_run_reaches_it(self, tmp_path):
        """The pem the declaration never names stays until the person says its name.

        `doctor --fix` never touches it — a private key is not debris — and this verb reaches
        it only through `--clear`, which is the difference between a folder the product clears
        and one it clears on instruction.
        """
        key = tmp_path / "first-party.private.pem"
        key.write_text("secret", encoding="utf-8")

        assert persistence.move_to_trash(tmp_path, names=[], dry_run=False)["moved"] == []
        assert key.exists(), "an unnamed key moved without being named"

        result = persistence.move_to_trash(tmp_path, names=[key.name], dry_run=False, stamp="RUN")
        assert result["moved"] == [key.name]
        assert not key.exists()
