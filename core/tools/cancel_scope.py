"""Per-run child processes, and the kill a cancel owes them.

A cancelled asyncio task unwinds the Python stack; it does not touch a child that is
already running. The shell tool executes in a worker thread, so the stop button left
the command alive — measured 2026-10-17 on a `sleep` in a cancelled turn. Every child
is started as its own process group (``_new_group_kwargs``); this module remembers
which group belongs to which run, and a cancelled run kills its groups.

The run id travels in a context variable, which ``asyncio.to_thread`` copies into the
worker, so the registration lands on the run that started the command rather than on
"whatever is current" at kill time.
"""
from __future__ import annotations

import os
import signal
import threading
from contextvars import ContextVar

CURRENT_RUN: ContextVar[str] = ContextVar("ephe_run_id", default="")

_lock = threading.Lock()
_groups: dict[str, set[int]] = {}


def enter_run(run_id: str) -> None:
    CURRENT_RUN.set(run_id or "")


def current_run() -> str:
    return CURRENT_RUN.get()


def register_group(pid: int) -> None:
    run_id = CURRENT_RUN.get()
    if not run_id or pid <= 0:
        return
    with _lock:
        _groups.setdefault(run_id, set()).add(pid)


def unregister_group(pid: int) -> None:
    run_id = CURRENT_RUN.get()
    if not run_id:
        return
    with _lock:
        groups = _groups.get(run_id)
        if groups is not None:
            groups.discard(pid)
            if not groups:
                _groups.pop(run_id, None)


def _kill(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def kill_run(run_id: str) -> int:
    """Kills every live group of ``run_id``; returns how many were signalled."""
    if not run_id:
        return 0
    with _lock:
        groups = _groups.pop(run_id, set())
    for pid in groups:
        _kill(pid)
    return len(groups)


def active_groups(run_id: str) -> set[int]:
    with _lock:
        return set(_groups.get(run_id, set()))
