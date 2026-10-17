"""server/routes/cell.py – WP5: GET /api/cell — the life line of a session.

Answers only with numbers that `core.ephemeral_cell.cell_life` really knows. The
line is the promise of ephemerality; a field the registry does not produce does
not exist here.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from core.ephemeral_cell import cell_life

router = APIRouter(tags=["Cell"])


@router.get("/cell")
async def get_cell(session: str = Query(default="")) -> dict:
    """Age, idle time and remaining lifetime of this session's cell ('default' when unset)."""
    return {"cell": cell_life(session.strip() or "default")}
