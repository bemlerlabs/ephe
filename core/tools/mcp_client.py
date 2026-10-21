"""Ephe – lightweight MCP client (Model Context Protocol): registry + freshness.

Attaches external MCP servers as tools to the tool registry without the heavy
`mcp` SDK dependency: we speak the standardized JSON-RPC 2.0 protocol directly
with `httpx` for HTTP servers, and stdio servers via subprocess.

The public entrypoint for the MCP surface: the server-spec registry, the sync
orchestration and the catalogue-freshness policy.
The JSON-RPC wire side — the per-server client, its payload builders and the
paginated ``tools/list`` walk — lives in the sibling module
``core.tools.mcp_transport`` (W7b-2) and is re-exported here, so every name
that used to be importable from ``core.tools.mcp_client`` stays importable.

The registry functions are deliberately fault-tolerant: a failed server is
skipped, not fatal. All functions are async, because the MCP standard is async.

Lifetime (I1-8): a stdio server is a child process — the wire module speaks
JSON-RPC, the process side (spawn, exit, backoff) lives in
``core.tools.mcp_process.StdioLink``. A JSON-RPC error is an error, not
an empty success.
"""
from __future__ import annotations

import asyncio
import shlex
import time
from dataclasses import dataclass, field
from typing import Any, Callable

# The wire client and its protocol constants live in a sibling module; re-import
# them so this module remains the one public entrypoint for the MCP surface.
from core.tools.mcp_transport import MAX_TOOL_PAGES, MCPClient  # noqa: F401

_MCP_NAMESPACE = "mcp_"
#: Freshness window of the *registered* catalogue (W7-10). After this much
#: wall-clock time the last ``tools/list`` no longer counts as current — an MCP
#: server's tool set can change underneath a long-lived session, so a stale
#: catalogue re-discovers instead of serving the old list forever.
MCP_CATALOG_TTL_S = 300.0
# Server-Specs (transport:endpoint). Env: EPHE_MCP_SERVERS="http://…/mcp,stdio:npx …"
_MCP_SERVERS: list[MCPServerSpec] = []
# Registered remote tools: {tool_name: {"server", "tool", "call", "schema"}}
_MCP_TOOLS: dict[str, dict[str, Any]] = {}
# Live stdio clients by spec key — the process stays open for call_tool,
# otherwise every call would be a cold restart without a session.
_LIVE_CLIENTS: dict[str, "MCPClient"] = {}
# Freshness of the registered catalogue (W7-10): when and from which specs the
# last discovery ran. ``None`` = never discovered — a configured server that was
# never synced (a failed startup sync) reads as stale, so the first read
# re-discovers instead of serving an empty or old list.
_MCP_DISCOVERED_AT: float | None = None
_MCP_DISCOVERED_SPECS: tuple[str, ...] = ()
#: The event loop that armed discovery. A synchronous stale read only fires a
#: background re-discovery on the loop that owns the catalogue, so a foreign
#: loop (a short-lived test loop, another worker) never spawns a subprocess.
#: The object is held (not its id) so a collected loop cannot alias a new one.
_MCP_ARMED_LOOP: "asyncio.AbstractEventLoop | None" = None
_MCP_REFRESH_TASK: "asyncio.Task | None" = None


@dataclass
class MCPServerSpec:
    transport: str
    endpoint: str = ""
    command: str = ""
    args: list[str] = field(default_factory=list)
    label: str = ""

    def render(self) -> str:
        if self.transport == "stdio":
            return f"stdio:{shlex.join([self.command, *self.args])}"
        return self.endpoint

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MCPServerSpec):
            return NotImplemented
        return (
            self.transport == other.transport
            and self.endpoint == other.endpoint
            and self.command == other.command
            and self.args == other.args
        )


def parse_server_spec(spec: str) -> MCPServerSpec:
    """Parse "stdio:cmd arg…" or "http://host:port[/mcp]" into a ServerSpec."""
    spec = spec.strip()
    if spec.startswith("stdio:"):
        rest = spec[len("stdio:"):].strip()
        parts = shlex.split(rest)
        cmd = parts[0] if parts else ""
        return MCPServerSpec(transport="stdio", command=cmd, args=parts[1:])
    endpoint = spec if spec.startswith("http://") or spec.startswith("https://") else f"https://{spec}"
    return MCPServerSpec(transport="http", endpoint=endpoint)


def set_mcp_servers(specs: list[str]) -> list[MCPServerSpec]:
    """Set the active MCP servers (from command line/env). Empties the registry."""
    global _MCP_SERVERS
    unregister_mcp_tools()
    _MCP_SERVERS = [parse_server_spec(s) for s in specs if s.strip()]
    return _MCP_SERVERS


def get_mcp_servers() -> list[MCPServerSpec]:
    return list(_MCP_SERVERS)


def get_mcp_tools() -> dict[str, dict[str, Any]]:
    """Only the remote tools; the built-ins live in a separate namespace.

    W7-10: a stale catalogue is never served as current. The read fires a
    background re-discovery (``_refresh_in_background``) and returns the last
    known list for this instant, so the next schema build — at most one
    ``TOOL_SCHEMA_CACHE_TTL_SECONDS`` later — sees the refreshed one.
    """
    if mcp_catalog_is_stale():
        _refresh_in_background()
    return dict(_MCP_TOOLS)


def _invalidate_schema_cache() -> None:
    """Lazy import avoids circularity (registry imports mcp_client)."""
    from core.tools.registry import invalidate_tool_schema_cache
    invalidate_tool_schema_cache()


def register_mcp_tool(name: str, server: str, tool: str, call: Callable, schema: dict,
                      *, discovered: bool = False) -> dict:
    """Registers a remote tool in the MCP namespace. Collision with built-ins → ValueError.

    ``discovered`` marks a tool a catalogue sync found on a configured server. A later
    refresh clears only those, so a tool registered by hand survives it — measured 2026-10-12:
    a background refresh used to delete a hand-registered tool while its call was in flight.
    """
    if name in _MCP_TOOLS:
        raise ValueError(f"MCP tool {name} is already registered")
    _MCP_TOOLS[name] = {"server": server, "tool": tool, "call": call, "schema": schema,
                        "discovered": discovered}
    _invalidate_schema_cache()
    return _MCP_TOOLS[name]


def unregister_mcp_tools() -> None:
    """Clears every MCP tool, discovered or hand-registered — the teardown path."""
    global _MCP_DISCOVERED_AT, _MCP_DISCOVERED_SPECS
    _MCP_TOOLS.clear()
    _MCP_DISCOVERED_AT = None
    _MCP_DISCOVERED_SPECS = ()
    _invalidate_schema_cache()


def _clear_discovered_mcp_tools() -> None:
    """Drops what a previous catalogue sync found, and nothing else.

    A refresh runs as a background task off a read, so clearing the whole namespace there
    would delete a tool a caller registered by hand while the refresh was in flight.
    """
    stale = [name for name, entry in _MCP_TOOLS.items() if entry.get("discovered")]
    for name in stale:
        del _MCP_TOOLS[name]
    if stale:
        _invalidate_schema_cache()


def _live_key(spec: MCPServerSpec) -> str:
    return f"{spec.transport}:{spec.render()}"


class MCPTeardownError(RuntimeError):
    """The MCP clients could not be closed safely; no teardown may be claimed."""


async def close_all_mcp_clients() -> None:
    """Closes every live MCP client — shutdown and plugin teardown.

    A stdio server that outlives the parent is a leak nobody sees:
    it holds the binary, directories and one entry in the process table. A
    client is removed only after its close returned, so a failed close stays
    reachable for a retry instead of turning into an unreferenced process.
    """
    errors: list[str] = []
    for key, client in list(_LIVE_CLIENTS.items()):
        try:
            await client.close()
        except Exception as exc:  # noqa: BLE001 — collected, then raised below
            errors.append(f"{key}: {exc}")
        else:
            _LIVE_CLIENTS.pop(key, None)
    if errors:
        raise MCPTeardownError("; ".join(errors))


async def _close_mcp_connector() -> None:
    await close_all_mcp_clients()
    unregister_mcp_tools()


def teardown_mcp_connector_sync() -> None:
    """Closes the connector from the synchronous lifecycle, fail-closed.

    The clients belong to the loop that armed discovery. Blocking that loop from
    inside itself would deadlock; skipping the close would claim a teardown that
    did not happen. Both cases raise, so the lifecycle keeps the plugin enabled.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise MCPTeardownError(
            "cannot close MCP clients from the event loop that is running them"
        )
    armed = _MCP_ARMED_LOOP
    if armed is not None and armed.is_running():
        future = asyncio.run_coroutine_threadsafe(_close_mcp_connector(), armed)
        try:
            future.result(timeout=15)
        except Exception as exc:  # noqa: BLE001 — the caller needs the reason
            raise MCPTeardownError(str(exc) or exc.__class__.__name__) from exc
        return
    if _LIVE_CLIENTS:
        if armed is not None:
            raise MCPTeardownError(
                "the MCP client loop is not running; no safe close"
            )
        asyncio.run(_close_mcp_connector())
        return
    unregister_mcp_tools()


def request_mcp_refresh() -> None:
    """Re-discovers the catalogue after the connector is enabled again.

    The next read also treats the catalogue as stale, so a loop that is not
    reachable here does not hide the tools forever.
    """
    loop = _MCP_ARMED_LOOP
    if loop is None or not loop.is_running():
        return
    coroutine = sync_mcp_tools()
    try:
        asyncio.run_coroutine_threadsafe(coroutine, loop)
    except RuntimeError:
        coroutine.close()
        return


def _record_discovery(specs: list[MCPServerSpec]) -> None:
    """Stamp the catalogue as current: when, from which specs, on which loop."""
    global _MCP_DISCOVERED_AT, _MCP_DISCOVERED_SPECS, _MCP_ARMED_LOOP, _MCP_REFRESH_TASK
    _MCP_DISCOVERED_AT = time.monotonic()
    _MCP_DISCOVERED_SPECS = _render_specs(specs)
    try:
        _MCP_ARMED_LOOP = asyncio.get_running_loop()
    except RuntimeError:
        _MCP_ARMED_LOOP = None
    _MCP_REFRESH_TASK = None


async def sync_mcp_tools(server_specs: list[MCPServerSpec] | None = None) -> list[str]:
    """Connects all configured MCP servers, lists their tools and registers them
    in the MCP namespace. Return: list of the newly registered tool names.

    The clients stay open after listing (in ``_LIVE_CLIENTS``) — the next
    call_tool talks to the same process and therefore the same session. A
    sync that shoots the server down again right away makes every tool call a
    cold start without an ``initialize`` handshake. Servers that have fallen
    out of the configuration are closed.
    """
    specs = server_specs if server_specs is not None else _MCP_SERVERS
    _clear_discovered_mcp_tools()
    registered: list[str] = []
    keep: set[str] = set()
    for idx, spec in enumerate(specs):
        endpoint = spec.endpoint if spec.transport == "http" else spec.command
        key = _live_key(spec)
        keep.add(key)
        client = _LIVE_CLIENTS.get(key)
        if client is None:
            client = MCPClient(
                endpoint=endpoint,
                transport=spec.transport,
                label=spec.label or f"mcp-{idx}",
                args=spec.args,
            )
            _LIVE_CLIENTS[key] = client
        tools = await client.list_tools()
        for tool in tools:
            if "error" in tool:
                continue
            name = tool.get("name")
            if not name:
                continue
            safe = name.replace(" ", "_").replace("-", "_")
            full = f"{_MCP_NAMESPACE}{safe}"

            async def _call(arguments: dict | None = None, _client=client, _name=name) -> tuple[str, bool]:
                return await _client.call_tool(_name, arguments or {})

            register_mcp_tool(full, spec.label or endpoint, name, _call, {"name": full, "description": tool.get("description", ""), "inputSchema": tool.get("inputSchema", {})}, discovered=True)
            registered.append(full)
    for stale in [key for key in _LIVE_CLIENTS if key not in keep]:
        await _LIVE_CLIENTS.pop(stale).close()
    _record_discovery(specs)
    return registered


def mcp_tool_names() -> list[str]:
    return sorted(_MCP_TOOLS.keys())


def is_mcp_tool(name: str) -> bool:
    """True for a name in the MCP namespace.

    Every remote tool's output is external content (E2 — untrusted), whether it
    was registered just now or only matches the namespace prefix.
    """
    return bool(name) and (name in _MCP_TOOLS or name.startswith(_MCP_NAMESPACE))


def _render_specs(specs: list[MCPServerSpec]) -> tuple[str, ...]:
    """The comparable identity of a server set — order does not matter."""
    return tuple(sorted(spec.render() for spec in specs))


def mcp_catalog_age(now: float | None = None) -> float | None:
    """Seconds since the last discovery of the catalogue, or ``None`` if never."""
    if _MCP_DISCOVERED_AT is None:
        return None
    return max(0.0, (now if now is not None else time.monotonic()) - _MCP_DISCOVERED_AT)


def mcp_catalog_is_stale(now: float | None = None, *, ttl: float | None = None) -> bool:
    """True when the registered catalogue must not be served as current.

    Three ways the catalogue goes stale:

    * never discovered although servers are configured — an earlier sync failed
      (the server was down) and nothing retried it;
    * older than ``MCP_CATALOG_TTL_S`` — the server's tool set can change
      underneath a long-lived session;
    * the configured server set differs from the set the last discovery made —
      ``mcp.json`` / ``EPHE_MCP_SERVERS`` changed out from under the process.

    Inert when no servers are configured: a hand-registered tool (a test, a host
    that injects its own transport) is never judged against a freshness window.
    """
    if not _MCP_SERVERS:
        return False
    window = MCP_CATALOG_TTL_S if ttl is None else ttl
    age = mcp_catalog_age(now)
    if age is None or age > window:
        return True
    return _render_specs(_MCP_SERVERS) != _MCP_DISCOVERED_SPECS


async def ensure_mcp_catalog_fresh(force: bool = False) -> bool:
    """Re-discover the catalogue when it is stale (or ``force`` is set).

    Returns ``True`` when a re-discovery ran. This is the awaited entry for a
    serving path that can afford the round-trip; the synchronous
    ``get_mcp_tools`` uses the non-blocking ``_refresh_in_background`` instead.
    """
    if not force and not mcp_catalog_is_stale():
        return False
    in_flight = _MCP_REFRESH_TASK
    if in_flight is not None and not in_flight.done():
        await in_flight  # join the background re-discovery already under way
        return True
    await sync_mcp_tools()
    return True


def _refresh_in_background() -> None:
    """Stale-while-revalidate: re-discover without blocking a synchronous read.

    Fires only on the loop that armed discovery (the app's loop). A foreign loop
    — a short-lived test loop, another worker — never spawns an MCP subprocess.
    One refresh is in flight at a time; the task reference is kept so the GC
    cannot resolve it mid-flight.
    """
    global _MCP_REFRESH_TASK
    if _MCP_REFRESH_TASK is not None and not _MCP_REFRESH_TASK.done():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    if _MCP_ARMED_LOOP is None or loop is not _MCP_ARMED_LOOP:
        return
    task = loop.create_task(sync_mcp_tools())

    def _mark_retrieved(done: "asyncio.Task") -> None:
        # The read never awaits this task; retrieve its result so a failure
        # surfaces as a warning-free no-op instead of "exception never retrieved".
        if not done.cancelled():
            done.exception()

    task.add_done_callback(_mark_retrieved)
    _MCP_REFRESH_TASK = task


async def call_registered_mcp_tool(name: str, arguments: dict | None = None) -> tuple[str, bool]:
    """Dispatch onto a registered remote tool (name like 'mcp_filesystem_read_text').

    W7-10: a stale catalogue is re-discovered before the dispatch, so the agent
    never invokes a tool from a list the server has already retired.
    """
    if mcp_catalog_is_stale():
        await ensure_mcp_catalog_fresh()
    entry = _MCP_TOOLS.get(name)
    if entry is None:
        return f"unknown MCP tool {name}", True
    call: Callable = entry["call"]
    return await call(arguments or {})
