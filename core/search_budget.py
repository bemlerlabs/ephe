"""The interactive search budget of one turn.

The reported turn (2026-10-25) spent 5m19s in web_search rounds with no visible
progress and no answer. The budget bounds that: at most four searches or sixty
seconds, one call per distinct query, and past it the loop tells the model to
answer from what it has instead of searching again.
"""
from __future__ import annotations

import time
from collections.abc import Callable

SEARCH_CALL_CAP = 4
SEARCH_WINDOW_SECONDS = 60.0

DEDUPED = (
    "[search deduplicated: this query already ran in this turn. "
    "Use its results, or ask a different question.]"
)
EXHAUSTED = (
    "[search budget reached: at most 4 searches or 60 s per turn. "
    "Answer now from the results you have, name the sources, and say "
    "what remains unverified.]"
)


class SearchBudget:
    """Per-turn count, clock and query set for ``web_search``."""

    def __init__(
        self,
        cap: int = SEARCH_CALL_CAP,
        window: float = SEARCH_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.cap = int(cap)
        self.window = float(window)
        self._clock = clock
        self.calls = 0
        self.started: float | None = None
        self.queries: set[str] = set()

    def check(self, name: str, args: dict) -> str | None:
        """The refusal sentence, or None to let the call run."""
        if name != "web_search":
            return None
        query = str((args or {}).get("query") or "").strip()
        key = query.lower()
        if key and key in self.queries:
            return DEDUPED
        if self.started is None:
            self.started = self._clock()
        if self.calls >= self.cap or (self._clock() - self.started) > self.window:
            return EXHAUSTED
        self.calls += 1
        if key:
            self.queries.add(key)
        return None
