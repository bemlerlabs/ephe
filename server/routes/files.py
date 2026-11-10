"""Ephe – file route: deliver generated artifacts (charts/PDFs/decks/SVGs) safely.

The P2-1 preview rail needs a way to show tool-output files in the browser.
Instead of a new StaticFiles mount per folder, ONE endpoint that serves files
from the workspace and the output folder. Not an arbitrary path reader.

Security boundary (task #81, ported here by #120): this route reads a narrower
scope than the kernel tools. A tool that opens a user file goes through
`core.tools.base._get_allowed_roots` (HOME + subfolders + tmp); the artifact
route answers from the workspace plus the configured output folder, which is
what the surface shows next to the preview. A plugin call adds that bundle's
resolved data roots, the same list the kernel path and the confined worker use.
"""
from __future__ import annotations

import mimetypes
import os
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from core.path_guard import denied, secret_shaped

# The kernel's scope helpers are reached through their module, the way `server/routes/fs.py`
# reaches the root list. `from core.tools.base import allowed_root_of` copies the name into this
# namespace at import time, so a route mounted while a test has patched that attribute keeps the
# patch after the test is gone, and the guard judges paths against whichever answer was live when
# the module first imported. Asking the module each call is what lets a patch be honoured.
from core.tools import base as kernel
from server.refusals import Refused

router = APIRouter()

# Hard ceiling: stops huge files (logs, DBs) from being passed through as an
# "artifact". Artifacts are charts/PDFs/decks — never gigabytes.
MAX_FILE_BYTES = 50 * 1024 * 1024


def _get_artifact_roots() -> list[Path]:
    """The narrow whitelist for artifact delivery: workspace + output folder.

    Two answers to "may this path be read" are two scopes, and the client hitting
    `/api/file?path=` gets whichever one the route happened to call. The kernel
    path (`_get_allowed_roots`) keeps HOME + subfolders + tmp for the tools that
    read user files; this route keeps the scope the surface shows.

    In a plugin call (`PLUGIN_FILE_SCOPE`), the bundle's declared data roots are
    added through `resolved_data_roots` — the one resolution the kernel file scope
    and the confined worker share, so a bundle sees the same reach on both rails.
    """
    from core.tools.base import PLUGIN_FILE_SCOPE

    plugin = PLUGIN_FILE_SCOPE.get()
    workspace: Path | None = None
    try:
        from core.engine_config import get_workspace_dir, validate_workspace_dir

        chosen = validate_workspace_dir(get_workspace_dir())
        if chosen:
            workspace = Path(chosen).resolve()
    except (OSError, ValueError):
        workspace = None

    if plugin:
        if workspace is None:
            return []
        from core.capability_policy import resolved_data_roots

        return [workspace, *resolved_data_roots(plugin, workspace)]

    roots: list[Path] = []
    if workspace is not None:
        roots.append(workspace)
    try:
        from core.engine_config import get_output_dir

        output = get_output_dir()
        if output:
            out = Path(output).resolve()
            if out.is_dir() and out not in roots:
                roots.append(out)
    except Exception:
        pass
    return roots


def _in_artifact_roots(resolved: Path) -> bool:
    for root in _get_artifact_roots():
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
    # workspace. Resolving the name where the file actually is keeps the answer a
    # scope refusal; answering "not found" to a file that exists sends the reader
    # looking for it somewhere else.
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


def _guarded_file(path: str) -> Path:
    """The one answer for "may this path be read here", or the coded refusal that says why.

    The route that streams the bytes and the route that renders them cannot each carry
    their own copy of this chain — the second one would be a way to read a protected file
    past the first. Everything that decides containment lives here: the expansion, the
    relative resolve against the workspace and output bases, the real-path probe against
    the governing root, the credential-shaped name, the artifact-roots re-check, and the
    size ceiling.

    Task #120: the re-check is `_in_artifact_roots` (workspace + output folder), the scope
    the surface shows. `kernel.allowed_root_of` below stays: that is the resolution which stops a
    `..` part or a symlink leaving a real folder, and the narrow list then says which of
    those folders this route reads.
    """
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
            raise Refused("file_not_found")
    # The real path plus its separator, then the prefix check against the governing
    # kernel root: that is what keeps `..` and symlinks inside a folder the process
    # may look at (py/path-injection). The artifact list below is the narrower
    # decision of the two — which folder inside that reach this route reads.
    probe = real + os.sep
    root = kernel.allowed_root_of(probe)
    if root is None:
        raise Refused("file_path_not_allowed")
    if not probe.startswith(root + os.sep):
        raise Refused("file_path_not_allowed")
    resolved = Path(probe)
    if denied(resolved) or secret_shaped(resolved):
        # The tool path asks a human for a credential-shaped name; this HTTP
        # route has no dialog, so it refuses the file instead.
        raise Refused("file_path_protected")
    if not _in_artifact_roots(resolved):
        raise Refused("file_path_not_allowed")
    if not resolved.is_file():
        raise Refused("file_not_found")
    if resolved.stat().st_size > MAX_FILE_BYTES:
        raise Refused("file_too_large", max_mb=MAX_FILE_BYTES // (1024 * 1024))
    return resolved


@router.get("/file", tags=["Files"])
async def get_file(
    path: str = Query(..., description="Absolute or workspace-relative artifact path"),
):
    """Serve a generated file from the allowed roots, for the preview."""
    resolved = _guarded_file(path)
    media_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
    # inline instead of attachment: FileResponse(filename=...) sets
    # Content-Disposition: attachment — the AgentPanel iframe then started a
    # download instead of rendering (a white preview). Downloads go through the
    # download attribute of the rail button (same-origin).
    #
    # no-store: the file changes under the person's feet. Measured 2026-11-03 in the
    # desktop shell — a file deleted on disk and re-read through the column's reload kept
    # showing its old bytes, because an `ETag` plus `Last-Modified` without any
    # `Cache-Control` lets WKWebView answer from its own cache by heuristic freshness and
    # never reach the server, which had already turned to 404 for that path.
    return FileResponse(
        str(resolved),
        media_type=media_type,
        headers={
            "Content-Disposition": f'inline; filename="{resolved.name}"',
            "Cache-Control": "no-store",
        },
    )


@router.head("/file", tags=["Files"])
async def head_file(
    path: str = Query(..., description="Absolute or workspace-relative artifact path"),
):
    """Return file metadata (size, type) without the bytes — for progress bars and size checks.
    
    Uses the same guard as GET, so it cannot leak metadata about protected files.
    """
    from starlette.responses import Response
    
    resolved = _guarded_file(path)
    media_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
    return Response(
        headers={
            "Content-Length": str(resolved.stat().st_size),
            "Content-Type": media_type,
            "Content-Disposition": f'inline; filename="{resolved.name}"',
            "Accept-Ranges": "bytes",
        }
    )


@router.get("/file/preview", tags=["Files"])
async def get_file_preview(
    path: str = Query(..., description="Absolute or workspace-relative artifact path"),
):
    """Render the formats a browser cannot show, for a path rather than a card.

    The workbench has had this answer since R4/A5 through
    `GET /api/artifacts/{id}/preview`: a spreadsheet as rows, a document as text, a deck
    as slides. The workspace column lists the same files by path, and until now it could
    only name them — clicking a `.docx` handed the person a download. One guard, one
    renderer, two ways to point at a file.
    """
    from core.artifact_preview import preview_payload

    resolved = _guarded_file(path)
    return preview_payload(resolved, resolved.suffix.lstrip("."))
