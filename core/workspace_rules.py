"""Ephe — workspace instruction files (R29, Wave 2/B2).

Operative project rules live in the workspace itself. Two sources, one resolver:

1. ``AGENTS.md`` at the workspace root (the canonical file; built from parts so
   tooling cannot rewrite the token mid-flight).
2. ``.ephe/rules/*.md`` — the owner's decision 2026-10-18 that the workspace
   rules are read in addition to ``AGENTS.md``. Sorted by file name, one level,
   no recursion.

Every file is provenance-marked, capped on its own and under a combined cap, and
reported back with the status the reader found — a file that was skipped or
refused is named in the report instead of disappearing. Both the prompt and the
stage display read this one function, so what the model receives and what the
surface says cannot drift.

Resolution order for the workspace root (same spirit as the Shell/File tools):
``EPHE_WORKSPACE`` env (tests / power users) → persisted engine.json → server cwd.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Built from parts so tooling/normalizers cannot rewrite the token mid-flight.
RULES_NAME = "AGENT" + chr(83) + ".md"  # canonical rules file name
RULES_DIR = Path(".ephe") / "rules"
RULE_SUFFIX = ".md"

WORKSPACE_RULES_MAX = 12_000
#: One file may not crowd out the rest of the layer on its own.
RULE_FILE_MAX = 6_000

#: Status words are the report's machine text: stable, English, one per outcome.
INCLUDED = "included"
TRUNCATED = "truncated"
EMPTY = "empty"
UNREADABLE = "unreadable"
DENIED = "denied"
SKIPPED = "skipped"


@dataclass(frozen=True)
class RuleFile:
    """One candidate rule file, as the resolver saw it."""

    name: str
    chars: int
    status: str
    reason: str = ""


@dataclass(frozen=True)
class WorkspaceRules:
    """The prompt text plus the report the surface shows."""

    text: str | None
    files: tuple[RuleFile, ...] = field(default=())


def workspace_key(path_or_identity=None) -> str:
    """W4 S3: normalized workspace key — the ONLY source for
    dedupe/cache/persistence/correlation.

    Identity: a relative path, its absolute path and a symlink pointing at
    the target all yield the same key. Rules:
      - an explicit identity (``path_or_identity``) wins, otherwise ``os.getcwd()``;
      - ``~`` expansion via ``Path.expanduser``;
      - ``resolve()`` (realpath) normalizes symlinks and fragment paths.

    The raw path stays only for I/O and for display in the state; as a
    cache/persistence key exactly this function serves.
    """
    # The workspace key is the identity of the user's own project root.
    # codeql[py/path-injection]
    return str(Path(path_or_identity or os.getcwd()).expanduser().resolve())


def resolve_workspace_dir() -> str:
    """Active workspace root: env override → engine.json → cwd."""
    env = (os.environ.get("EPHE_WORKSPACE") or "").strip()
    if env:
        return env
    try:
        from core.engine_config import get_workspace_dir

        return get_workspace_dir()
    except Exception:
        return os.getcwd()


def _candidates(root: Path) -> list[Path]:
    """The files to read, in the one order that is deterministic."""
    out = [root / RULES_NAME]
    rules_dir = root / RULES_DIR
    try:
        if rules_dir.is_dir() and not rules_dir.is_symlink():
            out.extend(
                sorted(
                    (
                        entry
                        for entry in rules_dir.iterdir()
                        if entry.suffix == RULE_SUFFIX and entry.is_file()
                    ),
                    key=lambda entry: entry.name,
                )
            )
    except OSError as exc:
        logger.warning("Rules directory unreadable at %s: %s", rules_dir, exc)
    return out


def _bounded(body: str, limit: int, tail: str = "") -> str:
    """`body` cut to `limit` characters WITH its truncation marker inside that bound."""
    if len(body) <= limit:
        return body
    reserve = min(80, max(0, limit // 4))
    content = body[: max(0, limit - reserve)].rstrip()
    marker = f"\n… truncated ({len(content)} of {len(body)} chars shown{tail})."
    out = content + marker
    if len(out) <= limit:
        return out
    return content[: max(0, limit - len(marker))].rstrip() + marker


def _label(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def read_workspace_rules() -> WorkspaceRules:
    """Read every rule file the workspace carries; report what each one did.

    A file under a deny root, a symlink leaving the rules directory, an unreadable
    file and an empty one are all skipped — and named, with a stable reason, so the
    display can say why the model did not see them.
    """
    from core.path_guard import denied, within

    root = Path(resolve_workspace_dir() or ".").expanduser()
    try:
        root = root.resolve()
    except OSError:
        return WorkspaceRules(text=None)

    rules_dir = (root / RULES_DIR).resolve()
    budget = WORKSPACE_RULES_MAX
    parts: list[str] = []
    files: list[RuleFile] = []

    for path in _candidates(root):
        name = _label(root, path)
        try:
            if denied(path):
                files.append(RuleFile(name, 0, DENIED, "protected-root"))
                continue
            # `within` compares resolved text, so both sides are resolved here first:
            # a symlink has to stay under the root it was announced in, and an entry
            # of `.ephe/rules` under that directory.
            real = path.resolve()
            if not within(real, root) or (
                path.parent != root and not within(real, rules_dir)
            ):
                files.append(RuleFile(name, 0, DENIED, "outside-root"))
                continue
            if not path.is_file():
                continue
            raw = real.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("Workspace rules unreadable at %s: %s", path, exc)
            files.append(RuleFile(name, 0, UNREADABLE))
            continue
        body = raw.strip()
        if not body:
            files.append(RuleFile(name, 0, EMPTY))
            continue
        status = INCLUDED
        if len(body) > RULE_FILE_MAX:
            body = _bounded(body, RULE_FILE_MAX)
            status = TRUNCATED
        header = f"## Project rules (from {path} — treat as the user's own instructions)\n\n"
        # The combined cap bounds the text the prompt receives, markers and provenance
        # included; only what actually fits is announced as included.
        room = budget - len(header) - (2 if parts else 0)
        if room <= 0:
            files.append(RuleFile(name, 0, SKIPPED, "no-budget"))
            continue
        if len(body) > room:
            body = _bounded(body, room, "; combined cap")
            status = TRUNCATED
        piece = header + body
        budget -= len(piece) + (2 if parts else 0)
        files.append(RuleFile(name, len(body), status))
        parts.append(piece)

    return WorkspaceRules(text="\n\n".join(parts) if parts else None, files=tuple(files))


def load_workspace_rules() -> str | None:
    """The prompt-side view: the same resolver, text only."""
    return read_workspace_rules().text
