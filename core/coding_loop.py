"""Verification after a file edit, and the directive that starts the repair.

`write_file` and `edit_file` return a string the model reads in the same turn.
Appending the check's outcome turns that string into the feedback edge of a
self-repair loop: a broken file comes back with the compiler's own words and an
instruction to fix it, a clean file comes back with a silent pass. The budget is
two repairs per user turn — a model that cannot fix a file in two attempts must
report the failure instead of editing in circles.
"""
from __future__ import annotations

import shlex
import subprocess
import sys
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from core import shell_sandbox

#: Repairs a single user turn may spend; the third failure gets the report line.
MAX_REPAIRS = 2
#: A checker is a compile, not a test suite: 30 s is the slowest healthy run.
TIMEOUT_SECONDS = 30.0
#: How much of the checker's output the model sees; a traceback is shorter.
MAX_OUTPUT_CHARS = 4000

_used: ContextVar[int] = ContextVar("coding_loop_repairs", default=0)


@dataclass(frozen=True)
class Verdict:
    ok: bool
    command: str
    output: str


def reset_turn() -> None:
    """One turn = one budget; the chat route calls this before the model loop."""
    _used.set(0)


def repairs_used() -> int:
    return _used.get()


def verification_command(path: Path) -> list[str] | None:
    """The cheapest checker this file type has, or None where there is none."""
    suffix = path.suffix.lower()
    if suffix == ".py":
        return [sys.executable, "-m", "py_compile", str(path)]
    if suffix in {".js", ".cjs", ".mjs"}:
        return ["node", "--check", str(path)]
    if suffix == ".json":
        return [sys.executable, "-c", "import json,sys;json.load(open(sys.argv[1]))", str(path)]
    return None


def verify(path: Path, *, timeout: float = TIMEOUT_SECONDS) -> Verdict | None:
    """Run the checker in the sandbox when the platform has one, else directly."""
    command = verification_command(path)
    if command is None or not path.exists():
        return None
    line = shlex.join(command)
    run = shell_sandbox.wrap_command(line, str(path.parent)) if shell_sandbox.is_available() else None
    argv = run if run else command
    try:
        done = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(path.parent),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return Verdict(False, line, f"checker could not run: {exc}")
    output = f"{done.stdout}{done.stderr}".strip()
    return Verdict(done.returncode == 0, line, output[-MAX_OUTPUT_CHARS:])


def annotation(path: Path) -> str:
    """What a successful edit appends to its own result; empty where unchecked."""
    verdict = verify(path)
    if verdict is None:
        return ""
    if verdict.ok:
        return f"\n\n[sandbox check passed: {verdict.command}]"
    used = _used.get()
    if used >= MAX_REPAIRS:
        return (
            f"\n\n[sandbox check FAILED after {used} repair attempt(s); the budget is spent. "
            f"Report what still fails and why instead of editing again.]\n{verdict.output}"
        )
    _used.set(used + 1)
    return (
        f"\n\n[sandbox check FAILED ({used + 1}/{MAX_REPAIRS}) — tests failed after edit. "
        f"Analyze this output and repair the file in this turn.]\n{verdict.output}"
    )
