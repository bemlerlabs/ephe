"""Ephe – test_tools: run_tests (R22 Agentic Coding Loop).

Verification primitive of the coding loop: runs TEST RUNNERS in the workspace
(pytest / vitest / npm test / python -m pytest / npx vitest). Not a general
shell substitute — the segment guard (validate_shell_command) runs BEFORE the
runner whitelist, the approval gate (mutating) comes from the registry.

Output cap: the last 8000 characters (error endings stay visible, buffers do not
flood the context).
"""
from __future__ import annotations

import asyncio
import subprocess
import sys
import time

from core.tools.shell_tools import validate_shell_command

#: Allowed runner heads (first token). Anything else → run_shell (approval).
#: R37: 'node' added (node type runner: 'node --test …').
TEST_RUNNERS: frozenset[str] = frozenset({
    "pytest", "python", "python3", "npm", "npx", "vitest", "node",
})


def resolve_test_cwd(cwd: str | None) -> str:
    """R37: resolve cwd inside the workspace; outside/missing → workspace root.
    Conservative rule: only paths under the active workspace count."""
    import os

    from core.engine_config import get_workspace_dir

    base = get_workspace_dir()
    if not cwd:
        return base
    candidate = cwd if os.path.isabs(cwd) else os.path.join(base, cwd)
    candidate = os.path.normpath(candidate)
    base_norm = os.path.normpath(base)
    if os.path.isdir(candidate) and (candidate == base_norm or candidate.startswith(base_norm + os.sep)):
        return candidate
    return base_norm

TEST_TIMEOUT_SECONDS = 300
MAX_OUTPUT_CHARS = 8000


async def run_tests(command: str = "pytest -q", cwd: str | None = None) -> str:
    """Runs a test runner in the workspace and summarizes the result.

    Limits: validate_shell_command (segments/substitution/redirects) + runner
    whitelist + 300 s timeout + 8000-character output (the tail stays). Return with
    an `[exit N]` marker like run_shell.

    R37: optional `cwd` (resolved in-workspace; outside it, the
    resolution falls back to the workspace root).
    """
    command = (command or "").strip()
    if not command:
        return "[run_tests] Leerer Befehl."

    rejection = validate_shell_command(command)
    if rejection is not None:
        return f"[run_tests] {rejection}"

    first = command.split()[0]
    if first not in TEST_RUNNERS:
        return (
            f"[run_tests] Only test runners allowed: {', '.join(sorted(TEST_RUNNERS))}. Anything else belongs in run_shell (with approval)."
        )

    # map 'python'/'python3'/'pytest' onto the running server interpreter:
    # otherwise the subprocess shell, depending on PATH, hits a Python without pytest
    # (e.g. a tools-only interpreter) and '[exit 0]' never occurs. A bare `pytest` head is the
    # same defect wearing a console script: PATH picks whichever interpreter owns the first
    # `pytest` it finds, so a machine's ambient install decides the verdict. Measured on the
    # self-hosted arm64 runner — `pytest -q` fell through to a stale ~/.local/bin/pytest of
    # another Python and returned `[exit 1]` with `ModuleNotFoundError: No module named
    # 'typing_extensions'`, while the same test passed on a leg whose PATH did have the
    # script. `-m pytest` keeps the choice inside the environment the user controls; its worst
    # case is an honest `No module named pytest`.
    if first in ("python", "python3"):
        rest = command.split(None, 1)
        command = sys.executable + ((" " + rest[1]) if len(rest) > 1 else "")
    elif first == "pytest":
        rest = command.split(None, 1)
        command = sys.executable + " -m pytest" + ((" " + rest[1]) if len(rest) > 1 else "")

    started = time.monotonic()
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=TEST_TIMEOUT_SECONDS,
            cwd=resolve_test_cwd(cwd),
        )
    except subprocess.TimeoutExpired:
        return f"[run_tests] Timeout after {TEST_TIMEOUT_SECONDS}s — Befehl abgebrochen."

    output = (result.stdout or "").strip()
    errors = (result.stderr or "").strip()
    combined = f"{output}\n{errors}".strip()
    duration = int((time.monotonic() - started) * 1000)

    tail = combined[-MAX_OUTPUT_CHARS:]
    if len(combined) > MAX_OUTPUT_CHARS:
        tail = f"... [beginning truncated, {len(combined) - MAX_OUTPUT_CHARS} characters]\n{tail}"

    header = f"run_tests: [exit {result.returncode}] ({duration} ms)"
    return f"{header}\n{tail}" if tail else header
