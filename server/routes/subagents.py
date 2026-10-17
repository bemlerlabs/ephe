"""Ephe — P4-D: REST read access to the subagent history.

    server/routes/subagents.py

The frontend detail tab hangs on these two endpoints:

    GET /api/subagents            → {"agents": [summaries…]}   (newest first)
    GET /api/subagents/<agent_id> → the full record (report/tool_calls/transcript),
                                    or 404 for an unknown id.

One thin layer: the registry (core.subagent_history) is the truth source,
only requests pass through — REST and SSE answer from that one registry.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core import subagent_history

router = APIRouter()


@router.get("/subagents", tags=["Subagents"])
async def list_subagents(cursor: str | None = None, limit: int = 10) -> dict:
    """Compact overview of all known subagent runs (P6 B1: curated)."""
    return subagent_history.summaries(cursor=cursor, limit=limit)


@router.get("/subagents/{agent_id}", tags=["Subagents"])
async def get_subagent(agent_id: str) -> dict:
    """Detail pane per agent_id — timings, report, transcript."""
    record = subagent_history.get(agent_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"unknown agent: {agent_id}")
    return record
