"""
◑ Ephe – MCP page routes (E3c, docs/EXTENSIONS_V2_PLAN.md)
server/routes/mcp.py

POST /api/mcp/health  → health probe of the CONFIGURED MCP servers.
    Deliberately without request parameters: only what
    mcp.json / EPHE_MCP_SERVERS names gets probed (the same trust base as
    the existing sync in PUT /settings/mcp) — so there is no SSRF playground.
    Per server: status ok/unreachable, tool_count, transport, latency_ms.
    Fail-soft, never raises.

GET  /api/mcp/catalog → curated start catalog (core/mcp_catalog.py).

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Request

from core.mcp_catalog import catalog_entries, curated_entries, registry_entries
from core.tools.mcp_client import MCPClient, parse_server_spec


def _mutation_guard(request: Request) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise HTTPException(
            status_code=403,
            detail={
                "code": "unauthorized",
                "detail": "X-Requested-With: XMLHttpRequest required",
            },
        )


router = APIRouter(tags=["mcp"])

_PROBE_TIMEOUT_S = 4.0
_MAX_SERVERS = 32


@router.post("/mcp/health")
async def post_mcp_health() -> dict:
    """Probe every configured MCP server (initialize + tools/list)."""
    from core import secret_store
    from core.mcp_config import load_mcp_servers, load_server_env

    declared = load_server_env()
    specs_raw, _source = load_mcp_servers()
    servers: list[dict] = []
    for raw in specs_raw[:_MAX_SERVERS]:
        missing = [
            name for name in declared.get(str(raw), []) if not secret_store.mode(name)
        ]
        try:
            spec = parse_server_spec(str(raw))
        except Exception:  # noqa: BLE001 — an unparsable entry stays fail-soft
            servers.append({"spec": str(raw), "status": "unreachable", "tool_count": 0,
                            "transport": "http", "latency_ms": None, "error": "unparsable spec",
                            "missing_env": missing})
            continue
        endpoint = spec.endpoint if spec.transport == "http" else spec.command
        client = MCPClient(endpoint=endpoint, transport=spec.transport,
                           label=spec.label or raw, timeout=_PROBE_TIMEOUT_S, args=spec.args)
        started = time.perf_counter()
        tools: list = []
        try:
            await client.initialize()
        except Exception:  # noqa: BLE001 — initialize is optional (many servers
            pass          # answer tools/list without a session)
        try:
            tools = await client.list_tools()
        except Exception:  # noqa: BLE001
            tools = []
        latency_ms = int((time.perf_counter() - started) * 1000)
        errors = [t for t in tools if isinstance(t, dict) and "error" in t]
        reachable = bool(tools) and not errors
        servers.append({
            "spec": raw,
            "status": "ok" if reachable else "unreachable",
            "tool_count": len([t for t in tools if isinstance(t, dict) and t.get("name")]),
            "transport": spec.transport,
            "latency_ms": latency_ms,
            "error": errors[0].get("error") if errors else (None if reachable else "no tools listed"),
            "missing_env": missing,
        })
        await client.close()
    return {"servers": servers}


@router.get("/mcp/env")
async def get_mcp_env() -> dict:
    """Which secret names each configured connector may receive."""
    from core.mcp_config import load_server_env

    return {"servers": load_server_env()}


@router.post("/mcp/env")
async def post_mcp_env(request: Request, body: dict) -> dict:
    """Declares the names one connector may receive; empty forgets them.

    The value never travels here: this route records the declaration, the vault
    route writes the secret, and the child process is the only reader."""
    from core import secret_store
    from core.mcp_config import load_server_env, save_server_env

    _mutation_guard(request)
    spec = str(body.get("spec") or "").strip()
    names = [str(name).strip() for name in (body.get("names") or []) if str(name).strip()]
    if not spec:
        raise HTTPException(
            status_code=400, detail={"code": "spec_required", "detail": "no connector named"}
        )
    bad = [name for name in names if not secret_store.is_name(name)]
    if bad:
        raise HTTPException(
            status_code=400,
            detail={"code": "env_name_invalid", "detail": ", ".join(bad)[:200]},
        )
    return {"servers": save_server_env(spec, names), "declared": load_server_env().get(spec, [])}


@router.get("/mcp/catalog")
def get_mcp_catalog() -> dict:
    """Curated starter list of open MCP servers (pure data, no network)."""
    return {"entries": catalog_entries()}


@router.get("/discover/registry")
def get_discover_registry(full: bool = False) -> dict:
    """The connector tiers: the curated window always, the full mirror only
    when asked. Separate from /mcp/catalog, whose contract promises curated
    bilingual rows without a single secret-shaped word; the mirror carries
    publisher text verbatim and needs its own contract."""
    entries = registry_entries()
    return {
        "curated": curated_entries(),
        "registry": entries if full else [],
        "registry_count": len(entries),
    }
