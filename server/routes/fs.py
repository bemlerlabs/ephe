"""server/routes/fs.py – GET /api/fs (file browser for AgentPanel + workspace dialog)

Read-only directory listing for the PWA (round 4):
  - file explorer in the AgentPanel (tree + click → /api/file preview)
  - workspace folder dialog (settings) instead of typing a path

Security (release bar, conservative):
  - READ only, never write; no file contents (those come via /api/file).
  - Path guard: allowed are (a) the default roots (HOME subfolders, tmp)
    including the user-set workspace, (b) the home directory ITSELF at
    depth 1 (so the folder dialog can start at ~ and see the root
    folders). No escape via symlinks (resolve()).
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from core.path_guard import denied
from core.tools.base import _get_allowed_roots, allowed_root_of

router = APIRouter(tags=["FS"])

_MAX_ENTRIES = 500


class MkdirRequest(BaseModel):
    parent: str
    name: str


def _in_allowed_roots(resolved: Path) -> bool:
    for root in _get_allowed_roots():
        try:
            resolved.relative_to(root.resolve())
            return True
        except ValueError:
            continue
    return False


@router.get("/fs", tags=["FS"])
async def list_fs(path: str = Query("", description="Verzeichnis; leer = Startpunkt (Home)")) -> dict:
    # Resolve once: a symlinked HOME (/tmp -> /private/tmp) otherwise fails the
    # equality against its own resolved form and 403s the default listing.
    home = Path.home().resolve()
    raw = (path or "").strip()
    if not raw:
        target = home
    else:
        expanded = os.path.expanduser(raw)
        if not os.path.isabs(expanded):
            raise HTTPException(status_code=400, detail="Absoluter Pfad erforderlich")
        if os.path.realpath(expanded) == os.path.realpath(home):
            target = home
        else:
            # The real path plus its separator, then the prefix check against the
            # governing root: that is the containment, so neither a `..` part nor a
            # symlink steps out (py/path-injection). The separator makes the root
            # itself count, and Path() folds it away again.
            probe = os.path.realpath(expanded) + os.sep
            root = allowed_root_of(probe)
            if root is None:
                raise HTTPException(status_code=403, detail="path not in allowed roots")
            if not probe.startswith(root + os.sep):
                raise HTTPException(status_code=403, detail="path not in allowed roots")
            target = Path(probe)

    is_dir_entry = target == home.resolve()
    if denied(target):
        raise HTTPException(status_code=403, detail="path is protected")
    if not is_dir_entry and not _in_allowed_roots(target):
        raise HTTPException(status_code=403, detail="path not in allowed roots")
    if not target.is_dir():
        raise HTTPException(status_code=404, detail="directory not found")

    entries: list[dict] = []
    try:
        children = sorted(target.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower()))
    except PermissionError:
        children = []

    hidden = {".", ".."}
    for child in children:
        if child.name in hidden or child.name.startswith("."):
            continue
        try:
            is_dir = child.is_dir()
        except OSError:
            continue
        entry: dict = {"name": child.name, "type": "dir" if is_dir else "file"}
        if not is_dir:
            try:
                entry["size"] = child.stat().st_size
            except OSError:
                entry["size"] = 0
        entries.append(entry)
        if len(entries) >= _MAX_ENTRIES:
            entries.append({"name": f"... [{_MAX_ENTRIES} entries truncated]", "type": "info"})
            break

    parent = str(target.parent) if target != home.resolve() and _in_allowed_roots(target.parent) else None
    workspace, workspace_set = _workspace_state()
    return {
        "path": str(target),
        "parent": parent,
        "home": str(home),
        "workspace": workspace,
        "workspace_set": workspace_set,
        "entries": entries,
    }


def _workspace_state() -> tuple[str | None, bool]:
    """(workspace, workspace_set) — the header's three-state machine.

    workspace_set=True  ⇒ the user picked a project (engine.json, deliberate
    SSOT — no second source in settings.json). Display: the project name.
    workspace_set=False ⇒ no project: neutral display ("Workspace") over the
    neutral default root. A server started from the source checkout never
    reports that checkout as the user's workspace.
    """
    try:
        from core.engine_config import load_engine_config

        choice = load_engine_config()
        if choice and choice.workspace_dir:
            return choice.workspace_dir, True
    except Exception:
        pass
    try:
        from core.engine_config import get_workspace_dir

        return get_workspace_dir(), False
    except Exception:
        return None, False


def _workspace_or_none() -> str | None:
    try:
        from core.engine_config import load_engine_config

        choice = load_engine_config()
        if choice and choice.workspace_dir:
            return choice.workspace_dir
    except Exception:
        pass
    # No configured workspace: the same neutral root get_workspace_dir() uses,
    # so /api/fs and /api/projects agree (R26).
    try:
        from core.engine_config import get_workspace_dir

        return get_workspace_dir()
    except Exception:
        return None


@router.post("/fs/mkdir", tags=["FS"])
async def create_dir(req: MkdirRequest) -> dict:
    """W19 F3: create one folder for the workspace dialog.

    Conservative (release bar): the parent must lie in the allowed roots, the
    name is ONE path segment (no separators, no leading dot, ≤ 80 characters).
    At most exactly this one folder is created — no nested creation, no file
    contents.
    """
    parent_raw = (req.parent or "").strip()
    if not parent_raw:
        raise HTTPException(status_code=422, detail="parent required")
    # The real path plus its separator, then the prefix check against the governing
    # root: that is the containment for the folder that gets created, `..` parts and
    # symlinks included (py/path-injection). The separator makes a root itself count.
    probe = os.path.realpath(os.path.expanduser(parent_raw)) + os.sep
    root = allowed_root_of(probe)
    if root is None:
        raise HTTPException(status_code=403, detail="path not in allowed roots")
    if not probe.startswith(root + os.sep):
        raise HTTPException(status_code=403, detail="path not in allowed roots")
    parent = Path(probe)
    if not _in_allowed_roots(parent):
        raise HTTPException(status_code=403, detail="path not in allowed roots")
    if not parent.is_dir():
        raise HTTPException(status_code=404, detail="directory not found")

    name = (req.name or "").strip()
    if (
        not name
        or "/" in name
        or "\\" in name
        or name in {".", ".."}
        or name.startswith(".")
        or len(name) > 80
    ):
        raise HTTPException(status_code=422, detail="invalid folder name")

    # The folder the request names, kept inside the parent by the same real-path prefix
    # check: `name` is one segment by the rules above, and this makes the containment a
    # property of the created path itself (py/path-injection).
    target_probe = os.path.realpath(os.path.join(str(parent), name)) + os.sep
    if not target_probe.startswith(str(parent) + os.sep):
        raise HTTPException(status_code=422, detail="invalid folder name")
    target = Path(target_probe)
    if target.exists():
        if target.is_dir():
            return {"path": str(target), "created": False}
        raise HTTPException(status_code=409, detail="a file with that name exists")
    try:
        target.mkdir()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"mkdir failed: {exc}") from exc
    return {"path": str(target), "created": True}
