"""
◑ Ephe – Session Persistence

JSON-based session persistence in ~/.ephe/sessions/default.json

Key design decisions:
- Atomic writes (tmp + rename) to prevent corruption on crash
- Never raises on load – returns [] on any error (fail-safe)
- save_session() is safe to call after every message

Ephe – Bad Liebenzell, Schwarzwald
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from core.types import Message

# Paths

SESSION_DIR: Path = Path.home() / ".ephe" / "sessions"
SESSION_FILE: Path = SESSION_DIR / "default.json"


# Public API


def load_last_session() -> list[Message]:
    """
    The transcript persisted in SESSION_FILE.

    Returns [] on any error (file not found, corrupt JSON, wrong format).
    Never raises. Fail-safe by design.
    """
    if not SESSION_FILE.exists():
        return []

    try:
        raw = SESSION_FILE.read_text(encoding="utf-8")
        if not raw.strip():
            return []

        data = json.loads(raw)

        if not isinstance(data, list):
            return []

        # Validate and filter messages
        valid: list[Message] = []
        for item in data:
            if (
                isinstance(item, dict)
                and item.get("role") in ("user", "assistant", "system")
                and isinstance(item.get("content"), str)
            ):
                valid.append(
                    Message(role=item["role"], content=item["content"])
                )
        return valid

    except (json.JSONDecodeError, OSError, TypeError, KeyError):
        return []


def save_session(messages: list[Message]) -> None:
    """
    Atomically save the session to disk.

    Uses write-to-tmp + rename() to prevent corruption on crash.
    Creates ~/.ephe/sessions/ if it doesn't exist.
    Silently ignores write errors (local-first, best-effort).
    """
    try:
        SESSION_DIR.mkdir(parents=True, exist_ok=True)

        tmp_path = SESSION_DIR / f".tmp_{os.getpid()}.json"
        payload = json.dumps(list(messages), ensure_ascii=False, indent=2)
        tmp_path.write_text(payload, encoding="utf-8")

        # Atomic rename – on POSIX this is guaranteed atomic
        tmp_path.rename(SESSION_FILE)

    except OSError:
        # Best-effort – don't crash the app over persistence
        pass


def delete_session() -> None:
    """
    Delete the current session file. Used by Ctrl+R reset.
    Safe to call even if file doesn't exist.
    """
    SESSION_FILE.unlink(missing_ok=True)


def session_info() -> tuple[int, str]:
    """
    Return (message_count, last_updated_str) for the welcome message.

    Returns (0, "") if no session exists or it's empty.
    """
    if not SESSION_FILE.exists():
        return 0, ""

    try:
        mtime = SESSION_FILE.stat().st_mtime
        last_modified = datetime.fromtimestamp(mtime, tz=timezone.utc)
        # Format relative to now
        now = datetime.now(tz=timezone.utc)
        delta = now - last_modified

        if delta.days == 0:
            hours = delta.seconds // 3600
            if hours == 0:
                time_str = "just now"
            elif hours == 1:
                time_str = "1 hour ago"
            else:
                time_str = f"{hours} hours ago"
        elif delta.days == 1:
            time_str = "yesterday"
        else:
            time_str = f"{delta.days} days ago"

        messages = load_last_session()
        return len(messages), time_str

    except OSError:
        return 0, ""


def was_session_corrupt() -> bool:
    """
    Returns True if a session file exists but is not parseable.
    Used to show a one-time corruption warning.
    """
    if not SESSION_FILE.exists():
        return False
    try:
        raw = SESSION_FILE.read_text(encoding="utf-8")
        if not raw.strip():
            return False
        json.loads(raw)
        return False
    except (json.JSONDecodeError, OSError):
        return True
