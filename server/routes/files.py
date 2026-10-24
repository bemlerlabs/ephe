"""Ephe – file route: deliver generated artifacts (charts/PDFs/decks/SVGs) safely.

The P2-1 preview rail needs a way to show tool-output files in the browser.
Instead of a new StaticFiles mount per folder, ONE endpoint that reuses the
existing path whitelist guard from core.tools.base
(HOME/Desktop/Documents/Downloads/tmp). Not an arbitrary path reader.
"""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from core.path_guard import denied, secret_shaped
from core.tools.base import _get_allowed_roots, allowed_root_of

router = APIRouter()

# Hard ceiling: stops huge files (logs, DBs) from being passed through as an
# "artifact". Artifacts are charts/PDFs/decks — never gigabytes.
MAX_FILE_BYTES = 50 * 1024 * 1024


def _in_allowed_roots(resolved: Path) -> bool:
    for root in _get_allowed_roots():
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


def _relative_bases() -> list[Path]:
    """Bases used to resolve relative artifact paths.

    Finding 2026-10-01: the Deliverable-Detector reports filenames relative to the
    workspace/output dir ("document.md") — the preview otherwise got HTTP 400
    ("Absoluter Pfad erforderlich")  # language-gate: ignore (verbatim HTTP 400 detail from server/routes/fs.py:53)
    and the panel iframe rendered black.
    """
    bases: list[Path] = []
    try:
        from server.routes.fs import _workspace_or_none

        ws = _workspace_or_none()
        if ws:
            bases.append(Path(ws))
    except Exception:
        pass
    try:
        from core.engine_config import get_output_dir

        od = get_output_dir()
        if od:
            bases.append(Path(od))
    except Exception:
        pass
    # The engine's storage-location prompt offers the home folders
    # (Desktop/Documents/Downloads) — relative artifacts land there, not in the
    # workspace. Try home + those folders last; the whitelist guard stays behind
    # them.
    try:
        home = Path.home()
        bases.append(home)
        for sub in ("Desktop", "Documents", "Dokumente", "Downloads"):
            candidate = home / sub
            if candidate.is_dir():
                bases.append(candidate)
    except Exception:
        pass
    return bases


@router.get("/file", tags=["Files"])
async def get_file(
    path: str = Query(..., description="Absolute or workspace-relative artifact path"),
):
    """Serve a generated file from the allowed roots, for the preview."""
    expanded = os.path.expanduser(path)
    if os.path.isabs(expanded):
        real = os.path.realpath(expanded)
    else:
        # A relative name (the detector reports those) is resolved against the
        # workspace / output dir; the first base that holds a file wins.
        real = ""
        for base in _relative_bases():
            # Each candidate is checked against its own base first: that is the
            # containment, so a relative name cannot walk out of the base it is
            # resolved against (py/path-injection).
            base_real = os.path.realpath(str(base))
            candidate_probe = os.path.realpath(os.path.join(base_real, expanded)) + os.sep
            if not candidate_probe.startswith(base_real + os.sep):
                continue
            candidate_real = candidate_probe[: -len(os.sep)]
            if os.path.isfile(candidate_real):
                real = candidate_real
                break
        if not real:
            raise HTTPException(
                status_code=404,
                detail="file not found (relative path resolved against workspace/output dir)",
            )
    # The real path plus its separator, then the prefix check against the governing
    # root: that is what keeps the read inside the allowed roots, `..` and symlinks
    # included (py/path-injection). The whitelist guard below re-checks the same thing.
    probe = real + os.sep
    root = allowed_root_of(probe)
    if root is None:
        raise HTTPException(status_code=403, detail="path not in allowed roots")
    if not probe.startswith(root + os.sep):
        raise HTTPException(status_code=403, detail="path not in allowed roots")
    resolved = Path(probe)
    if denied(resolved) or secret_shaped(resolved):
        # The tool path asks a human for a credential-shaped name; this HTTP
        # route has no dialog, so it refuses the file instead.
        raise HTTPException(status_code=403, detail="path is protected")
    if not _in_allowed_roots(resolved):
        raise HTTPException(status_code=403, detail="path not in allowed roots")
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    if resolved.stat().st_size > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="File too large for preview")
    media_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
    # inline instead of attachment: FileResponse(filename=...) sets
    # Content-Disposition: attachment — the AgentPanel iframe then started a
    # download instead of rendering (a white preview). Downloads go through the
    # download attribute of the rail button (same-origin).
    return FileResponse(
        str(resolved),
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{resolved.name}"'},
    )
