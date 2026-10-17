"""Ephe – core/change_set: what changed, where, and why, with a digest of each diff.

Finding 2026-10-14: a publish in this product ships a set of file changes that nothing
describes. A run is measured (`core/run_evidence.py`) and an artifact is versioned with
its provenance (`core/artifact_store.py`), while the changes a publish hands over have no
object at all: the reason they exist lives in the session that made them and is gone by
the time a reviewer, or the next session on the same tree, looks at them.

What replaces it: ``build`` reads the workspace's git worktree, so every entry carries
the path, the operation git reports and ``diff_sha`` — a hash of that file's diff text.
Because the digest covers the diff and not the file, an edit made after the fact is
detectable while this store never holds the file's bytes: ``core.change_set_read.verify_current``
recomputes the digests and names the paths that moved.

Storage is one JSON file per change set under ``~/.ephe/changesets`` (``EPHE_CHANGESETS_DIR``
or ``EPHE_CONFIG_DIR`` override, module attribute monkeypatchable in tests), keyed by id the
way ``core/artifact_store.py`` keys its rows. Errors are raised, never swallowed.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

#: Operations a single path can carry. `build` maps git's status letters onto these three.
OPS = ("create", "modify", "delete")

#: The lifecycle: a draft is sent back for review, approved on a verdict, then published;
#: a `reject` verdict leaves it rejected, which is a branch rather than a station.
STATES = ("draft", "review", "approved", "published", "rejected")

#: Provenance fields a change set must carry. `why` is the one a session cannot drop.
PROVENANCE_FIELDS = ("session_id", "agent_id", "why")

DIGEST_PREFIX = "sha256:"
#: Diff output must not follow this machine's git config: a `diff.algorithm`, a prefix
#: form or an external filter from `~/.gitconfig` reshapes the text the digest covers.
DIFF_CONFIG = ("-c", "diff.algorithm=myers", "-c", "diff.noprefix=false",
               "-c", "diff.mnemonicprefix=false")
DIFF_FLAGS = ("diff", "--no-color", "--no-ext-diff", "--no-textconv", "--binary")

ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")


class ChangeSetError(ValueError):
    """A change set that cannot be built, stored or read as asked."""


def _default_dir() -> Path:
    return Path(os.environ.get("EPHE_CONFIG_DIR") or str(Path.home() / ".ephe")) / "changesets"


CHANGESETS_DIR: Path = Path(os.environ.get("EPHE_CHANGESETS_DIR") or _default_dir())


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def _new_id() -> str:
    """Sortable by time and unique without a registry — the shape `new_turn_id` uses."""
    stamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"cs-{stamp}-{secrets.token_hex(4)}"


class _AsMapping:
    """Field access and ``cs["summary"]`` read the same value.

    Callers were written against the mapping form of this interface, so both work.
    """

    def _fields(self) -> dict:
        return dataclasses.asdict(cast(Any, self))

    def __getitem__(self, key: str):
        try:
            return self._fields()[key]
        except KeyError as exc:
            raise KeyError(f"{type(self).__name__} has no field {key!r}") from exc

    def __iter__(self):
        return iter(self._fields())

    def get(self, key: str, default=None):
        return self._fields().get(key, default)

    def keys(self):
        return self._fields().keys()


@dataclass(frozen=True)
class FileChange(_AsMapping):
    """One path in a change set, and the digest of the diff that describes it."""

    path: str
    op: str
    diff_sha: str


@dataclass(frozen=True)
class Provenance(_AsMapping):
    """Who asked for the change and why — the part a session would otherwise take with it.

    ``why`` is required and non-empty: a change set that cannot say why it exists is only
    the diff nobody described, which this module replaces.
    """

    session_id: str = ""
    agent_id: str = ""
    why: str = ""


@dataclass(frozen=True)
class ChangeSet(_AsMapping):
    """A described set of changes: id, workspace, summary, files, provenance, state."""

    id: str
    workspace_id: str
    summary: str
    files: list[FileChange]
    provenance: Provenance
    state: str
    created_at: str
    #: When this set reached ``published``, and empty until it does. A landing carries a second
    #: time because ``created_at`` is when the diff was read, not when the bytes reached a
    #: branch, and only the second one tells a later set whether the branch moved under it.
    published_at: str = ""
    #: The commit a landing wrote, empty until a set publishes.
    published_oid: str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, raw: object) -> ChangeSet:
        """Rebuild one change set from stored JSON, refusing a malformed record."""
        if not isinstance(raw, dict):
            raise ChangeSetError("a change set must be a mapping")
        missing = [k for k in ("id", "workspace_id", "summary", "files", "provenance", "state")
                   if k not in raw]
        if missing:
            raise ChangeSetError(f"change set is missing {', '.join(missing)}")
        if raw["state"] not in STATES:
            raise ChangeSetError(f"unknown state: {raw['state']!r}")
        files = []
        for entry in raw["files"] or []:
            if not isinstance(entry, dict) or entry.get("op") not in OPS:
                raise ChangeSetError(f"file entry is not a change: {entry!r}")
            files.append(FileChange(path=str(entry.get("path", "")),
                                     op=entry["op"], diff_sha=str(entry.get("diff_sha", ""))))
        return cls(
            id=str(raw["id"]), workspace_id=str(raw["workspace_id"]),
            summary=str(raw["summary"]), files=files,
            provenance=provenance_of(raw["provenance"]), state=raw["state"],
            created_at=str(raw.get("created_at") or ""),
            published_at=str(raw.get("published_at") or ""),
            published_oid=str(raw.get("published_oid") or ""),
        )


def provenance_of(raw: dict | Provenance | None) -> Provenance:
    """Validate a provenance block: the three fields, nothing unknown, `why` non-empty."""
    if isinstance(raw, Provenance):
        raw = dataclasses.asdict(raw)
    if not isinstance(raw, dict):
        raise ChangeSetError("provenance must be a mapping")
    unknown = sorted(set(raw) - set(PROVENANCE_FIELDS))
    if unknown:
        raise ChangeSetError(f"unknown provenance field(s): {', '.join(unknown)}")
    values = {k: str(raw.get(k) or "").strip() for k in PROVENANCE_FIELDS}
    if not values["why"]:
        raise ChangeSetError("provenance needs a non-empty why")
    return Provenance(**values)


def diff_sha_of(text: str) -> str:
    """Digest of one file's diff text — the value a later edit to that file moves."""
    return DIGEST_PREFIX + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git(repo: str | Path, argv: list[str], timeout: float = 20.0) -> tuple[int, str]:
    """Returncode and stdout of one git call; (-1, "") when git is absent or hangs."""
    if not shutil.which("git"):
        return -1, ""
    try:
        done = subprocess.run(
            ["git", "-C", str(repo), *argv], capture_output=True, text=True, timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return -1, ""
    return done.returncode, done.stdout or ""


def worktree_root(workspace_id: str) -> str:
    """The git repo root that owns the workspace — the tree every path is read from."""
    # The workspace path is the user's own project root: there is no boundary this
    # store could jail a project folder to.
    # codeql[py/path-injection]
    path = Path(str(workspace_id or "")).expanduser()
    if not path.is_dir():
        raise ChangeSetError(f"workspace is not a directory: {workspace_id!r}")
    rc, out = _git(path, ["rev-parse", "--show-toplevel"])
    root = out.strip()
    if rc != 0 or not root:
        raise ChangeSetError(f"workspace is not a git worktree: {path}")
    return root


def _head(root: str) -> str | None:
    """HEAD of the tree, or None in a repo that has no commit yet."""
    rc, out = _git(root, ["rev-parse", "--verify", "HEAD"])
    return out.strip() if rc == 0 and out.strip() else None


def _scope_of(workspace_id: str, root: str) -> str:
    """The workspace as a pathspec below the repo root, so a nested workspace stays bounded."""
    # The workspace path is the user's own project root, as above.
    # codeql[py/path-injection]
    path = Path(str(workspace_id)).expanduser().resolve()
    root_path = Path(root).resolve()
    if path == root_path:
        return "."
    relative = os.path.relpath(path, root_path)
    return relative if not relative.startswith("..") else "."


def _op_of(xy: str) -> str:
    """create|modify|delete from git's two status letters.

    ``??`` (untracked) and ``A`` (added to the index) are both creates: the store speaks
    about the change, and for a path HEAD does not carry, that change is the file arriving.
    """
    x, y = xy[0], xy[1]
    if xy == "??" or x == "A" or y == "A":
        return "create"
    if x == "D" or y == "D":
        return "delete"
    return "modify"


def _status_entries(root: str, scope: str) -> list[tuple[str, str, str]]:
    """(op, path, status letters) per path git reports as changed inside the scope."""
    rc, out = _git(root, ["status", "--porcelain=v1", "-z", "--untracked-files=all", "--", scope])
    if rc != 0:
        raise ChangeSetError(f"git status failed in {root}")
    fields = out.split("\0")
    entries: list[tuple[str, str, str]] = []
    index = 0
    while index < len(fields):
        record = fields[index]
        index += 1
        if len(record) < 4:
            continue
        xy, path = record[:2], record[3:]
        if xy[0] in ("R", "C"):
            index += 1  # the source path of a rename or copy is its own field
        entries.append((_op_of(xy), path, xy))
    return entries


def _file_diff_text(repo: str, path: str, tracked: bool, head: str | None) -> str:
    """The diff text one path contributes, read against HEAD or an empty tree.

    An untracked path has no HEAD entry, so ``git diff HEAD`` stays silent about it and
    the diff is synthesized against ``/dev/null`` instead. Paths stay relative to the repo
    root, which keeps the digest free of this machine's directories, and ``--binary`` keeps
    an edit to a binary file visible where "Binary files differ" alone would not move.
    """
    if tracked:
        base = ["HEAD"] if head else ["--cached"]
        argv = [*DIFF_CONFIG, *DIFF_FLAGS, *base, "--", path]
    else:
        argv = [*DIFF_CONFIG, *DIFF_FLAGS, "--no-index", "--", os.devnull, path]
    rc, out = _git(repo, argv)
    if rc not in (0, 1):
        raise ChangeSetError(f"git diff failed for {path}")
    return out


def _workspace_key(workspace_id: str) -> str:
    """One key per workspace: the resolved path, so a symlink and its target agree."""
    text = str(workspace_id or "").strip()
    if not text:
        return ""
    try:
        from core.workspace_rules import workspace_key
    except Exception:
        # The workspace path is the user's own project root, as above.
        # codeql[py/path-injection]
        return str(Path(text).expanduser().resolve())
    return workspace_key(text)


def read_files(workspace_id: str) -> list[FileChange]:
    """The paths a tree has moved right now, each with a digest of its diff.

    The one reader of a worktree this store exposes: `build`, `amend` and
    ``core.change_set_read.verify_current`` all ask it, so neither can disagree with it.
    """
    root = worktree_root(workspace_id)
    head = _head(root)
    files = []
    for op, path, xy in _status_entries(root, _scope_of(workspace_id, root)):
        text = _file_diff_text(root, path, tracked=xy != "??", head=head)
        files.append(FileChange(path=path, op=op, diff_sha=diff_sha_of(text)))
    files.sort(key=lambda change: change.path)
    return files


def build(workspace_id: str, summary: str, provenance: dict | Provenance) -> ChangeSet:
    """Read the worktree's diff into a draft change set and store it.

    ``workspace_id`` is the workspace root (``core.workspace_rules.workspace_key``). A
    path unchanged against HEAD contributes nothing, so an empty ``files`` list means the
    tree holds no change. Every call mints a new id: the change set built after an edit is
    a new record, and the digest that moved is the proof it is.
    """
    if not _workspace_key(workspace_id):
        raise ChangeSetError("a change set needs a workspace_id")
    summary = str(summary or "").strip()
    if not summary:
        raise ChangeSetError("a change set needs a summary")
    why = provenance_of(provenance)
    files = read_files(workspace_id)
    change_set = ChangeSet(
        id=_new_id(), workspace_id=_workspace_key(workspace_id), summary=summary,
        files=files, provenance=why, state="draft", created_at=_now_iso(),
    )
    save(change_set)
    return change_set


def _path_of(change_set_id: str) -> Path:
    """The file for one id, refusing any id that would leave the store."""
    if not ID_PATTERN.fullmatch(str(change_set_id or "")):
        raise ChangeSetError(f"not a change-set id: {change_set_id!r}")
    # The id pattern carries no separator; the real path plus the prefix check keeps
    # the file in the store regardless (py/path-injection).
    root = os.path.realpath(CHANGESETS_DIR)
    target = os.path.realpath(os.path.join(root, f"{change_set_id}.json"))
    if not target.startswith(root + os.sep):
        raise ChangeSetError(f"change-set path leaves the store: {change_set_id!r}")
    return Path(target)


def save(change_set: ChangeSet) -> Path:
    """Write one change set over the file for its id, by tmp-then-rename."""
    path = _path_of(change_set.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".tmp-{os.getpid()}-{secrets.token_hex(4)}")
    tmp.write_text(json.dumps(change_set.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return path


def load(change_set_id: str) -> ChangeSet | None:
    """One change set by id, or None when it is absent, malformed or unreadable."""
    try:
        path = _path_of(change_set_id)
    except ChangeSetError:
        return None
    try:
        # The id fullmatches ID_PATTERN, which carries no path separator, and
        # _path_of() resolves the file through the store root.
        # codeql[py/path-injection]
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return None
    try:
        return ChangeSet.from_dict(raw)
    except ChangeSetError:
        return None


def set_state(change_set_id: str, state: str, published_oid: str = "") -> ChangeSet | None:
    """Move one change set to another state; None when the id is unknown.

    Landing is the one move that carries a time of its own: a record that reaches ``published``
    is stamped with when it did, and with the oid ``published_oid`` names, and keeps both
    through any later move, because the bytes went to the branch once.
    """
    if state not in STATES:
        raise ChangeSetError(f"unknown state: {state!r}")
    current = load(change_set_id)
    if current is None:
        return None
    landed = current.published_at or (_now_iso() if state == "published" else "")
    oid = published_oid if state == "published" else current.published_oid
    moved = dataclasses.replace(current, state=state, published_at=landed, published_oid=oid)
    save(moved)
    return moved
