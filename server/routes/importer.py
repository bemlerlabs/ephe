"""The vendor-neutral import behind the tour's last question.

`core/importer.py` already detects a setup by structure and writes it
additively; this route gives the in-app stop the same gesture the CLI has. The
source is a folder the user picked on this machine. `apply=false` returns the
plan without writing, which is what the surface shows before the click that
commits it.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.importer import apply_import, build_import_plan

router = APIRouter(tags=["Import"])


class ImportRequest(BaseModel):
    source: str
    apply: bool = False


@router.post("/import")
def post_import(req: ImportRequest) -> dict:
    source = Path(req.source).expanduser()
    if not source.is_dir():
        raise HTTPException(status_code=422, detail="the source folder does not exist")
    try:
        plan = build_import_plan(source)
    except OSError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not req.apply:
        return {"plan": plan, "applied": None}
    applied = apply_import(source)
    return {"plan": plan, "applied": applied}
