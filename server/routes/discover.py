"""Discover bootstrap (Y1): one roundtrip for the whole shelf.

The page used to fire eight parallel requests (skills, MCP settings, MCP
health, MCP catalog, market home, market index, market installed, tool
usage). Health probes wait on third-party processes and stay decoupled;
everything else is a pure local read and rides here in one frame.
"""
from __future__ import annotations

from fastapi import APIRouter

from core import marketplace_service, marketplace_sources
from core.mcp_catalog import catalog_entries, curated_entries, registry_entries
from server.routes.audit import get_audit_usage
from server.routes.marketplace import market_home, market_index
from server.routes.skills import list_skills

router = APIRouter(tags=["discover"])


@router.get("/discover/bootstrap")
async def discover_bootstrap(top: int = 12) -> dict:
    skills = (await list_skills()).skills
    home = await market_home()
    index = await market_index()
    usage = await get_audit_usage(top=top)
    data = marketplace_sources.load_sources()
    return {
        "skills": skills,
        "sources": data["sources"],
        "last_read": data["last_read"],
        "last_error": data["last_error"],
        "home": home,
        "index": index.get("index"),
        "catalog": catalog_entries(),
        "curated": curated_entries(),
        "registry_count": len(registry_entries()),
        "installed": marketplace_service.installed()["plugins"],
        "usage": usage,
    }
