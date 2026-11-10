"""Bounded respawn for a worker that keeps dying — a ladder, then a visible refusal.

An infinite respawn loop turns one broken plugin into a machine-wide stall; the
budget is the wave-2 reading of fail-closed applied to restarts. The shape:
explicit backoff per consecutive failure, a hard restart bound, and one
`Refusal` once the budget is spent. `Refusal` carries a code and a sentence, and
the code is the identifier `core.dynamic_refusals` registers end to end — #10's
registry reads that one, so this layer neither raises the HTTP error nor invents a
code in parallel with the confinement-unavailable one.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from core.dynamic_refusals import PLUGIN_WORKER_RESTART_EXHAUSTED

#: Consecutive worker deaths tolerated before the tool is refused for the turn.
DEFAULT_MAX_RESTARTS = 3
#: Explicit, visible ladder — failure N waits backoff[N-1] seconds; nothing geometric
#: is hidden, and the list is the whole policy.
DEFAULT_BACKOFF_SECONDS = (0.5, 2.0, 8.0)


@dataclass(frozen=True)
class Refusal:
    """A refusal the surface can translate: code plus sentence, no bare exception."""

    code: str
    message: str


class RestartBudget:
    """Track one plugin's consecutive worker failures; hand out delays or refuse."""

    def __init__(
        self,
        *,
        max_restarts: int = DEFAULT_MAX_RESTARTS,
        backoff_seconds: tuple[float, ...] = DEFAULT_BACKOFF_SECONDS,
        clock=time.monotonic,
    ) -> None:
        self.max_restarts = int(max_restarts)
        self.backoff_seconds = tuple(float(s) for s in backoff_seconds)
        self._clock = clock
        self.failures = 0
        self.last_failure_at: float | None = None

    @property
    def spent(self) -> bool:
        return self.failures >= self.max_restarts

    def record_success(self) -> None:
        self.failures = 0
        self.last_failure_at = None

    def record_failure(self) -> float | Refusal:
        """One death accounted for. Returns the backoff before the next attempt,
        or the refusal that replaces every further attempt."""
        self.failures += 1
        self.last_failure_at = self._clock()
        if self.spent:
            return Refusal(
                code=PLUGIN_WORKER_RESTART_EXHAUSTED,
                message=(
                    f"plugin worker died {self.failures} times in a row (restart budget "
                    f"{self.max_restarts}) — the tool is refused for this turn instead of "
                    "respawning again; check the worker's exit status in the audit trail"
                ),
            )
        if self.failures - 1 < len(self.backoff_seconds):
            return self.backoff_seconds[self.failures - 1]
        return self.backoff_seconds[-1] if self.backoff_seconds else 0.0
