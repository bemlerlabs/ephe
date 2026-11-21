"""Ephe – core/change_set_read: the questions a stored change set answers without a write.

``core.change_set`` owns the record and the 400-line wall ``scripts/architecture_check.mjs``
enforces, so the read side lives here: ``list_for`` gives one workspace's sets newest first;
``claims_by_path`` gives the runs sitting in a set of paths, each with the tree it works in, the
state of its set and the moment its diff was taken; ``conflicts`` narrows that to the rivals one
set will actually meet; ``verify_current`` recomputes each recorded digest against the worktree
and names the paths that moved.

Nothing here writes, and every reading goes through ``core.change_set`` rather than through a
copy of its directory, so a test that redirects the store redirects these with it.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from core import change_set

#: What one run holds in another run's way. A set that is `draft` or `review` is *in* its files
#: right now; a `published` one already wrote them to a branch, which is a landing and not a
#: claim — `rejected` names nothing a reader can act on either.
#: The states a live claim can be read in. `rejected` names nothing to act on.
CLAIM_STATES = ("draft", "review", "approved", "published")

#: The states in which a run is still *in* a file rather than done with it. `approved`
#: belongs here: a reviewer signed the set, but its bytes have not landed, so the paths
#: are still held and a second run publishing them meets this one.
HOLDING_STATES = ("draft", "review", "approved")


@dataclass(frozen=True)
class Claim(change_set._AsMapping):
    """One run's hold on one path: who, from which tree, since when, and in which state.

    ``since`` is the change set's own ``created_at`` — the moment its diff was read out of that
    tree — and ``landed_at`` is filled only once the set published. ``diff_sha`` rides along so
    two holds on one path can be compared by eye without a second read of the store.
    """

    path: str
    change_set_id: str
    workspace_id: str
    agent_id: str
    session_id: str
    why: str
    state: str
    op: str
    diff_sha: str
    since: str
    landed_at: str


def list_for(workspace_id: str) -> list[change_set.ChangeSet]:
    """Every stored change set of one workspace, newest first."""
    key = change_set._workspace_key(workspace_id)
    found = []
    for path in sorted(change_set.CHANGESETS_DIR.glob("*.json")):
        stored = change_set.load(path.stem)
        if stored is not None and change_set._workspace_key(stored.workspace_id) == key:
            found.append(stored)
    found.sort(key=lambda stored: (stored.created_at, stored.id), reverse=True)
    return found


def claims_by_path(
    paths: Sequence[str] | None = None,
    *,
    exclude_workspace: str = "",
    states: Sequence[str] = CLAIM_STATES,
) -> dict[str, list[Claim]]:
    """Who is in each of ``paths`` right now, and since when.

    The question a run asks before it writes and the one a reader asks when two of them are in
    one file: per path, every stored hold, with the tree, the author, the state and the moment
    the diff was taken. ``paths`` bounds the answer to the files a caller is about to touch;
    absent, every held path in the store answers. ``exclude_workspace`` drops one tree's own
    holds, because a run is not in conflict with itself. Paths and holders come back in a fixed
    order — ``(path, since, change-set id)`` — so two readings of one store agree.
    """
    wanted = {str(path) for path in paths} if paths is not None else None
    own = change_set._workspace_key(exclude_workspace) if exclude_workspace else ""
    allowed = set(states)
    held: dict[str, list[Claim]] = {}
    for stored_path in sorted(change_set.CHANGESETS_DIR.glob("*.json")):
        stored = change_set.load(stored_path.stem)
        if stored is None or stored.state not in allowed:
            continue
        if own and change_set._workspace_key(stored.workspace_id) == own:
            continue
        for change in stored.files:
            if wanted is not None and change.path not in wanted:
                continue
            claim = Claim(
                path=change.path, change_set_id=stored.id, workspace_id=stored.workspace_id,
                agent_id=stored.provenance.agent_id, session_id=stored.provenance.session_id,
                why=stored.provenance.why, state=stored.state, op=change.op,
                diff_sha=change.diff_sha, since=stored.created_at,
                landed_at=stored.published_at,
            )
            held.setdefault(change.path, []).append(claim)
    for claims in held.values():
        claims.sort(key=lambda claim: (claim.since, claim.change_set_id))
    return dict(sorted(held.items()))


def conflicts(stored: change_set.ChangeSet) -> dict[str, list[Claim]]:
    """The other runs this set will meet, per path it names.

    A *holding* set is in those files now, so publishing this one either way meets a file the
    other one is still moving — the disagreement the humans never saw coming. A *published* set
    whose landing is newer than this set's ``since`` landed after the diff a reviewer approved
    was read, so publishing writes over it. A landing older than this set is no conflict: it was
    already on the branch when the diff was taken.
    """
    rivals: dict[str, list[Claim]] = {}
    for path, claims in claims_by_path(
        [change.path for change in stored.files], exclude_workspace=stored.workspace_id
    ).items():
        met = [
            claim for claim in claims
            if claim.state in HOLDING_STATES
            or (claim.landed_at and claim.landed_at > stored.created_at)
        ]
        if met:
            rivals[path] = met
    return rivals


def verify_current(stored: change_set.ChangeSet | str) -> list[dict]:
    """Paths whose diff no longer matches what the change set recorded.

    Each row names the recorded digest and the digest now found; ``current`` is None when
    the path is no longer part of the diff at all. Only the worktree is read, so a stored
    change set is checkable long after the session that wrote it is gone.
    """
    if isinstance(stored, str):
        loaded = change_set.load(stored)
        if loaded is None:
            return []
        stored = loaded
    live = {change.path: change.diff_sha for change in change_set.read_files(stored.workspace_id)}
    drifted = []
    for change in stored.files:
        current = live.get(change.path)
        if current != change.diff_sha:
            drifted.append({"path": change.path, "recorded": change.diff_sha, "current": current})
    return drifted
