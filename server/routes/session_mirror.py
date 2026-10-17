"""server/routes/session_mirror.py – the mirror: sync (R30) + restore (R6/S1).

The PWA kept its sessions in the browser's IndexedDB only, so the server-side
FTS5 index could never see conversation content (documented search gap).
This route mirrors client sessions into the server session store under a
``pwa-`` namespace; the existing mtime-driven incremental indexer then picks
them up on the next search — no re-index pass, no new dependency.

Hardening: ids are validated against path traversal, batch and message
sizes are capped (413), deletion is mirrored so removed sessions leave both
the store and the FTS index. The mirror is local-only data on the user's own
machine; nothing leaves the device.

R6/S1: split out of sessions.py when the mirror half tore through the
400-line limit — the mirror (sync/restore) and the bundle (export/import) are
two ways into the same folder, not one module.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Sessions"])

MAX_SESSIONS_PER_CALL = 50
MAX_MESSAGES_PER_SESSION = 2000
MAX_MESSAGE_CHARS = 64_000
# R6/S1: tool results can carry file contents. The mirror is a recovery
# path for the surface, not an archive — over-fat messages lose
# their result but keep the card's name, arguments and status.
MAX_MESSAGE_JSON = 512_000
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class SyncMessage(BaseModel):
    role: str
    content: str
    timestamp: float | None = None
    # The client's message id (ChatMessage.id, a randomUUID). Optional: the
    # shipped client does not send it yet, so the projection also derives one.
    id: str | None = None
    # R44 (P2): beat chronology from the PWA store (index/sidecar capable);
    # null for legacy data without phases. The message JSON of the session file
    # carries the same fields — one added legacy path in load_messages makes them
    # available for context assembly without changing the index.
    blocks: list | None = None
    thinkingPhases: list | None = None
    # Finding 2026-10-01 (F-N): activities/artifacts/durationMs/thinking fell
    # out of the mirror roundtrip — after a reload without
    # IndexedDB (storage eviction, fresh browser) the replay bar and the
    # deliverable row were gone. Pydantic dropped the fields silently.
    thinking: dict | None = None
    durationMs: float | None = None
    activities: list | None = None
    artifacts: list | None = None
    error: str | None = None
    # R4 (A3): the turn id is the anchor of the chain chat → workbench → replay.
    # Missing from the mirror, the backlink only works in the live
    # session — the same gap F-N opened for activities.
    turnId: str | None = None
    # R6/S1: the tool cards themselves. `blocks` carries only the order
    # ({kind: tool, callId}) — without the payloads a restored
    # history shows empty references or nothing at all. The sender never sent them
    # this far; the mirror was a text transcript.
    tool_calls: list | None = None


class SyncSession(BaseModel):
    id: str
    title: str = ""
    # R6/S1: the birth of the session. Without it the restore set createdAt to
    # the mtime of the mirror file — and that slides to "now" on every sync.
    created_at: float | None = None
    mode: str | None = None
    parent_id: str | None = None
    messages: list[SyncMessage] = Field(default_factory=list)


class SessionSyncRequest(BaseModel):
    sessions: list[SyncSession] = Field(default_factory=list)
    deleted: list[str] = Field(default_factory=list)


def _geburt_ms(entry: dict) -> float | None:
    """Birth of the session in milliseconds, as the client keeps it.

    Two sources: the epoch number mirrored by the client (R6/S1) and the
    server stamp of first sight — an ISO string, not a number. Blindly
    float()ing either threw 500 on every session the server
    had created itself.
    """
    wert = entry.get("created_at")
    if isinstance(wert, (int, float)):
        return float(wert)
    roh = entry.get("createdAt")
    if isinstance(roh, (int, float)):
        return float(roh) * 1000
    if isinstance(roh, str):
        try:
            return datetime.fromisoformat(roh).timestamp() * 1000
        except ValueError:
            return None
    return None


def _schlank(msg: dict) -> dict:
    """Trim an over-fat message: result out, card stays."""
    if len(json.dumps(msg, ensure_ascii=False)) <= MAX_MESSAGE_JSON:
        return msg
    calls = msg.get("tool_calls")
    if isinstance(calls, list):
        msg = {
            **msg,
            "tool_calls": [
                {k: v for k, v in (c if isinstance(c, dict) else {}).items() if k != "result"}
                for c in calls
            ],
        }
    if len(json.dumps(msg, ensure_ascii=False)) > MAX_MESSAGE_JSON:
        msg = {k: v for k, v in msg.items() if k != "tool_calls"}
    return msg


def _message_id(session_id: str, index: int, timestamp: object) -> str:
    """The deterministic message id the PWA reader derives (`restore.ts::withMessageId`).

    JS ``String(number)`` drops the ``.0`` of an integral value while Python's float
    repr keeps it, so the integral case is formatted as an int and both sides build the
    same string — the reader keeps a present id, so the two must agree to be a no-op.
    """
    try:
        num = float(timestamp)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        num = 0.0
    stamp = str(int(num)) if num.is_integer() else repr(num)
    return f"restored:{session_id}:{index}:{stamp}"


def _sessions_dir():
    import core.multi_session as ms

    return ms.SESSIONS_DIR


def _load_registry():
    import core.multi_session as ms

    reg_file = ms.SESSIONS_DIR / "registry.json"
    try:
        return json.loads(reg_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"sessions": []}


def _save_registry(reg: dict) -> None:
    import core.multi_session as ms

    reg_file = ms.SESSIONS_DIR / "registry.json"
    tmp = reg_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(reg_file)


MAX_RESTORE_SESSIONS = 50
_MAX_RESTORE_FILE_BYTES = 40 * 1024 * 1024


@router.get("/sessions/restore")
async def restore_sessions(limit: int = MAX_RESTORE_SESSIONS) -> dict:
    """Serve mirrored ``pwa-`` sessions back to the PWA (restore-on-empty).

    The sync mirror exists for search, but it doubles as the only durable copy
    on the user's machine when the browser cache is gone (storage eviction,
    fresh browser, cleared site data). Returns the newest sessions first,
    ids stripped of the ``pwa-`` prefix so the client can re-sync them 1:1.
    """
    sdir = _sessions_dir()
    if not sdir.exists():
        return {"sessions": []}
    limit = max(1, min(limit, MAX_RESTORE_SESSIONS))
    try:
        files = [p for p in sdir.glob("pwa-*.json") if _ID_RE.match(p.stem[4:])]
    except OSError:
        return {"sessions": []}
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    registry = {e.get("id"): e for e in _load_registry().get("sessions", [])}
    out = []
    for path in files:
        if len(out) >= limit:
            break
        try:
            if path.stat().st_size > _MAX_RESTORE_FILE_BYTES:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, list):
            continue
        raw_id = path.stem[4:]
        entry = registry.get(f"pwa-{raw_id}", {})
        restored = {
            "id": raw_id,
            "title": str(entry.get("title") or ""),
            "updated_at": int(path.stat().st_mtime * 1000),
            **({"created_at": _geburt_ms(entry)} if _geburt_ms(entry) else {}),
            "messages": payload,
        }
        if entry.get("mode"):
            restored["mode"] = entry["mode"]
        if entry.get("parent_id"):
            restored["parent_id"] = entry["parent_id"]
        out.append(restored)
    return {"sessions": out}


@router.post("/sessions/sync")
async def sync_sessions(request: SessionSyncRequest) -> dict:
    """Mirror PWA sessions into the server store; mirror deletions too."""
    from core.session_search import drop_session

    if len(request.sessions) > MAX_SESSIONS_PER_CALL:
        raise HTTPException(status_code=413, detail=f"too many sessions per call (max {MAX_SESSIONS_PER_CALL})")
    for sess in request.sessions:
        if len(sess.messages) > MAX_MESSAGES_PER_SESSION:
            raise HTTPException(status_code=413, detail=f"too many messages in session (max {MAX_MESSAGES_PER_SESSION})")
        for msg in sess.messages:
            if len(msg.content) > MAX_MESSAGE_CHARS:
                raise HTTPException(status_code=413, detail=f"message too large (max {MAX_MESSAGE_CHARS} chars)")

    sdir = _sessions_dir()
    sdir.mkdir(parents=True, exist_ok=True)
    stored = 0
    dropped = 0

    for sess in request.sessions:
        if not _ID_RE.match(sess.id or ""):
            logger.warning("session sync refused invalid id: %r", sess.id)
            continue
        sid = f"pwa-{sess.id}"
        payload = [
            {
                "role": m.role,
                "content": m.content,
                "timestamp": m.timestamp or 0,
                **({"id": m.id} if m.id else {}),
                **({"blocks": m.blocks} if m.blocks else {}),
                **({"thinkingPhases": m.thinkingPhases} if m.thinkingPhases else {}),
                **({"thinking": m.thinking} if m.thinking else {}),
                **({"durationMs": m.durationMs} if m.durationMs is not None else {}),
                **({"activities": m.activities} if m.activities else {}),
                **({"artifacts": m.artifacts} if m.artifacts else {}),
                **({"error": m.error} if m.error else {}),
                **({"turnId": m.turnId} if m.turnId else {}),
                **({"tool_calls": m.tool_calls} if m.tool_calls else {}),
            }
            for m in sess.messages
            if m.role in ("user", "assistant", "system")
        ]
        # The projection carried no message id, so every mirrored row was id-less
        # (measured 2026-10-13: 298 of 298 rows across the pwa-*.json files) and a
        # consumer that keys rows by id — restore.ts's virtual list — saw `undefined`.
        # The reader falls back to `restored:{session}:{index}:{stamp}`; the mirror
        # writes that same deterministic id at the source, so the fallback becomes a
        # no-op and the id exists for every other reader of the file. A client that
        # already sends an id keeps it.
        for index, msg in enumerate(payload):
            if not msg.get("id"):
                msg["id"] = _message_id(sess.id, index, msg.get("timestamp"))
        payload = [_schlank(m) for m in payload]
        path = sdir / f"{sid}.json"
        tmp = sdir / f"{sid}.json.tmp"
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        # registry: title names the session for the FTS index/rows; mode is the
        # P4 composer mode so a fresh-browser restore (empty IndexedDB) replays the
        # exact mode instead of falling back to 'ask'. parent_id keeps the session
        # tree (branch/fork) intact across a reload — the mirror is the durable
        # per-device store, so without it the sidebar comes up flat.
        if sess.title or sess.mode or sess.parent_id or sess.created_at is not None:
            reg = _load_registry()
            entries = reg.setdefault("sessions", [])
            stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
            for entry in entries:
                if entry.get("id") == sid:
                    if sess.title:
                        entry["title"] = sess.title[:160]
                    if sess.mode:
                        entry["mode"] = sess.mode
                    if sess.parent_id:
                        entry["parent_id"] = sess.parent_id
                    if sess.created_at is not None:
                        entry["created_at"] = sess.created_at
                    entry["last_active"] = stamp
                    break
            else:
                entries.append({
                    "id": sid,
                    "title": (sess.title or "")[:160],
                    "createdAt": stamp,
                    "last_active": stamp,
                    "source": "pwa-sync",
                    **({"mode": sess.mode} if sess.mode else {}),
                    **({"parent_id": sess.parent_id} if sess.parent_id else {}),
                    **({"created_at": sess.created_at} if sess.created_at is not None else {}),
                })
            _save_registry(reg)
        stored += 1

    # R1 (ephemerality): the control decides whether the cell of a deleted
    # session dies at once or lives out its idle limit. The session itself
    # is gone in both cases, and a run that wrote into the output
    # path loses nothing there.
    from core import ephemeral_cell
    from core.settings_schema import deep_bool

    evaporate = deep_bool("ephemera.evaporate_on_delete")

    for raw_id in request.deleted:
        if not _ID_RE.match(raw_id or ""):
            continue
        sid = f"pwa-{raw_id}"
        # The store file of the id: the real path plus the prefix check keeps the delete
        # inside the store, whether or not _ID_RE already barred a separator
        # (py/path-injection).
        root = os.path.realpath(sdir)
        target = os.path.realpath(os.path.join(root, f"{sid}.json"))
        if not target.startswith(root + os.sep):
            continue
        path = Path(target)
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass
        if evaporate:
            ephemeral_cell.forget(raw_id)
        drop_session(sid)
        reg = _load_registry()
        reg["sessions"] = [e for e in reg.get("sessions", []) if e.get("id") != sid]
        _save_registry(reg)
        dropped += 1

    logger.info("session sync: stored=%s dropped=%s", stored, dropped)
    return {"stored_sessions": stored, "dropped_sessions": dropped}


# W6: portable session bundle (zip/tar.gz) — per-device folder parity
