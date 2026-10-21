"""SSE subscriber bus for lifecycle state changes."""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any

_SUBSCRIBERS: dict[str, list[queue.Queue]] = {}
_EVENT_IDS: dict[str, int] = {}
_EVENT_LOCK = threading.Lock()


def _state_key(state_path: Path | None) -> str:
    return str(Path(state_path).resolve()) if state_path is not None else "<memory>"


def subscribe(state_path: Path | None) -> queue.Queue:
    """One SSE subscriber for a state file; the route drains the queue."""
    subscriber: queue.Queue = queue.Queue()
    with _EVENT_LOCK:
        _SUBSCRIBERS.setdefault(_state_key(state_path), []).append(subscriber)
    return subscriber


def unsubscribe(subscriber: queue.Queue) -> None:
    with _EVENT_LOCK:
        empty: list[str] = []
        for key, subscribers in _SUBSCRIBERS.items():
            if subscriber in subscribers:
                subscribers.remove(subscriber)
            if not subscribers:
                empty.append(key)
        for key in empty:
            del _SUBSCRIBERS[key]


def publish(state_path: Path | None, event: str, data: dict[str, Any]) -> None:
    key = _state_key(state_path)
    with _EVENT_LOCK:
        _EVENT_IDS[key] = _EVENT_IDS.get(key, 0) + 1
        message = {"id": _EVENT_IDS[key], "event": event, "data": data}
        subscribers = list(_SUBSCRIBERS.get(key, ()))
    for subscriber in subscribers:
        subscriber.put_nowait(message)
