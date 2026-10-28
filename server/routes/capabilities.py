"""GET /api/capabilities — what each agent kind may do, read from the source.

The settings surface states the read-only boundary of a sub-agent. That number
and that list live in `core/subagent.py`; this route reads them there instead of
letting a view carry a copy that can drift from the guard that enforces it.
"""
from __future__ import annotations

from fastapi import APIRouter

from core.subagent import SUBAGENT_MAX_ITERATIONS, SUBAGENT_TOOL_WHITELIST

router = APIRouter(tags=["Agents"])


@router.get("/capabilities")
def capabilities() -> dict:
    return {
        "subagent": {
            "tools": list(SUBAGENT_TOOL_WHITELIST),
            "tool_count": len(SUBAGENT_TOOL_WHITELIST),
            "max_iterations": SUBAGENT_MAX_ITERATIONS,
            "read_only": True,
        },
        "main_agent": {
            "read_only": False,
            "note": "every registered tool; each write passes the approval gate",
        },
    }
