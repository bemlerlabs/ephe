"""
◑ Ephe – Multi-Session Persistence (Phase 2 Item 7)

Extends the existing single-session persistence (core/session.py) to several
parallel sessions:

  ~/.ephe/sessions/
    default.json          (legacy – active session before the multi-session era)
    registry.json         (meta info: id, title, created_at, last_active)
    <8-hex>.json          (one session per file, 8-hex-character short code)

Design decisions:
- The store decision for the 0.1 line (JSON transcripts, SQLite as derived index, and
  the 0.2.0 triggers) is written down in `docs/SESSION_STORE_DECISION.md`.
- Backward compat: the existing `default.json` is migrated into the registry on
  the first call (no data loss, idempotent).
- Atomic writes: tmp + rename (POSIX-atomic), identical to core/session.py.
- Fail-safe: corrupt JSON → empty list + None, never a crash.
- Stable IDs: UUID4-hex short codes (8 characters) — low collision risk, readable.

Ephe – Bad Liebenzell, Schwarzwald
"""

from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.types import Message
from core.engine_config import config_subdir

# Paths

SESSIONS_DIR: Path = Path(
    os.environ.get("EPHE_SESSIONS_DIR")
    or str(config_subdir("sessions"))
)
REGISTRY_FILE: Path = SESSIONS_DIR / "registry.json"
LEGACY_FILE: Path = SESSIONS_DIR / "default.json"

#: A session id is a file stem under SESSIONS_DIR: letters, digits, dash and
#: underscore, no dot and no separator, so a caller cannot name a path outside
#: the store.
_SID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


# Internal helpers


def _new_id() -> str:
    """8-hex-character short code from secrets (low collision risk, readable)."""
    return secrets.token_hex(4)


def _session_file(sid: str) -> Path | None:
    """The file of one session id, None when the id would leave the store."""
    text = str(sid or "")
    if not _SID_RE.fullmatch(text):
        return None
    # The store file of the id, folded to its real spelling and checked to stay in the
    # store: the id charset already bars a separator, and this keeps the containment a
    # property of the path itself (py/path-injection).
    root = os.path.realpath(SESSIONS_DIR)
    target = os.path.realpath(os.path.join(root, f"{text}.json"))
    if not target.startswith(root + os.sep):
        return None
    return Path(target)


#: Fields a turn can carry beyond role/content. The PWA mirror and the chat
#: route write them; the TUI reads role/content and ignores the rest.
_MESSAGE_EXTRA_KEYS = (
    "id",
    "timestamp",
    "blocks",
    "thinkingPhases",
    "thinking",
    "durationMs",
    "activities",
    "artifacts",
    "error",
    "turnId",
    "tool_calls",
)


def _clean_message(item: object) -> dict[str, Any] | None:
    """One valid transcript row, extra turn fields preserved; None otherwise."""
    if not isinstance(item, dict):
        return None
    if item.get("role") not in ("user", "assistant", "system"):
        return None
    if not isinstance(item.get("content"), str):
        return None
    msg: dict[str, Any] = {"role": item["role"], "content": item["content"]}
    for key in _MESSAGE_EXTRA_KEYS:
        if key in item:
            msg[key] = item[key]
    return msg


def legacy_was_corrupt() -> bool:
    """True when default.json exists but cannot be parsed (it is left in place)."""
    if not LEGACY_FILE.exists():
        return False
    try:
        raw = LEGACY_FILE.read_text(encoding="utf-8")
        if not raw.strip():
            return False
        json.loads(raw)
        return False
    except (json.JSONDecodeError, OSError):
        return True


def _now_iso() -> str:
    """ISO-8601 with micro precision — for deterministic sorting."""
    return datetime.now(tz=timezone.utc).isoformat(timespec="microseconds")


def _atomic_write(path: Path, payload: str) -> None:
    """Atomic write via tmp + rename. Ignores OSError (best effort, local-first).

    P1-6: a POSIX lock (fcntl) around the tmp+rename step prevents lost updates
    when two processes write the same registry/session key. The lock is set
    non-blocking; without fcntl (e.g. Windows) tmp+rename remains as the minimum
    guarantee.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.parent / f".tmp_{os.getpid()}_{secrets.token_hex(4)}"
        tmp.write_text(payload, encoding="utf-8")
        try:
            import fcntl
            with open(tmp, "r+") as fh:
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                try:
                    pass
                finally:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except (ImportError, OSError):
            pass
        tmp.rename(path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except OSError:
        # Best-effort – don't crash the app over persistence
        pass


def _load_registry() -> dict[str, Any]:
    """Loads the registry; on corrupt/missing → empty structure. Never raises."""
    if not REGISTRY_FILE.exists():
        return {"active_id": None, "sessions": []}
    try:
        raw = REGISTRY_FILE.read_text(encoding="utf-8")
        if not raw.strip():
            return {"active_id": None, "sessions": []}
        data = json.loads(raw)
        if not isinstance(data, dict) or not isinstance(data.get("sessions"), list):
            return {"active_id": None, "sessions": []}
        return data
    except (json.JSONDecodeError, OSError, TypeError, KeyError):
        return {"active_id": None, "sessions": []}


def _save_registry(registry: dict[str, Any]) -> None:
    _atomic_write(REGISTRY_FILE, json.dumps(registry, ensure_ascii=False, indent=2))


def _legacy_migration_needed() -> bool:
    """True when default.json exists and has not been migrated yet."""
    if not LEGACY_FILE.exists():
        return False
    reg = _load_registry()
    # Migration is done once the "legacy" session sits in the registry
    for s in reg.get("sessions", []):
        if s.get("title") == "legacy" and s.get("migrated_from") == "default.json":
            return False
    return True


def _run_legacy_migration() -> None:
    """Brings default.json into the registry (idempotent)."""
    if not _legacy_migration_needed():
        return
    try:
        raw = LEGACY_FILE.read_text(encoding="utf-8")
        data = json.loads(raw) if raw.strip() else []
    except (json.JSONDecodeError, OSError):
        # Corrupt legacy – we do not migrate the file, we leave it where it is.
        return
    if not isinstance(data, list):
        return

    # Only take over valid messages (same validation as core.session)
    valid: list[dict[str, str]] = []
    for item in data:
        if (
            isinstance(item, dict)
            and item.get("role") in ("user", "assistant", "system")
            and isinstance(item.get("content"), str)
        ):
            valid.append({"role": item["role"], "content": item["content"]})

    sid = _new_id()
    now = _now_iso()

    # Write the session file
    _atomic_write(
        SESSIONS_DIR / f"{sid}.json",
        json.dumps(valid, ensure_ascii=False, indent=2),
    )

    # Update the registry
    reg = _load_registry()
    reg["sessions"].append(
        {
            "id": sid,
            "title": "legacy",
            "migrated_from": "default.json",
            "created_at": now,
            "last_active": now,
        }
    )
    if reg.get("active_id") is None:
        reg["active_id"] = sid
    _save_registry(reg)


# Public API


def create_session(title: str) -> dict[str, Any]:
    """Creates a new session and writes it into the registry."""
    sid = _new_id()
    now = _now_iso()
    # Empty session file
    _atomic_write(SESSIONS_DIR / f"{sid}.json", "[]")
    reg = _load_registry()
    entry = {
        "id": sid,
        "title": title,
        "created_at": now,
        "last_active": now,
    }
    reg["sessions"].append(entry)
    # A new session does not become active automatically – explicitly via switch_to()
    _save_registry(reg)
    return entry


def list_sessions() -> list[dict[str, Any]]:
    """Returns all sessions, sorted by last_active descending.

    Triggers the legacy migration if default.json exists.
    """
    if _legacy_migration_needed():
        _run_legacy_migration()
    reg = _load_registry()
    sessions = [s for s in reg.get("sessions", []) if isinstance(s, dict)]
    sessions.sort(key=lambda s: s.get("last_active", ""), reverse=True)
    return sessions


def get_session(sid: str) -> dict[str, Any] | None:
    """Returns the meta info of a single session, or None."""
    for s in _load_registry().get("sessions", []):
        if s.get("id") == sid:
            return s
    return None


def rename_session(sid: str, new_title: str) -> None:
    """Changes the title of a session. No-op when the ID is unknown."""
    reg = _load_registry()
    for s in reg.get("sessions", []):
        if s.get("id") == sid:
            s["title"] = new_title
            _save_registry(reg)
            return


def delete_session(sid: str) -> None:
    """Deletes a session (meta + message file).

    If the deleted session was active, active_id is set to None.
    """
    reg = _load_registry()
    reg["sessions"] = [s for s in reg.get("sessions", []) if s.get("id") != sid]
    if reg.get("active_id") == sid:
        reg["active_id"] = None
    _save_registry(reg)
    session_file = _session_file(sid)
    if session_file is not None:
        session_file.unlink(missing_ok=True)


def switch_to(sid: str) -> None:
    """Sets the active session. No-op when the ID is unknown."""
    reg = _load_registry()
    known = {s.get("id") for s in reg.get("sessions", [])}
    if sid not in known:
        return
    reg["active_id"] = sid
    # Update last_active
    for s in reg.get("sessions", []):
        if s.get("id") == sid:
            s["last_active"] = _now_iso()
            break
    _save_registry(reg)


def get_active_id() -> str | None:
    """ID of the active session, or None."""
    reg = _load_registry()
    active = reg.get("active_id")
    if not active:
        return None
    # Only return it when the session still exists
    if not any(s.get("id") == active for s in reg.get("sessions", [])):
        return None
    return active


# Message I/O


def save_messages(sid: str, messages: list[Message]) -> None:
    """Stores the messages of a session atomically on disk.

    The full turn row is kept: a PWA mirror or a chat turn carries ids, blocks,
    activities and tool cards, and dropping them here would make the one
    server-side transcript poorer than the mirror it replaces.
    """
    cleaned = [msg for msg in (_clean_message(item) for item in messages) if msg is not None]
    payload = json.dumps(cleaned, ensure_ascii=False, indent=2)
    session_file = _session_file(sid)
    if session_file is None:
        return
    _atomic_write(session_file, payload)
    # Update last_active
    reg = _load_registry()
    for s in reg.get("sessions", []):
        if s.get("id") == sid:
            s["last_active"] = _now_iso()
            break
    _save_registry(reg)


def load_messages(sid: str) -> list[Message]:
    """Loads the messages of a session. Return type is [] on error."""
    f = _session_file(sid)
    # The id must fullmatch [A-Za-z0-9_-]{1,64} and _session_file() resolves the file
    # through the store root.
    # codeql[py/path-injection]
    if f is None or not f.exists():
        return []
    try:
        # The same restricted id keeps the read inside the sessions store.
        # codeql[py/path-injection]
        raw = f.read_text(encoding="utf-8")
        if not raw.strip():
            return []
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        valid: list[Message] = []
        for item in data:
            msg = _clean_message(item)
            if msg is not None:
                valid.append(msg)  # type: ignore[arg-type]
        return valid
    except (json.JSONDecodeError, OSError, TypeError, KeyError):
        return []


def transcript_size(sid: str) -> int | None:
    """Bytes on disk for one validated session id; None when the id would leave the store."""
    path = _session_file(sid)
    if path is None:
        return None
    try:
        return path.stat().st_size
    except OSError:
        return None


def session_info(sid: str) -> dict[str, Any] | None:
    """Meta info + message count for a session. None when unknown."""
    meta = get_session(sid)
    if meta is None:
        return None
    msgs = load_messages(sid)
    return {
        "id": sid,
        "title": meta.get("title", ""),
        "message_count": len(msgs),
        "created_at": meta.get("created_at", ""),
        "updated_at": meta.get("last_active", ""),
        "is_active": meta.get("id") == get_active_id(),
    }


# Backward-compat shims (for the transition phase: the old core.session API)


def active_session_id() -> str:
    """ID of the active session; if there is none, creates a "default" session.

    Used by the TUI, so it can keep working without knowing the multi-session
    API.
    """
    sid = get_active_id()
    if sid is not None:
        return sid
    # Fallback: does default.json exist?
    if LEGACY_FILE.exists():
        # Take the legacy file over as a session
        list_sessions()  # triggers the migration
        return get_active_id() or create_session("default")["id"]
    return create_session("default")["id"]


def save_active_session(messages: list[Message]) -> None:
    """Stores messages under the active session (alias for save_messages)."""
    sid = active_session_id()
    save_messages(sid, messages)
