"""Ephe — atomic ChangeSet publishing (Welle 1 "Isolation", Welle 3 "Parallel & Atomic").

Rule: a publish either applies EVERY file of the change set to the target branch, or it
leaves the target byte-identical to its prior state. There is no third outcome.

Why the temporary-index technique — and why not the two obvious alternatives
The defect this replaces: ``git apply`` a partial set straight into the target checkout and
commit. ``git apply`` works file by file and is not transactional — file 3 fails and files
1..2 are already on disk. That half-applied tree is exactly the class of damage ``main``
must never see.

Chosen technique: build the whole set as *one new tree object* behind a private index
(``GIT_INDEX_FILE``), then move the branch ref with a single compare-and-swap. Concretely::

    read-tree <target>               seed the private index from the target's tree
    hash-object -w / apply --cached  stage each file into the private index
    write-tree                       one tree object — every file, or none
    commit-tree <tree> -p <target>   one commit object
    update-ref <ref> <new> <target>  the ONLY mutation of observable state

Everything before ``update-ref`` writes only into a temp index, a temp directory and
*unreferenced* loose objects. No ref and no worktree byte is touched, so an abort anywhere
before that line is a no-op for the target. ``update-ref`` with its old-oid guard is itself
atomic and all-or-nothing, so two publishers cannot interleave and a lost update is
impossible — the loser gets a clean abort, not a half tree.

Rejected alternatives. "Stash-free apply onto a detached head" still writes the working tree
file by file — a crash leaves the checkout half-applied — and it needs a checkout the caller
does not own. "Intermediate branch, then merge" makes a publish two mutations instead of one,
and the merge can itself conflict: the subset problem in a new costume.

The target's checkout is deliberately never written. In the worktree-isolation model ``main``
is the shared integration branch whose checkout belongs to the orchestrator, and the plan
forbids an agent writing into the main checkout's tree or index. Publishing owns the ref;
materialising a checkout is someone else's job.

Every build runs against a private object store (``GIT_OBJECT_DIRECTORY`` with the real store
as an alternate), so even the blobs of a set that later fails land only in a throwaway
directory. A ``dry_run`` stops there. A real publish, once the build has fully succeeded,
copies the in-flight objects into the real store (an add-only, content-addressed copy, hence
concurrency-safe) and only then moves the ref. An abort before that point therefore leaves
the ref, the index, every worktree byte *and* the real object store byte-identical.

Interface contract (duck-typed; the owners' types are not imported)
``publish(change_set, target="main", dry_run=False) -> PublishResult``.

``change_set`` is read structurally, so a fake works in tests. It is the shape
``core/change_set.py`` (w1-changeset) stores — ``ChangeSet(id, workspace_id, summary,
files=[FileChange(path, op, diff_sha)], provenance, state)`` — a set of *paths*, never file
bytes: the bytes stay in the workspace worktree and are read from there. The workspace root
comes from ``change_set.workspace`` (``core/workspace_lifecycle.Workspace`` exposes ``.path``,
and ``core/ephemeral_workspace.py`` is expected to as well) or ``change_set.workspace_id``;
failing those, ``change_set.repo_root`` / ``change_set.workspace_root`` / ``$EPHE_PUBLISH_REPO``
/ the current directory. ``op`` of ``delete`` removes the path; ``create``/``modify`` (and any
entry) are read from ``<workspace>/<path>``. For a fake or an inline call an entry may instead
carry ``.content`` (bytes or str) or ``.diff`` (unified diff text), and a plain
``(path, content)`` pair works too. Nothing here imports the owners' types.

``PublishResult`` is ``{ok, applied, rolled_back, reason, oid}``:

* ``applied``      — files committed to the target (all of them, or an empty list)
* ``rolled_back``  — files that had already landed in the in-flight tree when an abort
  happened, hence restored to the target's prior state; empty when the abort struck before
  any file landed (a preflight conflict, an empty set, a bad repository)
* ``reason``       — one short, stable sentence naming the failing path when there is one
* ``oid``          — the commit a real publish moved the target to, which a caller records
  beside the change set it landed; empty for a dry run and for an abort, where no ref moved
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_MESSAGE = "chore(publish): apply change set atomically"
_ZERO = "0" * 40


class PublishError(RuntimeError):
    """A publish was aborted. The target is guaranteed unchanged."""


@dataclass
class PublishResult:
    """Outcome of one ``publish`` call. See the module docstring for field semantics."""

    ok: bool
    applied: list[str] = field(default_factory=list)
    rolled_back: list[str] = field(default_factory=list)
    reason: str = ""
    oid: str = ""


def _file_boundary_hook(path: str) -> None:
    """Test seam: invoked at each file boundary, *before* ``path`` lands in the tree.

    A test replaces this to raise on the second file, which injects a failure exactly
    *between* two files — the case a per-file ``git apply`` cannot survive.
    """


@dataclass
class _Edit:
    """One normalised file operation."""

    path: str
    content: bytes | None = None
    diff: str | None = None
    delete: bool = False


def _get(source: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from a mapping or an attribute holder, so both work as a change set."""
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


def _as_bytes(value: Any) -> bytes:
    return value if isinstance(value, bytes) else str(value).encode("utf-8")


def _edit_from(item: Any, source: Path | None) -> _Edit:
    if isinstance(item, (tuple, list)) and len(item) == 2:
        return _Edit(path=str(item[0]), content=_as_bytes(item[1]))
    path = _get(item, "path") or _get(item, "relpath") or _get(item, "file")
    if not path:
        raise PublishError("change set entry without a path")
    path = str(path)
    if _get(item, "delete") or _get(item, "op") == "delete":
        return _Edit(path=path, delete=True)
    diff = _get(item, "diff")
    if diff is not None:
        return _Edit(path=path, diff=str(diff))
    content = _get(item, "content")
    if content is None:
        content = _get(item, "text")
    if content is not None:
        return _Edit(path=path, content=_as_bytes(content))
    return _Edit(path=path, content=_read_from_workspace(source, path))


def _read_from_workspace(source: Path | None, path: str) -> bytes:
    """One file's bytes, read from the workspace worktree.

    A change set (``FileChange(path, op, diff_sha)``) names paths; the bytes stay
    in the tree the run worked in, so a publish reads them from there and hashes them into the
    new target tree without ever writing the source.
    """
    if source is None:
        raise PublishError(f"{path!r}: no content in the change set and no workspace to read it from")
    candidate = source / path
    if not candidate.is_file():
        raise PublishError(f"{path!r} is not a file in the workspace")
    try:
        return candidate.read_bytes()
    except OSError as exc:
        raise PublishError(f"could not read {path!r} from the workspace: {exc}") from exc


def _resolve_edits(change_set: Any, source: Path | None) -> list[_Edit]:
    files = _get(change_set, "files") or _get(change_set, "edits") or []
    edits = [_edit_from(item, source) for item in files]
    if not edits:
        raise PublishError("empty change set: nothing to publish")
    return edits


def _workspace_dir(change_set: Any) -> Path | None:
    """The workspace worktree the change set's paths are read from, when it exists."""
    workspace = _get(change_set, "workspace")
    candidates = [_get(workspace, "path")] if workspace is not None else []
    candidates.append(_get(change_set, "workspace_id"))
    for candidate in candidates:
        if candidate:
            path = Path(str(candidate)).expanduser()
            if path.is_dir():
                return path.resolve()
    return None


def _repo_of(source: Path) -> Path:
    """The git repo that owns a worktree — a linked worktree's toplevel is itself, and the
    refs it shares live in the common git dir, which is exactly what a publish moves."""
    proc = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "--show-toplevel"], capture_output=True, check=False
    )
    out = proc.stdout.decode().strip()
    return Path(out).resolve() if proc.returncode == 0 and out else source


def _resolve_repo(change_set: Any, source: Path | None) -> Path:
    for key in ("repo_root", "workspace_root"):
        value = _get(change_set, key)
        if value:
            return Path(value).resolve()
    if source is not None:
        return _repo_of(source)
    env = os.environ.get("EPHE_PUBLISH_REPO")
    if env:
        return Path(env).resolve()
    return Path.cwd().resolve()


def _target_ref(target: str) -> str:
    return target if target.startswith("refs/") else f"refs/heads/{target}"


def _message_of(change_set: Any) -> str:
    return str(_get(change_set, "message") or DEFAULT_MESSAGE)


def _git(
    repo: Path,
    args: list[str],
    *,
    env: dict[str, str] | None = None,
    stdin: bytes | None = None,
) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=repo, env=env, input=stdin, capture_output=True, check=False
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout).decode("utf-8", "replace").strip()
        tail = detail.splitlines()[-1] if detail else f"git {' '.join(args)} failed"
        raise PublishError(tail)
    return proc.stdout.decode("utf-8", "replace").strip()


def _current_oid(repo: Path, ref: str) -> str:
    proc = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", ref], cwd=repo, capture_output=True, check=False
    )
    return proc.stdout.decode().strip() if proc.returncode == 0 else ""


def _real_objects_dir(repo: Path) -> Path:
    real = _git(repo, ["rev-parse", "--git-path", "objects"])
    return Path(real) if os.path.isabs(real) else (repo / real)


def _isolated_objects_env(scratch: Path, real_objects: Path) -> dict[str, str]:
    """Redirect the object store to a throwaway dir, with the real one as an alternate.

    The in-flight build reads real base objects but writes its new blobs, tree and commit
    into ``scratch`` only. Nothing reaches the real store until a build has fully succeeded
    and ``_promote_objects`` copies them across, so an abort — even one that got past every
    file — leaves the real object store untouched as well.
    """
    objects = scratch / "objects"
    objects.mkdir(parents=True, exist_ok=True)
    return {
        "GIT_OBJECT_DIRECTORY": str(objects),
        "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(real_objects),
    }


def _promote_objects(source: Path, dest: Path) -> None:
    """Copy the in-flight objects into the real store. Add-only, hence concurrency-safe.

    Objects are content-addressed — the path *is* the hash — so a copy is idempotent and can
    never clobber a different object. That is exactly why promoting after a green build is
    safe while deleting loose objects on an abort would not be.
    """
    try:
        for src in source.rglob("*"):
            if src.is_file():
                target = dest / src.relative_to(source)
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.copyfile(src, target)
    except OSError as exc:
        raise PublishError(f"could not promote objects: {exc}") from exc


def _stage(repo: Path, env: dict[str, str], edit: _Edit, scratch: Path, seq: int) -> None:
    if edit.delete:
        # --force-remove on a path absent from the target is a silent success (verified).
        _git(repo, ["update-index", "--force-remove", edit.path], env=env)
        return
    if edit.diff is not None:
        patch = scratch / f"edit-{seq}.patch"
        patch.write_text(edit.diff, encoding="utf-8")
        # --cached applies to the private index only; the worktree is never read or written.
        _git(repo, ["apply", "--cached", "--whitespace=nowarn", str(patch)], env=env)
        return
    blob = _git(repo, ["hash-object", "-w", "--stdin"], env=env, stdin=edit.content or b"")
    _git(repo, ["update-index", "--add", "--cacheinfo", "100644", blob, edit.path], env=env)


def _build_in_flight(
    repo: Path,
    base: str,
    edits: list[_Edit],
    staged: list[str],
    message: str,
    scratch: Path,
    real_objects: Path,
) -> str:
    """Stage the whole set in an isolated index and object store; return the candidate commit.

    ``staged`` accumulates every path that has landed, so the caller can report exactly what
    an abort rolled back. Raises ``PublishError`` on the first failure — at which point the
    private index and the isolated objects are simply discarded, and the target, its index and
    the real object store were never written.
    """
    env = {**os.environ, "GIT_INDEX_FILE": str(scratch / "index")}
    env.update(_isolated_objects_env(scratch, real_objects))
    # ``commit-tree`` needs an author and a committer. A clean runner carries neither a git
    # config nor GIT_* identity, and a publish must not depend on the ambient machine, so
    # name them here when the environment is silent.
    for role in ("AUTHOR", "COMMITTER"):
        env.setdefault(f"GIT_{role}_NAME", "Ephe")
        env.setdefault(f"GIT_{role}_EMAIL", "ephe@localhost")
    _git(repo, ["read-tree", base] if base else ["read-tree", "--empty"], env=env)
    for seq, edit in enumerate(edits):
        _file_boundary_hook(edit.path)
        _stage(repo, env, edit, scratch, seq)
        staged.append(edit.path)
    tree = _git(repo, ["write-tree"], env=env)
    args = ["commit-tree", tree, "-m", message]
    if base:
        args[2:2] = ["-p", base]
    return _git(repo, args, env=env)


def _commit_ref(repo: Path, ref: str, commit: str, base: str) -> None:
    """Move ``ref`` to ``commit`` only if it still points at ``base`` (atomic CAS)."""
    _git(repo, ["update-ref", ref, commit, base or _ZERO])


def publish(change_set: Any, target: str = "main", dry_run: bool = False) -> PublishResult:
    """Publish ``change_set`` to ``target`` atomically and report the outcome.

    Every file or none: on any failure the target ref is left exactly where it was, and no
    worktree byte changes. ``dry_run=True`` builds the identical in-flight tree against an
    isolated object store and discards it, reporting what a real publish would do.
    """
    try:
        source = _workspace_dir(change_set)
        repo = _resolve_repo(change_set, source)
        edits = _resolve_edits(change_set, source)
    except PublishError as exc:
        return PublishResult(ok=False, reason=str(exc))

    ref = _target_ref(target)
    base = _current_oid(repo, ref)
    message = _message_of(change_set)
    paths = [edit.path for edit in edits]
    staged: list[str] = []

    try:
        real_objects = _real_objects_dir(repo)
    except PublishError as exc:
        return PublishResult(ok=False, reason=str(exc))

    with tempfile.TemporaryDirectory(prefix="ephe-publish-") as tmp:
        scratch = Path(tmp)
        try:
            commit = _build_in_flight(repo, base, edits, staged, message, scratch, real_objects)
        except PublishError as exc:
            return PublishResult(
                ok=False, applied=[], rolled_back=list(staged), reason=f"aborted before publish: {exc}"
            )

        if dry_run:
            return PublishResult(
                ok=True,
                applied=paths,
                rolled_back=[],
                reason=f"dry run: {len(edits)} file(s) would publish to {target}",
            )

        try:
            _promote_objects(scratch / "objects", real_objects)
            _commit_ref(repo, ref, commit, base)
        except PublishError as exc:
            return PublishResult(
                ok=False, applied=[], rolled_back=list(staged), reason=f"aborted at ref update: {exc}"
            )

    return PublishResult(
        ok=True, applied=paths, rolled_back=[], reason=f"published {len(edits)} file(s) to {target}",
        oid=commit,
    )
