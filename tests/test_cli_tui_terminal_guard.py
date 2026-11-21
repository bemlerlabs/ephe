"""QA residue 3 — `ephe tui` refuses a non-terminal instead of hanging in it.

Measured: `python -m ephe_cli tui < /dev/null` with stdout on a pipe never returned. The
terminal app drew an 80x24 frame into the pipe and then waited for keys nobody could
type, so a script, a CI step or a `| tee` call hung until it was killed.

The front door now checks the two streams the app uses before it builds the screen, and
answers with a message and the usage exit code (2) — the same code the bare `ephe` path
already returns without a TTY (`_default_command`).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import ephe_cli

from tests.subprocess_env import hermetic_env

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "ephe_cli.py"


class _Stream:
    """A stream that answers ``isatty()`` the way the test needs and forwards the rest."""

    def __init__(self, inner: object, interactive: bool) -> None:
        self._inner = inner
        self._interactive = interactive

    def isatty(self) -> bool:
        return self._interactive

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


def _terminal(monkeypatch: pytest.MonkeyPatch, interactive: bool) -> None:
    monkeypatch.setattr(sys, "stdin", _Stream(sys.stdin, interactive))
    monkeypatch.setattr(sys, "stdout", _Stream(sys.stdout, interactive))


def test_without_a_terminal_the_front_door_refuses(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import ephe_cli

    _terminal(monkeypatch, False)
    with pytest.raises(SystemExit) as exc:
        ephe_cli.require_terminal_for_tui()
    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "ephe tui" in err, err
    assert "terminal" in err, err
    assert "next:" in err, err


def test_with_a_terminal_it_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    import ephe_cli

    _terminal(monkeypatch, True)
    assert ephe_cli.require_terminal_for_tui() is None


def test_the_real_command_returns_instead_of_hanging(tmp_path: Path) -> None:
    """The exact repro: stdin from /dev/null, both streams pipes."""
    completed = subprocess.run(
        [sys.executable, str(CLI), "tui"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=ROOT,
        env=hermetic_env(PYTHONPATH="", EPHE_CONFIG_DIR=str(tmp_path / "config")),
    )
    printed = completed.stdout + completed.stderr
    assert completed.returncode == 2, printed[-2000:]
    assert "terminal" in printed, printed[-2000:]
    assert "Traceback" not in printed, printed[-2000:]


def test_main_guards_the_tui_verb_before_it_starts(monkeypatch, capsys):
    """The front door, not just the helper: `ephe tui` on a pipe never reaches the app."""
    monkeypatch.setattr("sys.argv", ["ephe", "tui"])
    monkeypatch.setattr(ephe_cli, "_attached_to_a_terminal", lambda: False)
    with pytest.raises(SystemExit) as excinfo:
        ephe_cli.main()
    assert excinfo.value.code == 2
    assert "interactive terminal" in capsys.readouterr().err
