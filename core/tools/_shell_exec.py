"""Ephe – run_shell / execute_confirmed_shell tools."""

from __future__ import annotations

import asyncio
import os
import select
import subprocess
import time

from core.tools.base import (
    SHELL_TIMEOUT_SECONDS,
    ShellTimeoutError,
)
from core.tools._shell_proc import (
    SANDBOX_UNAVAILABLE,
    _exec_sync,
    _kill_group,
    _new_group_kwargs,
    _reap,
    _shell_backend,
    _docker_exec,
    resolve_sandbox,
)
from core.tools._shell_validate import validate_shell_command


# J2: background-task register (module-global table, FIFO cap like the R23 reservoir).
# each entry: {"status": running|done|stopped|error, "out": str, "handle": Task}
_BG_TASKS: dict[str, dict] = {}


_BG_COUNTER = 0


_BG_MAX_TASKS = 50


def _resolve_cwd(cwd: str | None) -> str:
    """R37: resolve cwd inside the workspace; outside/missing → workspace root.
    Conservative rule: only paths under the active workspace count."""
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


def _sandbox_args(command: str, cwd: str | None) -> list[str] | None:
    """W16: Seatbelt wrapper arguments, ONLY when the real wrapper takes effect.

    The 'sandboxed' status used for interpreter hardening is a successful
    wrap_command return (not merely the config flag) — that keeps the
    semantics honest even on platforms where the wrapper is unavailable.
    """
    return resolve_sandbox(command, _resolve_cwd(cwd))[0]


async def run_shell(command: str, run_in_background: bool = False, cwd: str | None = None) -> str:
    """Run a shell command (whitelist + blocked patterns as the barrier).

    The approval gate (y/n/a in the TUI / --yes in the CLI) runs OUTSIDE
    — in execute_tool() or inline in chat_with_tools(). Whoever calls
    run_shell() directly gets the whitelisted behaviour.

    Security model (repo-hygiene audit 2026-09-06, W16-P3 hardened):
    1. BLOCKED_PATTERNS — destructive patterns, command/process substitution,
       newlines (raw-string check, catches quote tricks)
    2. ALLOWED_COMMANDS — checks the head of EVERY segment (; | && || &),
       not just the first token; curl/wget deliberately not whitelisted
    3. No redirects / subshells
    4. Interpreter flags (-c/-e/-i) only with a really active Seatbelt sandbox

    J2: run_in_background=True → immediate task id ('bg1', 'bg2', …), the work
    continues as an asyncio task; output/status via task_output(), abort
    via task_stop(). Validation runs before registration (identical
    barriers to the synchronous path).
    """
    global _BG_COUNTER

    rejection = validate_shell_command(command, sandboxed=_sandbox_args(command, cwd) is not None)
    if rejection is not None:
        return rejection

    if not run_in_background:
        return await execute_confirmed_shell(command, confirmed=True, cwd=cwd)

    _BG_COUNTER += 1
    task_id = f"bg{_BG_COUNTER}"
    while len(_BG_TASKS) >= _BG_MAX_TASKS:
        _BG_TASKS.pop(next(iter(_BG_TASKS)), None)
    # cmd/started/cwd are recorded so `process_manage(action='list')` can say
    # WHICH job an id names and how long it has run — without them the register
    # was addressable only by an id the agent had to have kept.
    _BG_TASKS[task_id] = {
        "status": "running",
        "out": "",
        "handle": None,
        "cmd": command,
        "cwd": cwd or "",
        "started": time.time(),
    }
    _BG_TASKS[task_id]["handle"] = asyncio.create_task(
        _exec_bg_task(task_id, command, cwd)
    )
    return task_id


async def _exec_bg_task(task_id: str, command: str, cwd: str | None = None) -> None:
    """Run the command in the background and write it into the register."""
    try:
        out = await execute_confirmed_shell(command, confirmed=True, cwd=cwd)
        entry = _BG_TASKS.get(task_id)
        if entry is not None:
            entry["out"] = out
            if entry["status"] == "running":
                entry["status"] = "done"
    except asyncio.CancelledError:
        entry = _BG_TASKS.get(task_id)
        if entry is not None:
            entry["status"] = "stopped"
    except (OSError, ValueError) as exc:
        entry = _BG_TASKS.get(task_id)
        if entry is not None:
            entry["status"] = "error"
            entry["out"] = str(exc)


async def task_output(
    task_id: str, block: bool = True, timeout_s: float = 30.0
) -> str:
    """Output + status of a background task (J2, point 7).

    block=True waits up to timeout_s for completion; block=False reads the
    current state. Unknown id → an honest 'not found' message.
    """
    entry = _BG_TASKS.get(task_id)
    if entry is None:
        return f"[Error: background task '{task_id}' not found]"

    handle = entry.get("handle")
    if block and handle is not None and not handle.done():
        try:
            await asyncio.wait_for(asyncio.shield(handle), timeout=timeout_s)
        except asyncio.TimeoutError:
            pass

    status = entry.get("status", "running")
    out = entry.get("out", "")
    if status == "running":
        return (
            f"[{task_id} | running] no output yet — "
            "call again (block=false) or wait with block=true."
        )
    return f"[{task_id} | {status}]\n{out}" if out else f"[{task_id} | {status}] (no output)"


async def task_stop(task_id: str) -> str:
    """Abort a background task (J2, item 8). Cancel + status 'stopped'."""
    entry = _BG_TASKS.get(task_id)
    if entry is None:
        return f"[Error: background task '{task_id}' not found]"

    handle = entry.get("handle")
    if handle is not None and not handle.done():
        handle.cancel()
        entry["status"] = "stopped"
        return f"Task {task_id} stopped."
    return f"Task {task_id} already {entry.get('status', 'done')}."


async def execute_confirmed_shell(command: str, confirmed: bool, cwd: str | None = None) -> str:
    if not confirmed:
        # A refusal is a coded fact before it is a sentence: the same `[TOOL-DENIED]`
        # line the other gates emit, carrying `Denied.code` for the frame and the card.
        # A bare sentence here is what let a denied run read as a successful one — no
        # marker for the audit (`core.quality.result_decision`), no code for `tool_done`
        # (`server/routes/chat.py`), so every surface downstream saw an ordinary run.
        from core.tools.chat_gate import denial_message

        return denial_message("run_shell", "not_approved_by_user")

    # F (workspace): commands run in the user-set project folder
    # (engine.json → get_workspace_dir). Relative paths (git status, ls,
    # pytest …) therefore hit the project, not the server folder. The
    # validation below stays the hard security boundary.
    # R37: an optional cwd (resolved in-workspace) overrides that root.
    workspace = _resolve_cwd(cwd)

    # W16/WB-16: decide the wrapper ONCE — the same resolver feeds the validation
    # flag, the exec path and the audit detail, so no host reads a different surface.
    sandbox_args, sandbox_detail = resolve_sandbox(command, workspace)
    rejection = validate_shell_command(command, sandboxed=sandbox_args is not None)
    if rejection is not None:
        return rejection

    # A configured sandbox with no wrapper on this host (sandbox-exec is macOS-only)
    # still runs unsandboxed here; the resolver already named that outcome.
    sandbox_unavailable = sandbox_detail == SANDBOX_UNAVAILABLE

    # R23: audit — time, hash + redacted command, exit status, duration.
    import time as _time

    from core.audit_log import audit_event
    from core.redact import redact

    _started = _time.monotonic()

    def _audit(status: str, detail: str = "") -> None:
        audit_event(
            "shell", tool="run_shell",
            args={"command": redact(command)},
            status=status, detail=detail[:300],
            duration_ms=int((_time.monotonic() - _started) * 1000),
        )

    try:
        if sandbox_args is not None:
            # Sandbox active → subprocess WITHOUT shell=True (wrapper chain).
            # The Seatbelt sandbox is local by definition — it wins
            # against the backend env (conservative, release bar).
            result = await asyncio.to_thread(
                _exec_sync, sandbox_args, workspace, False
            )
            _audit("sandboxed")
        elif _shell_backend() == "docker":
            # Issue #19: the runs-anywhere entry — execution in the per-workspace
            # container (workspace mounted as /workspace). Validation
            # above runs unchanged BEFORE the backend; fail-closed on an
            # unusable daemon. The PTY route (terminal panel) stays local.
            try:
                result = await asyncio.to_thread(_docker_exec, command, workspace)
                _audit("executed", detail=(
                    "backend=docker sandbox-unavailable" if sandbox_unavailable else "backend=docker"
                ))
            except RuntimeError as exc:
                _audit("docker-unusable", str(exc))
                return f"[docker backend error] {exc}"
        else:
            result = await asyncio.to_thread(
                _exec_sync, command, workspace, True
            )
            _audit("executed", detail="sandbox-unavailable" if sandbox_unavailable else "")

        output = result.stdout.strip()
        if result.returncode != 0:
            error = result.stderr.strip()
            final_out = f"{output}\n[exit {result.returncode}] {error}".strip()
        else:
            final_out = output or "(no output)"

        if len(final_out) > 10000:
            final_out = final_out[:10000] + "\n\n... [shell output truncated to 10,000 characters for safety]"

        return final_out

    except subprocess.TimeoutExpired:
        _audit("timeout")
        raise ShellTimeoutError(command, SHELL_TIMEOUT_SECONDS)


def run_shell_pty(command: str, stdin_text: str = "") -> str:
    """W17 P1-1: PTY-backed execution (onlcr, stdin via write+EOF).

    Without os.openpty (e.g. some Windows setups) the path falls back to the
    PIPE-based _exec_sync — the output stays deterministic.
    """
    rejection = validate_shell_command(command)
    if rejection is not None:
        return rejection
    workspace = _resolve_cwd(None)
    if not hasattr(os, "openpty"):
        return _exec_sync(command, workspace, True).stdout or "(no output)"
    primary, secondary = os.openpty()
    proc = None
    try:
        proc = subprocess.Popen(
            command,
            shell=True,
            stdin=secondary,
            stdout=secondary,
            stderr=secondary,
            text=False,
            cwd=workspace,
            **_new_group_kwargs(),
        )
        # The secondary stays open in the parent until the master is drained
        # (closing it earlier cost the last data block in measurements).
        if stdin_text:
            try:
                os.write(primary, stdin_text.encode("utf-8"))
            except OSError:
                pass
        deadline = time.monotonic() + SHELL_TIMEOUT_SECONDS
        chunks: list[bytes] = []
        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            ready = select.select([primary], [], [], min(0.1, remaining))[0]
            if not ready:
                # The exit status can arrive before the master EOF —
                # in that case no further bytes are to be expected.
                if proc.poll() is not None:
                    break
                continue
            try:
                more = os.read(primary, 4096)
            except OSError:
                break
            if not more:
                break
            chunks.append(more)
        else:
            _kill_group(proc.pid)
            _reap(proc)
            return f"[timeout after {SHELL_TIMEOUT_SECONDS}s] {command}"
        body = b"".join(chunks).decode("utf-8", "replace").strip()
        return body if body else "(no output)"
    finally:
        for fd in (primary, secondary):
            if fd is None:
                continue
            try:
                os.close(fd)
            except OSError:
                pass
