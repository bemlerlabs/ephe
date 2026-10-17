"""Ephe – artifact_workbench: birth place, provenance and the deadline (R4).

Two things that belong together live here: **where** an output file lies
and **how long** Ephe may keep it. The index for that is
``core.artifact_store`` (SQLite); this module holds the rules around it.

* **Birth place** (A1): ``~/.ephe/artifacts/<session>/<name>``. One single
  tool asks for it — ``core.engine_config.artifact_output_dir()`` — and
  ``core.chat.chat_with_tools`` binds the session through a contextvar instead of
  threading it through 40 tool signatures.
* **Identity** (A0): ``artifact_target(id)`` is the one validated path to the
  bytes of a card. Before this eleven places picked a path themselves.
* **Deadline** (owner rule 2026-10-06): ``RETENTION_DAYS`` days after the
  birth Ephe asks. **Expiry is a question, not a delete operation** — there is
  no branch that takes anything away without the answer, and ``keep`` stops the
  clock for a card permanently.

The imports in ``core.artifact_store`` are deliberately late (inside the
functions): the index is the user of these rules, not their source.
"""
from __future__ import annotations

import contextvars
import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKBENCH_DIRNAME = "artifacts"
RETENTION_DAYS = 30
# Hashing sits in the chat stream — a large file must not hold up the answer.
# The same ceiling as for delivery (server.routes.files).
MAX_HASH_BYTES = 50 * 1024 * 1024


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def now_iso() -> str:
    return iso(datetime.now(timezone.utc))


def workbench_dir() -> Path:
    from core.engine_config import config_root

    return config_root() / WORKBENCH_DIRNAME


# The birth place groups by session, and only the run that
# calls the tools knows the session (core.chat.chat_with_tools sets it).
_artifact_session: contextvars.ContextVar[str] = contextvars.ContextVar(
    "ephe_artifact_session", default=""
)


def set_artifact_session(session_id: str) -> None:
    _artifact_session.set(str(session_id or "").strip())


# Same pattern for the turn: set by chat_with_tools, read by the audit
# (core.audit_log) and by the artifact registration. One chain, one carrier.
_artifact_turn: contextvars.ContextVar[str] = contextvars.ContextVar("ephe_artifact_turn", default="")


def set_artifact_turn(turn_id: str) -> None:
    _artifact_turn.set(str(turn_id or "").strip())


def artifact_turn() -> str:
    return _artifact_turn.get()


def artifact_session_dir(session_id: str | None = None) -> Path:
    """~/.ephe/artifacts/<session> — the birth place of an output tool."""
    sid = (session_id if session_id is not None else _artifact_session.get()) or "ohne-session"
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sid)[:64]
    return workbench_dir() / safe


def in_workbench(path: str | Path) -> bool:
    """Is the only copy at Ephe's? Only then may the deadline concern it
    at all — a file in ~/Downloads belongs to the user, not to the workbench."""
    wb = workbench_dir().resolve()
    try:
        Path(path).expanduser().resolve().relative_to(wb)
    except (OSError, ValueError):
        return False
    return True


def content_hash(path: str | Path) -> str:
    """sha256 over the bytes — the basis for "is my adopted copy
    still current?". Files that are too large stay unhashed."""
    p = Path(path)
    try:
        if not p.is_file() or p.stat().st_size > MAX_HASH_BYTES:
            return ""
        digest = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return ""
    return f"sha256:{digest.hexdigest()}"


def _target_of(art: dict) -> Path | None:
    try:
        from core.tools.base import _get_allowed_roots

        p = Path(art["path"]).expanduser().resolve()
        for root in _get_allowed_roots():
            try:
                p.relative_to(Path(root).resolve())
            except ValueError:
                continue
            return p if p.is_file() else None
    except Exception:
        return None
    return None


def artifact_target(artifact_id: str) -> Path | None:
    """The validated path to the bytes of an artifact **id**.

    One target instead of eleven ladders: every surface that picked a path for
    itself (Downloads, Documents, workspace, output_dir …) could end up
    hitting a different file. No route goes through the id, and this one
    checks the allowed roots (core.tools.base) and the existence.
    """
    from core import artifact_store

    art = artifact_store.get_artifact(artifact_id)
    return _target_of(art) if art else None


def mark_viewed(artifact_id: str) -> None:
    """Counts only one call that delivers bytes — not every <img> load."""
    from core import artifact_store

    artifact_store._write(
        "UPDATE artifacts SET viewed_at = ? WHERE id = ?", (now_iso(), artifact_id)
    )


def set_adopted(artifact_id: str, adopted_path: str, digest: str = "") -> bool:
    """Records the adoption: the user's copy now lies there.

    From here the workbench copy is the redundant one — the deadline then asks about
    the workbench, never about the user's disk.
    """
    from core import artifact_store

    artifact_store._write(
        "UPDATE artifacts SET adopted_path = ?, adopted_hash = ? WHERE id = ?",
        (str(adopted_path), digest, artifact_id),
    )
    return True


def adopted_state(art: dict) -> str:
    """Is the user's copy still the same as what the workbench holds?

    current · stale · missing · unknown. 'unknown' means Ephe cannot
    compare the bytes (no hash basis, file unreadable) — the
    surface then says exactly that, not "current".
    """
    dest = art.get("adopted_path") or ""
    if not dest:
        return "none"
    target = Path(dest).expanduser()
    if not target.is_file():
        return "missing"
    source = _target_of(art)
    if source is None or not art.get("content_hash"):
        return "unknown"
    mine = content_hash(source)
    if not mine:
        return "unknown"
    return "current" if art.get("adopted_hash") == mine and content_hash(target) == mine else "stale"


def expiry_due(limit: int = 200) -> list[dict]:
    """What the deadline has reached and that is **not yet answered**.

    Excludes what is pinned or was answered with "keep".
    """
    from core import artifact_store

    return [
        artifact_store._row_to_dict(r)
        for r in artifact_store._read(
            f"SELECT {artifact_store._COLS} FROM artifacts "
            "WHERE expires_at IS NOT NULL AND expires_at <= ? AND keep = 0 AND favorite = 0 "
            "ORDER BY expires_at ASC LIMIT ?",
            (now_iso(), max(1, min(int(limit), 500))),
        )
    ]


def answer_expiry(ids: list[str], action: str) -> dict:
    """The answer to the deadline question — the only path that deletes.

    ``keep``: detach the card, never ask again. ``delete``: the row and, if the
    file lies in an allowed root, the file too. Without an answer this
    deadline deletes nothing; there is no delete branch in the background.
    """
    from core import artifact_store

    wanted = [str(i).strip() for i in ids if str(i).strip()]
    if action not in ("keep", "delete"):
        raise ValueError("action must be 'keep' or 'delete'")
    kept: list[str] = []
    deleted: list[str] = []
    skipped: list[str] = []
    for art_id in wanted:
        art = artifact_store.get_artifact(art_id)
        if not art or not art.get("expires_at"):
            skipped.append(art_id)  # never scheduled → never part of this question
            continue
        if action == "keep":
            artifact_store._write(
                "UPDATE artifacts SET keep = 1, expires_at = NULL, expiry_answered_at = ? WHERE id = ?",
                (now_iso(), art_id),
            )
            kept.append(art_id)
        elif artifact_store.delete_artifact(art_id, delete_file=True):
            deleted.append(art_id)
        else:
            skipped.append(art_id)
    return {"kept": kept, "deleted": deleted, "skipped": skipped}


def schedule_for(path: str | Path, born_at: datetime) -> str | None:
    """The fall date of a newly born file — or none.

    Only what lies in the workbench gets a deadline. ``expires_at`` is NULL
    for everything that lives with the user: expiring there would be an access,
    and an access reaches into what the user kept.
    """
    if not in_workbench(path):
        return None
    return iso(born_at + timedelta(days=RETENTION_DAYS))
