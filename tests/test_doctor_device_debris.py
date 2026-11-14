"""`ephe doctor` and the device folder's stale entries.

The folder holds what the product declared plus what hands and old releases left. The
doctor names the leftovers, and `--fix` moves the recognised ones under the folder's own
trash — a repair that stays reversible, because a hand that wrote a backup meant it.
"""

from __future__ import annotations

import ephe_cli


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
        real_move = ephe_cli.shutil.move

        def hold_one(src, dst):
            if "qwen" in str(src):
                raise OSError("held by another process")
            return real_move(src, dst)

        monkeypatch.setattr(ephe_cli.shutil, "move", hold_one)

        ok, detail = ephe_cli._repair_device_debris(folder=tmp_path)

        assert not ok
        assert "1 stayed" in detail
        assert (tmp_path / "engine.json.qwen-backup").exists()
        assert not (tmp_path / "engine.key.pre-openrouter").exists()

    def test_given_every_move_failing_when_repaired_then_it_names_the_refusal(self, tmp_path, monkeypatch):
        (tmp_path / "engine.json.qwen-backup").write_text("bytes", encoding="utf-8")

        def refuse(src, dst):
            raise OSError("held by another process")

        monkeypatch.setattr(ephe_cli.shutil, "move", refuse)

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
