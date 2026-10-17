"""The vendor-neutral import behind the tour's last question.

`core/importer.py` already detects a setup by structure and writes it
additively; this route gives the in-app stop the same gesture the CLI has.
The request carries no path: the desktop shell records the folder the user
picked in `import-source.json` with a one-time token, and the route imports
exactly that selection. A caller without the token cannot name a folder.
`apply=false` returns the plan without writing, which is what the surface
shows before the click that commits it.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.importer import apply_import, build_import_plan

router = APIRouter(tags=["Import"])

SELECTION_TTL_MS = 10 * 60 * 1000


class ImportRequest(BaseModel):
    token: str
    apply: bool = False


def _selection_file() -> Path:
    root = Path(os.environ.get("EPHE_CONFIG_DIR") or str(Path.home() / ".ephe"))
    return root / "import-source.json"


def _selected_source(token: str) -> Path:
    try:
        selected = json.loads(_selection_file().read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="no folder has been selected") from exc
    if not isinstance(selected, dict) or selected.get("token") != token:
        raise HTTPException(status_code=403, detail="the selection does not match this request")
    created = selected.get("created_at")
    if not isinstance(created, (int, float)) or time.time() * 1000 - created > SELECTION_TTL_MS:
        raise HTTPException(status_code=410, detail="the folder selection expired")
    raw = selected.get("path")
    if not isinstance(raw, str) or not raw:
        raise HTTPException(status_code=409, detail="no folder has been selected")
    source = Path(raw)
    if not source.is_absolute() or not source.is_dir():
        raise HTTPException(status_code=422, detail="the source folder does not exist")
    return source


@router.post("/import")
def post_import(req: ImportRequest) -> dict:
    source = _selected_source(req.token)
    try:
        plan = build_import_plan(source)
    except OSError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not req.apply:
        return {"plan": plan, "applied": None}
    applied = apply_import(source)
    _selection_file().unlink(missing_ok=True)
    return {"plan": plan, "applied": applied}
