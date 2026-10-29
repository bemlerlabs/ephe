"""GET /api/capabilities — what each agent kind may do, read from the source.

The settings surface states the read-only boundary of a sub-agent. That number
and that list live in `core/subagent.py`; this route reads them there instead of
letting a view carry a copy that can drift from the guard that enforces it.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core import capabilities as capability_store
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
    rows = capability_store.catalog()
    return {
        "tools": rows,
        "count": len(rows),
        "safe_count": sum(1 for row in rows if row["safe"]),
        "enabled_count": sum(1 for row in rows if row["enabled"]),
        "locked": sorted(capability_store.ALWAYS_ON),
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


class ToolSwitch(BaseModel):
    enabled: bool


class AllowlistEdit(BaseModel):
    names: list[str]


@router.get("/capabilities")
def capabilities() -> dict:
    allowlist = capability_store.subagent_allowlist()
    return {
        "subagent": {
            "tools": allowlist,
            "tool_count": len(allowlist),
            "base_tools": list(SUBAGENT_TOOL_WHITELIST),
            "extra_tools": capability_store.state()["subagent_extra"],
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


@router.patch("/capabilities/{name}")
def switch_capability(name: str, body: ToolSwitch) -> dict:
    """Switch one capability on or off. The name has to exist in the catalog."""
    known = {row["name"]: row for row in capability_store.catalog()}
    row = known.get(name)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown capability")
    if not body.enabled and row["locked"]:
        raise HTTPException(
            status_code=409,
            detail="this tool keeps the agent reachable and cannot be switched off",
        )
    capability_store.set_enabled(name, body.enabled)
    return {"name": name, "enabled": capability_store.is_enabled(name)}


@router.put("/capabilities/subagent-allowlist")
def set_subagent_allowlist(body: AllowlistEdit) -> dict:
    """Replace the names the user adds to the sub-agent whitelist.

    A name the registry does not know is refused: an allowlist entry that can
    never match is a promise the surface would show and the guard would not keep.
    """
    known = {row["name"] for row in capability_store.catalog()}
    unknown = sorted({str(entry).strip() for entry in body.names if str(entry).strip()} - known)
    if unknown:
        raise HTTPException(status_code=422, detail={"unknown": unknown})
    stored = capability_store.set_subagent_extra(body.names)
    return {"extra_tools": stored, "tools": capability_store.subagent_allowlist()}
