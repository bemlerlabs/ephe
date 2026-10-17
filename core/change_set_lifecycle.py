"""Ephe – core/change_set_lifecycle: the life a change set runs, from draft to published.

`core.change_set` stores one record and `core.review_gate` holds the verdicts on it, but
neither names the life between them. A built set is `draft`; a reviewer's approve left no
mark on the record at all, so a set that a second agent cleared still read as a draft; and a
set sent back with reasons could only be replaced by reading the tree again under a new id
(`core.change_set.build` mints one on every call), which threw away the id and the
provenance a reviewer had been looking at. This module holds the three things that were
missing: the states a set may move between and which pairs are legal, an ``amend`` that
re-reads the tree under the same id and provenance, and a ``view`` that folds the record and
the ledger into the stations a reviewer reads.

``approved`` sits between ``review`` and ``published`` in ``core.change_set.STATES`` because
it is a place a set stands, not a note on the ledger: a set leaves it the moment its bytes
change, which is what stops one amended after approval from publishing on the approval it no
longer earned. ``rejected`` is a branch off the loop rather than a station on it.

An illegal move raises instead of being clamped, and ``published`` is terminal: the value is
the refusal, because a set that shipped must not silently return to a draft.
"""
from __future__ import annotations

import dataclasses

from core import change_set as store
from core import review_gate as gate

#: The stations a reviewer reads, in the order a set passes them. A ``rejected`` set stays
#: off this line: the review station reaches that verdict and no state follows it.
STATIONS = ("draft", "review", "approved", "published")

#: Legal moves, keyed by the state a set stands in. ``published`` is empty on purpose: the
#: bytes are on the branch, so a set that shipped has no way back into the loop.
TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"review", "approved", "rejected"}),
    "review": frozenset({"draft", "approved", "rejected"}),
    "approved": frozenset({"draft", "review", "rejected", "published"}),
    "rejected": frozenset({"draft"}),
    "published": frozenset(),
}

#: The state each verdict leaves a set in. `approve` is the only way in to ``approved``.
VERDICT_STATE: dict[str, str] = {
    gate.APPROVE: "approved",
    gate.REQUEST_CHANGES: "review",
    gate.REJECT: "rejected",
}

#: The one move a surface makes by hand: reopening a set as a draft, so it can be reworked
#: without re-reading the tree. `review` is not here because only a verdict sends a set back,
#: and `approved`/`rejected`/`published` are earned by a verdict or a publish, never written.
BACK_MOVES = frozenset({"draft"})

#: The way off the end of the line: a landing undone. ``TRANSITIONS`` stays empty for
#: ``published`` so the forward loop treats a shipped set as final and an amend may not start
#: there; a reader asking for the set back asks for this pair by name.
REVERT_FROM = "published"
REVERT_TO = "draft"

#: The states an amend may start from — every state that can still move. Derived from the
#: table, so a state that becomes terminal leaves this set in the same edit.
AMENDABLE = frozenset(state for state, moves in TRANSITIONS.items() if moves)

#: The verdict-decided states, for reading whether a fresh verdict can move a set at all.
_DECIDED = frozenset(VERDICT_STATE.values())


class LifecycleError(ValueError):
    """A move the loop turns down: an unknown state, or one no set may make from here."""


def may_move(current: str, target: str) -> bool:
    """Whether a set standing in ``current`` may move to ``target``."""
    return target in TRANSITIONS.get(current, frozenset())


def _station_index(state: str) -> int:
    """Where a state sits on the reviewer's line. ``rejected`` sits at the review station."""
    if state in STATIONS:
        return STATIONS.index(state)
    return STATIONS.index("review")


def stations_of(state: str) -> list[dict]:
    """The four stations, each marked as passed and the one the set is standing in."""
    here = _station_index(state)
    return [
        {"name": name, "done": index <= here, "current": index == here}
        for index, name in enumerate(STATIONS)
    ]


def move(change_set_id: str, target: str, published_oid: str = ""):
    """Move one stored set to a legal next state.

    None when the id is unknown, the answer ``core.change_set.set_state`` already gives; a
    ``LifecycleError`` when the move is not one this loop allows from where the set stands.
    The state is written before it is reported, so a caller never reads a move that did not
    land. ``published_oid`` is the commit a landing wrote, kept on the record when the move is
    into ``published``.
    """
    stored = store.load(change_set_id)
    if stored is None:
        return None
    if target not in store.STATES:
        raise LifecycleError(f"unknown state: {target!r}")
    if not may_move(stored.state, target):
        raise LifecycleError(f"a change set in {stored.state} does not move to {target}")
    return store.set_state(change_set_id, target, published_oid=published_oid)


def settle(change_set_id: str, verdict: str) -> bool:
    """Move a set to the state its verdict reached. False when the loop does not allow it.

    A verdict on a set that already shipped changes nothing: the ledger keeps it because the
    ledger is append-only, while the record stays where it stands. Only the move is refused,
    so this answers False where the verdict is already recorded.
    """
    try:
        move(change_set_id, VERDICT_STATE[verdict])
    except LifecycleError:
        return False
    return True


def unpublish(change_set_id: str):
    """Walk a published set back to a draft, so the loop may carry it again.

    The landing keeps its stamp: ``published_at`` and ``published_oid`` record the branch
    state this set once wrote, and a reader of the store is told that it did. None when the
    id is unknown, the answer every other move on an unknown id gives. A ``LifecycleError``
    when the set stands anywhere but ``published``: only a landing has a mark to take back.
    """
    stored = store.load(change_set_id)
    if stored is None:
        return None
    if stored.state != REVERT_FROM:
        raise LifecycleError(f"a change set in {stored.state} has no landing to take back")
    return store.set_state(change_set_id, REVERT_TO)


def amend(change_set_id: str, summary: str | None = None):
    """Re-read the workspace's diff under the same id and provenance.

    The id, the workspace, the provenance and the moment the set was first recorded all
    survive; only the paths, their digests and the summary are read afresh. The set returns
    to ``draft`` so an approval the earlier bytes earned cannot carry the new ones, which is
    the whole reason the state is written here rather than left alone.

    None when the id is unknown. A ``LifecycleError`` when the set has already shipped, or
    when the tree now holds no change for this id to describe. A ``ChangeSetError`` when the
    tree cannot be read, raised by the store's own reader.
    """
    stored = store.load(change_set_id)
    if stored is None:
        return None
    if stored.state not in AMENDABLE:
        raise LifecycleError("a published change set is final")
    files = store.read_files(stored.workspace_id)
    if not files:
        raise LifecycleError("the tree holds no change to record under this id")
    wanted = str(summary).strip() if summary is not None else ""
    amended = dataclasses.replace(
        stored,
        summary=wanted or stored.summary,
        files=files,
        state="draft",
    )
    store.save(amended)
    return amended


def view(stored, author: str = "") -> dict:
    """The life of one change set: where it stands, the last word on it, and what is legal here.

    Every field is read from the record or the ledger — the state the store holds, the latest
    verdict the gate holds, and the transition table above. Nothing is inferred from the
    files, so a reader sees the set's stage even when the tree it came from is gone.
    """
    verdict = gate.decide(stored.id)
    moves = TRANSITIONS.get(stored.state, frozenset())
    return {
        "change_set_id": stored.id,
        "state": stored.state,
        "author": author,
        "stations": stations_of(stored.state),
        "verdict": verdict.to_dict() if verdict is not None else None,
        "reasons": [reason.to_dict() for reason in verdict.reasons] if verdict else [],
        "decidable": bool(moves & _DECIDED),
        "amendable": stored.state in AMENDABLE,
        "withdraw": sorted(moves & BACK_MOVES),
        "can_publish": stored.state == "approved" and gate.may_publish(stored.id),
    }


__all__ = [
    "AMENDABLE", "BACK_MOVES", "REVERT_FROM", "REVERT_TO", "STATIONS", "TRANSITIONS",
    "VERDICT_STATE", "LifecycleError", "amend", "may_move", "move", "settle", "stations_of",
    "unpublish", "view",
]
