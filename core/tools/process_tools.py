"""Ephe – process_manage (unified background process manager).

Parity harness: list | poll | wait | kill over the same task id that run_shell
(run_in_background=True) assigns. Uses the shared _BG_TASKS register from
shell_tools — no second register, no double bookkeeping.

G6 (workbench gap): the manager could only be driven by an id the agent had to
keep from an earlier answer. ``action='list'`` enumerates the register, so what
is running is visible without having remembered anything, and the id a stop
needs is found instead of guessed.
"""
from __future__ import annotations

import asyncio
import time

from core.reason import reason
from core.tools.shell_tools import _BG_TASKS

#: Command preview length in the listing — one line per task, enough to say
#: which job it is without turning the register into a second result channel.
_CMD_PREVIEW = 80


async def process_manage(action: str, task_id: str = "", timeout_s: float = 30.0) -> str:
    """Lists, polls, waits for or kills a background process.

    Args:
        action: 'list' (all registered jobs), 'poll' (current state, non-blocking),
                'wait' (until timeout_s finishes), 'kill' (abort).
        task_id: the id assigned by run_shell(run_in_background=True).
        timeout_s: waiting budget for 'wait'.

    Returns:
        Status + output, a listing, or confirmation.
    """
    action = (action or "").strip().lower()
    if action not in {"list", "poll", "wait", "kill"}:
        return reason(
            "process_action_unknown",
            f"[process_manage] unknown action '{action}' (list|poll|wait|kill)",
            action=action,
        )
    if action == "list":
        return _listing()
    if not task_id:
        return reason("process_needs_task_id", "[process_manage] 'task_id' is required")

    entry = _BG_TASKS.get(task_id)
    if entry is None:
        return reason(
            "process_unknown_task",
            f"[process_manage] no process with task_id '{task_id}'",
            task_id=task_id,
        )

    handle = entry.get("handle")

    if action == "poll":
        return _format(task_id, entry)

    if action == "wait":
        if handle is not None and not handle.done():
            try:
                await asyncio.wait_for(asyncio.shield(handle), timeout=timeout_s)
            except asyncio.TimeoutError:
                pass
        return _format(task_id, entry)

    # kill
    if handle is not None and not handle.done():
        handle.cancel()
        entry["status"] = "stopped"
        return reason("process_stopped", f"Process {task_id} stopped.", task_id=task_id)
    return reason(
        "process_already_state",
        f"Process {task_id} is already {entry.get('status', 'done')}.",
        task_id=task_id,
        state=str(entry.get("status", "done")),
    )


def _listing() -> str:
    """The register as a table: id, status, age, output size, command preview.

    Plain text, not a coded reason: a listing is not one sentence a card can
    replace with a locale entry. Every field is read from the entry and shown as
    it is — an entry whose command was not recorded says so instead of inventing
    one (a test-built entry has no 'cmd').
    """
    if not _BG_TASKS:
        return "[process_manage] no background process registered."

    now = time.time()
    lines = [f"[process_manage] {len(_BG_TASKS)} background process(es):"]
    for task_id, entry in _BG_TASKS.items():
        status = str(entry.get("status", "running"))
        out = entry.get("out") or ""
        started = entry.get("started")
        age = ""
        if isinstance(started, (int, float)) and started > 0:
            age = f" age={max(0.0, now - started):.1f}s"
        cmd = str(entry.get("cmd") or "(command not recorded)")
        cmd = " ".join(cmd.split())[:_CMD_PREVIEW]
        lines.append(
            f"  {task_id} | {status}{age} | out={len(out)}B | {cmd}"
        )
    lines.append("  stop one with: process_manage(action='kill', task_id='<id>')")
    return "\n".join(lines)


def _format(task_id: str, entry: dict) -> str:
    status = entry.get("status", "running")
    out = entry.get("out", "")
    if status == "running":
        return reason(
            "process_output_pending",
            f"[{task_id} | running] no output yet — use 'wait'.",
            task_id=task_id,
        )
    if not out:
        return reason(
            "process_no_output",
            f"[{task_id} | {status}] (no output)",
            task_id=task_id,
            status=status,
        )
    return f"[{task_id} | {status}]\n{out}"
