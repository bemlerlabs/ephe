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
    """The registry rows as a list, newest activity first, for the holdings view."""
    from core import session_lifecycle as life

    rows = [dict(e) for e in life.read_registry().get("sessions", []) if e.get("id")]
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
