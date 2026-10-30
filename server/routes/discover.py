"""Discover bootstrap (Y1): one roundtrip for the whole shelf.

The page used to fire eight parallel requests (skills, MCP settings, MCP
health, MCP catalog, market home, market index, market installed, tool
usage). Health probes wait on third-party processes and stay decoupled;
everything else is a pure local read and rides here in one frame.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from core import discover_search, marketplace_service, marketplace_sources
from core.marketplace_verify import verify_entry
from core.mcp_catalog import catalog_entries, curated_entries, registry_entries
from server.routes.audit import get_audit_usage
from server.routes.marketplace import market_home, market_index
from server.routes.skills import list_skills

router = APIRouter(tags=["discover"])


@router.get("/discover/search")
async def discover_search_entries(q: str = "", limit: int = 24) -> dict:
    """Intent search over the shelf: the task a person types, not the package name.

    Offline by construction — the tags were precomputed with the catalog and the
    ranking runs in an in-memory FTS5 table."""
    return {"query": q, "entries": discover_search.search(q, limit)}


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


@router.post("/discover/dry-run")
async def discover_dry_run(request: Request, body: dict) -> dict:
    """The rehearsal: scan one catalog entry before anything is downloaded.

    Same XHR rule as every mutation, because the rehearsal is a user action.
    The answer names its mode so the surface never implies a live handshake."""
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise HTTPException(
            status_code=403,
            detail={"code": "unauthorized", "detail": "X-Requested-With: XMLHttpRequest required"},
        )
    fields = {
        key: str(body.get(key) or "")
        for key in ("name", "description", "install_hint", "spec")
        if body.get(key)
    }
    if not fields:
        raise HTTPException(
            status_code=400,
            detail={"code": "entry_required", "detail": "nothing to rehearse"},
        )
    return verify_entry(fields)
