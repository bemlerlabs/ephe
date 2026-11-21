"""Discover bootstrap (Y1): one roundtrip for the whole shelf.

The page used to fire eight parallel requests (skills, MCP settings, MCP
health, MCP catalog, market home, market index, market installed, tool
usage). Health probes wait on third-party processes and stay decoupled;
everything else is a pure local read and rides here in one frame.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from core import discover_search, marketplace_service, marketplace_sources
from core.marketplace_verify import verify_entry
from core.mcp_catalog import (
    ICON_SLUG,
    catalog_entries,
    curated_entries,
    featured_entries,
    registry_entries,
)
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


#: The two shelves that ship with the app. The row names what is already readable
#: and where a refresh comes from, so nobody has to add a source to get the
#: default breadth.
PRESETS = (
    {
        "id": "ephe-index",
        "title": "Ephe verified index",
        "kind": "bundled",
        "url": "",
        "state": "bundled",
    },
    {
        "id": "mcp-registry",
        "title": "Official MCP community registry",
        "kind": "mirror",
        "url": "https://registry.modelcontextprotocol.io/v0/servers",
        "state": "mirrored weekly",
    },
)


@router.get("/discover/bootstrap")
async def discover_bootstrap(top: int = 12) -> dict:
    skills = (await list_skills()).skills
    home = await market_home()
    index = await market_index()
    usage = await get_audit_usage(top=top)
    data = marketplace_sources.load_sources()
    registry_count = len(registry_entries())
    presets = [
        dict(one, count=len(index.get("index", {}).get("plugins") or []))
        if one["id"] == "ephe-index"
        else dict(one, count=registry_count)
        for one in PRESETS
    ]
    return {
        "skills": skills,
        "sources": data["sources"],
        "last_read": data["last_read"],
        "last_error": data["last_error"],
        "home": home,
        "index": index.get("index"),
        "catalog": catalog_entries(),
        "featured": featured_entries(),
        "curated": curated_entries(),
        "registry_count": registry_count,
        "presets": presets,
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


#: Vendor icons for the featured tier, fetched once by
#: `scripts/fetch_marketplace_icons.py` and served from the tree so a render
#: never calls a third party.
_ICON_DIR = Path(__file__).resolve().parents[2] / "marketplace" / "icons" / "providers"


@router.get("/discover/icon/{slug}")
def discover_icon(slug: str) -> FileResponse:
    if not ICON_SLUG.fullmatch(slug or ""):
        raise HTTPException(status_code=404, detail="unknown icon")
    path = _ICON_DIR / f"{slug}.png"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="unknown icon")
    return FileResponse(
        path, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"}
    )
