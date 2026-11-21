"""tests/test_backend_log_rotation.py — the backend log has a size, and one file behind it.

`~/.ephe/logs/desktop-backend.log` reached 19 199 756 bytes on the owner's Mac 2026-11-16 with
nothing bounding it: both surfaces open it to append and neither ever looked at its length.
The CLI half is `ephe_cli._backend_log_handle`, the shell half is `backend_log_handle` in
`app/src-tauri/src/backend.rs`. The cap is spelled in two languages because the shell cannot
ask Python before the process it is about to start exists — which is the reason this file is
the third reader of a source text in the suite: it opens the Rust file to hold the two
spellings of that one number equal, and nothing else in it.

The mode (0600, re-asserted) is pinned in `tests/test_device_folder_modes.py` and is not
repeated here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import ephe_cli

LOG_NAME = "desktop-backend.log"


@pytest.fixture
def logs(tmp_path) -> Path:
    folder = tmp_path / "logs"
    folder.mkdir()
    return folder


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


class TestRotation:
    def test_given_a_short_log_when_the_backend_opens_it_then_the_words_stay_where_they_are(
        self, logs
    ):
        path = logs / LOG_NAME
        path.write_text("an earlier turn\n", encoding="utf-8")

        with ephe_cli._backend_log_handle(logs) as handle:
            handle.write(b"this turn\n")

        assert _lines(path) == ["an earlier turn", "this turn"]
        assert not (logs / f"{LOG_NAME}.1").exists(), "a short log is no reason to rotate"

    def test_given_a_log_past_the_cap_when_the_backend_opens_it_then_the_old_one_is_kept_aside(
        self, logs, monkeypatch
    ):
        monkeypatch.setattr(ephe_cli, "LOG_ROTATE_BYTES", 32)
        path = logs / LOG_NAME
        path.write_text("x" * 64, encoding="utf-8")
        path.chmod(0o644)

        with ephe_cli._backend_log_handle(logs) as handle:
            handle.write(b"fresh\n")

        rotated = logs / f"{LOG_NAME}.1"
        assert len(path.read_text(encoding="utf-8")) == len("fresh\n"), "the new file starts empty"
        assert len(rotated.read_text(encoding="utf-8")) == 64, "the rename kept what was written"
        assert rotated.stat().st_mode & 0o777 == 0o600, "the kept file drops the mode it came with"

    def test_given_two_starts_in_a_row_when_the_log_grows_again_then_only_one_file_is_kept(
        self, logs, monkeypatch
    ):
        """One file behind, not a growing series: a log archive is another store to bound."""
        monkeypatch.setattr(ephe_cli, "LOG_ROTATE_BYTES", 32)
        path = logs / LOG_NAME

        for _ in range(3):
            path.write_text("x" * 64, encoding="utf-8")
            with ephe_cli._backend_log_handle(logs):
                pass

        assert sorted(p.name for p in logs.iterdir()) == [LOG_NAME, f"{LOG_NAME}.1"]

    def test_given_the_real_cap_when_a_log_reaches_it_then_it_rotates(self, logs):
        """The number in the constant itself, where a stand-in would prove nothing."""
        path = logs / LOG_NAME
        path.write_bytes(b"x" * ephe_cli.LOG_ROTATE_BYTES)

        with ephe_cli._backend_log_handle(logs):
            pass

        assert path.stat().st_size == 0
        assert (logs / f"{LOG_NAME}.1").stat().st_size == ephe_cli.LOG_ROTATE_BYTES

    def test_given_a_rename_that_cannot_happen_when_the_backend_opens_it_then_the_start_goes_on(
        self, logs, monkeypatch
    ):
        """A log that will not move is no reason to refuse to start the app."""
        monkeypatch.setattr(ephe_cli, "LOG_ROTATE_BYTES", 32)
        path = logs / LOG_NAME
        path.write_text("x" * 64, encoding="utf-8")

        def refuse(src, dst, *args, **kwargs):
            raise OSError("busy")

        monkeypatch.setattr(ephe_cli.os, "replace", refuse)
        with ephe_cli._backend_log_handle(logs) as handle:
            handle.write(b"more\n")

        assert path.stat().st_size == 64 + len("more\n"), "the append went on in the old file"
        assert not (logs / f"{LOG_NAME}.1").exists()

    def test_given_no_log_yet_when_the_backend_opens_it_then_one_is_made(self, logs):
        with ephe_cli._backend_log_handle(logs) as handle:
            handle.write(b"first\n")

        assert _lines(logs / LOG_NAME) == ["first"]


class TestTheSameCapOnBothSurfaces:
    def test_the_shell_rotates_at_the_size_the_cli_names(self):
        """Two languages, one number.

        The shell cannot ask Python before the process it is about to start exists, so it
        spells the cap itself; this is where the two spellings are held equal.
        """
        source = (
            Path(ephe_cli.PROJECT_ROOT) / "app" / "src-tauri" / "src" / "backend.rs"
        ).read_text(encoding="utf-8")
        found = re.search(r"const BACKEND_LOG_ROTATE_BYTES: u64 = ([^;\n]+)", source)
        assert found, "the shell no longer names its rotation cap where this can read it"
        value = 1
        for token in re.findall(r"[0-9][0-9_]*", found.group(1)):
            value *= int(token.replace("_", ""))

        assert value == ephe_cli.LOG_ROTATE_BYTES, (
            f"the shell rotates at {value}, the CLI at {ephe_cli.LOG_ROTATE_BYTES}"
        )
