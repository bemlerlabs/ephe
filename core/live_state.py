"""One notify channel from the state writers to the live streams (L1).

The multiplex route used to learn about a change on its next tick. A writer that
has just changed state a frame carries calls `notify()`; every open stream wakes
at once and sends the frame it would otherwise have sent up to a tick later. The
listener list is process-local and as small as the number of open streams.
"""
from __future__ import annotations

import logging
from typing import Callable

Listener = Callable[[], None]

logger = logging.getLogger(__name__)
_listeners: list[Listener] = []


def subscribe(listener: Listener) -> Callable[[], None]:
    """Register a listener; the returned call removes it again."""
    _listeners.append(listener)

    def unsubscribe() -> None:
        try:
            _listeners.remove(listener)
        except ValueError:
            pass

    return unsubscribe


def notify() -> None:
    """Tell every listener that the state just changed."""
    for listener in list(_listeners):
        try:
            listener()
        except Exception:  # a broken reader must not break the writer
            logger.exception("live-state listener failed")


def listener_count() -> int:
    return len(_listeners)
