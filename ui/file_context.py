"""Workspace files for the composer's ``@`` type-ahead and prompt attachment.

A token is ``@path`` or ``@path#L10-L20``. Only a token that resolves inside
the configured workspace and names an existing file is attached; the prompt
carries one provenance block per attachment and a size cap. Without a
configured workspace the composer says so instead of doing nothing.

``get_workspace_dir()`` falls back to the server's cwd, which is honest for the
shell tools but would make ``@`` claim files the user never chose. This module
reads the configured value itself so the fallback never becomes an attachment.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from core.engine_config import load_engine_config

MAX_FILE_CHARS = 32_000
MAX_TOTAL_CHARS = 96_000
MAX_SCAN_FILES = 800
CACHE_SECONDS = 5.0

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".next",
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "target",
}

_TOKEN = re.compile(r"(?<![\w@])@([^\s@]+)")
_RANGE = re.compile(r"#L?(\d+)(?:-L?(\d+))?$")
_TYPING = re.compile(r"(?<![\w@])@([\w./-]*)$")

_CACHE: dict[str, tuple[float, list[str]]] = {}


@dataclass
class Attachment:
    path: str
    start: int | None = None
    end: int | None = None
    content: str = ""
    truncated: bool = False

    def label(self) -> str:
        if self.start is None:
            return self.path
        if self.end is None or self.end == self.start:
            return f"{self.path}#L{self.start}"
        return f"{self.path}#L{self.start}-L{self.end}"


@dataclass
class ContextResult:
    prompt: str
    attached: list[Attachment] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str = ""


def workspace_root() -> tuple[Path | None, str]:
    """The configured workspace, or ``(None, reason)`` when none is set."""
    env = (os.environ.get("EPHE_WORKSPACE") or "").strip()
    configured = env
    if not configured:
        try:
            choice = load_engine_config()
        except Exception:
            choice = None
        configured = (choice.workspace_dir if choice else "") or ""
    if not configured:
        return (
            None,
            "No workspace configured — set one in Settings ▸ Engine (or EPHE_WORKSPACE).",
        )
    path = Path(configured).expanduser()
    if not path.is_dir():
        return None, f"Workspace not found: {path}"
    return path.resolve(), ""


def workspace_files(root: Path, limit: int = MAX_SCAN_FILES) -> list[str]:
    key = str(root)
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached is not None and now - cached[0] < CACHE_SECONDS:
        return cached[1][:limit]
    found: list[str] = []
    for base, dirs, files in os.walk(root):
        dirs[:] = sorted(
            d for d in dirs if d not in SKIP_DIRS and not d.startswith(".git")
        )
        for name in sorted(files):
            try:
                rel = (Path(base) / name).relative_to(root).as_posix()
            except ValueError:
                continue
            found.append(rel)
            if len(found) >= MAX_SCAN_FILES:
                break
        if len(found) >= MAX_SCAN_FILES:
            break
    _CACHE[key] = (now, found)
    return found[:limit]


def clear_cache() -> None:
    _CACHE.clear()


def match_files(root: Path, prefix: str, limit: int = 8) -> list[str]:
    needle = (prefix or "").lower()
    files = workspace_files(root)
    if not needle:
        return files[:limit]
    starts = [p for p in files if p.lower().startswith(needle)]
    names = [
        p for p in files if Path(p).name.lower().startswith(needle) and p not in starts
    ]
    contains = [
        p for p in files if needle in p.lower() and p not in starts and p not in names
    ]
    return (starts + names + contains)[:limit]


def current_token(text: str, cursor: tuple[int, int] | None) -> str | None:
    """The ``@`` token being typed before the cursor, or None."""
    try:
        row, column = cursor  # Textual's Location is (row, column)
    except (TypeError, ValueError):
        return None
    lines = text.split("\n")
    if row >= len(lines):
        return None
    line = lines[row]
    match = _TYPING.search(line[:column])
    return match.group(1) if match else None


def replace_token(
    text: str, cursor: tuple[int, int] | None, path: str
) -> tuple[str, tuple[int, int]]:
    """Replace the token before the cursor with ``@path`` and place the cursor after it."""
    try:
        row, column = cursor
    except (TypeError, ValueError):
        return text, (0, 0)
    lines = text.split("\n")
    if row >= len(lines):
        return text, (0, 0)
    line = lines[row]
    match = _TYPING.search(line[:column])
    if match is None:
        return text, (row, column)
    replaced = line[: match.start()] + "@" + path + line[column:]
    lines[row] = replaced
    return "\n".join(lines), (row, match.start() + len(path) + 1)


def _parse_range(token: str) -> tuple[str, int | None, int | None]:
    match = _RANGE.search(token)
    if match is None:
        return token, None, None
    path = token[: match.start()]
    start = int(match.group(1))
    end = int(match.group(2)) if match.group(2) else start
    if start < 1:
        start = 1
    if end < start:
        start, end = end, start
    return path, start, end


def _read_attachment(root: Path, token: str) -> tuple[Attachment | None, str]:
    path_text, start, end = _parse_range(token)
    if not path_text:
        return None, f"Skipped @{token}: no path."
    candidate = (root / path_text).expanduser()
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (ValueError, OSError):
        return None, f"Skipped @{token}: outside the workspace."
    if not resolved.is_file():
        return None, f"Skipped @{token}: no such file."
    try:
        body = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, f"Skipped @{token}: not readable as text."
    if start is not None:
        lines = body.splitlines()
        selected = lines[start - 1 : end]
        body = "\n".join(selected)
    attachment = Attachment(path=path_text, start=start, end=end, content=body)
    if len(body) > MAX_FILE_CHARS:
        attachment.content = body[:MAX_FILE_CHARS]
        attachment.truncated = True
    return attachment, ""


def build_context(text: str, root: Path | None = None) -> ContextResult:
    """Append one provenance block per readable ``@`` attachment."""
    if root is None:
        root, reason = workspace_root()
        if root is None:
            return ContextResult(prompt=text, error=reason)
    tokens = [match.group(1) for match in _TOKEN.finditer(text)]
    if not tokens:
        return ContextResult(prompt=text)

    result = ContextResult(prompt=text)
    remaining = MAX_TOTAL_CHARS
    blocks: list[str] = []
    for token in dict.fromkeys(tokens):
        attachment, note = _read_attachment(root, token)
        if attachment is None:
            result.notes.append(note)
            continue
        content = attachment.content
        if len(content) > remaining:
            content = content[:remaining]
            attachment.truncated = True
        remaining -= len(content)
        attachment.content = content
        truncated = "\n[... truncated]" if attachment.truncated else ""
        blocks.append(
            f"[Context: {attachment.label()}]\n{content}{truncated}\n[End context: {attachment.label()}]"
        )
        result.attached.append(attachment)
        if remaining <= 0:
            result.notes.append(
                f"Context cap reached ({MAX_TOTAL_CHARS} characters); later attachments were not read."
            )
            break
    if blocks:
        result.prompt = text + "\n\n" + "\n\n".join(blocks)
    return result
