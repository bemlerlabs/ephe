"""Workspace lifecycle: one git worktree per agent run, and the register that holds them.

Fifty parallel runs need fifty checkouts, and every checkout is a tree git has to
learn about again afterwards. This module owns both halves: ``create`` adds a
worktree inside one managed directory and records it, ``remove`` takes a single
one down, and ``reap_orphans`` collects the trees whose owning process is gone.
Deletion is reachable from ``remove`` and ``reap_orphans`` alone, and both refuse a
path that resolves outside the managed directory, so the main checkout — whose path is
read from git but never deleted — stays unreachable from a teardown call even when the
register itself has been poisoned.

Register: ``<device folder>/workspaces/register.json``, one row per tree carrying
``id``, ``path``, ``branch``, ``state``, ``owner``, ``created_at`` and the owning
``pid``. Trees live beside it at ``<device folder>/workspaces/<8-hex>``, and a row
is written before git runs, which is what a crash between the two leaves behind for
the reaper to find.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterator

from core.engine_config import config_subdir
from core.workspace_rules import resolve_workspace_dir, workspace_key

logger = logging.getLogger(__name__)

STATES = ("creating", "ready", "dirty", "published", "discarded")
# Rows whose tree a caller may still use; the reaper never touches these.
LIVE_STATES = ("creating", "ready", "dirty", "published")
# Rows that already say their create failed; the reaper collects them by itself.
DEAD_STATES = ("discarded",)
DEFAULT_REAP_MINUTES = 240
GIT_TIMEOUT_SECONDS = 30.0

WORKSPACES_DIR: Path = Path(
    os.environ.get("EPHE_WORKSPACES_DIR") or str(config_subdir("workspaces"))
)
_ENV_REPO_ROOT = (os.environ.get("EPHE_REPO_ROOT") or "").strip()
REPO_ROOT: Path | None = Path(_ENV_REPO_ROOT).expanduser() if _ENV_REPO_ROOT else None


@dataclass(frozen=True)
class Workspace:
    """One agent run's checkout, exactly as the register describes it."""

    id: str
    path: str
    branch: str
    state: str
    owner: str
    created_at: str

    def as_dict(self) -> dict[str, str]:
        """The six fields as a JSON-ready mapping, which is the shape a route returns."""
        return asdict(self)


class WorkspaceError(RuntimeError):
    """A workspace call that could not be honoured."""


class UnsafePath(WorkspaceError):
    """A teardown aimed outside the managed directory: refused, nothing deleted."""


def register_file() -> Path:
    """The register this module reads and writes, beside the trees it names."""
    return WORKSPACES_DIR / "register.json"


def repo_root() -> Path:
    """The main checkout that hosts every tree of this repository.

    git answers from the common directory rather than the current tree, because a
    run may itself be working inside a linked worktree; ``EPHE_REPO_ROOT`` is the
    start value a test uses, so no case ever aims at the developer's own checkout.
    """
    if REPO_ROOT is not None:
        return Path(REPO_ROOT).expanduser().resolve()
    start = Path(resolve_workspace_dir() or os.getcwd())
    common = _git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=start)
    if common:
        return Path(common.strip()).parent.resolve()
    raise WorkspaceError(f"no git checkout above {start}; name one with EPHE_REPO_ROOT")


def create(owner: str, base: str = "main") -> Workspace:
    """Add a worktree for one agent run and return it.

    The register row is written before git runs, so a crash between the two leaves a
    row the reaper can find; the row reaches ``ready`` only once the tree exists.
    ``base`` is any branch or commit git accepts as the starting point.
    """
    root = _managed_root()
    root.mkdir(parents=True, exist_ok=True)
    tree_id = secrets.token_hex(4)
    target = root / tree_id
    branch = f"ws/{_slug(owner)}-{tree_id}"
    row = {"id": tree_id, "path": str(target), "branch": branch, "state": "creating",
           "owner": owner, "created_at": _now(), "pid": os.getpid()}
    # Held across the add, as `remove` holds it across its teardown: outside it, concurrent
    # adds race in git's worktree enumeration (3 of 48 refused at width 16, 3 of 50 at 50).
    with _locked():
        rows = _rows()
        rows.append(row)
        _write_rows(rows)
        added = _git(["worktree", "add", "-b", branch, str(target), base], cwd=repo_root())
    if added is None:
        _set_state(tree_id, "discarded")
        raise WorkspaceError(
            f"git worktree add failed for owner {owner!r} on base {base!r}; "
            f"row {tree_id} is marked discarded for the reaper"
        )
    _set_state(tree_id, "ready")
    return _to_workspace({**row, "state": "ready"})


def list_live() -> list[Workspace]:
    """The trees that exist right now and whose row is not discarded, register order."""
    live: list[Workspace] = []
    for row in _rows():
        if row.get("state") not in LIVE_STATES:
            continue
        if not Path(str(row.get("path", ""))).is_dir():
            continue
        live.append(_to_workspace(row))
    return live


def get(tree_id: str) -> Workspace | None:
    """One tree by id with its state refreshed from git; None when no live tree has it.

    Refresh is what makes the state worth reading: a tree that was clean when it was
    created and now carries edits reports ``dirty`` without a full list call.
    """
    row = next((r for r in _rows() if r.get("id") == tree_id), None)
    if row is None or row.get("state") not in LIVE_STATES:
        return None
    target = Path(str(row.get("path", "")))
    if not target.is_dir():
        return None
    if row.get("state") in ("ready", "dirty"):
        state = _state_of(target)
        if state != row.get("state"):
            _set_state(tree_id, state)
            row["state"] = state
    return _to_workspace(row)


def remove(tree_id: str, force: bool = False) -> None:
    """Take one tree down and drop its row; an id the register does not hold is a no-op.

    Without ``force`` git refuses a tree that carries local changes, and that refusal
    travels on as WorkspaceError. With ``force`` the directory goes even when git has
    already forgotten it, because a half-created tree is the shape a crash leaves behind.
    """
    with _locked():
        rows = _rows()
        row = next((r for r in rows if r.get("id") == tree_id), None)
        if row is None:
            return
        target = _guarded_path(str(row.get("path", "")))
        _teardown(target, str(row.get("branch", "")), force=force)
        _write_rows([r for r in rows if r.get("id") != tree_id])


def reap_orphans(older_than_minutes: float = DEFAULT_REAP_MINUTES) -> list[str]:
    """Remove every tree whose owner is gone, and return the ids that went.

    A row is an orphan when the process that wrote it no longer exists, or when its
    state already says the create failed. ``older_than_minutes`` is a grace period in
    front of both rules: a tree younger than that is left alone, which keeps a reaper
    from racing a run that has just started. Every case tears down with force, since a
    crashed run leaves local changes behind and the register exists to collect exactly
    those trees.
    """
    cutoff = datetime.now(tz=timezone.utc) - timedelta(minutes=max(0.0, float(older_than_minutes)))
    reaped: list[str] = []
    with _locked():
        rows = _rows()
        kept: list[dict] = []
        for row in rows:
            created = _parsed(row.get("created_at"))
            if created is not None and created > cutoff:
                kept.append(row)
                continue
            if row.get("state") not in DEAD_STATES and _alive(row.get("pid")):
                kept.append(row)
                continue
            tree_id = str(row.get("id", ""))
            try:
                target = _guarded_path(str(row.get("path", "")))
            except WorkspaceError as exc:
                logger.warning("orphan %s left where it stands: %s", tree_id, exc)
                kept.append(row)
                continue
            _teardown(target, str(row.get("branch", "")), force=True)
            reaped.append(tree_id)
        if reaped:
            _write_rows(kept)
    return reaped


def _managed_root() -> Path:
    """Where the trees and the register live, and the only directory this module deletes in."""
    # Real path, not a symlink's spelling: /tmp beside /private/tmp is one tree, one key.
    return Path(WORKSPACES_DIR).expanduser().resolve()


def _now() -> str:
    """ISO-8601 in UTC with microsecond precision, the stamp every row carries."""
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def _parsed(stamp: object) -> datetime | None:
    """A stored timestamp as an aware datetime, or None when it is absent or broken."""
    if not isinstance(stamp, str):
        return None
    try:
        parsed = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _alive(pid: object) -> bool:
    """Whether the process that started a tree still exists, asked with signal 0.

    PermissionError means the pid runs under another user, so it counts as alive.
    """
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _slug(owner: str) -> str:
    """A branch-safe trace of an owner name: git refs refuse spaces, colons and tildes."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", (owner or "agent").strip()).strip(".-")
    return (cleaned or "agent")[:40]


def _to_workspace(row: dict) -> Workspace:
    """One register row as the public dataclass, with an empty string for an absent field."""
    return Workspace(
        id=str(row.get("id", "")),
        path=str(row.get("path", "")),
        branch=str(row.get("branch", "")),
        state=str(row.get("state", "")),
        owner=str(row.get("owner", "")),
        created_at=str(row.get("created_at", "")),
    )


def _state_of(target: Path) -> str:
    """``dirty`` while the tree carries local changes, ``ready`` while it is clean."""
    porcelain = _git(["status", "--porcelain"], cwd=target)
    if porcelain is None:
        return "ready"
    return "dirty" if porcelain.strip() else "ready"


def _guarded_path(raw: str) -> Path:
    """The one path a teardown may delete, or UnsafePath naming why it may not.

    ``workspace_key`` is the product's own normaliser, so a relative path, a trailing
    ``..`` segment and a symlink resolve to the same target before the check runs. The
    checkout test runs one way only: a managed directory that sits inside the repository
    still works, while a target that contains the checkout — or the managed directory
    itself — is refused. A machine where git cannot name the checkout is refused too,
    since a guard that cannot prove a path safe must not delete anything.
    """
    target = Path(workspace_key(raw))
    root = Path(workspace_key(str(_managed_root())))
    if target == root or root not in target.parents:
        raise UnsafePath(f"{target} is not a tree inside {root}")
    checkout = Path(workspace_key(str(repo_root())))
    if target == checkout or target in checkout.parents:
        raise UnsafePath(f"{target} holds the checkout {checkout}")
    return target


def _teardown(target: Path, branch: str, *, force: bool) -> None:
    """Remove one tree, then its branch, tolerating a tree git never registered.

    Without ``force`` a dirty tree stops here: git refuses, and the caller learns the
    tree is still standing from WorkspaceError.
    """
    if target.exists():
        removed = _git(
            ["worktree", "remove", *(["--force"] if force else []), str(target)],
            cwd=repo_root(),
        )
        if removed is None:
            if not force:
                raise WorkspaceError(f"git kept {target}; take it down with force=True")
            shutil.rmtree(target, ignore_errors=True)
    _git(["worktree", "prune"], cwd=repo_root())
    if branch:
        _git(["branch", "-D", branch], cwd=repo_root())


def _set_state(tree_id: str, state: str) -> None:
    """Move one row's state, leaving every other row alone."""
    with _locked():
        rows = _rows()
        for row in rows:
            if row.get("id") == tree_id:
                row["state"] = state
        _write_rows(rows)


@contextlib.contextmanager
def _locked() -> Iterator[None]:
    """Hold an exclusive POSIX lock for one register read-modify-write.

    The register is shared by every run on the machine, so two processes that each
    read, append and write would lose one row to the other. Without fcntl (Windows)
    the atomic replace stays as the only guarantee, the way core/multi_session
    already treats its registry.
    """
    root = _managed_root()
    root.mkdir(parents=True, exist_ok=True)
    handle = open(root / "register.lock", "a+", encoding="utf-8")
    try:
        try:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        except (ImportError, OSError):
            pass
        yield
    finally:
        handle.close()


def _git(args: list[str], cwd: Path) -> str | None:
    """stdout of one git call, or None when git is missing or refuses the command.

    Callers treat None as a fact about the tree rather than as a fault: a tree that
    another process took down a moment ago is the ordinary case here.
    """
    try:
        done = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("git %s in %s did not run: %s", " ".join(args), cwd, exc)
        return None
    if done.returncode != 0:
        logger.warning("git %s in %s refused: %s", " ".join(args), cwd, done.stderr.strip()[:200])
        return None
    return done.stdout


def _rows() -> list[dict]:
    """The register as written; an absent, unreadable or foreign file reads as empty."""
    try:
        raw = json.loads(register_file().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = raw.get("workspaces") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and row.get("id")]


def _write_rows(rows: list[dict]) -> None:
    """Replace the register through a temporary file, so a reader never sees half of it."""
    target = register_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"workspaces": rows}, indent=1) + "\n", encoding="utf-8")
    tmp.replace(target)


__all__ = [
    "DEAD_STATES", "DEFAULT_REAP_MINUTES", "GIT_TIMEOUT_SECONDS", "LIVE_STATES", "REPO_ROOT",
    "STATES", "UnsafePath", "WORKSPACES_DIR", "Workspace", "WorkspaceError", "create", "get",
    "list_live", "reap_orphans", "register_file", "remove", "repo_root",
]
