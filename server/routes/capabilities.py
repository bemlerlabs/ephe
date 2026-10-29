"""GET /api/capabilities — what each agent kind may do, read from the source.

The settings surface states the read-only boundary of a sub-agent. That number
and that list live in `core/subagent.py`; this route reads them there instead of
letting a view carry a copy that can drift from the guard that enforces it.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter

from core.subagent import SUBAGENT_MAX_ITERATIONS, SUBAGENT_TOOL_WHITELIST
from core.mcp_sandbox import platform_boundary
from core.tools import get_tool_schemas
from core.tools.approval_rules import SAFE_TOOLS

router = APIRouter(tags=["Agents"])


def _tool_catalog() -> dict:
    """Every registered tool with the gate's own verdict on it.

    `safe` is membership in `SAFE_TOOLS` — the one list that decides a call runs
    without a prompt. A catalog that derived its own answer could drift from the
    guard that refuses; this one cannot.
    """
    rows = []
    for schema in get_tool_schemas():
        function = schema.get("function") or {}
        name = str(function.get("name") or "")
        if not name:
            continue
        rows.append({
            "name": name,
            "description": str(function.get("description") or ""),
            "safe": name in SAFE_TOOLS,
        })
    rows.sort(key=lambda row: row["name"])
    return {
        "tools": rows,
        "count": len(rows),
        "safe_count": sum(1 for row in rows if row["safe"]),
    }


def _mcp_sandbox() -> dict:
    """The boundary an MCP server runs under, read from the module that builds it.

    `network_isolated` is False because `build_bwrap` deliberately omits
    `--unshare-net` (an MCP server may legitimately be a network client), and
    `pid_isolated` follows the same argv: only bubblewrap carries `--unshare-pid`.
    """
    platform = platform_boundary()
    base = os.environ.get("EPHE_CONFIG_DIR")
    homes = (Path(base) if base else Path.home() / ".ephe") / "mcp" / "homes"
    return {
        "platform": platform,
        "available": platform != "unavailable",
        "home_root": str(homes),
        "network_isolated": False,
        "pid_isolated": platform == "bubblewrap",
    }


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
        "tools": _tool_catalog(),
        "mcp_sandbox": _mcp_sandbox(),
    }
