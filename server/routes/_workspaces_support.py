"""server/routes/_workspaces_support.py — the request bodies and non-route reads of /api/workspaces.

``server/routes/workspaces.py`` is the surface a page calls: the operations over the isolation
core, and the fleet read behind ``GET /api/workspaces``. Everything here is the part of that
surface a page never names — the seven request bodies those routes are typed by, and the reads
that turn a caller's ``workspace_id`` or change-set id into a register row, a stored record, or
the refusal an unknown name earns. They sit in one module so the route file stays a file of
routes, with room for the operations still landing beside it. The formatters a page reads live
here too: the sentence a publish answers with, the list rows with the last verdict on each set,
and the refusal a route would raise, stated as data before it is asked for.

A workspace is named twice over, and every read here resolves both forms. The register keys its
rows by an eight-hex tree id while `core.change_set` keys its store by the resolved path, so a
name arriving in either form is matched against the register, then against the resolved form of
each live row: where the managed directory sits behind a symlink the two differ as text, and the
comparison folds symlinks and ``..`` out before it compares. A name that matches neither form is
not a workspace, and the managed directory is the only root one can land in — no value a request
carries reaches a filesystem call or the store as a path.

Each refusal raised here is a `Refused` carrying a code from ``server.refusals.REASONS`` beside
its sentence, so the page answers in the reader's own language: an empty name earns 422, a name
no live tree carries earns 404, and a set whose tree has gone earns 409.
"""
from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field

from server.refusals import Refused

logger = logging.getLogger(__name__)


class WorkspaceRequest(BaseModel):
    """The owner a tree is created for, and the branch or commit it starts from."""

    owner: str = Field(min_length=1, max_length=80)
    base: str = Field(default="main", min_length=1, max_length=200)


class ReapRequest(BaseModel):
    """The grace period in front of a reaped tree; absent means the module's own default."""

    older_than_minutes: float | None = Field(default=None, ge=0, le=1_000_000)


class ChangeSetRequest(BaseModel):
    """A tree to read, the summary a reader sees, and the provenance the module validates."""

    workspace_id: str = Field(min_length=1, max_length=4096)
    summary: str = Field(min_length=1, max_length=500)
    provenance: dict[str, object]


class ReviewRequest(BaseModel):
    """One reviewer's verdict. The gate wants at least one located reason behind it."""

    verdict: str = Field(min_length=1, max_length=40)
    reviewer: str = Field(min_length=1, max_length=120)
    reasons: list[dict[str, object]] = Field(min_length=1)


class PublishRequest(BaseModel):
    """Where an accepted set goes, whether the answer is a rehearsal, and whether a named
    collision is written over."""

    target: str = Field(default="main", min_length=1, max_length=200)
    dry_run: bool = False
    force: bool = False


class AmendRequest(BaseModel):
    """An amended set keeps its id, its provenance and its workspace; a new summary may come."""

    summary: str | None = Field(default=None, min_length=1, max_length=500)


class StateRequest(BaseModel):
    """A state a surface asks to move a set to by hand. Only the moves back are allowed."""

    state: str = Field(min_length=1, max_length=40)


def _managed_root() -> Path:
    """The parent of every tree the register holds, the one directory a name may land in."""
    from core import workspace_lifecycle as life

    # The expression `create` builds its rows with.
    return Path(life.WORKSPACES_DIR).expanduser().resolve()


def _confined(candidate: Path) -> Path | None:
    """``candidate`` resolved and proven to sit inside the managed root, or None.

    The comparison is `core.path_guard.confine`: symlinks and ``..`` are folded out before
    it compares, and the comparison is a separator-bounded one, so a sibling that merely
    shares the root's prefix is refused rather than followed.
    """
    from core.path_guard import confine

    return confine(candidate, _managed_root())


def _resolved(text: str) -> Path | None:
    """A register comparison key: the text as a path inside the managed root, or None."""
    try:
        return _confined(Path(str(text)))
    except (OSError, ValueError):
        return None


def _register_row(workspace_id: str):
    """The register row a caller named, by tree id or by the path that row was given.

    A path matches on the resolved form: the register stores the path as it built it while
    `core.change_set` stores the resolved key, and where the managed directory sits behind a
    symlink the two differ as text. None means no live tree carries the name.
    """
    from core import workspace_lifecycle as life

    text = str(workspace_id or "").strip()
    if not text:
        return None
    row = life.get(text)
    if row is not None:
        return row
    key = _resolved(text)
    if key is None:
        return None
    for candidate in life.list_live():
        if _resolved(candidate.path) == key:
            return candidate
    return None


def _workspace_path(workspace_id: str) -> str:
    """The workspace root the change-set store keys on, or the answer an unknown name gets.

    A name is a tree id, the path a register row carries, or a directory the managed
    root holds — resolved and proven to stay inside that root before anything uses it,
    so a name arriving over /api never reaches the store or git as an arbitrary path
    on the machine.
    """
    text = str(workspace_id or "").strip()
    if not text:
        raise Refused("workspace_id_required")
    row = _register_row(text)
    if row is not None:
        key = _confined(Path(str(row.path)))
        # A row `create` wrote sits under the root. A row that does not — a register
        # kept from another tree root, or one edited by hand — is still the register's
        # own value, and the store is keyed by it rather than by the name the caller sent.
        return str(key or row.path)
    # The directory form: a tree whose row the reaper has already taken, or one the
    # caller is looking at while the register is written. Only a directory under the
    # managed root can be named here, and the physical spelling is what the store keys by.
    inside = _confined(Path(text))
    if inside is not None and inside.is_dir():
        return str(inside)
    raise Refused("workspace_unknown", workspace=text)


def _load_change_set(change_set_id: str):
    """One stored change set, or the 404 an unknown id is answered with across this app."""
    from core import change_set as store

    stored = store.load(change_set_id)
    if stored is None:
        raise Refused("change_set_unknown", change_set=change_set_id)
    return stored


def _name_of(provenance, workspace_id: str) -> str:
    """Who a record says wrote it: the agent, then the session, then the tree's owner.

    `core.review_gate` refuses an approval from the change set's own author, so this name is
    the one a reviewer is held against. A record whose provenance names nobody falls back to
    the register's owner for the tree it came from; an empty answer stays empty rather than
    becoming a stand-in that no agent could be held to.
    """
    for candidate in (provenance.agent_id, provenance.session_id):
        if str(candidate or "").strip():
            return str(candidate).strip()
    row = _register_row(str(workspace_id))
    return str(row.owner) if row is not None else ""


def _author_of(stored) -> str:
    """The author of one stored set, by the name the review gate holds it to."""
    return _name_of(stored.provenance, stored.workspace_id)


def _review_target(stored):
    """The record as the gate reads it; None when its provenance names no author."""
    from core.review_gate import ChangeSet as ReviewChangeSet

    author = _author_of(stored)
    if not author:
        return None
    return ReviewChangeSet(
        change_set_id=stored.id,
        author=author,
        paths=tuple(change.path for change in stored.files),
    )


def _change_set_rows(stored_sets: list) -> list[dict]:
    """One workspace's sets, each carrying the last verdict on it, from one ledger read.

    A review list that named no reasons left a reviewer opening every set to find out why one
    came back with changes requested; the ledger holds them, and one read answers for the list.
    """
    from core.review_gate import latest_by_id

    latest = latest_by_id()
    rows = []
    for stored in stored_sets:
        row = stored.to_dict()
        verdict = latest.get(stored.id)
        row["latest"] = verdict.to_dict() if verdict is not None else None
        rows.append(row)
    return rows


def _holder_row(claim) -> dict:
    """One hold as a surface meets it: the run, its tree, when it took the path, and its diff.

    ``workspace_id`` answers in the register's id form when that tree is live, because a page
    correlates the two by it; ``workspace_path`` carries the store's own key either way.
    """
    row = _register_row(str(claim.workspace_id))
    return {
        "path": claim.path,
        "change_set_id": claim.change_set_id,
        "workspace_id": row.id if row is not None else claim.workspace_id,
        "workspace_path": claim.workspace_id,
        "owner": str(row.owner) if row is not None else "",
        "author": _name_of(claim, claim.workspace_id),
        "session_id": claim.session_id,
        "why": claim.why,
        "state": claim.state,
        "op": claim.op,
        "diff_sha": claim.diff_sha,
        "since": claim.since,
        "landed_at": claim.landed_at,
    }


def _conflict_rows(by_path: dict[str, list]) -> list[dict]:
    """Per-path blocks, each with the runs holding it — the shape every surface reads."""
    return [
        {"path": path, "holders": [_holder_row(claim) for claim in claims]}
        for path, claims in sorted(by_path.items())
    ]


def _conflict_names(by_path: dict[str, list]) -> tuple[str, str]:
    """The two slots `publish_path_claimed` frames: the files, and the runs holding them."""
    names: list[str] = []
    for path in sorted(by_path):
        for claim in by_path[path]:
            stamp = (claim.landed_at or claim.since)[:16]
            note = f"{_name_of(claim, claim.workspace_id)} ({claim.state} since {stamp})"
            if note not in names:
                names.append(note)
    return ", ".join(sorted(by_path)), "; ".join(names)


def _publish_sentence(result, dry_run: bool) -> str:
    """What landed and what was rolled back, as one sentence a reviewer reads.

    The core's ``reason`` states the outcome; this adds the paths behind it, because a
    reviewer reads which files shipped and which were put back, not how many there were.
    """
    if dry_run:
        return result.reason
    if result.ok:
        return f"{result.reason}: {', '.join(result.applied)}"
    rolled = ", ".join(result.rolled_back)
    return f"{result.reason}; rolled back {rolled}" if rolled else result.reason


def _pending_waits() -> list[dict]:
    """The unanswered tool approvals, or none when the approval gate cannot be read.

    Fail-soft on purpose: a board that cannot say who is waiting is worth less, but a board
    that 500s because the chat router was not importable is worth nothing.
    """
    try:
        from server.routes.chat import pending_approvals

        return pending_approvals()
    except Exception:  # noqa: BLE001 — a missing wait is a smaller loss than a dead route
        logger.warning("fleet: pending approvals unreadable", exc_info=True)
        return []


def _preview(code: str, **params) -> dict:
    """The refusal a route would raise for ``code``, as data: code, sentence, params.

    Built through the same registry the raise goes through, so a surface that states a
    refusal before it is asked for cannot drift from the one the API answers with.
    """
    refused = Refused(code, **params)
    return {"code": refused.code, "sentence": refused.message, "params": refused.params}


def _custodians(author: str) -> list[str]:
    """Owners of live trees who may sign this record — everyone but the one who wrote it.

    `core.review_gate` refuses an approval whose reviewer is the author, so this is the fix
    that refusal offers, read off the register rather than guessed from the change set.
    """
    from core import workspace_lifecycle as life

    owners = {str(row.owner).strip() for row in life.list_live()}
    return sorted(owner for owner in owners if owner and owner != author)
