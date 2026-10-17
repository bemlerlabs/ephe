"""server/routes/artifacts.py – R17 Artifact Hub (the persistent library).

Artifacts survive session deletes: a SQLite store (core/artifact_store),
registered from the chat stream (FILE marker → file_result). Read-only
library API + favorites/tags + version history + bulk export as a zip.

Since A0 (R4) ``GET /artifacts/{id}/file`` is the way to the bytes **of a
workbench card** — through the id, never through a path the surface itself
assembles. ``GET /file?path=`` (server/routes/files.py) stays the preview for
tool output that was never registered.

Retention deadline (owner rule 2026-10-06): ``GET /artifacts/expiry`` asks the
question, ``POST /artifacts/expiry/answer`` answers it. There is no background
branch that deletes anything without that answer.
"""
from __future__ import annotations

import io
import mimetypes
import os
import re
import shutil
import zipfile
from pathlib import Path
from urllib.parse import quote
from zipfile import ZipFile

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from core import artifact_preview
from core import audit_log
from core import artifact_store
from core import artifact_workbench as workbench
from core.engine_config import get_output_dir
from server.routes.files import MAX_FILE_BYTES

router = APIRouter(tags=["Artifacts"])

# Export ceiling (conservative): total size of the files in the zip + their count.
MAX_EXPORT_TOTAL = 200 * 1024 * 1024
MAX_EXPORT_FILES = 500


def _in_adoptable_root(dest: Path) -> bool:
    """Adoption target check: the same allowed roots as when reading
    (core.tools.base), but applied to the target's directory — the file itself
    often does not exist yet."""
    from core.tools.base import _get_allowed_roots

    try:
        parent = dest.parent.resolve()
    except OSError:
        return False
    for root in _get_allowed_roots():
        try:
            parent.relative_to(Path(root).resolve())
            return True
        except (OSError, ValueError):
            continue
    return False


def _disposition(kind: str, name: str) -> str:
    """Content-Disposition without header injection: the ASCII part is filtered,
    the real name arrives URI-encoded as filename*."""
    ascii_name = re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:120] or "artifact"
    return f'{kind}; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(name)}'


class ArtifactFavoriteRequest(BaseModel):
    favorite: bool


class ArtifactTagsRequest(BaseModel):
    tags: list[str] = []


class ArtifactDeleteRequest(BaseModel):
    delete_file: bool = False


def _art_or_404(artifact_id: str) -> dict:
    art = artifact_store.get_artifact(artifact_id)
    if not art:
        raise HTTPException(status_code=404, detail=f"artifact '{artifact_id}' not found.")
    return art


@router.get("/artifacts")
async def list_artifacts(
    q: str = "",
    kind: str = "",
    session_id: str = "",
    favorite: bool | None = None,
    turn_id: str = "",
    limit: int = 200,
) -> dict:
    """Library search across all sessions (name/topic, kind, favorites)."""
    rows = artifact_store.list_artifacts(
        q=q, kind=kind, session_id=session_id, favorite=favorite, turn_id=turn_id, limit=limit
    )
    return {"artifacts": rows, "total": len(rows)}


@router.get("/artifacts/export")
async def export_artifacts(ids: str = "", q: str = "", kind: str = ""):
    """Bulk export as a zip (ids comma-separated; empty = the whole hit list/q filter)."""
    if ids.strip():
        wanted = [i.strip() for i in ids.split(",") if i.strip()]
        arts = [a for a in (artifact_store.get_artifact(i) for i in wanted) if a]
    else:
        arts = artifact_store.list_artifacts(q=q, kind=kind, limit=MAX_EXPORT_FILES)
    if not arts:
        raise HTTPException(status_code=404, detail="no artifacts found for export.")

    total = 0
    names: set[str] = set()
    buf = io.BytesIO()
    with ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for art in arts:
            path = art["path"]
            try:
                data = io.FileIO(path, "r").read()
            except OSError:
                continue  # file deleted in the meantime → skip the entry
            total += len(data)
            if total > MAX_EXPORT_TOTAL or len(names) >= MAX_EXPORT_FILES:
                break
            name = art["name"]
            base, ext = name.rsplit(".", 1) if "." in name else (name, "")
            unique = name
            n = 2
            while unique in names:
                unique = f"{base}_{n}.{ext}" if ext else f"{base}_{n}"
                n += 1
            names.add(unique)
            zf.writestr(unique, data)
    if not names:
        raise HTTPException(status_code=404, detail="artifact files no longer exist on disk.")
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="ephe-artifacts.zip"'},
    )


@router.get("/artifacts/stats")
async def get_stats() -> dict:
    """Header of the storage: count, bytes and the next deadline — over all
    rows, not just the first page slice."""
    return artifact_store.stats()


@router.get("/artifacts/expiry")
async def get_expiry() -> dict:
    """The deadline question, before it gets asked.

    ``DELETE /artifacts/{id}`` is the deliberate exception to this cut: there the
    delete comes from a button someone pressed. This route only counts what lay
    in the workbench for 30 days — **it deletes nothing.** Deleting happens
    exclusively through ``expiry/answer``.
    """
    due = workbench.expiry_due()
    return {
        "due": due,
        "count": len(due),
        "bytes": sum(int(a.get("size") or 0) for a in due),
        "days": workbench.RETENTION_DAYS,
    }


class ExpiryAnswerRequest(BaseModel):
    ids: list[str] = []
    action: str  # keep | delete


@router.post("/artifacts/expiry/answer")
async def post_expiry_answer(request: ExpiryAnswerRequest) -> dict:
    """The answer to that question — for one card or several at once."""
    if request.action not in ("keep", "delete"):
        raise HTTPException(status_code=422, detail="action must be 'keep' or 'delete'.")
    try:
        return workbench.answer_expiry(request.ids, request.action)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class ArtifactAdoptRequest(BaseModel):
    #: Where the copy belongs. Empty = the adoption target remembered in
    #: settings (output_dir — since A1 no longer a birthplace, only this).
    destination: str = ""
    #: Only for the case where the user themselves confirmed that a *different*
    #: file may be overwritten. Without this field the rule stays: Ephe writes
    #: new files and updates its own last copy.
    overwrite: bool = False


#: The refusal when no destination was given and none is remembered. Named here because the
#: string is a promise about another surface: it used to point at the German bundle's label for
#: the setting, which addresses nothing for a reader on the English one.
NO_DESTINATION_HINT = (
    "no destination — pass one in the request, or set the adoption folder under "
    "output_dir in Settings."
)


@router.post("/artifacts/{artifact_id}/adopt")
async def adopt_artifact(artifact_id: str, request: ArtifactAdoptRequest) -> dict:
    """Adopt: the card's bytes land in a place the user named.

    The counterpart to the birthplace: the workbench keeps what it gave birth
    to, and the user gets a copy where they want it. The card remembers the
    target (``adopted_path``) and the hash of that moment — out of that comes
    the only sensible question, "is your copy still up to date?".

    Conservative by construction: absolute path, existing parent directory,
    inside the allowed roots, and overwriting only its own last copy (or after
    an explicit answer).
    """
    art = _art_or_404(artifact_id)
    source = workbench.artifact_target(artifact_id)
    if source is None:
        raise HTTPException(
            status_code=404,
            detail=f"artifact '{artifact_id}' has no readable file to adopt.",
        )
    # Empty = the remembered target. This is output_dir being stripped of power: the
    # field no longer says where Ephe writes, but where the user adopts to.
    raw = request.destination.strip() or (get_output_dir() or "")
    if not raw:
        raise HTTPException(status_code=422, detail=NO_DESTINATION_HINT)
    from core.tools.base import allowed_root_of

    expanded = os.path.expanduser(raw)
    if not os.path.isabs(expanded):
        raise HTTPException(status_code=422, detail="destination must be an absolute path.")
    # The real path plus its separator, then the prefix check against the governing
    # root: the containment is a property of the destination itself, so `..` parts
    # and symlinks included nothing lands outside (py/path-injection).
    dest_probe = os.path.realpath(expanded) + os.sep
    root = allowed_root_of(dest_probe)
    if root is None:
        raise HTTPException(status_code=403, detail="destination is not in an allowed root.")
    if not dest_probe.startswith(root + os.sep):
        raise HTTPException(status_code=403, detail="destination is not in an allowed root.")
    real = dest_probe[: -len(os.sep)]
    if os.path.isdir(real):
        # An existing folder: the artifact's own name is appended below it.
        dest_probe = real + os.sep + art["name"]
    dest = Path(dest_probe)
    if not _in_adoptable_root(dest):
        raise HTTPException(status_code=403, detail="destination is not in an allowed root.")
    if not dest.parent.is_dir():
        raise HTTPException(status_code=422, detail="destination directory does not exist.")
    already_ours = art.get("adopted_path") == str(dest)
    if dest.exists() and not (already_ours or request.overwrite):
        raise HTTPException(
            status_code=409,
            detail=f"'{dest.name}' exists and is not this artifact's own copy.",
        )
    try:
        shutil.copyfile(source, dest)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"adopt failed: {exc}") from exc
    digest = workbench.content_hash(dest)
    workbench.set_adopted(artifact_id, str(dest), digest)
    return {
        "id": artifact_id,
        "adopted_path": str(dest),
        "content_hash": workbench.content_hash(source),
        "adopted_hash": digest,
        "size": dest.stat().st_size,
    }


@router.get("/artifacts/{artifact_id}/provenance")
async def get_artifact_provenance(artifact_id: str) -> dict:
    """The chain read backwards: which tool calls belong to this card?

    `known: false` is the honest answer for everything born before A3 (or run
    without a turn) — the surface then shows the gap instead of selling it, via
    an empty list, as "no provenance".
    """
    art = _art_or_404(artifact_id)
    turn = art.get("turn_id") or ""
    base = {
        "turn_id": turn,
        "call_id": art.get("call_id") or "",
        "args_hash": art.get("args_hash") or "",
        "session_id": art.get("session_id") or "",
        "known": bool(turn),
    }
    if not turn:
        return {**base, "calls": []}
    calls = [
        {
            "ts": e.get("ts"),
            "kind": e.get("kind"),
            "tool": e.get("tool"),
            "args": e.get("args"),
            "decision": e.get("decision"),
            "status": e.get("status"),
            "duration_ms": e.get("duration_ms"),
        }
        for e in audit_log.tail(limit=200, turn_id=turn)
    ]
    return {**base, "calls": calls}


@router.get("/artifacts/{artifact_id}/preview")
async def get_artifact_preview(artifact_id: str) -> dict:
    """Content preview for the two kinds no browser renders (xlsx, docx).

    `mode: none` is information, not an error: the card then shows the file
    name, the size and its own gestures instead of an empty surface.
    """
    art = _art_or_404(artifact_id)
    target = workbench.artifact_target(artifact_id)
    if target is None:
        raise HTTPException(
            status_code=404,
            detail=f"artifact '{artifact_id}' has no readable file to preview.",
        )
    return artifact_preview.preview_payload(target, art.get("kind", ""))


@router.get("/artifacts/{artifact_id}/file")
async def get_artifact_file(artifact_id: str, download: bool = False):
    """The only way to a card's bytes: through its **id**.

    Before A0 every surface assembled the path itself (Downloads, Documents,
    Workspace, output_dir — eleven copies of the same ladder) and sometimes
    caught a different file that way. ``artifact_target`` checks the allowed
    roots and existence; ``download`` separates viewing (inline, counts as a
    view) from adopting (attachment, the user is asked for the target).
    """
    art = _art_or_404(artifact_id)
    target = workbench.artifact_target(artifact_id)
    if target is None:
        raise HTTPException(
            status_code=404,
            detail=f"artifact '{artifact_id}' has no readable file at '{art.get('path')}'.",
        )
    if target.stat().st_size > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="file too large to serve")
    if not download:
        workbench.mark_viewed(artifact_id)
    disposition = "attachment" if download else "inline"
    media_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
    return FileResponse(
        str(target),
        media_type=media_type,
        headers={"Content-Disposition": _disposition(disposition, art["name"])},
    )


@router.get("/artifacts/{artifact_id}")
async def get_artifact(artifact_id: str) -> dict:
    """One card in full: the row + the state of its adopted copy.

    The hash comparison happens here, not in the list — with 500 cards that
    would otherwise be a read of 500 files for a view nobody is looking at.
    """
    art = _art_or_404(artifact_id)
    return {**art, "adopted_state": workbench.adopted_state(art)}


@router.get("/artifacts/{artifact_id}/versions")
async def get_artifact_versions(artifact_id: str) -> dict:
    art = _art_or_404(artifact_id)
    return {"versions": artifact_store.get_versions(art["root_id"])}


@router.post("/artifacts/{artifact_id}/favorite")
async def set_artifact_favorite(artifact_id: str, request: ArtifactFavoriteRequest) -> dict:
    _art_or_404(artifact_id)
    artifact_store.set_favorite(artifact_id, request.favorite)
    return {"id": artifact_id, "favorite": request.favorite}


@router.put("/artifacts/{artifact_id}/tags")
async def set_artifact_tags(artifact_id: str, request: ArtifactTagsRequest) -> dict:
    _art_or_404(artifact_id)
    artifact_store.set_tags(artifact_id, request.tags)
    return {"id": artifact_id, "tags": sorted({t.strip() for t in request.tags if t.strip()})}


@router.delete("/artifacts/{artifact_id}")
async def delete_artifact(artifact_id: str, delete_file: bool = False) -> dict:
    """Removes the library entry; delete_file only deletes the file inside the
    allowed roots (otherwise it stays where it is — conservative)."""
    _art_or_404(artifact_id)
    file_removed = artifact_store.delete_artifact(artifact_id, delete_file=delete_file)
    return {"deleted": artifact_id, "file_removed": file_removed}
