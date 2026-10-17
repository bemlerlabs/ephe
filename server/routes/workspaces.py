"""server/routes/workspaces.py — the isolation surface: trees, change sets, verdicts, publish.

Four modules hold the isolation between parallel agent runs and, until this router, none had a
caller: `core.workspace_lifecycle` (one git worktree per run and its orphans), `core.change_set`
(the paths a tree changed, with provenance), `core.review_gate` (a second agent's verdict on
that record) and `core.atomic_publish` (an accepted set onto a branch, never half-applied).

A workspace is named twice over. The register keys its rows by an eight-hex tree id
(``GET /api/workspaces`` returns it as ``id``), while `core.change_set` keys its store by the
resolved path — so a ``workspace_id`` travelling as a query value or a body field takes either
form, and a stored change set carries the path key it was built with. A page that correlates the
two by value therefore compares against that path, or passes the id back in and lets this router
resolve it; ``/api/workspaces/{id}`` is documented with the id form.

Three refusals are this router's own and none of them answers 500. An unknown id answers 404 the
way ``DELETE /api/sessions/{id}`` does, a refused argument answers 422, and a request the state
cannot honour answers 409: a publish with no earned approval in the ledger, one whose tree moved
after the set was recorded (`core.change_set_read.verify_current`), or one whose paths another
run is holding (`core.change_set_read.conflicts`) — because the set a reviewer approved would
otherwise ship different bytes, or write over a run that is still in those files. A ``dry_run``
publish is exempt from all of them, since it changes nothing. Each is a `Refused` carrying a code
from ``server.refusals.REASONS`` beside its sentence, so the page answers in the reader's own
language instead of the one this file is written in.

The collision half is answered where it is still a decision. ``GET /change-sets/claims`` names,
per path, which runs hold it and since when; `POST /change-sets` carries the same reading back
to the run that just wrote, in its own response; and the publish refusal names the holder it
would overwrite. Until this existed the store knew all of it and only the page could see it —
the loser learned at publish, after the work was done.

`core.agent_limits` enters through ``POST /api/workspaces`` alone: the width of a wave is the
one bound a route can read for itself, so the register's live count is handed to
``check`` and a reached bound answers 429 naming it. Cpu share, disk and runtime stay with the
orchestrator that started the wave, because a route guessing at them would refuse work for
reasons that are nobody's wave.

The request bodies and the reads behind these routes live in
``server/routes/_workspaces_support.py``, so this file stays a file of routes.
"""
from __future__ import annotations

import logging
from dataclasses import asdict

from fastapi import APIRouter, Query

from server.refusals import Refused
from server.routes._workspaces_support import (
    AmendRequest,
    ChangeSetRequest,
    PublishRequest,
    ReapRequest,
    ReviewRequest,
    StateRequest,
    WorkspaceRequest,
    _author_of,
    _change_set_rows,
    _conflict_names,
    _conflict_rows,
    _custodians,
    _load_change_set,
    _pending_waits,
    _preview,
    _publish_sentence,
    _register_row,
    _review_target,
    _workspace_path,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Workspaces"])


@router.get("/workspaces")
async def list_workspaces() -> dict:
    """Every live tree, and behind it the fleet: one row per run, state and last touch.

    Two halves, one read. ``workspaces`` keeps the register's six fields and gains the run
    fields a row needs to say what it is doing (``run_state``, ``needs_you``,
    ``running_for_seconds``, ``owner_alive``, ``last_event``). ``runs`` is the whole board —
    the same trees plus the helper runs and the waits that own no checkout — so a caller
    polling this one route has the fleet without a second endpoint. Nothing is stored here:
    `core.fleet` reads the registers that already exist.
    """
    from core import fleet
    from core import workspace_lifecycle as life

    rows = life.list_live()
    owners = fleet.register_owners()
    waits = _pending_waits()
    return {
        "workspaces": [fleet.workspace_view(row, pids=owners) for row in rows],
        "runs": fleet.build(waits=waits, owners=owners),
    }


@router.post("/workspaces")
async def create_workspace(request: WorkspaceRequest) -> dict:
    """Add one worktree for one owner, or refuse while the wave is already at its width."""
    from core import agent_limits
    from core import workspace_lifecycle as life

    reached = agent_limits.check(agent_limits.defaults(), {"agents": len(life.list_live())})
    if reached:
        raise Refused("agent_limit_reached", reason="; ".join(reached))
    try:
        created = life.create(request.owner, request.base)
    except life.WorkspaceError as exc:
        raise Refused("workspace_create_refused", reason=str(exc)) from exc
    logger.info("workspace create: %s for %s", created.id, created.owner)
    return {"workspace": created.as_dict()}


@router.get("/workspaces/{id}")
async def get_workspace(id: str) -> dict:
    """One tree by id or by path, with its state read from the tree itself."""
    row = _register_row(id)
    if row is None:
        raise Refused("workspace_not_live", workspace=id)
    return {"workspace": row.as_dict()}


@router.delete("/workspaces/{id}")
async def remove_workspace(id: str, force: bool = False) -> dict:
    """Take one tree down; a tree carrying local changes is refused without force."""
    from core import workspace_lifecycle as life

    row = _register_row(id)
    if row is None:
        raise Refused("workspace_not_live", workspace=id)
    try:
        life.remove(row.id, force=force)
    except life.WorkspaceError as exc:
        raise Refused("workspace_remove_refused", reason=str(exc)) from exc
    logger.info("workspace remove: %s force=%s", row.id, force)
    return {"removed": row.id}


@router.post("/workspaces/reap")
async def reap_workspaces(request: ReapRequest | None = None) -> dict:
    """Collect the trees whose owning process is gone, after the grace period."""
    from core import workspace_lifecycle as life

    grace = request.older_than_minutes if request is not None else None
    minutes = life.DEFAULT_REAP_MINUTES if grace is None else grace
    reaped = life.reap_orphans(minutes)
    logger.info("workspace reap: %s collected after %s minutes", len(reaped), minutes)
    return {"reaped": reaped}


@router.get("/change-sets")
async def list_change_sets(workspace_id: str) -> dict:
    """Every stored change set of one workspace, newest first."""
    from core.change_set_read import list_for

    path = _workspace_path(workspace_id)
    return {"change_sets": _change_set_rows(list_for(path))}


@router.post("/change-sets")
async def build_change_set(request: ChangeSetRequest) -> dict:
    """Read one tree's diff into a described change set and store it."""
    from core import change_set as store
    from core.change_set_read import conflicts

    path = _workspace_path(request.workspace_id)
    try:
        built = store.build(path, request.summary, request.provenance)
    except store.ChangeSetError as exc:
        raise Refused("change_set_build_refused", reason=str(exc)) from exc
    logger.info("change set built: %s over %s file(s)", built.id, len(built.files))
    # The builder's own surface: the runs already in these files, answered where the run that
    # just wrote can read them, instead of only on a page it may never open.
    return {"change_set": built.to_dict(), "conflicts": _conflict_rows(conflicts(built))}


@router.get("/change-sets/claims")
async def path_claims(
    path: list[str] | None = Query(default=None),
    exclude_workspace: str = "",
) -> dict:
    """Which runs are in these files right now, and since when.

    A run asks this before it writes, so a collision surfaces while it is still a choice, and a
    reader asks it when two of them are in one file. Without ``path`` every held path in the
    store answers; ``exclude_workspace`` drops one tree's own holds.
    """
    from core.change_set_read import claims_by_path

    own = _workspace_path(exclude_workspace) if exclude_workspace.strip() else ""
    held = claims_by_path(path or None, exclude_workspace=own)
    return {"paths": _conflict_rows(held)}


@router.get("/change-sets/{id}")
async def get_change_set(id: str) -> dict:
    """One stored change set, with the paths and digests it was built from."""
    return {"change_set": _load_change_set(id).to_dict()}


@router.post("/change-sets/{id}/review")
async def review_change_set(id: str, request: ReviewRequest) -> dict:
    """Record one reviewer's verdict on a stored change set.

    The gate turns down a reason that names no path in the set and an approval from the
    change set's own author, and nothing reaches the ledger when it does.
    """
    from core.review_gate import ReviewGateError, submit

    target = _review_target(_load_change_set(id))
    if target is None:
        raise Refused("change_set_no_author", change_set=id)
    try:
        recorded = submit(target, request.verdict, request.reviewer, request.reasons)
    except ReviewGateError as exc:
        raise Refused("review_refused", reason=str(exc)) from exc
    from core import change_set_lifecycle as loop

    loop.settle(id, recorded.verdict)
    logger.info("change set review: %s %s by %s", id, recorded.verdict, recorded.reviewer)
    return {"verdict": recorded.to_dict()}


@router.post("/change-sets/{id}/publish")
async def publish_change_set(id: str, request: PublishRequest | None = None) -> dict:
    """Move an approved change set onto its target branch, atomically, or name the refusal."""
    from core import atomic_publish
    from core import change_set as store
    from core import change_set_lifecycle as loop
    from core import publish_readiness
    from core.change_set_read import conflicts
    from core.review_gate import may_publish

    stored = _load_change_set(id)
    body = request if request is not None else PublishRequest()
    met = conflicts(stored)
    if not body.dry_run:
        target = _review_target(stored)
        # Both are read here: the ledger, and then the one shared preflight. A set amended
        # after its approval stands back in draft, so the approval it earned then covers bytes
        # that are gone — and the state and the tree come from `core.publish_readiness`, the
        # same read the terminal asks, so neither surface can answer one set differently.
        if target is None or not may_publish(target):
            raise Refused("publish_without_approval", change_set=id)
        refusal = publish_readiness.refusal(stored)
        if refusal is not None:
            raise Refused(refusal.code, **refusal.params)
        if met and not body.force:
            paths, holders = _conflict_names(met)
            raise Refused("publish_path_claimed", paths=paths, holders=holders)
    result = atomic_publish.publish(stored, target=body.target, dry_run=body.dry_run)
    if result.ok and not body.dry_run:
        # A landing leaves the store as one: a set that already wrote its bytes
        # to a branch is no longer a claim on those paths, and a later run reading
        # this store must see that.
        loop.move(id, "published", result.oid)
    logger.info("change set publish: %s ok=%s dry_run=%s", id, result.ok, body.dry_run)
    return {
        "result": asdict(result),
        "sentence": _publish_sentence(result, body.dry_run),
        "conflicts": _conflict_rows(met),
    }


@router.post("/change-sets/{id}/unpublish")
async def unpublish_change_set(id: str) -> dict:
    """Take one landing back: the set returns to a draft it can be worked on and land from."""
    from core import change_set_lifecycle as loop

    _load_change_set(id)
    try:
        reverted = loop.unpublish(id)
    except loop.LifecycleError as exc:
        raise Refused("change_set_unpublish_refused", reason=str(exc)) from exc
    if reverted is None:
        raise Refused("change_set_unknown", change_set=id)
    logger.info("change set unpublish: %s -> %s", id, reverted.state)
    return {"change_set": reverted.to_dict()}


@router.get("/change-sets/{id}/custody")
async def change_set_custody(id: str) -> dict:
    """The record's chain of custody: who wrote it, who signed it, whether it still matches.

    The two answers a diff cannot carry sit here together. A signature is only a signature
    when someone other than the author gave it, and the bytes a reviewer approved are only
    those bytes while the tree still hashes to what the record says — so this reads the
    ledger and re-runs ``core.change_set_read.verify_current`` live. It is the same state
    ``POST …/publish`` acts on, stated before it is asked for; ``refusal`` is the sentence
    that route would answer with, or null when it would land.
    """
    from core import change_set as store
    from core import workspace_lifecycle as life
    from core.change_set_read import verify_current
    from core.review_gate import decide, may_publish

    stored = _load_change_set(id)
    author = _author_of(stored)
    target = _review_target(stored)
    approval = decide(stored.id)

    drifted: dict[str, object] = {}
    checked = True
    drift_refusal = None
    try:
        drifted = {str(entry["path"]): entry.get("current") for entry in verify_current(stored)}
    except store.ChangeSetError as exc:
        # The record outlives the tree it was built from; only the live half is unanswerable.
        # The exception is for the log below; the refusal carries a fixed reason a reader can act on.
        logger.warning("change set custody: tree unreadable for %s: %s", id, exc, exc_info=True)
        checked, drift_refusal = False, _preview("change_set_tree_gone", reason="the tree is gone")

    files = [
        {
            "path": change.path,
            "op": change.op,
            "recorded": change.diff_sha,
            # A path absent from the drift read is one the digest still covers, so what is
            # on disk is what was recorded; an unread tree answers nothing rather than a guess.
            "current": None if not checked else drifted.get(change.path, change.diff_sha),
            "moved": change.path in drifted,
        }
        for change in stored.files
    ]

    if drift_refusal is not None:
        refusal = drift_refusal
    elif target is None:
        refusal = _preview("change_set_no_author", change_set=stored.id)
    elif not may_publish(target):
        refusal = _preview("publish_without_approval", change_set=stored.id)
    elif drifted:
        refusal = _preview("publish_tree_moved", paths=", ".join(sorted(drifted)))
    else:
        refusal = None

    return {
        "change_set": stored.to_dict(),
        "author": author,
        "approval": approval.to_dict() if approval is not None else None,
        "custodians": _custodians(author),
        "files": files,
        "checked": checked,
        "publishable": refusal is None,
        "refusal": refusal,
    }


@router.get("/change-sets/{id}/lifecycle")
async def read_change_set_lifecycle(id: str) -> dict:
    """Where one change set stands, the last verdict on it, and the moves still open to it."""
    from core import change_set_lifecycle as loop

    stored = _load_change_set(id)
    return {"lifecycle": loop.view(stored, author=_author_of(stored))}


@router.post("/change-sets/{id}/amend")
async def amend_change_set(id: str, request: AmendRequest | None = None) -> dict:
    """Re-read a set's tree under the same id and provenance, and stand it back in draft."""
    from core import change_set as store
    from core import change_set_lifecycle as loop

    _load_change_set(id)
    summary = request.summary if request is not None else None
    try:
        amended = loop.amend(id, summary=summary)
    except loop.LifecycleError as exc:
        raise Refused("change_set_amend_refused", reason=str(exc)) from exc
    except store.ChangeSetError as exc:
        raise Refused("change_set_tree_gone", reason=str(exc)) from exc
    if amended is None:
        raise Refused("change_set_unknown", change_set=id)
    logger.info("change set amend: %s over %s file(s)", id, len(amended.files))
    return {"change_set": amended.to_dict()}


@router.post("/change-sets/{id}/state")
async def move_change_set(id: str, request: StateRequest) -> dict:
    """Move a set back by hand, to draft alone; every other state needs a verdict or a publish."""
    from core import change_set_lifecycle as loop

    _load_change_set(id)
    target = request.state.strip().lower()
    if target not in loop.BACK_MOVES:
        raise Refused("change_set_state_reserved", change_set=id, state=target)
    try:
        moved = loop.move(id, target)
    except loop.LifecycleError as exc:
        raise Refused("change_set_state_refused", reason=str(exc)) from exc
    if moved is None:
        raise Refused("change_set_unknown", change_set=id)
    logger.info("change set state: %s -> %s", id, target)
    return {"change_set": moved.to_dict()}
