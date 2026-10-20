"""server/routes/sessions.py – the session bundle: export/import (W6).

The mirror (POST /api/sessions/sync, GET /api/sessions/restore) has lived in
`session_mirror.py` since R6/S1; its router is attached to this one so the paths
under /api/* stay the same (playbook rule 11: userspace must not break).

The store's holding count and its pruning live here too: GET /api/sessions
reports what the directory holds (the REST and PWA mirrors included, which no
list reached before), DELETE /api/sessions/{id} removes one, and POST
/api/sessions/prune applies the retention policy in `core.session_lifecycle`.
"""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from server.routes.session_mirror import _sessions_dir
from server.routes.session_mirror import router as mirror_router

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Sessions"])
router.include_router(mirror_router)

MAX_IMPORT_BYTES = 40 * 1024 * 1024   # total archive size
MAX_ENTRIES = 500                     # file count inside the archive
MAX_ENTRY_BYTES = 2 * 1024 * 1024     # a single file
_ALLOWED_EXTS = {".json"}


def _safe_name(name: str) -> str | None:
    """Normalize one archive entry; None on traversal/absolute/blank."""
    if not name:
        return None
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if ".." in parts:
        return None
    if len(parts) != 1:  # flat bundle folder, no subfolders needed
        return "/".join(parts) if all(p != ".." for p in parts) else None
    return parts[0]


def _read_zip(data: bytes) -> list[tuple[str, bytes]]:
    import io
    import zipfile

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        out: list[tuple[str, bytes]] = []
        for info in zf.infolist()[:MAX_ENTRIES]:
            name = _safe_name(info.filename)
            if name is None:
                raise ValueError(f"invalid archive entry: {info.filename!r}")
            if Path(name).suffix.lower() not in _ALLOWED_EXTS:
                continue
            raw = zf.read(info)
            out.append((name, raw[:MAX_ENTRY_BYTES]))
        return out


def _read_tgz(data: bytes) -> list[tuple[str, bytes]]:
    import io
    import tarfile

    out: list[tuple[str, bytes]] = []
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            name = _safe_name(member.name)
            if name is None:
                raise ValueError(f"invalid archive entry: {member.name!r}")
            if Path(name).suffix.lower() not in _ALLOWED_EXTS:
                continue
            handle = tar.extractfile(member)
            raw = handle.read(MAX_ENTRY_BYTES + 1)[:MAX_ENTRY_BYTES]
            out.append((name, raw))
        return out


@router.get("/sessions/export")
async def export_sessions(format: str = "zip") -> Response:
    """Bundle the session folder (registry.json + *.json) as zip or tar.gz."""
    import io
    import zipfile
    import tarfile

    sdir = _sessions_dir()
    if not sdir.exists():
        raise HTTPException(status_code=404, detail="session store is empty")
    entries = [(p.name, p.read_bytes()) for p in sorted(sdir.glob("*.json"))]
    fmt = (format or "zip").lower()
    buf = io.BytesIO()
    if fmt in ("tgz", "tar.gz", "gz"):
        with tarfile.open(fileobj=buf, mode="w:gz") as tar:
            for name, raw in entries:
                info = tarfile.TarInfo()
                info.name = name
                info.size = len(raw)
                info.mtime = int(time.time())
                tar.addfile(info, fileobj=io.BytesIO(raw))
        media = "application/gzip"
    else:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for name, raw in entries:
                zf.writestr(name, raw.decode("utf-8", "replace"))
        media = "application/zip"
    return Response(
        content=buf.getvalue(),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="sessions.{fmt}.json"'},
    )


@router.post("/sessions/import")
async def import_sessions(file: UploadFile = ...) -> dict:
    """Restore a previously exported bundle into the session folder."""
    data = await file.read()
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="archive too large")
    if data[:2] == b"\x1f\x8b":
        try:
            entries = _read_tgz(data)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid tar.gz: {exc}") from exc
    elif data[:2] == b"PK":
        try:
            entries = _read_zip(data)
        except (ValueError, OSError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid zip: {exc}") from exc
    else:
        raise HTTPException(status_code=400, detail="not a zip/tar.gz archive")

    sdir = _sessions_dir()
    sdir.mkdir(parents=True, exist_ok=True)
    restored = 0
    for name, raw in entries:
        if name == "registry.json":
            target = sdir / "registry.json"
        else:
            target = sdir / name
        tmp = target.with_suffix(".tmp")
        tmp.write_bytes(raw)
        tmp.replace(target)
        if name != "registry.json":
            restored += 1
    logger.info("session import: restored=%s", restored)
    return {"restored": restored}


class PruneRequest(BaseModel):
    """The operator's bound on the store, one cap per namespace.

    ``keep_registered`` is absent by default: the sessions a user created are
    theirs, and a prune that names no number for them leaves them alone.
    """

    keep_rest: int = Field(default=500, ge=0, le=1_000_000)
    keep_pwa: int = Field(default=200, ge=0, le=1_000_000)
    keep_registered: int | None = Field(default=None, ge=0, le=1_000_000)
    dry_run: bool = False


def _registered_entries() -> list[dict]:
    """The registry rows as a list, newest activity first, with list metadata.

    `message_count` reads the session file, which is the cost the store decision
    measures against its 0.2.0 trigger. `namespace` is `user` for a session a
    surface created, or the mirror prefix (`rest-`/`pwa-`) for a mirror row.
    """
    from core import multi_session as ms
    from core import session_lifecycle as life

    rows = [dict(e) for e in life.read_registry().get("sessions", []) if e.get("id")]
    for row in rows:
        sid = str(row.get("id"))
        info = ms.session_info(sid) or {}
        row["message_count"] = int(info.get("message_count") or 0)
        row["namespace"] = life.namespace_of(sid) or "user"
    rows.sort(key=lambda e: str(e.get("last_active") or ""), reverse=True)
    return rows


@router.get("/sessions")
async def list_sessions() -> dict:
    """What the store holds: totals per namespace, bytes, and the registered list."""
    from core import session_lifecycle as life

    return {**life.store_stats(), "sessions": _registered_entries()}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str) -> dict:
    """Remove one session the caller owns: its file, its index row, its registry row."""
    from core import session_lifecycle as life

    result = life.remove_sessions([session_id])
    if not result["deleted"]:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not in the store")
    logger.info("session delete: %s", session_id)
    return result


@router.post("/sessions/clear")
async def clear_sessions() -> dict:
    """Delete the whole session store: every namespace, zero kept.

    The one-action counterpart to the per-session delete. It runs the same store
    function as the prune row with a keep count of zero, so the registry rows go
    with the files and the report says what was freed.
    """
    from core import session_lifecycle as life

    result = life.prune_store({"rest-": 0, "pwa-": 0, "": 0}, dry_run=False)
    logger.info("session clear: deleted=%s freed=%s", len(result["deleted"]), result["bytes_freed"])
    return result


@router.post("/sessions/prune")
async def prune_sessions(request: PruneRequest) -> dict:
    """Apply the retention counts and report what went, how much that freed, what stays."""
    from core import session_lifecycle as life

    keep = {"rest-": request.keep_rest, "pwa-": request.keep_pwa}
    if request.keep_registered is not None:
        keep[""] = request.keep_registered
    result = life.prune_store(keep, dry_run=request.dry_run)
    logger.info(
        "session prune: deleted=%s freed=%s dry_run=%s",
        len(result["deleted"]), result["bytes_freed"], request.dry_run,
    )
    return result


# The server-authoritative store (Wave 5D). Static routes above are registered
# first, so `/sessions/export`, `/restore`, `/sync`, `/clear` and `/prune` never
# fall into the `{session_id}` route below.

_SID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_TRANSCRIPT_BYTES = 40 * 1024 * 1024
MAX_TRANSCRIPT_MESSAGES = 10_000


class SessionCreateRequest(BaseModel):
    title: str = Field(default="New Session", max_length=200)


class SessionRenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)


def _checked_sid(session_id: str) -> str:
    if not _SID_RE.fullmatch(session_id or ""):
        raise HTTPException(status_code=400, detail="invalid session id")
    return session_id


def _namespace_of(session_id: str) -> str:
    from core import session_lifecycle as life

    return life.namespace_of(session_id) or "user"


def _session_entry(session_id: str, meta: dict) -> dict:
    from core import multi_session as ms

    info = ms.session_info(session_id) or {}
    return {
        "id": session_id,
        "title": str(meta.get("title") or ""),
        "created_at": meta.get("created_at", ""),
        "last_active": meta.get("last_active", ""),
        "message_count": int(info.get("message_count") or 0),
        "namespace": _namespace_of(session_id),
    }


@router.post("/sessions")
async def create_session(request: SessionCreateRequest) -> dict:
    """Create one server-authoritative session; it is not active until activated."""
    from core import multi_session as ms

    title = request.title.strip() or "New Session"
    entry = ms.create_session(title)
    return _session_entry(str(entry["id"]), entry)


@router.get("/sessions/{session_id}")
async def read_session(session_id: str) -> dict:
    """The transcript of one registered session, validated and size-capped."""
    session_id = _checked_sid(session_id)
    from core import multi_session as ms

    meta = ms.get_session(session_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not in the store")
    path = ms.SESSIONS_DIR / f"{session_id}.json"
    try:
        if path.exists() and path.stat().st_size > MAX_TRANSCRIPT_BYTES:
            raise HTTPException(status_code=413, detail="session transcript too large")
    except OSError:
        pass
    messages = ms.load_messages(session_id)
    if len(messages) > MAX_TRANSCRIPT_MESSAGES:
        raise HTTPException(status_code=413, detail="session transcript has too many messages")
    return {**_session_entry(session_id, meta), "messages": messages}


@router.patch("/sessions/{session_id}")
async def rename_session(session_id: str, request: SessionRenameRequest) -> dict:
    """Rename one registered session; the id and the transcript stay."""
    session_id = _checked_sid(session_id)
    from core import multi_session as ms

    meta = ms.get_session(session_id)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not in the store")
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title must not be blank")
    ms.rename_session(session_id, title)
    return _session_entry(session_id, {**meta, "title": title})


@router.post("/sessions/{session_id}/activate")
async def activate_session(session_id: str) -> dict:
    """Make one registered session the machine's active cursor."""
    session_id = _checked_sid(session_id)
    from core import multi_session as ms

    if ms.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail=f"session {session_id!r} not in the store")
    ms.switch_to(session_id)
    return {"active_id": ms.get_active_id()}
