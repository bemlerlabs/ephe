"""core/fleet.py — the fleet: every run this process can see, and who waits on a human.

Nothing here stores anything. The four questions a person with ten concurrent runs asks —
*which runs exist, what is each doing, what did it touch last, who needs me* — are read off
the registers that already answer them, and answered in one list:

* **workspace runs** — one agent run's checkout, from `core.workspace_lifecycle`. The state
  comes from the row's tree state, from whether the owning process is still there
  (`register.json` records the pid; the reaper reads it the same way), and from the newest
  change set, which is what the run last touched.
* **agent runs** — one helper run, from `core.subagent_history`: status, last tool call.
* **waits** — one unanswered tool approval, from the registry the app-wide approval gate
  fills (`server/routes/chat.py`, `_active_sandbox_events`). A wait is a run that stopped and
  will not move until a person answers, so it is `waiting_on_human` and nothing else: no
  status in any registry can say it, because that run is alive and idle. The waits arrive as
  plain rows rather than imports, so this module never reaches into `server`.

A state is one of four words. `blocked` is not "broken": it is a run whose owning process is
gone, or one that ended in an error or a step limit — work that will not continue on its own.
`needs_you` is exactly `waiting_on_human` or `blocked`.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

#: The closed vocabulary. `app/src/lib/api/workspaces.ts` and the surface over it name the
#: same four, so a word that reaches the screen still means what it means here.
RUNNING = "running"
WAITING_ON_HUMAN = "waiting_on_human"
BLOCKED = "blocked"
DONE = "done"
RUN_STATES = (RUNNING, WAITING_ON_HUMAN, BLOCKED, DONE)

#: States that are a decision a person owes, and the window a finished run stays on the
#: board for (long enough to see that it landed, short enough that this is a fleet, not a
#: history). AGENT_LIMIT is the newest-first page size of the only paginated register.
NEEDS_YOU_STATES = (WAITING_ON_HUMAN, BLOCKED)
RECENT_SECONDS = 900
AGENT_LIMIT = 50

#: Where a state sorts: the one that needs an answer first, then the stuck, then the busy.
_SORT_ORDER = {WAITING_ON_HUMAN: 0, BLOCKED: 1, RUNNING: 2, DONE: 3}


def needs_you(state: str) -> bool:
    """Whether this state is a thing a person has to do."""
    return state in NEEDS_YOU_STATES


def run_state(*, status: str = "", tree_state: str = "", owner_alive: bool | None = None) -> str:
    """One run's state, from the marks the registries carry.

    A status, when the record has one, decides. A workspace row has none, so its tree state
    and its owner's liveness decide instead; `published` is the one tree state that means the
    work landed.

    A wait is deliberately *not* an input here. It is not a mark a run carries — it is a
    separate row (`wait_runs`), because a run that is alive and idle on a person's answer has
    no status that says so, and no other record can be given that status without lying about
    it. The live board showed why the difference matters: matching a wait to every helper
    started from the waiting session painted three finished helpers as "waiting for your
    answer", and a finished run cannot wait.
    """
    text = str(status or "").strip().lower()
    if text:
        if text in ("running", "spawned"):
            return RUNNING
        if text == "done":
            return DONE
        return BLOCKED
    if str(tree_state or "").strip().lower() == "published":
        return DONE
    if owner_alive is False:
        return BLOCKED
    return RUNNING


def seconds_since(stamp: Any, now: float | None = None) -> int | None:
    """How long ago an ISO stamp was, in whole seconds; None when it cannot be read.

    The register writes microseconds with a `+00:00` offset, `core.subagent_history` writes
    epoch seconds. Both reach here. A stamp this cannot read answers None, never a zero.
    """
    if isinstance(stamp, (int, float)) and not isinstance(stamp, bool):
        base = float(stamp)
    elif isinstance(stamp, str) and stamp.strip():
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


def owner_alive(pid: Any) -> bool | None:
    """Whether the process that claimed a tree still exists; None when it cannot be told.

    Asked with signal 0, as `core.workspace_lifecycle` asks it before reaping. An absent or
    unusable pid answers None — unknown is not gone, and must not be painted as stuck.
    """
    try:
        number = int(pid)
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    try:
        os.kill(number, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return None
    return True


def register_owners(register_file_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """The pid each live tree's row was written with, keyed by tree id.

    The dataclass the register hands out (`Workspace`) carries the six fields a client needs;
    the pid is the seventh, written before git runs so a crash between the two leaves
    something for the reaper. Read through the path that module publishes,
    `core.workspace_lifecycle.register_file()`.
    """
    from core import workspace_lifecycle as life

    target = register_file_path if register_file_path is not None else life.register_file()
    try:
        raw = json.loads(open(target, encoding="utf-8").read())
    except (OSError, ValueError):
        return {}
    rows = raw.get("workspaces") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return {}
    out: dict[str, Any] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        tree_id = str(row.get("id") or "")
        if tree_id:
            out[tree_id] = row.get("pid")
    return out


def _ledger_of(run_id: str) -> dict | None:
    """The run ledger as a fleet view; None for a run whose ledger has no lines."""
    try:
        from core.run.ledger import snapshot_if_present

        return snapshot_if_present(run_id)
    except Exception:
        return None


def _row(
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
) -> dict:
    """One fleet row, with every field present so the client never guesses a missing one."""
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
        "ledger": _ledger_of(run_id),
    }


def _awaiting(tool: str, seconds: Any) -> dict:
    """The last event of a run that stopped on an unanswered approval."""
    return {
        "kind": "awaiting",
        "text": str(tool or ""),
        "op": "",
        "age_seconds": int(seconds) if isinstance(seconds, int) else None,
    }


def _newest_change_set(path: str) -> dict:
    """What a workspace last touched: the first file of its newest change set.

    The store keeps change sets per workspace root (`core.change_set_read.list_for`), so its
    last touch is a read of what it already reported — not a `git status` the fleet would
    have to run ten times a poll.
    """
    from core import change_set_read as store

    try:
        sets = store.list_for(path)
    except Exception:  # noqa: BLE001 — a store that cannot answer must not sink the board
        return {"kind": "none", "text": "", "op": "", "age_seconds": None}
    if not sets:
        return {"kind": "none", "text": "", "op": "", "age_seconds": None}

    def _stamp(item: Any) -> float:
        moment = seconds_since(getattr(item, "created_at", None))
        return float(moment) if moment is not None else -1.0

    newest = max(sets, key=_stamp)
    files = list(getattr(newest, "files", []) or [])
    if not files:
        return {"kind": "none", "text": "", "op": "", "age_seconds": None}
    first = files[0]
    return {
        "kind": "file",
        "text": str(getattr(first, "path", "")),
        "op": str(getattr(first, "op", "")),
        "age_seconds": seconds_since(getattr(newest, "created_at", None)),
    }


def workspace_runs(
    *,
    now: float | None = None,
    owners: dict[str, Any] | None = None,
    alive: Callable[[Any], bool | None] = owner_alive,
) -> list[dict]:
    """One row per live checkout in the register, in register order."""
    from core import workspace_lifecycle as life

    pids = register_owners() if owners is None else owners
    rows: list[dict] = []
    for row in life.list_live():
        owner_pid = pids.get(row.id)
        aliveness = alive(owner_pid) if owner_pid is not None else None
        state = run_state(tree_state=row.state, owner_alive=aliveness)
        rows.append(
            _row(
                run_id=f"workspace:{row.id}",
                kind="workspace",
                agent=row.owner or row.id,
                task=row.branch,
                workspace_id=row.id,
                path=row.path,
                state=state,
                running_for_seconds=seconds_since(row.created_at, now),
                last_event=_newest_change_set(row.path),
            )
        )
    return rows


def agent_runs(
    *, now: float | None = None, recent_seconds: int = RECENT_SECONDS, limit: int = AGENT_LIMIT
) -> list[dict]:
    """One row per helper run that is live now or finished inside the recent window."""
    from core import subagent_history

    moment = time.time() if now is None else now
    page = subagent_history.summaries(limit=limit).get("agents") or []
    rows: list[dict] = []
    for summary in page:
        agent_id = str(summary.get("agent_id") or "")
        if not agent_id:
            continue
        status = str(summary.get("status") or "")
        started = summary.get("started_ts")
        duration_ms = summary.get("duration_ms")
        finished: float | None = None
        if isinstance(started, (int, float)) and isinstance(duration_ms, (int, float)):
            finished = float(started) + float(duration_ms) / 1000.0
        if status != "running" and finished is not None and moment - finished > recent_seconds:
            continue
        state = run_state(status=status)
        record = subagent_history.get(agent_id) or {}
        calls = list(record.get("tool_calls") or [])
        last = calls[-1] if calls else None
        rows.append(
            _row(
                run_id=f"agent:{agent_id}",
                kind="agent",
                agent=agent_id,
                task=str(summary.get("description") or summary.get("task") or ""),
                state=state,
                running_for_seconds=seconds_since(started, moment),
                last_event={
                    "kind": "tool",
                    "text": str((last or {}).get("tool") or ""),
                    "op": "",
                    "age_seconds": seconds_since(started, moment),
                },
            )
        )
    return rows


def wait_runs(*, waits: Iterable[dict] = (), now: float | None = None) -> list[dict]:
    """One row per unanswered approval — the runs that are waiting on a person.

    A wait the helper registry could not be matched to (a chat turn, a CLI run) is still a
    run, and it is the one a person most needs to see: it is alive, it is idle, and it will
    not move until they answer.
    """
    rows: list[dict] = []
    for wait in waits:
        session = str(wait.get("session_id") or "")
        seconds = wait.get("waiting_seconds")
        rows.append(
            _row(
                run_id=f"session:{session or wait.get('token') or 'unknown'}",
                kind="session",
                agent=session or "unknown",
                state=WAITING_ON_HUMAN,
                running_for_seconds=int(seconds) if isinstance(seconds, int) else None,
                last_event=_awaiting(str(wait.get("tool") or ""), seconds),
            )
        )
    return rows


def build(
    *,
    waits: Iterable[dict] = (),
    now: float | None = None,
    owners: dict[str, Any] | None = None,
    alive: Callable[[Any], bool | None] = owner_alive,
) -> list[dict]:
    """The board: every run, the ones that need a person first, then longest-running first.

    The wait rows are added last and then sorted to the front, so a run that is waiting on a
    human never sits under four rows that are merely busy.
    """
    pending = list(waits)
    rows = workspace_runs(now=now, owners=owners, alive=alive)
    rows += agent_runs(now=now)
    rows += wait_runs(waits=pending, now=now)
    rows.sort(
        key=lambda row: (
            _SORT_ORDER.get(str(row.get("state")), 9),
            -int(row.get("running_for_seconds") or 0),
            str(row.get("run_id") or ""),
        )
    )
    return rows


def workspace_view(row: Any, *, pids: dict[str, Any] | None = None) -> dict:
    """One register row plus the run fields the list column shows beside it.

    Kept beside `workspace_runs` so the per-row state and the board's row for the same tree
    are computed by one function — two readers disagreeing about one tree is the failure this
    avoids.
    """
    owners = register_owners() if pids is None else pids
    payload = row.as_dict() if hasattr(row, "as_dict") else dict(row)
    tree_id = str(payload.get("id") or "")
    owner_pid = owners.get(tree_id)
    aliveness = owner_alive(owner_pid)
    state = run_state(tree_state=str(payload.get("state") or ""), owner_alive=aliveness)
    payload.update(
        {
            "run_state": state,
            "needs_you": needs_you(state),
            "owner_alive": aliveness,
            "running_for_seconds": seconds_since(payload.get("created_at")),
            "last_event": _newest_change_set(str(payload.get("path") or "")),
        }
    )
    return payload
