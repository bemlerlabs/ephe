"""tests/test_cli_stdin_task.py — a task can arrive through a pipe.

Measured 2026-10-15: `grep -n 'sys.stdin' ephe_cli.py core/_cli_run.py core/_cli_onboarding.py`
was empty, so `cat spec.md | ephe run` could not express the task the file holds. The
task-taking verbs are `ephe code`, `ephe run` and `ephe goal`, and all three read their
task from the argument list only.

Two ways to say it, one lever: the task is the words, or `-`, or — when a pipe is
attached and no words were given — what the pipe carries. A terminal never supplies the
task, so a verb called with no argument and no pipe keeps its usage error instead of
blocking on a read nobody would answer.
"""
from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import pytest

from core._cli_common import resolve_task, task_from_stdin
from tests.subprocess_env import hermetic_env

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "ephe_cli.py"


class _Pipe(io.StringIO):
    """A stdin that is not a terminal, the way a shell pipe arrives."""

    def isatty(self) -> bool:
        return False


class _Terminal(io.StringIO):
    """A stdin a human is sitting in front of."""

    def isatty(self) -> bool:
        return True


class _Unreadable(io.StringIO):
    """The stdin pytest installs while it captures: a read there raises OSError."""

    def isatty(self) -> bool:
        return False

    def read(self, *args, **kwargs):  # type: ignore[override]
        raise OSError("pytest: reading from stdin while output is captured!")


def _stdin(monkeypatch, stream) -> None:
    monkeypatch.setattr(sys, "stdin", stream)


# the lever itself


def test_words_win_over_a_pipe(monkeypatch):
    _stdin(monkeypatch, _Pipe("from the pipe"))

    assert resolve_task(["make", "the", "test", "green"]) == "make the test green"


def test_a_dash_names_the_pipe(monkeypatch):
    _stdin(monkeypatch, _Pipe("make the test green\n"))

    assert resolve_task(["-"]) == "make the test green"


def test_no_words_reads_the_pipe(monkeypatch):
    _stdin(monkeypatch, _Pipe("  take the failing test to green \n"))

    assert resolve_task([]) == "take the failing test to green"


def test_a_terminal_supplies_nothing(monkeypatch):
    _stdin(monkeypatch, _Terminal("typed at the prompt"))

    assert task_from_stdin() == ""
    assert resolve_task([]) == ""


def test_an_unreadable_stdin_is_not_a_task(monkeypatch):
    """A captured or closed stdin answers "" instead of raising into the verb."""
    _stdin(monkeypatch, _Unreadable("x"))

    assert task_from_stdin() == ""
    assert resolve_task(["-"]) == ""


# the verbs, end to end


def _run_piped(
    cfg: Path, *argv: str, stdin: str = "make the failing test green"
) -> subprocess.CompletedProcess:
    """The real CLI with a real pipe attached, in a config dir of its own.

    No engine is configured in that dir, so a verb that accepted the task stops at the
    fail-closed engine gate (exit 1). A verb that ignored the pipe never gets there.
    """
    return subprocess.run(
        [sys.executable, str(CLI), *argv],
        input=stdin,
        capture_output=True,
        text=True,
        env=hermetic_env(PYTHONPATH="", EPHE_CONFIG_DIR=str(cfg)),
    )


@pytest.fixture
def cfg(tmp_path) -> Path:
    """An empty config dir: no engine.json, no engine env, so no engine is chosen."""
    path = tmp_path / "cfg"
    path.mkdir()
    return path


@pytest.mark.parametrize("verb", ["code", "run", "goal"])
def test_the_piped_task_reaches_the_verb(verb, cfg):
    """
    GIVEN `cat task.md | ephe <verb>` — no task argument at all
    WHEN the verb runs
    THEN it reads the pipe: the run gets past the task check and stops at the engine gate.
    """
    r = _run_piped(cfg, verb)

    assert r.returncode == 1, r.stdout + r.stderr
    assert "No engine configured" in (r.stdout + r.stderr)
    assert "Usage: ephe" not in r.stdout


@pytest.mark.parametrize("verb", ["code", "run", "goal"])
def test_a_lone_dash_reaches_the_verb_too(verb, cfg):
    """
    GIVEN `cat task.md | ephe <verb> -`
    WHEN the verb runs
    THEN the dash names the pipe explicitly and the task arrives the same way.
    """
    r = _run_piped(cfg, verb, "-")

    assert r.returncode == 1, r.stdout + r.stderr
    assert "No engine configured" in (r.stdout + r.stderr)


@pytest.mark.parametrize("verb", ["code", "run", "goal"])
def test_no_task_and_an_empty_pipe_is_still_a_usage_error(verb, cfg):
    """
    GIVEN an empty pipe and no task argument
    WHEN the verb runs
    THEN it prints the usage line and answers 2 — an empty read is no task.
    """
    r = _run_piped(cfg, verb, stdin="")

    assert r.returncode == 2
    assert "Usage: ephe" in r.stdout


def test_the_argument_still_outranks_the_pipe(cfg):
    """
    GIVEN a task on the command line and a different one in the pipe
    WHEN `ephe run "<task>"` runs
    THEN the argument is the task: the pipe is only a fallback.
    """
    r = _run_piped(cfg, "run", "from the command line")

    assert r.returncode == 1, r.stdout + r.stderr
    assert "No engine configured" in (r.stdout + r.stderr)

