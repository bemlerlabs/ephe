"""SSE subscriber bus for lifecycle state changes."""

from __future__ import annotations

import queue
import threading
from pathlib import Path
from typing import Any

_SUBSCRIBERS: dict[str, list[queue.Queue]] = {}
_FILTERED_SUBSCRIBERS: dict[str, list[tuple[queue.Queue, dict[str, Any]]]] = {}
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


def subscribe_filtered(
    state_path: Path | None,
    *,
    plugin_id: str | None = None,
    event_type: str | None = None,
) -> queue.Queue:
    """One filtered SSE subscriber; receives only events matching the criteria.

    `plugin_id` filters on the plugin that produced the event; `event_type` filters on
    the event name. Both are optional; a subscriber with neither filter behaves like
    `subscribe()`. The waterfall pattern: Plugin A subscribes to Plugin B's events by
    passing `plugin_id="plugin-b"`, and reacts to each registration without noise from
    other plugins.
    """
    subscriber: queue.Queue = queue.Queue()
    filters = {}
    if plugin_id is not None:
        filters["plugin_id"] = plugin_id
    if event_type is not None:
        filters["event_type"] = event_type
    with _EVENT_LOCK:
        _FILTERED_SUBSCRIBERS.setdefault(_state_key(state_path), []).append(
            (subscriber, filters)
        )
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

        empty_filtered: list[str] = []
        for key, filtered_list in _FILTERED_SUBSCRIBERS.items():
            _FILTERED_SUBSCRIBERS[key] = [
                (sub, filters) for sub, filters in filtered_list if sub is not subscriber
            ]
            if not _FILTERED_SUBSCRIBERS[key]:
                empty_filtered.append(key)
        for key in empty_filtered:
            del _FILTERED_SUBSCRIBERS[key]


def _matches_filters(event: str, data: dict[str, Any], filters: dict[str, Any]) -> bool:
    """True if the event passes all filters; an empty filter dict passes everything."""
    if "event_type" in filters and event != filters["event_type"]:
        return False
    if "plugin_id" in filters:
        # The plugin id lives in different places depending on the event:
        # - plugin.tool_registered: data["plugin"]
        # - plugin.mount: data["name"]
        plugin_id = filters["plugin_id"]
        if data.get("plugin") != plugin_id and data.get("name") != plugin_id:
            return False
    return True


def publish(state_path: Path | None, event: str, data: dict[str, Any]) -> None:
    key = _state_key(state_path)
    with _EVENT_LOCK:
        _EVENT_IDS[key] = _EVENT_IDS.get(key, 0) + 1
        message = {"id": _EVENT_IDS[key], "event": event, "data": data}
        subscribers = list(_SUBSCRIBERS.get(key, ()))
        filtered_subscribers = list(_FILTERED_SUBSCRIBERS.get(key, ()))
    for subscriber in subscribers:
        subscriber.put_nowait(message)
    for subscriber, filters in filtered_subscribers:
        if _matches_filters(event, data, filters):
            subscriber.put_nowait(message)
