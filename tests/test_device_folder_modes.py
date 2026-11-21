"""The device folder's modes: what the writers set and what `ephe doctor` reads back.

The start banner says `local & private`. Two files carried a mode that made that a
sentence about intention rather than about the disk — measured 2026-11-16 on the machine
that ships Ephe, the turn trace at 3 610 934 bytes and 644, the detached backend's log at
19 155 576 bytes and 644. The writers now open private, `core.persistence.world_readable`
reads the modes off the folder the declaration names, and `doctor --fix` tightens what it
finds.
"""

from __future__ import annotations

import os
import stat

import ephe_cli
from core import persistence, trajectory


def _mode(path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


class TestWritersOpenPrivate:
    def test_given_a_recorded_turn_when_the_trace_is_persisted_then_only_the_owner_reads_it(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        trajectory.begin_turn("modes", model="m")
        trajectory.record("modes", {"type": "user", "title": "the prompt text"})
        trajectory.end_turn("modes")

        path = tmp_path / "trajectory.json"
        assert path.is_file(), "the trace never reached the disk, so the mode proves nothing"
        assert _mode(path) == persistence.PRIVATE_FILE_MODE
        assert not list(tmp_path.glob("trajectory.json.tmp*")), "the temporary outlived the replace"

    def test_given_an_existing_world_readable_trace_when_it_is_written_again_then_it_closes(
        self, tmp_path, monkeypatch
    ):
        path = tmp_path / "trajectory.json"
        path.write_text("{}", encoding="utf-8")
        path.chmod(0o644)
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))

        trajectory.begin_turn("modes", model="m")
        trajectory.record("modes", {"type": "user", "title": "the prompt text"})
        trajectory.end_turn("modes")

        assert _mode(path) == persistence.PRIVATE_FILE_MODE, (
            "a trace an older build left at 644 stayed 644 through the rewrite"
        )

    def test_given_the_backend_log_when_the_backend_is_spawned_then_the_log_opens_private(
        self, tmp_path
    ):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        with ephe_cli._backend_log_handle(log_dir) as handle:
            handle.write(b"line\n")
        assert _mode(log_dir / "desktop-backend.log") == persistence.PRIVATE_FILE_MODE

    def test_given_an_existing_world_readable_log_when_the_backend_opens_it_again_then_it_closes(
        self, tmp_path
    ):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        path = log_dir / "desktop-backend.log"
        path.write_text("old\n", encoding="utf-8")
        path.chmod(0o644)

        with ephe_cli._backend_log_handle(log_dir) as handle:
            handle.write(b"new\n")

        assert _mode(path) == persistence.PRIVATE_FILE_MODE
        assert path.read_text(encoding="utf-8") == "old\nnew\n", "the append became a truncate"


class TestPermissionScan:
    def test_given_an_open_content_file_when_scanned_then_it_is_named_with_its_mode(self, tmp_path):
        (tmp_path / "trajectory.json").write_text("{}", encoding="utf-8")
        (tmp_path / "trajectory.json").chmod(0o644)

        report = persistence.world_readable(tmp_path)

        assert [row["name"] for row in report["open"]] == ["trajectory.json"]
        assert report["open"][0]["mode"] == "644"

    def test_given_a_private_file_when_scanned_then_nothing_is_reported(self, tmp_path):
        (tmp_path / "trajectory.json").write_text("{}", encoding="utf-8")
        (tmp_path / "trajectory.json").chmod(0o600)

        assert persistence.world_readable(tmp_path)["open"] == []

    def test_given_a_folder_that_is_itself_private_when_scanned_then_its_contents_are_not_read(
        self, tmp_path
    ):
        logs = tmp_path / "logs"
        logs.mkdir()
        logs.chmod(0o700)
        (logs / "desktop-backend.log").write_text("x", encoding="utf-8")
        (logs / "desktop-backend.log").chmod(0o644)

        assert persistence.world_readable(tmp_path)["open"] == [], (
            "bytes behind a 700 door are reachable by nobody but the owner; reporting them "
            "would make the row say something the disk does not"
        )

    def test_given_an_open_folder_when_scanned_then_the_folder_and_its_files_are_named(
        self, tmp_path
    ):
        logs = tmp_path / "logs"
        logs.mkdir()
        logs.chmod(0o755)
        (logs / "desktop-backend.log").write_text("x", encoding="utf-8")
        (logs / "desktop-backend.log").chmod(0o644)

        names = {row["name"] for row in persistence.world_readable(tmp_path)["open"]}

        assert names == {"logs", "logs/desktop-backend.log"}

    def test_given_more_files_than_the_cap_when_scanned_then_the_answer_says_it_stopped(
        self, tmp_path
    ):
        logs = tmp_path / "logs"
        logs.mkdir()
        logs.chmod(0o755)
        for index in range(4):
            (logs / f"log-{index}.txt").write_text("x", encoding="utf-8")
            (logs / f"log-{index}.txt").chmod(0o644)

        report = persistence.world_readable(tmp_path, cap=2)

        assert report["capped"] == ["logs"]
        assert len([row for row in report["open"] if row["name"].startswith("logs/")]) == 2


class TestPermissionRepair:
    def test_given_open_entries_when_repaired_in_dry_run_then_the_disk_is_untouched(self, tmp_path):
        path = tmp_path / "trajectory.json"
        path.write_text("{}", encoding="utf-8")
        path.chmod(0o644)

        result = persistence.make_private(tmp_path, dry_run=True)

        assert len(result["would_tighten"]) == 1
        assert result["tightened"] == []
        assert _mode(path) == 0o644

    def test_given_open_entries_when_repaired_then_files_and_folders_close(self, tmp_path):
        logs = tmp_path / "logs"
        logs.mkdir()
        logs.chmod(0o755)
        log = logs / "desktop-backend.log"
        log.write_text("x", encoding="utf-8")
        log.chmod(0o644)

        result = persistence.make_private(tmp_path, dry_run=False)

        assert len(result["tightened"]) == 2
        assert _mode(logs) == persistence.PRIVATE_DIR_MODE
        assert _mode(log) == persistence.PRIVATE_FILE_MODE

    def test_given_an_entry_another_account_owns_when_repaired_then_it_is_left_alone(
        self, tmp_path, monkeypatch
    ):
        path = tmp_path / "trajectory.json"
        path.write_text("{}", encoding="utf-8")
        path.chmod(0o644)
        owner = os.getuid()
        monkeypatch.setattr(os, "getuid", lambda: owner + 1)

        result = persistence.make_private(tmp_path, dry_run=False)

        assert result["tightened"] == []
        assert result["skipped"] == ["trajectory.json"]
        assert _mode(path) == 0o644

    def test_given_a_clean_folder_when_the_repair_runs_then_it_says_so(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        (tmp_path / "trajectory.json").write_text("{}", encoding="utf-8")
        (tmp_path / "trajectory.json").chmod(0o600)

        ok, detail = ephe_cli._repair_permissions()

        assert ok, detail
        assert detail == "device folder already private"

    def test_given_entries_of_another_account_when_the_repair_runs_then_they_are_reported(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        (tmp_path / "trajectory.json").write_text("{}", encoding="utf-8")
        (tmp_path / "trajectory.json").chmod(0o644)
        owner = os.getuid()
        monkeypatch.setattr(os, "getuid", lambda: owner + 1)

        ok, detail = ephe_cli._repair_permissions()

        assert ok, detail
        assert "1 left alone" in detail and "trajectory.json" in detail

    def test_given_many_open_entries_when_the_repair_runs_then_the_report_stays_short(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        logs = tmp_path / "logs"
        logs.mkdir()
        logs.chmod(0o755)
        for index in range(5):
            line = logs / f"line-{index}.log"
            line.write_text("x", encoding="utf-8")
            line.chmod(0o644)

        ok, detail = ephe_cli._repair_permissions()

        assert ok, detail
        assert "6 tightened" in detail and "3 more" in detail
        assert _mode(logs) == persistence.PRIVATE_DIR_MODE


class TestDoctorRow:
    def test_given_an_open_content_file_when_doctor_reports_then_the_row_goes_red_by_name(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        path = tmp_path / "trajectory.json"
        path.write_text("{}", encoding="utf-8")
        path.chmod(0o644)

        ok, detail = ephe_cli._doctor_permissions()

        assert ok is False
        assert "trajectory.json (644)" in detail
        assert "doctor --fix" in detail

    def test_given_private_entries_when_doctor_reports_then_the_row_is_green(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        logs = tmp_path / "logs"
        logs.mkdir()
        logs.chmod(0o700)
        (tmp_path / "trajectory.json").write_text("{}", encoding="utf-8")
        (tmp_path / "trajectory.json").chmod(0o600)

        ok, detail = ephe_cli._doctor_permissions()

        assert ok, detail
        assert "no content file readable beside the owner" in detail

    def test_given_open_folders_and_no_open_file_when_doctor_reports_then_the_count_is_said(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        logs = tmp_path / "logs"
        logs.mkdir()
        logs.chmod(0o755)
        (logs / "desktop.log").write_text("x", encoding="utf-8")
        (logs / "desktop.log").chmod(0o600)

        ok, detail = ephe_cli._doctor_permissions()

        assert ok, detail
        assert "1 folder(s) list their names" in detail

    def test_given_a_content_folder_beyond_the_cap_when_doctor_reports_then_the_row_says_it_stopped(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        logs = tmp_path / "logs"
        logs.mkdir()
        logs.chmod(0o755)
        for index in range(persistence.SCAN_CAP + 1):
            line = logs / f"line-{index}.log"
            line.write_text("x", encoding="utf-8")
            line.chmod(0o644)

        ok, detail = ephe_cli._doctor_permissions()

        assert ok is False
        assert f"deeper than {persistence.SCAN_CAP} files not read in: logs" in detail

    def test_given_an_os_whose_modes_mean_nothing_when_doctor_reports_then_the_row_says_that(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        (tmp_path / "trajectory.json").write_text("{}", encoding="utf-8")
        (tmp_path / "trajectory.json").chmod(0o644)
        monkeypatch.delattr(os, "getuid")

        ok, detail = ephe_cli._doctor_permissions()

        assert ok, detail
        assert "carries no POSIX modes" in detail
