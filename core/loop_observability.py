"""Per-turn counters and structured events for the agent tool loop.

The loop holds the only honest view of how many tool rounds a turn spent and
whether its history had to be trimmed before a follow-up. This module carries
those numbers out of it: counters a caller reads after the turn and ``ephe.loop``
log lines an operator watches while it runs. The TUI context meter and the run
record read the same counters, so neither invents a second number for the same
turn.
"""
from __future__ import annotations

import contextvars
import time
from dataclasses import dataclass, field

from core.observability import structured_log

SCOPE = "loop"

#: Rounds left when a turn is nearly out. The observer warns once, at this
#: remaining count, so the limit is observable as it is approached — not only
#: once it has already been hit.
BUDGET_LOW_WATER = 3

#: Why the tool loop ended. The reason, not the round count, tells a spent budget
#: from a model that chose to stop: a turn that answers on its last allowed round
#: still has ``tool_rounds == budget_cap``, which a caller reading only the count
#: would report as exhausted.
STOP_ANSWER = "answer"   # the model produced a final answer, no tool calls
STOP_BUDGET = "budget"   # the tool-round cap bound the turn
STOP_REPAIR = "repair"   # the repair budget (MAX_REPAIRS_PER_STEP) bound the turn
STOP_STALL = "stall"     # the circling guard tripped
#: A steer asked for the turn to end. Distinct from the stall: nothing failed,
#: the run was called off, and the note names the round boundary it landed on.
STOP_STEERED = "steered"

#: The two ends a reader needs named: both bound a turn that was still trying, and
#: neither is the model's own stop. ``answer`` and ``stall`` are already reported by
#: the turn's ordinary lines and the circling note.
_BUDGET_STOP_REASONS = (STOP_BUDGET, STOP_REPAIR)


@dataclass
class LoopCounters:
    """Counters of one agent turn as the loop produced them."""

    budget_cap: int = 0
    tool_rounds: int = 0
    budget_exhausted: bool = False
    loop_stalled: bool = False
    stop_reason: str = ""
    compaction_events: int = 0
    messages_dropped: int = 0

    @property
    def rounds_remaining(self) -> int:
        return max(0, self.budget_cap - self.tool_rounds)

    def as_dict(self) -> dict:
        return {
            "budget_cap": self.budget_cap,
            "tool_rounds": self.tool_rounds,
            "rounds_remaining": self.rounds_remaining,
            "budget_exhausted": self.budget_exhausted,
            "loop_stalled": self.loop_stalled,
            "stop_reason": self.stop_reason,
            "compaction_events": self.compaction_events,
            "messages_dropped": self.messages_dropped,
        }


@dataclass
class LoopObserver:
    """One turn's counters plus the events every increment came from.

    ``events`` keeps a counter traceable to the line that moved it, so a number
    that looks wrong can be replayed instead of guessed at.
    """

    budget_cap: int = 0
    turn_id: str = ""
    counters: LoopCounters = field(init=False)
    events: list[dict] = field(default_factory=list)
    _started: float = field(default_factory=time.monotonic, repr=False)
    _low_warned: bool = field(default=False, init=False, repr=False)

    def __post_init__(self) -> None:
        self.set_budget_cap(self.budget_cap)

    def set_budget_cap(self, cap: int) -> None:
        """Set the cap before the first round; the counters carry the same value.

        The cap is announced once, when it changes — that event is what makes the
        limit a first-class fact of the turn, visible from its first moment rather
        than only inferred at its end. Re-seeding the same value stays silent.
        """
        cap = int(cap)
        changed = cap != self.budget_cap
        self.budget_cap = cap
        self.counters = LoopCounters(budget_cap=cap)
        if changed:
            self._emit("info", "budget_set")

    def _emit(self, level: str, event: str, **fields) -> dict:
        record = {
            "event": event,
            "turn_id": self.turn_id,
            **self.counters.as_dict(),
            **fields,
        }
        self.events.append(record)
        structured_log(
            level,
            event,
            scope=SCOPE,
            **{key: value for key, value in record.items() if key != "event"},
        )
        return record

    def note_tool_round(self, index: int) -> dict:
        """Count an executed tool round and announce its place in the budget."""
        self.counters.tool_rounds = max(self.counters.tool_rounds, int(index))
        return self._emit("info", "tool_round", round=int(index))

    def note_compaction(self, source: str, dropped: int) -> dict | None:
        """Record a history trim; a trim of zero drops nothing and counts nothing."""
        dropped = int(dropped)
        if dropped <= 0:
            return None
        self.counters.compaction_events += 1
        self.counters.messages_dropped += dropped
        return self._emit("info", "compaction", source=str(source), dropped=dropped)

    def note_budget_exhausted(self) -> dict:
        """Mark the turn as ended at its cap, without a final answer."""
        self.counters.budget_exhausted = True
        return self._emit("warning", "budget_exhausted")

    def note_stall(self, reason: str, detail: str = "") -> dict:
        """Mark the turn as stopped by the circling guard, with its reason.

        The turn is not out of budget, it is out of progress: the loop kept
        failing one target, or failed a run of results with no success in
        between. ``reason`` names which signal fired and ``detail`` the target
        or run that proved it, so the stop is replayable rather than guessed at.
        """
        self.counters.loop_stalled = True
        return self._emit(
            "warning", "loop_stalled", reason=str(reason), detail=str(detail)
        )

    def note_stop(self, reason: str) -> dict | None:
        """Name why the loop ended, and make a binding budget its own line.

        The ordinary answer end is already reported by the turn's ``tool_round`` and
        ``loop_turn`` lines, so only a budget that bound the turn raises ``loop_stop``.
        That is the line that tells "out of budget" from "chose to stop" without a
        reader having to reconstruct it from the round count.
        """
        reason = str(reason)
        self.counters.stop_reason = reason
        if reason in _BUDGET_STOP_REASONS:
            return self._emit("warning", "loop_stop", reason=reason)
        return None

    def note_budget_low(self, remaining: int) -> dict | None:
        """Warn once as the budget nears its end.

        A spent budget is not "low" — that is the exhausted event's job — so a
        non-positive ``remaining`` is ignored. The first call wins; later rounds
        at or below the watermark do not repeat the warning.
        """
        remaining = int(remaining)
        if self._low_warned or remaining <= 0:
            return None
        self._low_warned = True
        return self._emit("warning", "budget_low", rounds_remaining=remaining)

    def note_turn_end(self) -> dict:
        """Close the turn with a summary event after the loop has returned."""
        wall_ms = round(1000 * (time.monotonic() - self._started), 1)
        return self._emit("info", "loop_turn", wall_ms=wall_ms)


_ACTIVE: contextvars.ContextVar[LoopObserver | None] = contextvars.ContextVar(
    "ephe.loop.observer", default=None
)


def bind_observer(observer: LoopObserver):
    """Install ``observer`` for the current task and return the reset token."""
    return _ACTIVE.set(observer)


def reset_observer(token) -> None:
    """Restore the observer that was bound before ``bind_observer``."""
    _ACTIVE.reset(token)


def current_observer() -> LoopObserver | None:
    """The observer bound in this task, or None outside a chat turn."""
    return _ACTIVE.get()


def note_tool_round(index: int) -> None:
    """Count a tool round on the bound observer; a no-op without one."""
    observer = _ACTIVE.get()
    if observer is not None:
        observer.note_tool_round(index)


def note_compaction(source: str, dropped: int) -> None:
    """Record a history trim on the bound observer; a no-op without one."""
    observer = _ACTIVE.get()
    if observer is not None:
        observer.note_compaction(source, dropped)


def note_budget_exhausted() -> None:
    """Mark the bound turn as ended at its cap; a no-op without an observer."""
    observer = _ACTIVE.get()
    if observer is not None:
        observer.note_budget_exhausted()


def note_stall(reason: str, detail: str = "") -> None:
    """Record a circling stop on the bound turn; a no-op without an observer."""
    observer = _ACTIVE.get()
    if observer is not None:
        observer.note_stall(reason, detail)


def note_stop(reason: str) -> None:
    """Name the loop's end reason on the bound turn; a no-op without an observer."""
    observer = _ACTIVE.get()
    if observer is not None:
        observer.note_stop(reason)


def current_stop_reason() -> str:
    """The bound turn's loop end reason, or ``""`` before the loop named one.

    A caller branches on this instead of on ``tool_rounds >= budget_cap``: a turn
    that answered on its last allowed round reaches the same round count as one
    the cap cut off, and only this reason separates them.
    """
    observer = _ACTIVE.get()
    return observer.counters.stop_reason if observer is not None else ""


def note_budget_low(remaining: int) -> None:
    """Warn on the bound turn as the budget nears its end; a no-op without one."""
    observer = _ACTIVE.get()
    if observer is not None:
        observer.note_budget_low(remaining)


def note_turn_end() -> None:
    """Close the bound turn with a summary event; a no-op without an observer."""
    observer = _ACTIVE.get()
    if observer is not None:
        observer.note_turn_end()


__all__ = [
    "BUDGET_LOW_WATER",
    "SCOPE",
    "STOP_ANSWER",
    "STOP_BUDGET",
    "STOP_REPAIR",
    "STOP_STALL",
    "STOP_STEERED",
    "LoopCounters",
    "LoopObserver",
    "bind_observer",
    "current_observer",
    "current_stop_reason",
    "note_budget_exhausted",
    "note_budget_low",
    "note_compaction",
    "note_stall",
    "note_stop",
    "note_tool_round",
    "note_turn_end",
    "reset_observer",
]
