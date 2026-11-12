"""Workspace evidence: the local half of a hybrid answer.

A file line is evidence in the same sense as a page passage. It is copied into
the answer verbatim, it carries its address as ``path:line``, and a checker can
find the same line again. That is the whole contract; nothing here summarises,
rewrites or ranks by meaning.

The search is bounded by wall-clock time, files visited and bytes read per file,
so a research call cannot turn into a full index pass. ``core.semindex`` owns
both the ignore rules and the list of file types, so this scan visits what the
index would visit and no build output.
"""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

#: The scan holds to these numbers; a workspace bigger than this answers with the
#: first matches it found rather than spending a turn on the walk.
MAX_FILES = 600
MAX_BYTES_PER_FILE = 512 * 1024
MAX_HITS = 6
MAX_CLAIM_CHARS = 400
WALL_CLOCK_SECONDS = 2.0

#: Code the index parses plus the text files a workspace states its rules in.
TEXT_SUFFIXES = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".rs",
    ".md", ".txt", ".json", ".toml", ".yaml", ".yml", ".css", ".html",
})

_STOP_TERMS = frozenset(
    "about after also been does from have into just like more most only other over "
    "same some such than that their them then there these they this those very was "
    "were what when where which while will with would your".split()
)


@dataclass(frozen=True)
class WorkspaceHit:
    """One copied line, addressed as ``path:line`` in the workspace."""

    path: str
    line: int
    text: str

    @property
    def reference(self) -> str:
        return f"{self.path}:{self.line}"

    def as_dict(self) -> dict:
        return {"path": self.path, "line": self.line, "reference": self.reference,
                "text": self.text}


def terms_of(query: str) -> list[str]:
    return [
        word
        for word in re.findall(r"[a-z0-9]{3,}", (query or "").casefold())
        if word not in _STOP_TERMS
    ]


def _is_path_scope(root: Path, scope: str) -> bool:
    """A scope is a path prefix when it names a path; a bare word is a symbol."""
    raw = scope.strip().strip("/")
    if not raw:
        return True
    if "/" in raw or raw.endswith((".py", ".ts", ".tsx", ".md", ".json", ".toml")):
        return True
    try:
        return (root / raw).is_dir()
    except OSError:
        return False


def _scope_matches(relative: str, scope: str) -> bool:
    raw = scope.strip().strip("/")
    if not raw:
        return True
    return relative == raw or relative.startswith(f"{raw}/")


def _candidate_files(root: Path, scope: str, max_files: int) -> list[Path]:
    """The same ignore rules the index reads, over code and prose alike."""
    from core.semindex.store import SKIP_DIRECTORIES, ignored_relative_path, read_ignore_patterns

    try:
        patterns = read_ignore_patterns(root)
    except OSError:
        return []
    path_scope = _is_path_scope(root, scope)
    kept: list[Path] = []
    for current, directories, names in os.walk(root):
        directories[:] = sorted(
            name for name in directories
            if name not in SKIP_DIRECTORIES and not name.startswith(".")
        )
        base = Path(current)
        try:
            relative_dir = base.relative_to(root).as_posix()
        except ValueError:
            continue
        if relative_dir != "." and ignored_relative_path(relative_dir, patterns):
            directories[:] = []
            continue
        for name in sorted(names):
            if Path(name).suffix.lower() not in TEXT_SUFFIXES:
                continue
            relative = name if relative_dir == "." else f"{relative_dir}/{name}"
            if ignored_relative_path(relative, patterns):
                continue
            if path_scope and not _scope_matches(relative, scope):
                continue
            kept.append(base / name)
            if len(kept) >= max_files:
                return kept
    return kept


def _read_lines(path: Path, cap: int) -> list[str]:
    try:
        if path.stat().st_size > cap:
            return []
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            body = handle.read(cap)
    except OSError:
        return []
    if "\x00" in body:
        return []
    return body.splitlines()


def search_workspace(
    query: str,
    *,
    root: str | Path | None = None,
    scope: str = "",
    limit: int = MAX_HITS,
    max_files: int = MAX_FILES,
    max_bytes: int = MAX_BYTES_PER_FILE,
    wall_clock: float = WALL_CLOCK_SECONDS,
    clock=time.monotonic,
) -> list[WorkspaceHit]:
    """Copied lines that carry the query's terms, ranked by how many it carries.

    ``scope`` is a workspace-relative path prefix; a bare word keeps only lines
    that carry it, which is how a symbol reaches its definition site.
    """
    wanted = terms_of(query)
    bare = scope.strip().strip("/")
    if not wanted and not bare:
        return []
    root_path = Path(root).expanduser() if root is not None else _workspace_root()
    try:
        root_path = root_path.resolve()
    except OSError:
        return []
    if not root_path.is_dir():
        return []
    token_filter = bool(bare) and not _is_path_scope(root_path, scope)
    if not wanted and not token_filter:
        return []

    deadline = clock() + max(0.1, float(wall_clock))
    files = _candidate_files(root_path, scope, max_files)
    wanted_set = set(wanted)
    scored: list[tuple[int, str, int, str]] = []
    seen: set[str] = set()
    for path in files:
        if clock() > deadline:
            break
        try:
            relative = path.resolve().relative_to(root_path).as_posix()
        except (ValueError, OSError):
            continue
        for number, text in enumerate(_read_lines(path, max_bytes), 1):
            line = text.strip()
            if not line or len(line) > MAX_CLAIM_CHARS:
                continue
            folded = line.casefold()
            if token_filter and bare.casefold() not in folded:
                continue
            score = sum(1 for term in wanted_set if term in folded)
            if score == 0:
                continue
            key = f"{relative}\n{line.casefold()}"
            if key in seen:
                continue
            seen.add(key)
            scored.append((score, relative, number, line))
    scored.sort(key=lambda item: (-item[0], item[1], item[2]))
    hits: list[WorkspaceHit] = []
    per_file: dict[str, int] = {}
    for _score, relative, number, line in scored:
        if per_file.get(relative, 0) >= 2:
            continue
        per_file[relative] = per_file.get(relative, 0) + 1
        hits.append(WorkspaceHit(path=relative, line=number, text=line))
        if len(hits) >= limit:
            break
    return hits


def _workspace_root() -> Path:
    from core.workspace_rules import resolve_workspace_dir

    return Path(resolve_workspace_dir())
