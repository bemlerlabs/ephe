"""The doctor's Storage row: the bytes under the configuration dir, read from the module
that already decided per store whether a count bounds them.

`core/store_retention.py` grew out of a 2.8 GB folder nobody could see, and until this row
its own report had no reader outside its own tests. The assertions read the line the user
reads, because a row that names the wrong store or hides the prunable half fails silently.
"""

from __future__ import annotations

import pytest

import ephe_cli

MB = 1024 * 1024


@pytest.fixture
def cfg(monkeypatch, tmp_path):
    monkeypatch.setattr("core.engine_config.config_root", lambda: tmp_path)
    return tmp_path


def _write(path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


class TestStorageRow:
    def test_given_two_stores_when_read_then_the_largest_and_the_state_total_are_named(
        self, cfg
    ):
        _write(cfg / "cells" / "work" / "one.bin", 4 * MB)
        _write(cfg / "sessions" / "a.json", 1 * MB)

        line = ephe_cli._doctor_storage_row()

        assert str(cfg) in line
        assert "largest: cells 4.0 MB" in line
        assert "state 5.0 MB" in line
        assert "no build scratch" in line

    def test_given_build_scratch_when_read_then_the_count_that_bounds_it_is_stated(self, cfg):
        for name in ("cpython-wasi", "cpython-wasi-verify"):
            _write(cfg / "build" / name / "stage" / "python.bin", MB)

        line = ephe_cli._doctor_storage_row()

        assert "build scratch 2.0 MB in 2 trees, kept to 2" in line

    def test_given_a_folder_nothing_has_written_to_when_read_then_it_says_so(self, cfg):
        assert "nothing here yet" in ephe_cli._doctor_storage_row()

    def test_given_an_empty_scratch_folder_when_read_then_it_reads_as_absent(self, cfg):
        (cfg / "build").mkdir()

        assert "no build scratch" in ephe_cli._doctor_storage_row()

    def test_given_a_stray_file_where_the_scratch_lives_when_read_then_its_bytes_stand(self, cfg):
        # Only directories are trees the recipe owns; a dropped tarball is still bytes the
        # folder carries, so an entry count of zero may never silence the size.
        _write(cfg / "build" / "leftover.tar.gz", 3 * MB)

        line = ephe_cli._doctor_storage_row()

        assert "no build scratch" not in line
        assert "build scratch 3.0 MB in 0 trees, kept to 2" in line
