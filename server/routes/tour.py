"""The first-run tour's device marker.

The four questions of the first open span the PWA and the desktop app, and their
answers live with the rest of the device state under `~/.ephe/`. A marker in
localStorage would be per browser and could replay the tour after the engine
already answers. `GET /api/tour` answers the defaults when the file is absent or
unreadable, so the surface needs no special case. `POST /api/tour` writes the
whole marker atomically. The register is a step, two flags and the answers the
stops can name.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["Tour"])

TOUR_FILE = "tour.json"
TOUR_VERSION = 1
#: The four question stops plus the greeting and the desk. A marker outside this
#: range is a file from another build, not a resume point.
MAX_STEP = 5


def config_root() -> Path:
    return Path(os.environ.get("EPHE_CONFIG_DIR") or str(Path.home() / ".ephe"))


def marker_path() -> Path:
    return config_root() / TOUR_FILE


def _defaults() -> dict[str, Any]:
    return {"version": TOUR_VERSION, "step": 0, "walked": False, "skipped": False, "answers": {}}


class TourMarker(BaseModel):
    version: int = TOUR_VERSION
    step: int = Field(default=0, ge=0, le=MAX_STEP)
    walked: bool = False
    skipped: bool = False
    answers: dict[str, Any] = Field(default_factory=dict)


@router.get("/tour")
def get_tour() -> dict[str, Any]:
    path = marker_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {**_defaults(), "exists": False}
    if not isinstance(raw, dict):
        return {**_defaults(), "exists": False}
    try:
        marker = TourMarker.model_validate(raw).model_dump()
    except ValueError:
        return {**_defaults(), "exists": False}
    return {**marker, "exists": True}


@router.post("/tour")
def save_tour(marker: TourMarker) -> dict[str, Any]:
    path = marker_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(marker.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return {**marker.model_dump(), "exists": True}
