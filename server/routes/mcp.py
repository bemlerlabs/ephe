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

from fastapi import APIRouter

from core.mcp_catalog import catalog_entries
from core.tools.mcp_client import MCPClient, parse_server_spec

router = APIRouter(tags=["mcp"])

_PROBE_TIMEOUT_S = 4.0
_MAX_SERVERS = 32


@router.post("/mcp/health")
async def post_mcp_health() -> dict:
    """Probe every configured MCP server (initialize + tools/list)."""
    from core.mcp_config import load_mcp_servers

    specs_raw, _source = load_mcp_servers()
    servers: list[dict] = []
    for raw in specs_raw[:_MAX_SERVERS]:
        try:
            spec = parse_server_spec(str(raw))
        except Exception:  # noqa: BLE001 — an unparsable entry stays fail-soft
            servers.append({"spec": str(raw), "status": "unreachable", "tool_count": 0,
                            "transport": "http", "latency_ms": None, "error": "unparsable spec"})
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
        })
        await client.close()
    return {"servers": servers}


@router.get("/mcp/catalog")
def get_mcp_catalog() -> dict:
    """Curated starter list of open MCP servers (pure data, no network)."""
    return {"entries": catalog_entries()}
