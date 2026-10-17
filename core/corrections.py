"""
◑ Ephe – error journal / Correction Memory
core/corrections.py

Persists user corrections.
Fed in as context so the same mistakes do not repeat.

Storage path: ~/.ephe/memory/corrections.md (default)
Format: Markdown, newest entry first.
"""
from __future__ import annotations

import contextlib
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DEFAULT_CORRECTIONS_PATH = Path.home() / ".ephe" / "memory" / "corrections.md"

ENTRY_SEPARATOR = "---"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_LINE_BREAKS = re.compile(r"[\r\n]+")


def _one_line(text: str) -> str:
    """Collapse line breaks so a value cannot forge or split a journal entry.

    The file format is line-based (one field per line, ``---`` between entries);
    a correction carrying its own ``\\n---\\n`` would otherwise write a second
    entry and drop the real one on the next read.
    """
    return _LINE_BREAKS.sub(" ", text).strip()


@contextlib.contextmanager
def _journal_lock(path: Path):
    """Exclusive lock around the journal's read-modify-write.

    add() rewrites the whole file (newest first) and the TUI process and the
    server process both append to it: without the lock the second writer's
    read-modify-write silently drops the first one's entry. Best effort —
    without fcntl (non-POSIX) or when the lock file cannot be opened the
    context degrades to the unlocked path, and the write still reports its
    own errors.
    """
    try:
        import fcntl
    except ImportError:
        yield
        return
    lock_path = path.with_suffix(path.suffix + ".lock")
    try:
        # Deliberately not a with-block: the fd must outlive the yield, the lock
        # is held across the journal's read-modify-write.
        handle = open(lock_path, "a+", encoding="utf-8")  # noqa: SIM115
    except OSError:
        yield
        return
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    except OSError:
        handle.close()
        yield  # locking is best effort: a write never fails because of it
        return
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


@dataclass
class Correction:
    """A single correction entry."""
    wrong: str
    correct: str
    timestamp: datetime


class CorrectionJournal:
    """
    Append-only error journal.

    Stores corrections as a Markdown file.
    Supports: add(), get_recent(), to_context_string()
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or DEFAULT_CORRECTIONS_PATH)

    # Public API

    def add(self, wrong: str, correct: str) -> None:
        """
        Add a new correction (newest first).

        Args:
            wrong:   What Ephe wrongly claimed
            correct: The correct information
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)

        now = datetime.now().strftime(DATE_FORMAT)
        entry = (
            f"## {now}\n"
            f"**Falsch behauptet:** {_one_line(wrong)}\n"
            f"**Korrekt:** {_one_line(correct)}\n"
            f"{ENTRY_SEPARATOR}\n"
        )

        with _journal_lock(self.path):
            # Newest entries on top (prepend), read-modify-write under the lock.
            # An undecodable remainder is dropped so the new correction still
            # lands — the old bytes were unreadable to every reader anyway.
            existing = ""
            if self.path.exists():
                try:
                    existing = self.path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    existing = ""
            # Write a sibling temp file and swap it in: an interrupted write
            # (crash, ENOSPC) then leaves the journal untouched instead of
            # truncating every entry it held. Same shape as the checkpoint store.
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(entry + existing, encoding="utf-8")
            os.replace(tmp, self.path)

    def get_recent(self, n: int) -> list[Correction]:
        """
        Return the n most recent corrections.

        Returns:
            List of Correction objects, newest first.
            Empty list when no journal exists.
        """
        if not self.path.exists():
            return []

        try:
            content = self.path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # Corrupt bytes read as empty — same rule as the checkpoint store:
            # an unparsable file never crashes the caller that builds a prompt.
            return []
        return self._parse(content)[:n]

    def to_context_string(self, max_items: int = 5) -> str:
        """
        Return the most recent corrections as system-prompt context.
        Inserted before every answer so the same mistake does not repeat.
        """
        corrections = self.get_recent(max_items)
        if not corrections:
            return ""

        lines = ["[Known past mistakes – avoid these:]"]
        for c in corrections:
            lines.append(f"- Previously wrong: '{c.wrong}' → Correct: '{c.correct}'")

        return "\n".join(lines)

    # Private

    def _parse(self, content: str) -> list[Correction]:
        """Parses Markdown content into Correction objects."""
        corrections: list[Correction] = []
        blocks = content.split(f"{ENTRY_SEPARATOR}\n")

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            # Anchored to a line start: a marker that appears mid-line (a
            # correction whose text carries it) must not be read as the field.
            wrong_match = re.search(r"^\*\*Falsch behauptet:\*\*\s*(.+)", block, re.MULTILINE)
            correct_match = re.search(r"^\*\*Korrekt:\*\*\s*(.+)", block, re.MULTILINE)
            date_match = re.search(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", block, re.MULTILINE)

            if not (wrong_match and correct_match):
                continue

            timestamp = datetime.now()
            if date_match:
                try:
                    timestamp = datetime.strptime(date_match.group(1), DATE_FORMAT)
                except ValueError:
                    pass

            corrections.append(Correction(
                wrong=wrong_match.group(1).strip(),
                correct=correct_match.group(1).strip(),
                timestamp=timestamp,
            ))

        return corrections
