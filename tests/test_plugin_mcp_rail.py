"""◑ Ephe · TDD — a plugin MCP tool rides its own confined server over stdio.

Slice 2 of #50: the walking skeleton proves one tool call over the MCP rail.
The plugin declares `components.mcp.entry`, the host starts the server as a
confined subprocess, discovers tools via `tools/list`, and routes `tools/call`
through the live connection. Ruling A1 holds: the host never imports the
plugin's server module.

The test creates a minimal MCP server script, a manifest declaring it, and
proves the call reaches the subprocess and returns its answer.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from core.tools.dynamic_registry import (
    TRANSPORT_MCP,
    ToolDescriptor,
    default_registry,
    fingerprint_for,
)


SERVER_SCRIPT = '''\
import json
import sys

def _result(request_id, payload):
    return {"jsonrpc": "2.0", "id": request_id, "result": payload}

def _error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

def _tool_reply(text, *, is_error=False):
    return {
        "content": [{"type": "text", "text": text}],
        **({"isError": True} if is_error else {}),
    }

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(_error(None, -32700, "Parse error")) + "\\n")
            sys.stdout.flush()
            continue
        method = request.get("method")
        request_id = request.get("id")
        if method == "initialize":
            sys.stdout.write(json.dumps(_result(request_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "test-countdown", "version": "1.0.0"},
            })) + "\\n")
        elif method == "tools/list":
            sys.stdout.write(json.dumps(_result(request_id, {"tools": [
                {
                    "name": "mcp_countdown_set",
                    "description": "Start a countdown timer.",
                    "inputSchema": {
                        "type": "object",
                        "properties": {"seconds": {"type": "integer"}},
                        "required": ["seconds"],
                    },
                }
            ]})))
        elif method == "tools/call":
            params = request.get("params", {})
            name = params.get("name")
            arguments = params.get("arguments", {})
            if name == "mcp_countdown_set":
                seconds = arguments.get("seconds", 0)
                sys.stdout.write(json.dumps(_result(request_id, _tool_reply(
                    f"Countdown started: {seconds} seconds"
                ))) + "\\n")
            else:
                sys.stdout.write(json.dumps(_result(request_id, _tool_reply(
                    f"Unknown tool: {name}", is_error=True
                ))) + "\\n")
        else:
            sys.stdout.write(json.dumps(_error(request_id, -32601, f"Method not found: {method}")) + "\\n")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
'''


@pytest.fixture
def plugin_dir(tmp_path: Path) -> Path:
    """A minimal plugin bundle with an MCP server script."""
    bundle = tmp_path / "plugins" / "countdown"
    bundle.mkdir(parents=True)
    server_script = bundle / "server.py"
    server_script.write_text(SERVER_SCRIPT, encoding="utf-8")
    manifest = {
        "manifest_version": 2,
        "name": "countdown",
        "version": "1.0.0",
        "description": "A timer the agent can set and read back.",
        "publisher": {"name": "Ephe"},
        "license": "MIT",
        "origin": "first-party",
        "permissions": {"tool_families": ["read"], "data_roots": []},
        "components": {
            "tools": [
                {
                    "name": "mcp_countdown_set",
                    "transport": "mcp",
                    "family": "read",
                    "description": "Start a countdown timer.",
                    "parameters": {
                        "type": "object",
                        "properties": {"seconds": {"type": "integer"}},
                        "required": ["seconds"],
                    },
                }
            ],
            "mcp": {"entry": "server.py:main"},
        },
    }
    (bundle / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    return bundle


@pytest.fixture(autouse=True)
def clean_registry():
    """Unregister the test plugin after each test."""
    yield
    default_registry().unregister_plugin("countdown")


class TestPluginMCPRail:
    """The MCP rail: a plugin tool call reaches its confined server."""

    @pytest.mark.asyncio
    async def test_a_plugin_mcp_tool_call_reaches_the_confined_server(self, plugin_dir: Path, monkeypatch):
        """GIVEN a plugin with an MCP server and one tool declared on the MCP rail
        WHEN the tool is called via dispatch_dynamic_call
        THEN the call reaches the confined server and returns its answer."""
        from core.plugin_mcp_server import PluginMCPServerManager
        from core.tools.dynamic_wiring import dispatch_dynamic_call

        manager = PluginMCPServerManager()
        monkeypatch.setattr(
            "core.plugin_mcp_server.plugin_mcp_manager", lambda: manager
        )

        # Start the server and register the tool
        client = await manager.start_server("countdown", plugin_dir, "server.py:main")
        assert client is not None

        schema = {
            "type": "function",
            "function": {
                "name": "mcp_countdown_set",
                "description": "Start a countdown timer.",
                "parameters": {
                    "type": "object",
                    "properties": {"seconds": {"type": "integer"}},
                    "required": ["seconds"],
                },
            },
        }
        descriptor = ToolDescriptor(
            name="mcp_countdown_set",
            plugin_id="countdown",
            schema=schema,
            transport=TRANSPORT_MCP,
            entry=None,
            tool_family="read",
            fingerprint=fingerprint_for(schema),
            families=frozenset({"read"}),
        )
        assert default_registry().register(descriptor).ok

        # Call the tool
        result = await dispatch_dynamic_call("mcp_countdown_set", {"seconds": 42})

        assert result is not None
        assert "Countdown started: 42 seconds" in result
        assert "is not available" not in result

        # Clean up
        await manager.stop_server("countdown")

    @pytest.mark.asyncio
    async def test_a_plugin_mcp_tool_call_without_a_started_server_refuses(
        self, plugin_dir: Path, monkeypatch
    ):
        """GIVEN a registered MCP descriptor whose server was never started
        WHEN the tool is called
        THEN the call is refused with the existing 'not available' line."""
        from core.plugin_mcp_server import PluginMCPServerManager
        from core.tools.dynamic_wiring import dispatch_dynamic_call

        manager = PluginMCPServerManager()
        monkeypatch.setattr(
            "core.plugin_mcp_server.plugin_mcp_manager", lambda: manager
        )

        schema = {
            "type": "function",
            "function": {
                "name": "mcp_countdown_set",
                "description": "Start a countdown timer.",
                "parameters": {
                    "type": "object",
                    "properties": {"seconds": {"type": "integer"}},
                    "required": ["seconds"],
                },
            },
        }
        descriptor = ToolDescriptor(
            name="mcp_countdown_set",
            plugin_id="countdown",
            schema=schema,
            transport=TRANSPORT_MCP,
            entry=None,
            tool_family="read",
            fingerprint=fingerprint_for(schema),
            families=frozenset({"read"}),
        )
        assert default_registry().register(descriptor).ok

        # Call without starting the server
        result = await dispatch_dynamic_call("mcp_countdown_set", {"seconds": 10})

        assert result is not None
        assert "is not available" in result

    @pytest.mark.asyncio
    async def test_stopping_a_plugin_server_reaps_the_subprocess(
        self, plugin_dir: Path, monkeypatch
    ):
        """GIVEN a started plugin MCP server
        WHEN the server is stopped
        THEN the subprocess is reaped and no longer alive."""
        from core.plugin_mcp_server import PluginMCPServerManager

        manager = PluginMCPServerManager()
        client = await manager.start_server("countdown", plugin_dir, "server.py:main")
        assert client is not None
        assert manager.is_running("countdown")

        await manager.stop_server("countdown")

        assert not manager.is_running("countdown")


@pytest.fixture
def mcp_manager(monkeypatch):
    """A fresh MCP manager, so one test's subprocess cannot serve another's."""
    from core.plugin_mcp_server import PluginMCPServerManager

    manager = PluginMCPServerManager()
    monkeypatch.setattr(
        "core.plugin_mcp_server.plugin_mcp_manager", lambda: manager
    )
    yield manager
    try:
        manager.stop_all_sync()
    except Exception:  # noqa: BLE001 - teardown must not mask the test's own failure
        pass


@pytest.fixture
def rail_lane(tmp_path, monkeypatch, plugin_dir):
    """The fixture bundle installed in a hermetic root, with its own lifecycle."""
    from core import plugin_manifest, plugin_runtime
    from core.plugin_lifecycle import STATE_FILENAME, PluginLifecycle

    config = tmp_path / "cfg"
    config.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", plugin_dir.parent)
    plugin_runtime.invalidate_ownership_cache()
    lifecycle = PluginLifecycle(
        config / STATE_FILENAME, versions=plugin_runtime._installed_versions()
    )
    yield {"lifecycle": lifecycle, "config": config}
    plugin_runtime.invalidate_ownership_cache()


@pytest.mark.asyncio
async def test_mounting_a_bundle_starts_its_mcp_server_and_a_call_reaches_it(
    rail_lane, mcp_manager
):
    """GIVEN a mounted bundle that declares components.mcp
    WHEN the declared tool is called
    THEN the host started the confined server and the call returns its answer."""
    from core.tools.dynamic_wiring import dispatch_dynamic_call

    result = rail_lane["lifecycle"].mount("countdown")

    assert result.names == ("mcp_countdown_set",)
    assert mcp_manager.is_running("countdown")

    answer = await dispatch_dynamic_call("mcp_countdown_set", {"seconds": 42})

    assert "Countdown started: 42 seconds" in answer
    assert "is not available" not in answer

    rail_lane["lifecycle"].unmount("countdown")
    assert not mcp_manager.is_running("countdown")


@pytest.mark.asyncio
async def test_a_bundle_without_a_declared_server_does_not_reach_the_rail(
    rail_lane, mcp_manager
):
    """GIVEN a mounted bundle whose manifest declares no components.mcp
    WHEN its plugin id is asked for the MCP rail
    THEN no server was started and the call is refused."""
    directory = rail_lane["config"].parent / "plugins" / "countdown"
    manifest = json.loads((directory / "ephe-plugin.json").read_text(encoding="utf-8"))
    manifest["components"].pop("mcp")
    manifest["components"]["tools"] = [
        {
            "name": "plain_tick",
            "entry": "handlers.py:run",
            "family": "read",
            "description": "A plain plugin tool.",
            "parameters": {"type": "object", "properties": {}},
        }
    ]
    (directory / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (directory / "handlers.py").write_text(
        "def run(arguments, state_dir):\n    return {'ok': True}\n",
        encoding="utf-8",
    )

    result = rail_lane["lifecycle"].mount("countdown")

    assert result.names == ("plain_tick",)
    assert not mcp_manager.is_running("countdown")
    text, is_error = await mcp_manager.call_tool(
        "countdown", "mcp_countdown_set", {"seconds": 1}
    )
    assert is_error
    assert "unavailable" in text


@pytest.mark.asyncio
async def test_a_started_server_refuses_a_tool_the_manifest_did_not_declare(
    mcp_manager, plugin_dir
):
    """GIVEN a server started with the manifest's declared names
    WHEN a call names a tool outside that allowlist
    THEN the manager refuses it."""
    client = await mcp_manager.start_server(
        "countdown", plugin_dir, "server.py:main", allowed_tools=("mcp_countdown_set",)
    )

    assert client is not None
    text, is_error = await mcp_manager.call_tool(
        "countdown", "mcp_secret", {"seconds": 1}
    )

    assert is_error
    assert "not declared" in text
