"""Ephe – file_search, read_file, list_directory tools."""

from __future__ import annotations

import asyncio
import difflib
import os
import subprocess
import sys
from pathlib import Path

from core.tools.base import (
    FileNotAllowedError,
    MAX_FILE_CHARS,
    _is_path_allowed,
)


# Lazy-import pdfplumber
try:
    import pdfplumber as _pdfplumber
    _PDF_AVAILABLE = True
except ImportError:
    _pdfplumber = None
    _PDF_AVAILABLE = False


async def file_search(query: str, path: str | None = None) -> str:
    query = query.strip()
    if not query:
        raise ValueError("query must not be empty")

    if path:
        search_path = path
    else:
        from core.engine_config import get_workspace_dir

        search_path = get_workspace_dir()

    if not _is_path_allowed(Path(search_path)):
        return f"access to '{search_path}' not allowed (security whitelist)."

    def _fallback_search(root: Path, needle: str) -> str:
        matches: list[str] = []
        needle_lower = needle.lower()
        try:
            for current_root, dirs, files in os.walk(root):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for filename in files:
                    if needle_lower in filename.lower():
                        matches.append(str(Path(current_root) / filename))
                        if len(matches) >= 100:
                            matches.append("... [search truncated to 100 results]")
                            return "\n".join(matches)
        except (PermissionError, OSError):
            pass
        return "\n".join(matches)

    try:
        if sys.platform == "darwin":
            cmd = ["mdfind", "-name", query]
            if path:
                cmd += ["-onlyin", search_path]
        elif sys.platform.startswith("win"):
            cmd = ["where", "/R", search_path, f"*{query}*"]
        else:
            cmd = ["find", search_path, "-iname", f"*{query}*", "-maxdepth", "10"]

        result = await asyncio.to_thread(
            subprocess.run,
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = result.stdout.strip()
        if output:
            lines = output.splitlines()
            if len(lines) > 100:
                lines = lines[:100]
                lines.append("... [search truncated to 100 results]")
            output = "\n".join(lines)
        elif sys.platform == "darwin":
            output = await asyncio.to_thread(_fallback_search, Path(search_path), query)
        return output if output else f"No files found for '{query}'."

    except subprocess.TimeoutExpired:
        return f"Searching for '{query}' took too long."
    except FileNotFoundError:
        return f"file search not available on this system ({sys.platform})."


def _resolve_against_workspace(path: str) -> Path:
    """Expanduser; resolve relative paths against the active workspace (F).

    This lets the agent run ``read_file(path="src/app.py")`` in the user-set
    project folder. Absolute paths stay unchanged — except the
    documented short/long form of the project root (``~/ephe`` or
    ``$HOME/ephe``): that one is rewritten onto the active workspace so
    runner root and tool root see the same folder (N4-bench divergence,
    RC-4: the model prefixes task paths with the root short form from context).
    """
    from core.engine_config import get_workspace_dir

    p = Path(path).expanduser()
    if not p.is_absolute():
        return Path(get_workspace_dir()) / p
    try:
        rel = str(p.relative_to(Path.home() / "ephe"))
    except ValueError:
        # N7: the documented short form has two spellings — `~/ephe/x` and
        # `~/x` (the model prefixes the bare filename with the home short form).
        # Rule: a home-relative path without a directory separator is a
        # workspace filename, so the active workspace wins (RC-4
        # generalization: identical target location for write and read access).
        try:
            rel_home = str(p.relative_to(Path.home()))
        except ValueError:
            return p
        if rel_home in ("", "."):
            return Path(get_workspace_dir())
        # bare (no '/'): an existing absolute path wins (tests set
        # HOME to tmp_path); otherwise it is a workspace filename.
        if "/" not in rel_home:
            if p.exists():
                return p
            return Path(get_workspace_dir()) / rel_home
        # deeper home path (~/Documents/…): only redirect when the
        # workspace copy exists and the absolute one does not.
        if not p.exists():
            cand = Path(get_workspace_dir()) / rel_home
            if cand.exists():
                return cand
        return p
    if rel in ("", "."):
        return Path(get_workspace_dir())
    return Path(get_workspace_dir()) / rel


def _number_lines(content: str, offset: int | None, limit: int | None) -> str:
    """J1: cat -n-style numbering (1-based), optional offset/limit window."""
    lines = content.splitlines()
    if not lines:
        return ""
    start = offset if isinstance(offset, int) and offset > 0 else 1
    max_lines = limit if isinstance(limit, int) and limit > 0 else 2000
    end = min(start + max_lines - 1, len(lines))
    numbered = [f"{n}\t{lines[n - 1]}" for n in range(start, end + 1)]
    out = "\n".join(numbered)
    if end < len(lines):
        out += f"\n\n[Truncated: showing lines {start}–{end} of {len(lines)}]"
    return out


async def read_file(path: str, offset: int | None = None, limit: int | None = None) -> str:
    resolved = _resolve_against_workspace(path)

    if not _is_path_allowed(resolved):
        raise FileNotAllowedError(str(resolved))

    if not resolved.exists():
        raise FileNotFoundError(f"File not found: '{resolved}'")

    if resolved.suffix.lower() == ".pdf":
        return _number_lines(_extract_pdf_text(resolved), offset, limit)

    content = resolved.read_text(encoding="utf-8", errors="replace")

    if len(content) > MAX_FILE_CHARS:
        content = content[:MAX_FILE_CHARS]
        content += f"\n\n[File truncated: original had more than {MAX_FILE_CHARS} chars]"

    return _number_lines(content, offset, limit)


async def edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    """Replaces old_string exactly in the file and returns a diff.

    Conservative (release bar): path whitelist like read_file, refusal on a
    missing or ambiguous hit, no write change in those cases.
    replace_all=True lifts the ambiguity barrier (all hits).
    """
    resolved = _resolve_against_workspace(path)

    if not _is_path_allowed(resolved):
        raise FileNotAllowedError(str(resolved))

    if not resolved.exists():
        # Create path: a missing file has by definition 0 occurrences of
        # old_string — that is why 'new file with new_string' is the logical
        # fallback, independent of whether old_string is empty (N4 W1: with
        # a non-empty old_string the loop otherwise broke on FileNotFound).
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(new_string, encoding="utf-8")
        from core import coding_loop

        return f"created '{resolved}' ({len(new_string)} chars)." + coding_loop.annotation(resolved)

    if old_string == new_string:
        return "old_string and new_string are identical — nothing to do."

    content = resolved.read_text(encoding="utf-8", errors="replace")
    occurrences = content.count(old_string)

    if occurrences == 0:
        return f"old_string was not found in '{resolved}'. No change made."
    if occurrences > 1 and not replace_all:
        return (
            f"old_string is not unique ({occurrences} matches) in '{resolved}'. "
            "Provide more context so it is unique. No change made."
        )

    updated = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
    resolved.write_text(updated, encoding="utf-8")

    diff = "".join(
        difflib.unified_diff(
            content.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=str(resolved),
            tofile=str(resolved),
            n=2,
        )
    )
    from core import coding_loop

    return (diff if diff else "File changed (no text diff possible).") + coding_loop.annotation(resolved)


def _extract_pdf_text(path: Path) -> str:
    if not _PDF_AVAILABLE:
        return (
            "[PDF reading requires 'pdfplumber'. "
            "Install it with: pip install pdfplumber]"
        )

    try:
        pages: list[str] = []
        with _pdfplumber.open(str(path)) as pdf:
            total = len(pdf.pages)
            for i, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                if text.strip():
                    pages.append(f"--- Page {i}/{total} ---\n{text.strip()}")

        if not pages:
            return f"[PDF '{path.name}' contains no extractable text — may be scanned image]"

        full = "\n\n".join(pages)
        if len(full) > MAX_FILE_CHARS:
            full = full[:MAX_FILE_CHARS]
            full += f"\n\n[PDF truncated: original had more than {MAX_FILE_CHARS} chars]"
        return full

    except Exception as exc:
        return f"[Could not read PDF '{path.name}': {exc}]"


async def list_directory(path: str) -> list[str]:
    resolved = _resolve_against_workspace(path)

    if not _is_path_allowed(resolved):
        raise FileNotAllowedError(str(resolved))

    from core.tools.base import DirectoryNotFoundError

    if not resolved.exists():
        raise DirectoryNotFoundError(str(resolved))

    entries = [entry.name for entry in sorted(resolved.iterdir())]
    if len(entries) > 500:
        return entries[:500] + ["... [list truncated to 500 entries]"]
    return entries


# R22 Agentic Coding Loop: write_file (+ edit_file as canonical edit path)
# Both mutate → registry approval gate (diff preview in core/tools/approval).
# R35: apply_patch removed — edit_file (old/new) + write_file cover all
# edit cases; multi-hunk cases run as several edit_file calls in the loop.

MAX_WRITE_CHARS = 200_000


async def delete_file(path: str) -> str:
    """Deletes a file in the workspace (approval-gated). N4-W2: rename =
    create + delete, since the tool list has no own rename primitive."""
    resolved = _resolve_against_workspace(path)
    if not _is_path_allowed(resolved):
        raise FileNotAllowedError(str(resolved))
    if not resolved.exists():
        return f"deleted: no (already absent) '{resolved}'"
    if resolved.is_dir():
        raise IsADirectoryError(f"'{resolved}' is a directory.")
    resolved.unlink()
    return f"deleted '{resolved}'"


async def write_file(path: str, content: str) -> str:
    """Creates or overwrites a file in the workspace (approval-gated).

    Limits like edit_file: path whitelist, size cap. Return: confirmation +
    unified diff against the previous state (if the file existed).
    """
    import difflib

    resolved = _resolve_against_workspace(path)
    if not _is_path_allowed(resolved):
        raise FileNotAllowedError(str(resolved))
    content = str(content or "")
    if len(content) > MAX_WRITE_CHARS:
        raise ValueError(f"content too large: {len(content)} characters (limit {MAX_WRITE_CHARS})")
    if resolved.exists() and resolved.is_dir():
        raise IsADirectoryError(f"'{resolved}' is a directory.")

    existed = resolved.exists()
    previous = resolved.read_text(encoding="utf-8", errors="replace") if existed else ""
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")

    diff = "".join(
        difflib.unified_diff(
            previous.splitlines(keepends=True),
            content.splitlines(keepends=True),
            fromfile=str(resolved),
            tofile=str(resolved),
            n=2,
        )
    )
    from core import coding_loop

    diff += coding_loop.annotation(resolved)
    header = f"WRITE_FILE:{resolved}"
    detail = (
        f"({len(content)} characters written"
        + (f", overwritten — diff:\n{diff[:4000]}" if diff else ", created new)")
    )
    # W10: the marker line carries the path ALONE. The chat route's file-result table
    # reads line 1 as the path, and a path may contain spaces — appending the human
    # detail on the same line made every write_file result unparsable there, which is
    # why a written file never reached the artifact library. Detail goes on line 2.
    return f"{header}\n{detail}"


#: Cap for the approval preview — keeps the sandbox_confirm event small, so
#: a multi-kilobyte write does not flood the SSE stream.
_PREVIEW_DIFF_CAP = 6000


def approval_preview_diff(name: str, arguments: dict) -> str:
    """Upfront unified diff for the approval dialog (edit_file / write_file).

    Strict read-only: NEVER writes, and returns "" for non-edit tools, illegal
    paths or any read disturbance — the dialog then falls back to the
    pure argument preview (no behavior drift on the actual execution).
    """
    args = dict(arguments or {})
    try:
        if name == "edit_file":
            path = str(args.get("path", "") or "")
            old = str(args.get("old_string", "") or "")
            new = str(args.get("new_string", "") or "")
            if not old and not new:
                return ""
            diff = "".join(
                difflib.unified_diff(
                    old.splitlines(keepends=True),
                    new.splitlines(keepends=True),
                    fromfile=path,
                    tofile=path,
                    n=2,
                )
            )
            return diff[:_PREVIEW_DIFF_CAP]

        if name == "write_file":
            path = str(args.get("path", "") or "")
            content = str(args.get("content", "") or "")
            if not path:
                return ""
            resolved = _resolve_against_workspace(path)
            if not _is_path_allowed(resolved):
                return ""
            previous = resolved.read_text(encoding="utf-8", errors="replace") if resolved.exists() else ""
            diff = "".join(
                difflib.unified_diff(
                    previous.splitlines(keepends=True),
                    content.splitlines(keepends=True),
                    fromfile=str(resolved),
                    tofile=str(resolved),
                    n=2,
                )
            )
            return diff[:_PREVIEW_DIFF_CAP]
    except Exception:  # noqa: BLE001 — the preview may never break the stream
        return ""
    return ""
