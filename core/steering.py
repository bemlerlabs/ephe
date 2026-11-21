"""Mid-flight steering: a direction change that reaches a turn already running.

A turn is one long stretch of model calls and tool rounds. Until now the only
control over it was ``task.cancel()`` — a hard kill at whatever moment the user
pressed it, including the moment between a tool's side effect and the record of
it. This module carries the other control: a message the user drops into a running
turn, taken up at the next round boundary, plus the transcript line that names
where the direction changed and who changed it.

Three rules about where a steer may land fall out of the loop's shape:

- Between rounds only. At a round boundary every tool call of the finished round
  already has its result in the message list, so no steer can sit between a side
  effect and the record of it.
- The innermost consumer drains. A subagent runs inside a tool call of its
  parent's round; while it runs, the parent must not swallow a steer meant for the
  work the user is watching.
- A steer nobody takes up is reported as unlanded, or the user reads the answer
  as though the direction had been understood.

The channel is a contextvar bound per task, the ``LoopObserver`` pattern, so core
stays transport-agnostic and the CLI runs a turn without a server. It is also
registered under its session, because the HTTP endpoint that delivers a steer runs
in a different task and cannot see the turn's context.
"""

from __future__ import annotations

import collections
import contextvars
import itertools
import re
import threading
import time
from typing import Any, Callable

#: Whoever the caller says pressed the control. Recorded as a claim — the local
#: API is exactly as authenticated as the rest of it.
ACTOR_USER = "user"

#: A queue that never empties is a second turn queued behind the first. Past this
#: many pending steers the channel refuses (the endpoint answers 429), so the
#: composer learns the direction was not taken instead of assuming it was.
MAX_PENDING = 8

#: How often a turn re-opens for a steer that arrived while the model was already
#: writing its answer. Each re-open is another model round, so it is bounded on
#: its own instead of only by the tool budget.
MAX_REOPEN_PER_TURN = 3

MAX_STEER_CHARS = 4000
MAX_ACTOR_CHARS = 24

_ACTOR_CLEAN = re.compile(r"[^a-z0-9_.:-]+")

#: Opening token of the message a steered turn reads on its next step.
STEER_TOKEN = "[STEER]"


def _clean_actor(actor: str) -> str:
    cleaned = _ACTOR_CLEAN.sub("", (actor or "").strip().lower())[:MAX_ACTOR_CHARS]
    return cleaned or ACTOR_USER


def _clean_text(text: object) -> str:
    return str(text or "").strip()[:MAX_STEER_CHARS]


class Steer:
    """One direction change: what was asked, by whom, and where it landed."""

    __slots__ = ("text", "actor", "turn_id", "seq", "at", "agent_id", "stop")

    def __init__(
        self,
        text: str,
        *,
        actor: str = ACTOR_USER,
        turn_id: str = "",
        seq: int = 0,
        agent_id: str = "",
        stop: bool = False,
    ) -> None:
        self.text = text
        self.actor = actor
        self.turn_id = turn_id
        self.seq = seq
        self.at = time.monotonic()
        self.agent_id = agent_id
        self.stop = stop

    def as_message(self, boundary: int) -> dict[str, str]:
        """The user-role message a steered turn reads on its next step.

        A user role rather than a system one: the engine treats it as the human
        speaking into its own round, which is what happened.
        """
        lead = (
            f"{STEER_TOKEN} The user changed direction at this point in the run "
            f"(after tool round {boundary}). Follow the new direction from here; "
            "work already done stands."
        )
        return {"role": "user", "content": f"{lead}\n\n{self.text}"}

    def as_event(self, boundary: int, status: str = "landed") -> dict[str, Any]:
        """The transcript frame, carrying the two facts the user needs.

        ``msg`` is the step title in the persisted turn timeline (core.trajectory
        reads it first), so who changed the direction and at which round survives
        in the history. A steer the turn never took up says that instead of naming
        a round it never reached.
        """
        where = "the user" if self.actor == ACTOR_USER else f"the {self.actor}"
        if status == "unlanded":
            title = f"Direction change by {where} — the turn ended before it landed"
        else:
            lead = "Run stopped by" if self.stop else "Direction changed by"
            title = f"{lead} {where}"
            if boundary:
                title += f" (after tool round {boundary})"
        return {
            "type": "steer",
            "status": status,
            "actor": self.actor,
            "msg": title,
            "text": self.text,
            "turn_id": self.turn_id,
            "round": boundary,
            "agent_id": self.agent_id,
            "stop": self.stop,
        }


class SteeringChannel:
    """One running turn's inbox for direction changes.

    ``on_steer`` is the transcript sink. The SSE route points it at the frame
    emitter, which also records the frame as a trajectory step; the CLI leaves it
    unset and the steers still reach the model.
    """

    def __init__(
        self,
        *,
        turn_id: str = "",
        session_id: str = "",
        on_steer: Callable[[dict], None] | None = None,
    ) -> None:
        self.turn_id = turn_id
        self.session_id = session_id
        self.on_steer = on_steer
        self._pending: collections.deque[Steer] = collections.deque()
        self._seq = itertools.count(1)
        self._focus: list[str] = []
        self._lock = threading.Lock()
        self._closed = False

    def request(
        self,
        text: object,
        *,
        actor: str = ACTOR_USER,
        agent_id: str = "",
        stop: bool = False,
    ) -> Steer | None:
        """Queue one direction change. None when it is refused.

        Refusals are empty text, a closed turn and a full queue. The caller owes
        the user the difference, so none of them is silently accepted.
        """
        body = _clean_text(text)
        if not body and not stop:
            return None
        if not body:
            body = "Stop here."
        steer = Steer(
            body,
            actor=_clean_actor(actor),
            turn_id=self.turn_id,
            seq=next(self._seq),
            agent_id=str(agent_id or "").strip(),
            stop=bool(stop),
        )
        with self._lock:
            if self._closed or len(self._pending) >= MAX_PENDING:
                return None
            self._pending.append(steer)
        return steer

    def enter_focus(self, agent_id: str) -> None:
        """Claim the channel for the consumer that is running right now."""
        with self._lock:
            self._focus.append(str(agent_id or ""))

    def leave_focus(self, agent_id: str) -> None:
        with self._lock:
            if self._focus and self._focus[-1] == str(agent_id or ""):
                self._focus.pop()
            elif agent_id in self._focus:
                self._focus.remove(str(agent_id or ""))

    def _visible(self, consumer: str) -> list[Steer]:
        """The pending steers this consumer may take, oldest first.

        A steer without an ``agent_id`` is addressed to the turn, so whichever
        consumer is innermost when it drains takes it: the subagent holding the
        focus while it runs, the turn's own loop when none is. One carrying an
        ``agent_id`` waits for that consumer alone.
        """
        with self._lock:
            if self._focus:
                if consumer != self._focus[-1]:
                    return []
            elif consumer:
                return [steer for steer in self._pending if steer.agent_id == consumer]
            return [
                steer
                for steer in self._pending
                if not steer.agent_id or steer.agent_id == consumer
            ]

    def drain(self, *, consumer: str = "") -> list[Steer]:
        """Take everything this consumer may take; empty when it may take none."""
        taken = self._visible(consumer)
        if not taken:
            return []
        with self._lock:
            for steer in taken:
                try:
                    self._pending.remove(steer)
                except ValueError:
                    pass
        return taken

    def pending(self, *, consumer: str = "") -> int:
        return len(self._visible(consumer))

    @property
    def queued(self) -> int:
        """Everything waiting, whoever it is waiting for."""
        with self._lock:
            return len(self._pending)

    def announce(self, steer: Steer, boundary: int, status: str = "landed") -> dict:
        """Write the steer's transcript line. Returns the frame in every case."""
        frame = steer.as_event(boundary, status)
        if self.on_steer is not None:
            try:
                self.on_steer(frame)
            except Exception:  # noqa: BLE001 — a stream hiccup must not kill the turn
                pass
        return frame

    def announce_unlanded(self, boundary: int) -> list[dict]:
        """Report whatever the turn ended without taking up.

        The turn is over and the model is about to answer: a steer left in the
        queue changes nothing, and saying so is the only honest thing left.
        """
        with self._lock:
            leftovers = list(self._pending)
            self._pending.clear()
        return [self.announce(steer, boundary, status="unlanded") for steer in leftovers]

    def close(self) -> None:
        """Refuse further steers; the turn this channel belongs to is over."""
        with self._lock:
            self._closed = True

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed


def take_up(
    messages: list,
    *,
    boundary: int,
    consumer: str = "",
    channel: "SteeringChannel | None" = None,
) -> list[Steer]:
    """Take up the pending steers at a round boundary and brief the model.

    ``messages`` must already carry the results of the round that just finished;
    that ordering is the whole safety property of steering, so this belongs at
    the boundary and nowhere else. Each taken steer also writes its transcript
    line here — where it landed is only known once it has. ``channel`` is for a
    consumer that holds its own: a subagent gets the parent turn's handed down.
    """
    channel = channel or current_channel()
    if channel is None:
        return []
    taken = channel.drain(consumer=consumer)
    for steer in taken:
        if not steer.stop:
            messages.append(steer.as_message(boundary))
        channel.announce(steer, boundary)
    return taken


# The endpoint that delivers a steer runs in its own request task. Nothing of the
# turn's context reaches it, so a live channel is also addressable by session.

_TURNS: "collections.OrderedDict[str, SteeringChannel]" = collections.OrderedDict()
_REGISTRY_LOCK = threading.Lock()
MAX_LIVE_TURNS = 64


def register_turn(channel: SteeringChannel) -> None:
    """Make a live channel addressable. The turn id is the handle."""
    key = channel.turn_id or f"anon-{id(channel)}"
    with _REGISTRY_LOCK:
        _TURNS[key] = channel
        while len(_TURNS) > MAX_LIVE_TURNS:
            _TURNS.popitem(last=False)


def unregister_turn(channel: SteeringChannel) -> None:
    key = channel.turn_id or f"anon-{id(channel)}"
    with _REGISTRY_LOCK:
        if _TURNS.get(key) is channel:
            del _TURNS[key]


def resolve_turn(*, session_id: str = "", turn_id: str = "") -> SteeringChannel | None:
    """The live channel for a turn id, or the newest live turn of a session.

    A named turn id is exact. A session usually has one turn running; when it has
    two, the one that started last is the one the user is watching, and it is the
    only one the composer can mean.
    """
    turn_id = str(turn_id or "").strip()
    session_id = str(session_id or "").strip()
    with _REGISTRY_LOCK:
        if turn_id:
            channel = _TURNS.get(turn_id)
            if channel is not None and not channel.closed:
                return channel
            return None
        if not session_id:
            return None
        for channel in reversed(list(_TURNS.values())):
            if channel.session_id == session_id and not channel.closed:
                return channel
    return None


def reset_registry_for_test() -> None:
    with _REGISTRY_LOCK:
        _TURNS.clear()


_ACTIVE: contextvars.ContextVar[SteeringChannel | None] = contextvars.ContextVar(
    "ephe.steering.channel", default=None
)


def bind_channel(channel: SteeringChannel):
    """Install ``channel`` for the current task and return the reset token."""
    return _ACTIVE.set(channel)


def reset_channel(token) -> None:
    _ACTIVE.reset(token)


def current_channel() -> SteeringChannel | None:
    """The channel bound in this task, or None outside a running turn."""
    return _ACTIVE.get()


__all__ = [
    "ACTOR_USER",
    "MAX_PENDING",
    "MAX_REOPEN_PER_TURN",
    "MAX_STEER_CHARS",
    "STEER_TOKEN",
    "Steer",
    "SteeringChannel",
    "bind_channel",
    "current_channel",
    "register_turn",
    "reset_channel",
    "reset_registry_for_test",
    "resolve_turn",
    "take_up",
    "unregister_turn",
]
