"""Plugin MCP server lifecycle: start, call, stop — the confined subprocess behind a plugin's MCP rail.

Ruling A1: the host keeps its distance from the plugin's server module — no import, no
execution. The server runs as a subprocess, and the host speaks JSON-RPC 2.0 over stdio
via the existing MCPClient infrastructure. When a plugin with `components.mcp` is mounted,
the host starts the server, discovers tools via `tools/list`, and registers them in the
dynamic registry with `transport=TRANSPORT_MCP`. When the plugin is unmounted, the host
stops the server and reaps the subprocess.

The manager is a singleton accessed via `plugin_mcp_manager()`. It holds a dict of
running servers keyed by plugin_id. Each server is an MCPClient instance connected to
the plugin's subprocess.

A stdio child is bound to the event loop that spawned it. A mount runs on the lifecycle
thread and a call runs on the turn's loop, so every operation is routed onto one loop the
manager owns; a client started on a transient loop would be unusable from the other.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import threading
from pathlib import Path

from core.tools.mcp_transport import MCPClient

logger = logging.getLogger(__name__)

#: How long a synchronous mount or unmount waits for the manager's loop.
SYNC_TIMEOUT_SECONDS = 30.0


class PluginMCPServerManager:
    """One dict of clients, one lock, one loop, three operations: start, call, stop."""

    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}
        self._allowed: dict[str, frozenset[str]] = {}
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_lock = threading.Lock()

    def is_running(self, plugin_id: str) -> bool:
        """Check the active server map."""
        return plugin_id in self._clients

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        """The manager's own loop, started once on a daemon thread."""
        with self._loop_lock:
            loop = self._loop
            if loop is not None and loop.is_running():
                return loop
            loop = asyncio.new_event_loop()
            threading.Thread(
                target=loop.run_forever, name="ephe-plugin-mcp", daemon=True
            ).start()
            self._loop = loop
            return loop

    async def _routed(self, operation):
        """Run one operation on the manager loop, from any loop or thread."""
        loop = self._ensure_loop()
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            return await operation
        return await asyncio.wrap_future(
            asyncio.run_coroutine_threadsafe(operation, loop)
        )

    def _routed_sync(self, operation):
        """Run one operation on the manager loop and wait for its result."""
        loop = self._ensure_loop()
        return asyncio.run_coroutine_threadsafe(operation, loop).result(
            timeout=SYNC_TIMEOUT_SECONDS
        )

    async def start_server(
        self,
        plugin_id: str,
        plugin_dir: Path,
        entry: str,
        allowed_tools: tuple[str, ...] | None = None,
    ) -> MCPClient | None:
        """Spawn the subprocess and initialize the JSON-RPC session.

        The entry is `server.py:main` — the host resolves it to an absolute path
        inside the plugin directory and spawns it as a subprocess. The server speaks
        JSON-RPC 2.0 over stdio. `allowed_tools` is the manifest's declared MCP names;
        when it is given, a call outside it is refused.

        Returns the MCPClient instance on success, or None on failure.
        """

        async def operation() -> MCPClient | None:
            async with self._lock:
                if plugin_id in self._clients:
                    return self._clients[plugin_id]

            entry_file, _, _ = entry.partition(":")
            if not entry_file:
                logger.error(
                    "plugin %s: MCP entry %r has no file part", plugin_id, entry
                )
                return None

            server_path = plugin_dir / entry_file
            if not server_path.is_file():
                logger.error(
                    "plugin %s: MCP server script %s missing", plugin_id, server_path
                )
                return None

            try:
                client = MCPClient(
                    endpoint=sys.executable,
                    transport="stdio",
                    label=f"plugin_{plugin_id}",
                    timeout=30.0,
                    args=[str(server_path)],
                )
                init_result = await client.initialize()
                if "error" in init_result:
                    logger.error(
                        "plugin %s: MCP server initialization failed: %s",
                        plugin_id,
                        init_result["error"],
                    )
                    await client.close()
                    return None

                async with self._lock:
                    self._clients[plugin_id] = client
                    if allowed_tools is not None:
                        self._allowed[plugin_id] = frozenset(allowed_tools)

                logger.info(
                    "plugin %s: MCP server started at %s", plugin_id, server_path
                )
                return client

            except Exception as exc:
                logger.error(
                    "plugin %s: failed to start MCP server: %s",
                    plugin_id,
                    exc,
                    exc_info=True,
                )
                return None

        return await self._routed(operation())

    async def stop_server(self, plugin_id: str) -> None:
        """Reap the subprocess and drop the client reference."""
        await self._routed(self._stop_one(plugin_id))

    async def _stop_one(self, plugin_id: str) -> None:
        async with self._lock:
            client = self._clients.pop(plugin_id, None)
            self._allowed.pop(plugin_id, None)

        if client is not None:
            try:
                await client.close()
                logger.info("plugin %s: MCP server stopped", plugin_id)
            except Exception as exc:
                logger.error(
                    "plugin %s: error stopping MCP server: %s",
                    plugin_id,
                    exc,
                    exc_info=True,
                )

    async def call_tool(
        self, plugin_id: str, tool_name: str, arguments: dict
    ) -> tuple[str, bool]:
        """Forward one JSON-RPC request to the running subprocess.

        Returns (text, is_error). A missing server, or a name the manifest did not
        declare, yields an error message.
        """

        async def operation() -> tuple[str, bool]:
            async with self._lock:
                client = self._clients.get(plugin_id)
                allowed = self._allowed.get(plugin_id)

            if client is None:
                return f"plugin {plugin_id}: MCP server unavailable", True
            if allowed is not None and tool_name not in allowed:
                return (
                    f"plugin {plugin_id}: tool {tool_name} is not declared by its "
                    "manifest",
                    True,
                )

            try:
                return await client.call_tool(tool_name, arguments)
            except Exception as exc:
                logger.error(
                    "plugin %s: MCP tool call %s failed: %s",
                    plugin_id,
                    tool_name,
                    exc,
                    exc_info=True,
                )
                return f"MCP tool call failed: {exc}", True

        return await self._routed(operation())

    async def stop_all(self) -> None:
        """Shutdown hook: reap every active subprocess."""

        async def operation() -> None:
            async with self._lock:
                plugin_ids = list(self._clients.keys())
            for plugin_id in plugin_ids:
                await self._stop_one(plugin_id)

        await self._routed(operation())

    def start_server_sync(
        self,
        plugin_id: str,
        plugin_dir: Path,
        entry: str,
        allowed_tools: tuple[str, ...] | None = None,
    ) -> MCPClient | None:
        """Start from a synchronous caller (the lifecycle mount) and wait for it."""
        return self._routed_sync(
            self.start_server(plugin_id, plugin_dir, entry, allowed_tools)
        )

    def stop_server_sync(self, plugin_id: str) -> None:
        """Stop from a synchronous caller (the lifecycle unmount) and wait for it."""
        self._routed_sync(self.stop_server(plugin_id))

    def stop_all_sync(self) -> None:
        """Reap every server from a synchronous caller."""
        self._routed_sync(self.stop_all())


# Singleton instance
_manager: PluginMCPServerManager | None = None


def plugin_mcp_manager() -> PluginMCPServerManager:
    """The process-wide accessor — lazily builds the singleton on first use."""
    global _manager
    if _manager is None:
        _manager = PluginMCPServerManager()
    return _manager
