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
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from core.tools.mcp_transport import MCPClient

logger = logging.getLogger(__name__)


class PluginMCPServerManager:
    """One dict of clients, one lock, three operations: start, call, stop."""

    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}
        self._lock = asyncio.Lock()

    def is_running(self, plugin_id: str) -> bool:
        """Check the active server map."""
        return plugin_id in self._clients

    async def start_server(
        self, plugin_id: str, plugin_dir: Path, entry: str
    ) -> MCPClient | None:
        """Spawn the subprocess and initialize the JSON-RPC session.

        The entry is `server.py:main` — the host resolves it to an absolute path
        inside the plugin directory and spawns it as a subprocess. The server speaks
        JSON-RPC 2.0 over stdio.

        Returns the MCPClient instance on success, or None on failure.
        """
        async with self._lock:
            if plugin_id in self._clients:
                return self._clients[plugin_id]

        # Resolve the server script path
        entry_file, _, _ = entry.partition(":")
        if not entry_file:
            logger.error("plugin %s: MCP entry %r has no file part", plugin_id, entry)
            return None

        server_path = plugin_dir / entry_file
        if not server_path.is_file():
            logger.error(
                "plugin %s: MCP server script %s missing", plugin_id, server_path
            )
            return None

        # Spawn the server as a subprocess using the existing MCPClient infrastructure
        # The client speaks JSON-RPC 2.0 over stdio. The command is the Python interpreter,
        # and the server script is passed as an argument.
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

            logger.info("plugin %s: MCP server started at %s", plugin_id, server_path)
            return client

        except Exception as exc:
            logger.error(
                "plugin %s: failed to start MCP server: %s", plugin_id, exc, exc_info=True
            )
            return None

    async def stop_server(self, plugin_id: str) -> None:
        """Reap the subprocess and drop the client reference."""
        async with self._lock:
            client = self._clients.pop(plugin_id, None)

        if client is not None:
            try:
                await client.close()
                logger.info("plugin %s: MCP server stopped", plugin_id)
            except Exception as exc:
                logger.error(
                    "plugin %s: error stopping MCP server: %s", plugin_id, exc, exc_info=True
                )

    async def call_tool(self, plugin_id: str, tool_name: str, arguments: dict) -> tuple[str, bool]:
        """Forward one JSON-RPC request to the running subprocess.

        Returns (text, is_error). A missing server yields an error message.
        """
        async with self._lock:
            client = self._clients.get(plugin_id)

        if client is None:
            return f"plugin {plugin_id}: MCP server unavailable", True

        try:
            text, is_error = await client.call_tool(tool_name, arguments)
            return text, is_error
        except Exception as exc:
            logger.error(
                "plugin %s: MCP tool call %s failed: %s",
                plugin_id,
                tool_name,
                exc,
                exc_info=True,
            )
            return f"MCP tool call failed: {exc}", True

    async def stop_all(self) -> None:
        """Shutdown hook: reap every active subprocess."""
        async with self._lock:
            plugin_ids = list(self._clients.keys())

        for plugin_id in plugin_ids:
            await self.stop_server(plugin_id)


# Singleton instance
_manager: PluginMCPServerManager | None = None


def plugin_mcp_manager() -> PluginMCPServerManager:
    """The process-wide accessor — lazily builds the singleton on first use."""
    global _manager
    if _manager is None:
        _manager = PluginMCPServerManager()
    return _manager
