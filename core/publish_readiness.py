"""Ephe – core/publish_readiness: the two reads a publish meets before it moves a ref.

`core.review_gate` answers whether a set earned a publish and `core.change_set_read`
recomputes the digests a set was recorded from; neither one answers "may this set leave now".
That answer is a composition — the state the store holds, and the tree — and until this module
each surface composed it for itself: `server/routes/workspaces.py` refused a set whose tree
moved (`publish_tree_moved`) and one that stood outside `approved` (`publish_without_approval`),
while `ephe publish` composed neither and landed both. One tree, one set, two answers, and the
terminal was the hole.

So the composition lives here, once, and every surface asks it. The codes are the shared
identity, spelled exactly as ``server/refusals.REASONS`` keys them, so a refusal reached here
names the same reason in a terminal and on a page; what stays with a surface is the rendering,
its sentence and its params. The approval is the gate's one shared answer
(``core.review_gate.may_publish``), asked here as well, because a set that stands outside
``approved`` with an approval on file was moved after that approval and earns its own refusal
rather than the one a set nobody signed earns.

The order is the one the web route already had, and it is the order of what a reader can fix
first: a state a publish may not leave from, then the tree — absent (`change_set_tree_gone`),
or moved (`publish_tree_moved`).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core import change_set as store
from core import change_set_lifecycle as loop
from core import review_gate as gate

#: The reasons a publish does not leave, spelled as ``server/refusals.REASONS`` spells them:
#: one vocabulary, so a terminal refusal and a page refusal name one reason.
WITHOUT_APPROVAL = "publish_without_approval"
APPROVAL_SUPERSEDED = "change_set_approval_superseded"
TREE_GONE = "change_set_tree_gone"
TREE_MOVED = "publish_tree_moved"

#: The one state a publish leaves from, taken from the state an approve verdict writes so the
#: gate and this module cannot drift apart over which state a published set stands in.
APPROVED = loop.VERDICT_STATE[gate.APPROVE]


@dataclass(frozen=True)
class Refusal:
    """Why one set may not publish: the code, the sentence, the move left, and a route's slots.

    ``params`` are the slots ``server/refusals.REASONS`` renders the code with, so a route
    raises its own sentence from this answer instead of restating the rule; ``reason`` and
    ``fix`` are the plain pair a surface that prints cause and fix on two lines needs.
    """

    code: str
    reason: str
    fix: str
    params: dict = field(default_factory=dict)


def drifted_paths(stored: store.ChangeSet) -> list[str]:
    """Paths whose digest no longer matches the record. Raises when the tree cannot be read."""
    from core.change_set_read import verify_current

    return [str(entry.get("path")) for entry in verify_current(stored)]


def refusal(stored: store.ChangeSet) -> Refusal | None:
    """Why this set may not publish as it stands, or None when nothing stands in the way.

    A set an amend stood back in draft is the case the state read exists for: the approval it
    earned was filed against bytes that are gone, so the state is what a publish has to be
    refused on, and the gate's own answer tells the two causes apart.
    """
    if stored.state != APPROVED:
        if gate.may_publish(stored.id):
            return Refusal(
                APPROVAL_SUPERSEDED,
                f"the approval filed on {stored.id} covers bytes this set no longer holds",
                "review the set where it now stands, then publish on that verdict",
                {"change_set": stored.id},
            )
        return Refusal(
            WITHOUT_APPROVAL,
            f"the set stands in {stored.state}, and only an approved set lands",
            "the set has to be approved where it now stands: an approval covers the state it "
            "was filed in",
            {"change_set": stored.id},
        )
    try:
        moved = drifted_paths(stored)
    except store.ChangeSetError as exc:
        return Refusal(
            TREE_GONE,
            str(exc),
            "record the set again from a live tree, then review and publish it",
            {"reason": str(exc)},
        )
    if moved:
        return Refusal(
            TREE_MOVED,
            f"the tree moved after this set was recorded: {', '.join(moved)}",
            "record the set again from the tree as it now stands, then review and publish it",
            {"paths": ", ".join(moved)},
        )
    return None


__all__ = [
    "APPROVAL_SUPERSEDED", "APPROVED", "TREE_GONE", "TREE_MOVED", "WITHOUT_APPROVAL", "Refusal",
    "drifted_paths", "refusal",
]
