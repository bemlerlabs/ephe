"""Ephe — the turn-end hook: one confined worker run per active bundle, after the turn.

core/plugin_turn_hooks.py

The dispatcher half of `components.hooks.turn_end`. `core/chat.py` calls
`note_turn_end` in the `finally` that already closes the loop's observer, and this module
answers with a bounded queue, one daemon thread and the same confined runner a contributed
tool uses (`core/sandbox/runner.resolve_entry_file` → `core/sandbox/worker_spec.build_spec`
→ `core/sandbox/supervisor.run_worker`). The plugin's code runs in the child, never here
(ruling A1), the reply is discarded, and the turn never waits on any of it.

Why not `run_plugin_tool`: that function is the tool rail's, and it writes `tool_start` /
`tool_exec` rows, applies the restart budget and passes the bridge. A hook has no served
tool name, no model-facing result and no bridge, so it calls the three steps directly and
audits its own row. Reusing the tool rail would have put a hook's run in a call log the
user reads as "the model asked for this".

What crosses into the child: the fixed payload in `build_payload`. It carries the turn id,
the loop's stop reason, the tool names the turn called and the turn's duration. It never
carries the answer, the history, a tool argument or anything from the context report —
`tests/test_plugin_turn_hooks.py` pins the exact key set. The reply is read for its status
only and thrown away, so nothing the hook writes can reach the model, the answer or the
session.

Every boundary is the tool rail's and none is loosened: the network is denied at the OS
boundary for every worker, `child_env` scrubs host secrets, reads are confined to the
bundle directory and the roots its manifest declared, writes stay under the bundle's state
root, and the declared timeout (1..3 s) bounds the run. No bridge dispatch is passed, so a
hook that asks for the launcher's third parameter fails its own run and is audited instead
of reaching a product handle.

A full queue drops the run and audits the drop; a bundle switched off or paused between the
turn and the run is re-asked in the worker thread and skipped. The audit row's status is
the worker's own status when a run happened, and the host's word when it did not
(`refused`, `state_full`, `inactive`, `cancelled`, `dropped`). `begin_call`/`end_call`
register the in-flight run the way a tool call is registered, so the activity surface sees
it; the guard is taken in the worker thread on purpose, because a guard bound to the turn's
own asyncio task would let switching the bundle off cancel the user's turn.

A measured turn never spawns a hook: `core/plugin_golden.run_measured` enters `suppressed()`
around its turn, because a pass³ number that carried a bundle's hook would not be comparable
with one that did not.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import os
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from core.plugin_hooks_contract import TurnHook

#: Runs that may wait behind the turn that queued them. A turn never blocks on a hook; a
#: full queue is the bound, and the drop is a row in the audit trail.
QUEUE_DEPTH = 8
#: Ceilings on the payload's lists and strings. The kernel fixes the payload; a hook may
#: not make it grow with a caller-supplied id or a long tool name.
MAX_PAYLOAD_TOOL_NAMES = 16
MAX_PAYLOAD_NAME_CHARS = 64
MAX_PAYLOAD_ID_CHARS = 80

_SUPPRESSED: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "ephe.plugin.turn_hooks.suppressed", default=False
)


@contextlib.contextmanager
def suppressed():
    """Run the block with turn hooks off; a measured or headless turn spawns none."""
    token = _SUPPRESSED.set(True)
    try:
        yield
    finally:
        _SUPPRESSED.reset(token)


@dataclass(frozen=True)
class _Job:
    hook: TurnHook
    payload: dict[str, Any]


_LOCK = threading.Lock()
_QUEUE: queue.Queue | None = None
_THREAD: threading.Thread | None = None
_STOP = object()


def build_payload(
    *,
    plugin_id: str,
    turn_id: str,
    stop_reason: str,
    tool_names: Iterable[str],
    duration_ms: float,
) -> dict[str, Any]:
    """The whole payload: identifiers, the loop's stop reason, tool names and a duration.

    Bounded at the edges so a caller-supplied id or a long name cannot grow the request,
    and stable in shape so a hook can read every field without asking whether it exists.
    """
    names: list[str] = []
    for raw in tool_names:
        name = str(raw)[:MAX_PAYLOAD_NAME_CHARS]
        if name and name not in names:
            names.append(name)
        if len(names) >= MAX_PAYLOAD_TOOL_NAMES:
            break
    return {
        "event": "turn_end",
        "plugin": str(plugin_id)[:MAX_PAYLOAD_ID_CHARS],
        "turn_id": str(turn_id)[:MAX_PAYLOAD_ID_CHARS],
        "stop_reason": str(stop_reason)[:MAX_PAYLOAD_ID_CHARS],
        "tool_names": names,
        "duration_ms": max(0, int(round(duration_ms))),
    }


def note_turn_end(
    *,
    turn_id: str = "",
    stop_reason: str = "",
    tool_names: Iterable[str] = (),
    duration_ms: float = 0.0,
) -> None:
    """Queue one run per active hook, in plugin-id order. Returns before any run starts.

    Never raises: a hook that cannot be queued is a fact for the audit trail, not a turn
    that fails. Called from the turn's `finally`, before `reset_observer`, so the stop
    reason and the observer's own duration are still readable.
    """
    if _SUPPRESSED.get():
        return
    try:
        from core import plugin_runtime

        hooks = plugin_runtime.turn_hooks()
    except Exception:  # noqa: BLE001 — an unreadable portfolio spawns nothing
        return
    for hook in hooks:
        try:
            if not plugin_runtime.is_plugin_active(hook.plugin_id):
                continue
        except Exception:  # noqa: BLE001 — an unreadable switch spawns nothing
            continue
        payload = build_payload(
            plugin_id=hook.plugin_id,
            turn_id=turn_id,
            stop_reason=stop_reason,
            tool_names=tool_names,
            duration_ms=duration_ms,
        )
        _enqueue(_Job(hook, payload))


def flush(timeout: float = 10.0) -> bool:
    """Test seam: wait until the queued runs are done.

    Returns whether the queue drained within `timeout`. A run is bounded by the hook's
    declared seconds, so the default is generous; a caller that times out learns the queue
    is still busy rather than waiting forever.
    """
    jobs = _QUEUE
    if jobs is None:
        return True
    deadline = time.monotonic() + max(0.0, timeout)
    with jobs.all_tasks_done:
        while jobs.unfinished_tasks:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            jobs.all_tasks_done.wait(remaining)
    return True


def reset() -> None:
    """Test seam: drain the queue, stop the worker thread and forget both.

    The wait is bounded: a test that leaves a run blocked must not hang the suite. A run
    that outlives the bound is a daemon thread the interpreter reaps at exit, and the next
    `note_turn_end` starts a fresh queue.
    """
    global _QUEUE, _THREAD
    with _LOCK:
        jobs, thread = _QUEUE, _THREAD
        _QUEUE = None
        _THREAD = None
    if jobs is None:
        return
    deadline = time.monotonic() + 5.0
    with jobs.all_tasks_done:
        while jobs.unfinished_tasks and time.monotonic() < deadline:
            jobs.all_tasks_done.wait(0.05)
    try:
        jobs.put_nowait(_STOP)
    except queue.Full:
        return
    if thread is not None:
        thread.join(timeout=1.0)


def _worker_queue() -> queue.Queue:
    global _QUEUE, _THREAD
    with _LOCK:
        jobs = _QUEUE
        if jobs is None:
            jobs = queue.Queue(maxsize=QUEUE_DEPTH)
            thread = threading.Thread(
                target=_drain, args=(jobs,), name="ephe-turn-hooks", daemon=True
            )
            thread.start()
            _QUEUE, _THREAD = jobs, thread
        return jobs


def _drain(jobs: queue.Queue) -> None:
    while True:
        job = jobs.get()
        try:
            if job is _STOP:
                return
            _run_one(job)
        except Exception:  # noqa: BLE001 — the worker thread outlives one bad run
            pass
        finally:
            jobs.task_done()


def _enqueue(job: _Job) -> bool:
    try:
        _worker_queue().put_nowait(job)
        return True
    except queue.Full:
        _audit(job.hook, "dropped", 0)
        return False


def _is_active(plugin_id: str) -> bool:
    try:
        from core import plugin_runtime

        return bool(plugin_runtime.is_plugin_active(plugin_id))
    except Exception:  # noqa: BLE001 — an unreadable switch is not a yes
        return False


def _run_one(job: _Job) -> None:
    """One queued run: re-check the switch, register the call, execute, audit once."""
    from core import plugin_activity

    hook = job.hook
    if not _is_active(hook.plugin_id):
        _audit(hook, "inactive", 0)
        return
    started = time.monotonic()
    status = "refused"
    guard = None
    try:
        guard = plugin_activity.begin_call(hook.plugin_id)
        if guard is not None and guard.cancelled:
            status = "cancelled"
            return
        status = _execute(hook, job.payload)
    finally:
        plugin_activity.end_call(guard)
        _audit(hook, status, round(1000 * (time.monotonic() - started)))


def _execute(hook: TurnHook, payload: dict[str, Any]) -> str:
    """Resolve the entry, build the confined spec, run one worker, return its status."""
    from core import mcp_sandbox, plugin_state
    from core.plugin_tools_contract import module_entry
    from core.sandbox.runner import LAUNCHER, resolve_entry_file, worker_data_roots
    from core.sandbox.supervisor import run_worker
    from core.sandbox.worker_spec import build_spec

    plugin_dir = str(hook.plugin_dir or "")
    if not plugin_dir:
        return "refused"
    # The manifest writes `hooks/turn_end.py:main`; the confined worker names a dotted
    # module, the same conversion the contributed-tool rail applies (`module_entry`).
    dotted = module_entry(hook.entry)
    entry_file, _ = resolve_entry_file(plugin_dir, dotted)
    if entry_file is None:
        return "refused"
    root = Path(os.path.realpath(plugin_dir))
    try:
        relative = entry_file.relative_to(root).as_posix()
    except ValueError:
        return "refused"
    spec, _ = build_spec(
        plugin_id=hook.plugin_id,
        plugin_dir=plugin_dir,
        entry=relative,
        launcher=LAUNCHER,
        timeout_seconds=float(hook.timeout_seconds),
        host_roots=worker_data_roots(hook.plugin_id),
    )
    if spec is None:
        return "refused"
    home = mcp_sandbox.home_for(f"plugin_{hook.plugin_id}")
    cap = plugin_state.cap_bytes(hook.plugin_id)
    used, _files = plugin_state.usage(home)
    if plugin_state.over(cap, used):
        return "state_full"
    request = json.dumps(
        {
            "tool": hook.event,
            "arguments": payload,
            "state_dir": str(home),
            "entry_file": str(entry_file),
            "callable": dotted.rpartition(":")[2],
        }
    )
    outcome = run_worker(
        spec,
        protocol_check=_one_json_object,
        stdin_payload=request + "\n",
    )
    return outcome.status


def _one_json_object(text: str) -> bool:
    """The framing check the tool rail runs on stdout; the reply itself is discarded."""
    try:
        return isinstance(json.loads(text), dict)
    except (ValueError, TypeError):
        return False


def _audit(hook: TurnHook, status: str, duration_ms: int) -> None:
    """One row per dispatch. The payload never enters the trail."""
    try:
        from core.audit_log import audit_event

        audit_event(
            "plugin_hook",
            tool=hook.plugin_id,
            status=status,
            duration_ms=duration_ms,
            detail=hook.event,
        )
    except Exception:  # noqa: BLE001 — the audit path never breaks a run
        pass
