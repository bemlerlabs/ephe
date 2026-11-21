"""Ephe — P5: REST read of the model trajectory.

    server/routes/trajectory.py

    GET /api/trajectory?session=<id> → {"turns": [ … ]}   (newest first)

Every turn line: model, ts, duration_ms + steps[] with number, TYPE, title,
ms-offset and tokens (IN/OUT) when usage was measured. Feeds the panel view
'Trajectory' (successor of the audit-heavy tab, Ephe norm).
"""
from __future__ import annotations

from fastapi import APIRouter

from core import trajectory

router = APIRouter()


@router.get("/trajectory", tags=["Trajectory"])
async def get_trajectory(session: str = "") -> dict:
    """The last turns of a session as a numbered step timeline."""
    return {"turns": trajectory.get_turns(session)}
