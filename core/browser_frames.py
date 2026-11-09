"""The frame bus behind a watched browser run.

A watchable run needs two things that pull in opposite directions: the engine should keep
producing frames as long as anyone is watching, and the reader — a browser tab over loopback,
on the same machine that is also running the agent — must never be asked to drain faster than
it can draw. The measurements that set this design are in
`~/ephe-notes/PLAN_BROWSER_AND_AGENT_VIEW_2026-11-05.md`; in short, frames arrive
damage-driven (an animating page yields ~93 fps, a still one ~1 per 2 s), and the protocol
window for un-acknowledged frames is 3, so an ack loop that waits for a slow reader stalls
the page instead of the reader.

So this bus holds exactly one frame — the newest — and every subscriber sees the same
sequence at its own pace. A reader that falls behind misses intermediate frames and never
buffers, which is the right trade for a view whose purpose is "what is on screen now".
The last frame is kept for a late joiner, so opening a second tab does not show a blank
pane until the next change.
"""
from __future__ import annotations

import queue
import threading
import time
from collections import deque
from typing import Any, Callable

#: How many frames the bus remembers for a subscriber that joins mid-run. One is enough
#: for the newest frame; the rest is history, and history belongs to the audit row.
_RECENT = 8


class FrameBus:
    """Newest-wins fan-out with a watcher count, so casting can be off when nobody looks."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: dict[int, "queue.Queue[Any]"] = {}
        self._recent: deque[dict[str, Any]] = deque(maxlen=_RECENT)
        self._published = 0
        self._dropped = 0

    def subscribe(self) -> "FrameSubscription":
        return FrameSubscription(self)

    def publish(self, frame: dict[str, Any]) -> None:
        frame = {**frame, "at": frame.get("at") or time.time()}
        with self._lock:
            self._recent.append(frame)
            self._published += 1
            for entry in self._subs.values():
                # one-slot handoff: a slow reader loses the stale frame, never the newest
                while entry.qsize() >= 1:
                    try:
                        entry.get_nowait()
                        self._dropped += 1
                    except Exception:  # noqa: BLE001 — a drained queue is the common case
                        break
                entry.put(frame)

    def recent(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._recent)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "published": self._published,
                "dropped": self._dropped,
                "subscribers": len(self._subs),
            }

    def _attach(self, entry, *, newest_first: bool = False) -> int:
        """Register a reader, handing it the frame already on screen.

        A pane opened mid-run otherwise shows nothing until the page next changes, and a
        still page may not change for minutes — which reads as a broken view. Seeding is
        what makes "the last frame is kept for a late joiner" true rather than intended.
        """
        key = id(entry)
        with self._lock:
            if newest_first and self._recent:
                entry.put(self._recent[-1])
            self._subs[key] = entry
        return key

    def _detach(self, key: int) -> None:
        with self._lock:
            self._subs.pop(key, None)


class FrameSubscription:
    """One reader's handle. Closed explicitly, because a leaked subscriber keeps frames."""

    def __init__(self, bus: FrameBus) -> None:
        self._bus = bus
        self._queue: "queue.Queue[Any]" = queue.Queue()
        self._key = bus._attach(self._queue, newest_first=True)
        self._closed = False

    def get(self, timeout: float | None = None) -> dict[str, Any] | None:
        """Block this thread for a frame. Callers on the event loop go off-thread.

        `Queue.get` with a timeout parks the calling thread, so awaiting it directly on
        the loop starves the CDP callback that would have produced the frame: the cast
        then looks dead while the reader is what stopped it.
        """
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._bus._detach(self._key)

    def __enter__(self) -> "FrameSubscription":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


#: One bus per session id. The agent can run several browser sessions and a watch is per
#: session, so a global would show the wrong page in the second tab.
_BUSES: dict[str, FrameBus] = {}
_BUSES_LOCK = threading.Lock()


def bus_for(session: str = "default") -> FrameBus:
    with _BUSES_LOCK:
        bus = _BUSES.get(session)
        if bus is None:
            bus = _BUSES[session] = FrameBus()
        return bus


def forget(session: str) -> None:
    """Drop a session's bus when the session ends, so its frames cannot outlive it."""
    with _BUSES_LOCK:
        _BUSES.pop(session, None)


def sessions_with_frames() -> list[str]:
    with _BUSES_LOCK:
        return sorted(_BUSES)


WatcherHook = Callable[[str, bool], None]
