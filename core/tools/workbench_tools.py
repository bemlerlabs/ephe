"""Ephe – the agent's own workspace (G6): read what ran, read what it said.

The measured gap this module closes: an agent could start a background job and
lose the id, could execute code in the cell but never fetch the output the cell
had capped behind a byte range, and could be shown a turn in the panel without
any way to read the same turn itself. Three readers answer it:

- ``read_transcript`` — exposes ``core.trajectory`` as a tool: the agent reads
  the steps the panel shows (``GET /api/trajectory`` reads the same list).
- ``read_cell_journal`` — fetches a byte range of this session's ``/work``
  stream journal, which is where the cell tees output that did not fit the
  result block.
- ``process_manage(action='list')`` (``core.tools.process_tools``) — enumerates
  the background register, so a task id is something the agent finds instead of
  something it had to keep.

All three are read-only and therefore SAFE / chat auto-run: none starts a
process, writes into the workspace, or reaches the network. ``read_cell_journal``
resolves the session's ``/work`` through the cell's own ``work_dir`` — it does
not create a second path convention and it does not touch the guest.
"""
from __future__ import annotations

from typing import Any

#: Ceiling of one transcript answer. The trajectory step list is already capped
#: per turn (``trajectory.MAX_STEPS_PER_TURN``); this is the second cap, on the
#: rendered text, so a long turn cannot flood the model's context by accident.
MAX_TRANSCRIPT_CHARS = 8000

#: Default byte range of one journal read (64 KiB). The guest tee writes at most
#: ``cell_output.GUEST_TEE_CAP_BYTES`` (512 KiB) per run and stream, so a full
#: run fits in eight default reads.
DEFAULT_JOURNAL_BYTES = 64 * 1024


def _session_of(session_id: str) -> str:
    """The session a read belongs to: the argument, else the active one."""
    from core.tools.session_ctx import get_current_session

    return (session_id or "").strip() or get_current_session()


def _as_int(value: Any, default: int) -> int:
    """A tolerant integer read (the model sends strings as often as numbers)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _step_line(step: dict, include_text: bool) -> list[str]:
    """One rendered step: number, type, title, state, time, usage — text on request."""
    number = step.get("n", "?")
    etype = str(step.get("type") or "")
    title = str(step.get("title") or "").strip()
    state = str(step.get("state") or "").strip()
    ms = step.get("ms")
    head = f"  {number:>3}. {etype:<12} {title}"
    if state:
        head += f" [{state}]"
    if isinstance(ms, int):
        head += f" +{ms}ms"
    usage = step.get("usage")
    if isinstance(usage, dict):
        head += f" in={usage.get('in')} out={usage.get('out')}"
    lines = [head.rstrip()]
    body = str(step.get("text") or "") if include_text else ""
    if body:
        for raw in body.splitlines():
            lines.append(f"        | {raw}")
    return lines


async def read_transcript(
    session_id: str = "",
    turns: int = 1,
    include_text: bool = False,
    max_chars: int = MAX_TRANSCRIPT_CHARS,
) -> str:
    """Reads this session's model trajectory — the steps the panel shows.

    Args:
        session_id: Session to read; empty means the active session.
        turns: How many of the most recent turns to render (newest first, 1..).
        include_text: Include the captured text bodies (user prompt, reasoning,
            tool output), not only the step titles.
        max_chars: Ceiling of the rendered answer (marker names the cut).

    Returns:
        A numbered timeline, or a sentence stating that the session has none.
    """
    from core import trajectory

    sid = _session_of(session_id)
    recorded = trajectory.get_turns(sid)
    if not recorded:
        return (
            f"[read_transcript] session '{sid}' has no recorded turn. "
            "One entry is written per answered turn; the panel reads the same "
            "list (GET /api/trajectory)."
        )

    wanted = max(1, _as_int(turns, 1))
    selected = recorded[:wanted]
    cap = max(1, _as_int(max_chars, MAX_TRANSCRIPT_CHARS))

    lines = [
        f"[read_transcript] session={sid} showing {len(selected)} of "
        f"{len(recorded)} turn(s), newest first"
    ]
    for index, turn in enumerate(selected, start=1):
        steps = turn.get("steps") or []
        model = str(turn.get("model") or "?")
        duration = turn.get("duration_ms")
        head = f"turn {index} | model={model} | steps={len(steps)}"
        if isinstance(duration, int):
            head += f" | duration={duration}ms"
        lines.append(head)
        if not steps:
            lines.append("  (no steps recorded)")
            continue
        for step in steps:
            lines.extend(_step_line(step, include_text))

    text = "\n".join(lines)
    if len(text) > cap:
        text = text[:cap] + (
            f"\n[read_transcript] cut at {cap} chars — call again with a larger "
            "max_chars or fewer turns."
        )
    return text


async def read_cell_journal(
    stream: str = "stdout",
    start: int = 0,
    length: int = DEFAULT_JOURNAL_BYTES,
    session_id: str = "",
) -> str:
    """Fetches a byte range of this session's cell stream journal.

    The cell tees everything a program writes into ``/work/stdout.log`` and
    ``/work/stderr.log`` while it runs; the result block shows only a capped
    slice and names the byte range it left behind. This reads that range back,
    so capped output is retrievable instead of lost.

    Args:
        stream: 'stdout' or 'stderr'.
        start: First byte to read (0-based; the offset a loss marker named).
        length: How many bytes to read (capped at the guest tee cap).
        session_id: Session whose workspace to read; empty means the active one.

    Returns:
        The decoded range with its byte span, or a sentence naming why it is empty.
    """
    from core.cell_output import (
        GUEST_TEE_CAP_BYTES,
        STDERR_LOG_NAME,
        STDOUT_LOG_NAME,
        read_journal,
    )

    wanted = (stream or "stdout").strip().lower()
    if wanted not in {"stdout", "stderr"}:
        return f"[read_cell_journal] unknown stream '{stream}' (stdout|stderr)."

    # Lazy on purpose: core.cpython_guest would create the session's write root
    # when the registry imports its schemas, so the import waits for a real call.
    from core.cpython_guest import work_dir

    sid = _session_of(session_id)
    name = STDOUT_LOG_NAME if wanted == "stdout" else STDERR_LOG_NAME
    path = work_dir(sid) / name
    if not path.is_file():
        return (
            f"[read_cell_journal] session '{sid}' has no {name} yet — the cell "
            f"writes it while a program runs in execute_code (looked at {path})."
        )

    total = path.stat().st_size
    offset = max(0, _as_int(start, 0))
    want_bytes = _as_int(length, DEFAULT_JOURNAL_BYTES)
    if want_bytes <= 0:
        want_bytes = DEFAULT_JOURNAL_BYTES
    want_bytes = min(want_bytes, GUEST_TEE_CAP_BYTES)

    data = read_journal(path, offset, want_bytes)
    if not data:
        return (
            f"[read_cell_journal] {wanted} range {offset}..{offset + want_bytes} "
            f"is empty in {name} (file size {total})."
        )

    read_end = offset + len(data)
    head = (
        f"[read_cell_journal] {wanted} bytes {offset}..{read_end} of {total} "
        f"(session={sid})"
    )
    remaining = total - read_end
    if remaining > 0:
        head += f"\n{remaining} byte remain — call again with start={read_end}."
    body = data.decode("utf-8", errors="replace")
    return f"{head}\n{body.rstrip()}"


WORKBENCH_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "read_transcript",
            "description": (
                "Reads the agent's own model trajectory for a session — the same "
                "numbered steps (type, title, time, token usage) the panel shows. "
                "Use it to see what you actually did in a turn: which tools ran, in "
                "which order, and how long each took. include_text=True adds the "
                "captured text bodies (user prompt, reasoning, tool output). "
                "Read-only; no approval needed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session to read (default: the active session).",
                    },
                    "turns": {
                        "type": "integer",
                        "description": "How many recent turns to render, newest first (default 1).",
                    },
                    "include_text": {
                        "type": "boolean",
                        "description": "Include captured text bodies, not only step titles (default false).",
                    },
                    "max_chars": {
                        "type": "integer",
                        "description": f"Ceiling of the answer (default {MAX_TRANSCRIPT_CHARS}).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_cell_journal",
            "description": (
                "Fetches a byte range of this session's cell stream journal "
                "(/work/stdout.log or /work/stderr.log). The cell tees everything a "
                "program writes while it runs; when a result block was capped it names "
                "the byte range it left behind — read it back here instead of losing it. "
                "start is the offset from that marker, length the byte count. Read-only; "
                "no approval needed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "stream": {
                        "type": "string",
                        "enum": ["stdout", "stderr"],
                        "description": "Which journal to read (default stdout).",
                    },
                    "start": {
                        "type": "integer",
                        "description": "First byte to read, 0-based (default 0).",
                    },
                    "length": {
                        "type": "integer",
                        "description": f"Bytes to read, capped at the guest tee cap (default {DEFAULT_JOURNAL_BYTES}).",
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Session whose workspace to read (default: the active session).",
                    },
                },
                "required": [],
            },
        },
    },
]
