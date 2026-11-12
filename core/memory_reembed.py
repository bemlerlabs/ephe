"""
◑ Ephe – Re-embed the memory store in the background
core/memory_reembed.py

A finished model fetch hands the process a new embedder, but the chunks written
before it keep their old label, and the ranking leg selects on that label. Without
a pass over the existing rows a new model would cover every new note and none of
the old ones. This module runs that pass: in a thread of its own, one batch at a
time, with the counters `GET /api/models/embedding` reports.

The pass is idempotent and resumable by construction: `KeptaProvider.reembed_missing`
selects only the rows whose `embedding_model` differs from the active label and
commits each batch, so a finished store costs one count query and a run that was
killed halfway starts at the first missing chunk. One pass at a time; the flag
below is the process-local guard, and the worker thread gets its own SQLite
connection through the provider.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _initial() -> dict[str, Any]:
    return {
        "running": False,
        "done": False,
        "total": 0,
        "embedded": 0,
        "remaining": 0,
        "label": "",
        "error": "",
        "started_at": 0.0,
        "finished_at": 0.0,
    }


_lock = threading.Lock()
_state: dict[str, Any] = _initial()


def status() -> dict[str, Any]:
    """What the pass has done so far, safe to read from a route at any time."""
    with _lock:
        return dict(_state)


def reset_state() -> None:
    """Test hook: the module state outlives one test's temporary store."""
    with _lock:
        _state.clear()
        _state.update(_initial())


def _progress(done: int, total: int) -> None:
    with _lock:
        _state.update(embedded=int(done), total=int(total), remaining=max(0, int(total) - int(done)))


def _failure_text(exc: Exception) -> str:
    detail = str(exc).strip()
    return detail if detail else type(exc).__name__


def start(
    *,
    memory_factory: Callable[[], Any] | None = None,
    batch_size: int = 16,
    runner: Callable[[Any], dict[str, Any]] | None = None,
) -> bool:
    """Start one pass; False when one is already running.

    `memory_factory` lets the route hand in its cached facade factory, so the
    worker uses the store the server answers from rather than a second instance.
    `runner` is the test seam: it replaces the one call the worker makes.
    """
    with _lock:
        if _state["running"]:
            return False
        _state.clear()
        _state.update(_initial())
        _state["running"] = True
        _state["started_at"] = time.time()

    def work() -> None:
        try:
            if memory_factory is not None:
                memory = memory_factory()
            else:
                from core.memory import Memory

                memory = Memory()
            if runner is not None:
                result = runner(memory)
            else:
                result = memory.reembed_missing(batch_size=batch_size, on_progress=_progress)
        except Exception as exc:  # noqa: BLE001 — the reason belongs to the status, not to the thread
            reason = _failure_text(exc)
            with _lock:
                _state["error"] = reason
            logger.warning("memory: re-embedding stopped: %s", reason)
        else:
            total = int(result.get("total", 0) or 0)
            embedded = int(result.get("embedded", 0) or 0)
            label = str(result.get("label", "") or "")
            with _lock:
                _state.update(done=True, total=total, embedded=embedded, label=label)
                _state["remaining"] = max(0, total - embedded)
            logger.info(
                "memory: re-embedded %d of %d chunk(s) under %r", embedded, total, label
            )
        finally:
            with _lock:
                _state["running"] = False
                _state["finished_at"] = time.time()

    threading.Thread(target=work, name="memory-reembed", daemon=True).start()
    return True
