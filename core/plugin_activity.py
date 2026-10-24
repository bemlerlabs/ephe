"""In-flight plugin calls and disposer teardown (OWN-02).

A plugin-owned tool call is registered while it runs. Disabling the plugin marks
the call cancelled, cancels its asyncio task and kills the child process groups
the call started; disposers unload in reverse order. A disposer failure is
reported so the lifecycle can keep the plugin on instead of claiming a teardown
that did not finish.
"""

from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from pathlib import Path
import uuid
from dataclasses import dataclass
from typing import Callable


class TeardownError(RuntimeError):
    """One or more disposers failed; the plugin is not fully torn down."""


@dataclass
class CallGuard:
    plugin: str
    id: str
    task: asyncio.Task | None
    loop: asyncio.AbstractEventLoop | None
    run_id: str = ""
    cancelled: bool = False
    from_other_process: bool = False


_LOCK = threading.Lock()
_CALLS: dict[str, dict[str, CallGuard]] = {}
_DISPOSERS: dict[str, list[Callable[[], None]]] = {}
_TEARDOWN_LOCKS: dict[str, threading.Lock] = {}
#: A cancel that arrives in another Ephe process cannot reach this process's
#: asyncio tasks, so it is written down and read by the next call that starts.
_CANCEL_TTL_SECONDS = 120.0
#: Stamps this process wrote itself; its own guards are cancelled through their
#: tasks, and treating its own marker as foreign would refuse unrelated calls.
_LOCAL_CANCELS: dict[str, float] = {}


def _marker_path() -> Path:
    base = os.environ.get("EPHE_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".ephe") / "plugin-cancel.json"


def _record_cancel(plugin: str) -> None:
    path = _marker_path()
    now = time.time()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        rows = {str(k): float(v) for k, v in raw.items()} if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        rows = {}
    rows = {name: stamp for name, stamp in rows.items() if now - stamp <= _CANCEL_TTL_SECONDS}
    rows[plugin] = now
    _LOCAL_CANCELS[plugin] = now
    tmp = path.with_suffix(".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(json.dumps(rows), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(path)
    except OSError:
        pass


def _cancel_pending(plugin: str) -> bool:
    try:
        raw = json.loads(_marker_path().read_text(encoding="utf-8"))
        stamp = float(raw.get(plugin, 0)) if isinstance(raw, dict) else 0.0
    except (OSError, ValueError, TypeError):
        return False
    if _LOCAL_CANCELS.get(plugin) == stamp:
        return False
    return bool(stamp) and time.time() - stamp <= _CANCEL_TTL_SECONDS


def _current_run() -> str:
    try:
        from core import cancel_scope

        return cancel_scope.current_run()
    except Exception:
        return ""


def begin_call(plugin: str) -> CallGuard | None:
    """Registers the current tool call under its plugin.

    Returns None for a kernel-owned call. Outside an event loop the guard still
    tracks the cancellation flag, but there is no task to cancel.
    """
    if not plugin:
        return None
    try:
        task: asyncio.Task | None = asyncio.current_task()
        loop: asyncio.AbstractEventLoop | None = asyncio.get_running_loop()
    except RuntimeError:
        task, loop = None, None
    guard = CallGuard(
        plugin=plugin,
        id=uuid.uuid4().hex,
        task=task,
        loop=loop,
        run_id=_current_run(),
    )
    if _cancel_pending(plugin):
        guard.cancelled = True
        guard.from_other_process = True
    with _LOCK:
        _CALLS.setdefault(plugin, {})[guard.id] = guard
    return guard


def end_call(guard: CallGuard | None) -> None:
    if guard is None:
        return
    with _LOCK:
        calls = _CALLS.get(guard.plugin)
        if calls is None:
            return
        calls.pop(guard.id, None)
        if not calls:
            _CALLS.pop(guard.plugin, None)


def cancel_calls(plugin: str) -> int:
    """Marks every in-flight call of the plugin cancelled and signals its task."""
    with _LOCK:
        guards = list(_CALLS.get(plugin, {}).values())
    run_ids = sorted({guard.run_id for guard in guards if guard.run_id})
    for guard in guards:
        guard.cancelled = True
        if guard.task is not None and guard.loop is not None:
            try:
                guard.loop.call_soon_threadsafe(guard.task.cancel)
            except RuntimeError:
                pass
    _record_cancel(plugin)
    for run_id in run_ids:
        try:
            from core import cancel_scope

            cancel_scope.kill_run(run_id)
        except Exception:
            pass
    return len(guards)


def register_disposer(plugin: str, disposer: Callable[[], None]) -> None:
    """The activation registers what it opened; teardown runs it in reverse."""
    with _LOCK:
        _DISPOSERS.setdefault(plugin, []).append(disposer)


def _teardown_lock(plugin: str) -> threading.Lock:
    with _LOCK:
        lock = _TEARDOWN_LOCKS.get(plugin)
        if lock is None:
            lock = threading.Lock()
            _TEARDOWN_LOCKS[plugin] = lock
        return lock


def teardown_plugin(plugin: str) -> None:
    """Runs the plugin's disposers in reverse; failed ones stay for a retry.

    A disposer is dropped only after it returned. The per-plugin lock keeps two
    teardowns from running the same disposer beside each other, and it is held
    while the disposers run — the process-wide lock is not.
    """
    cancel_calls(plugin)
    with _teardown_lock(plugin):
        with _LOCK:
            disposers = list(_DISPOSERS.get(plugin, ()))
        errors: list[str] = []
        succeeded: list[Callable[[], None]] = []
        for disposer in reversed(disposers):
            try:
                disposer()
            except Exception as exc:
                errors.append(str(exc) or exc.__class__.__name__)
            else:
                succeeded.append(disposer)
        if succeeded:
            with _LOCK:
                remaining = [
                    disposer
                    for disposer in _DISPOSERS.get(plugin, ())
                    if not any(disposer is done for done in succeeded)
                ]
                if remaining:
                    _DISPOSERS[plugin] = remaining
                else:
                    _DISPOSERS.pop(plugin, None)
        if errors:
            raise TeardownError("; ".join(errors))


def inflight_count(plugin: str) -> int:
    with _LOCK:
        return len(_CALLS.get(plugin, {}))


def clear() -> None:
    """Test seam: forget every guard, disposer and teardown lock."""
    with _LOCK:
        _CALLS.clear()
        _DISPOSERS.clear()
        _TEARDOWN_LOCKS.clear()
