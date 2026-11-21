"""core/fleet_rows.py — the row a fleet board carries, and the runs the ledger records.

`core/fleet.py` asks four registers which runs exist and reads a state off each answer.
The row those answers travel in is one shape, so it is written once here, beside the
state words it is allowed to carry: a board whose rows were built twice would be free to
disagree with itself about what `blocked` means.

The fourth register is the run ledger (`core/run/ledger.py`), and it is the only one a
chat turn writes: every streamed turn opens one file under the device folder and appends
one line per fact until the turn closes. Measured 2026-11-03 on the machine that ships
Ephe, `GET /api/workspaces` answered `{"workspaces": [], "runs": []}` beside a chat that
had just produced a file, because the read stopped at the worktree register — which no
chat turn has ever written — and never asked the ledger, which had the run in it. Those
rows are `session_runs`.

A ledger line is content-free, so a row built from one states what the run did: the tool it
last ran, the path it last wrote, the approval it stopped on, and how it ended. What the
person read stays in the transcript.
"""
from __future__ import annotations

import time
from typing import Any

#: The closed vocabulary. `app/src/lib/api/workspaces.ts` and the surface over it name
#: the same four, so a word that reaches the screen still means what it means here.
RUNNING = "running"
WAITING_ON_HUMAN = "waiting_on_human"
BLOCKED = "blocked"
DONE = "done"
RUN_STATES = (RUNNING, WAITING_ON_HUMAN, BLOCKED, DONE)

#: States that are a decision a person owes, and the window a finished run stays on the
#: board for (long enough to see that it landed, short enough that the board stays a
#: fleet). AGENT_LIMIT is the newest-first page size of the paginated registers.
NEEDS_YOU_STATES = (WAITING_ON_HUMAN, BLOCKED)
RECENT_SECONDS = 900
AGENT_LIMIT = 50

#: The line kinds that close a run, and the phase that says a person owes an answer.
TERMINAL_KINDS = ("run_finished", "done")
WAITING_PHASE = "waiting"


def needs_you(state: str) -> bool:
    """Whether this state is a thing a person has to do."""
    return state in NEEDS_YOU_STATES


def seconds_since(stamp: Any, now: float | None = None) -> int | None:
    """How long ago a stamp was, in whole seconds; None when it cannot be read.

    The registers stamp their rows two ways: `core.workspace_lifecycle` writes ISO-8601
    with a `+00:00` offset, the run ledger and `core.subagent_history` write epoch
    seconds. Both reach here. A stamp this cannot read answers None, never a zero.
    """
    if isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
        base = float(stamp)
    elif isinstance(stamp, str) and stamp.strip():
        from datetime import datetime, timezone

        try:
            parsed = datetime.fromisoformat(stamp.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        base = parsed.timestamp()
    else:
        return None
    moment = time.time() if now is None else now
    return max(0, int(moment - base))


def ledger_view(run_id: str) -> dict | None:
    """The run ledger's projection as a fleet view; None when it has no lines."""
    try:
        from core.run.ledger import snapshot_if_present

        return snapshot_if_present(run_id)
    except Exception:
        return None


def row(
    *,
    run_id: str,
    kind: str,
    agent: str,
    task: str = "",
    workspace_id: str = "",
    path: str = "",
    state: str,
    running_for_seconds: int | None,
    last_event: dict | None = None,
    ledger: dict | None = None,
) -> dict:
    """One fleet row, with every field present so the client never guesses a missing one.

    ``ledger`` is the run's own projection. A caller that has already read the lines
    hands them over rather than paying for a second read of the file; every other row
    asks by its id and gets None when no ledger carries that name.
    """
    return {
        "run_id": run_id,
        "kind": kind,
        "agent": agent,
        "task": task,
        "workspace_id": workspace_id,
        "path": path,
        "state": state,
        "needs_you": needs_you(state),
        "running_for_seconds": running_for_seconds,
        "last_event": last_event or {"kind": "none", "text": "", "op": "", "age_seconds": None},
        "ledger": ledger if ledger is not None else ledger_view(run_id),
    }


def awaiting_event(tool: str, seconds: Any) -> dict:
    """The last event of a run that stopped on an unanswered approval."""
    return {
        "kind": "awaiting",
        "text": str(tool or ""),
        "op": "",
        "age_seconds": int(seconds) if isinstance(seconds, int) else None,
    }


def _empty_event() -> dict:
    return {"kind": "none", "text": "", "op": "", "age_seconds": None}


def _last_touch(rows: list[dict]) -> dict:
    """What the run last did: the newest line that names a file, a tool or a wait.

    Read backwards from the end, because a closed turn's last line is its terminal one and
    says nothing about the work; the frames below it still do. An `activity` line is a
    progress ping rather than a touch, so it does not end the search — a run that wrote a
    file and then announced it has touched that file.
    """
    for line in reversed(rows):
        kind = str(line.get("kind") or "")
        age = seconds_since(line.get("ts"))
        if kind in ("sandbox_confirm", "ask"):
            return {"kind": "awaiting", "text": str(line.get("tool") or ""), "op": "",
                    "age_seconds": age}
        if kind in ("artifact", "file_result"):
            paths = [str(p) for p in (line.get("paths") or []) if str(p)]
            return {"kind": "file", "text": paths[0] if paths else "", "op": "create",
                    "age_seconds": age}
        if kind in ("tool_start", "tool_done"):
            return {"kind": "tool", "text": str(line.get("tool") or ""), "op": "",
                    "age_seconds": age}
    return _empty_event()


def _ledger_state(rows: list[dict]) -> str:
    """Where a recorded run stands now, from the lines it left behind.

    A terminal line decides: an error is `blocked`, anything else `done`. Without one, the
    newest line is what the board can honestly say — an unanswered approval is a wait, a
    failed tool is a stop, and everything else is a run that was still moving when the
    ledger last wrote. A turn the process lost mid-flight is `running` until it ages off
    the board; the ledger cannot tell a killed run from a thinking one, and inventing
    `blocked` for both would put a person's own stopped task in the same column as a crash.
    """
    last = rows[-1]
    if str(last.get("kind") or "") in TERMINAL_KINDS or last.get("phase") == "next":
        reason = str(last.get("finish_reason") or "")
        return BLOCKED if (reason == "error" or last.get("reason_code") or last.get("failure_class")) else DONE
    if last.get("phase") == WAITING_PHASE:
        return WAITING_ON_HUMAN
    if str(last.get("kind") or "") == "error":
        return BLOCKED
    return RUNNING


def session_runs(
    *, now: float | None = None, recent_seconds: int = RECENT_SECONDS, limit: int = AGENT_LIMIT
) -> list[dict]:
    """One row per turn the run ledger recorded inside the recent window, newest first.

    The window is measured from the last line, since a live turn keeps writing and a run
    that stopped writing is the one that has left the board. The order answers
    the same question — the turn whose newest line is closest to now stands at the top, so
    a long run that is still working outranks one that finished a minute ago.
    """
    from core.run import ledger

    moment = time.time() if now is None else now
    rows: list[tuple[int, dict]] = []
    for run_id in ledger.active_run_ids():
        lines = ledger.read_run(run_id)
        if not lines:
            continue
        last_seen = seconds_since(lines[-1].get("ts"), moment)
        if last_seen is None or last_seen > recent_seconds:
            continue
        session = str(lines[0].get("session_id") or "")
        rows.append(
            (
                last_seen,
                row(
                    run_id=f"session:{session or run_id}",
                    kind="session",
                    agent=session or run_id,
                    task=str(lines[-1].get("finish_reason") or ""),
                    state=_ledger_state(lines),
                    running_for_seconds=seconds_since(lines[0].get("ts"), moment),
                    last_event=_last_touch(lines),
                    ledger=ledger.project(lines, run_id=run_id),
                ),
            )
        )
    rows.sort(key=lambda pair: pair[0])
    return [item for _last_seen, item in rows][:limit]
