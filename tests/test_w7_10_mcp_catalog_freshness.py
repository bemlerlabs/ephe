"""W7-10 — MCP catalogue freshness: a stale catalogue re-discovers.

``sync_mcp_tools`` already walks every ``tools/list`` page (the cursor-spin
guard, W3-40). W7-10 is the second half: the *registered* catalogue must not be
served once it has gone stale. A catalogue is stale when

* a server is configured but was never discovered (a failed startup sync),
* it is older than ``MCP_CATALOG_TTL_S`` (a server's tool set can change
  underneath a long-lived session), or
* the configured server set no longer matches the set the last discovery made
  (``mcp.json`` / ``EPHE_MCP_SERVERS`` changed out from under the process).

Reads re-discover instead of serving the old list — a synchronous read fires a
background refresh on the loop that owns the catalogue, the dispatch path awaits
one. When no server is configured the whole mechanism is inert, so a
hand-registered tool is never judged against a freshness window.

Every server here is a fake transport; the repository's own surface is only read.
"""
from __future__ import annotations

import asyncio

import pytest

import core.tools.mcp_client as mcp
from core.tools.mcp_client import MCP_CATALOG_TTL_S, parse_server_spec

_SPEC = "http://127.0.0.1:9/mcp"
_OTHER_SPEC = "http://127.0.0.1:8/mcp"


class _FakeClient:
    """A real stand-in for ``MCPClient``: no socket, a countable ``tools/list``."""

    instances: list["_FakeClient"] = []

    def __init__(self, endpoint, transport="http", label="", timeout=30.0, args=None):
        self.endpoint = endpoint
        self.transport = transport
        self.label = label
        self.args = args
        self.listed = 0
        self.calls: list[tuple[str, dict]] = []
        self.closed = False
        _FakeClient.instances.append(self)

    async def list_tools(self):
        self.listed += 1
        return [{"name": "read_text", "description": "read a file", "inputSchema": {}}]

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        return f"ok:{name}", False

    async def initialize(self):
        return None

    async def close(self):
        self.closed = True


def _age_catalog_past_the_window() -> None:
    mcp._MCP_DISCOVERED_AT -= (MCP_CATALOG_TTL_S + 1)


@pytest.fixture(autouse=True)
def _hermetic_mcp(monkeypatch):
    """Isolate the module globals this file drives (freshness + catalogue)."""
    _FakeClient.instances = []
    monkeypatch.setattr(mcp, "MCPClient", _FakeClient)
    monkeypatch.setattr(mcp, "_MCP_SERVERS", [])
    monkeypatch.setattr(mcp, "_MCP_TOOLS", {})
    monkeypatch.setattr(mcp, "_LIVE_CLIENTS", {})
    monkeypatch.setattr(mcp, "_MCP_DISCOVERED_AT", None)
    monkeypatch.setattr(mcp, "_MCP_DISCOVERED_SPECS", ())
    monkeypatch.setattr(mcp, "_MCP_ARMED_LOOP", None)
    monkeypatch.setattr(mcp, "_MCP_REFRESH_TASK", None)
    monkeypatch.setattr(mcp, "_invalidate_schema_cache", lambda: None)
    yield


# staleness — the three ways a catalogue goes stale, and the inert case


def test_a_configured_but_never_discovered_catalog_is_stale():
    mcp.set_mcp_servers([_SPEC])
    assert mcp.mcp_catalog_age() is None
    assert mcp.mcp_catalog_is_stale() is True


def test_a_config_change_makes_a_never_discovered_catalog_stale():
    mcp.set_mcp_servers([_SPEC])
    mcp.set_mcp_servers([_OTHER_SPEC])  # set_mcp_servers empties the registry
    assert mcp.mcp_catalog_age() is None
    assert mcp.mcp_catalog_is_stale() is True


def test_without_servers_the_catalog_is_never_stale():
    """The mechanism is inert with no configured server: a hand-registered tool
    (a test, a host that injects its own transport) is not a remote catalogue."""
    assert mcp.mcp_catalog_is_stale() is False
    mcp.register_mcp_tool("mcp_local", "local", "local", lambda *a, **k: None,
                          {"name": "mcp_local"})
    assert mcp.mcp_catalog_is_stale() is False


def test_a_freshly_synced_catalog_is_not_stale():
    mcp.set_mcp_servers([_SPEC])
    names = asyncio.run(mcp.sync_mcp_tools())
    assert names == ["mcp_read_text"]
    assert mcp.mcp_catalog_age() is not None
    assert mcp.mcp_catalog_is_stale() is False


def test_a_catalog_past_the_window_is_stale():
    mcp.set_mcp_servers([_SPEC])
    asyncio.run(mcp.sync_mcp_tools())
    at = mcp._MCP_DISCOVERED_AT
    assert mcp.mcp_catalog_is_stale(now=at + 1) is False
    assert mcp.mcp_catalog_is_stale(now=at + MCP_CATALOG_TTL_S + 1) is True


def test_a_changed_server_set_makes_a_discovered_catalog_stale(monkeypatch):
    """The drift case: the discovery is recent, but it was made for another set."""
    mcp.set_mcp_servers([_SPEC])
    asyncio.run(mcp.sync_mcp_tools())
    assert mcp.mcp_catalog_is_stale() is False
    monkeypatch.setattr(mcp, "_MCP_SERVERS", [parse_server_spec(_OTHER_SPEC)])
    assert mcp.mcp_catalog_age() is not None  # still recent ...
    assert mcp.mcp_catalog_is_stale() is True  # ... but for a different set


def test_unregister_resets_the_freshness_clock():
    mcp.set_mcp_servers([_SPEC])
    asyncio.run(mcp.sync_mcp_tools())
    assert mcp.mcp_catalog_is_stale() is False
    mcp.unregister_mcp_tools()
    assert mcp.mcp_catalog_age() is None
    assert mcp.mcp_catalog_is_stale() is True


# re-discovery — the awaited entry skips a fresh catalogue and re-runs a stale one


def test_ensure_rediscovers_a_stale_catalog_and_skips_a_fresh_one():
    mcp.set_mcp_servers([_SPEC])
    asyncio.run(mcp.sync_mcp_tools())

    assert asyncio.run(mcp.ensure_mcp_catalog_fresh()) is False, "fresh: no work"
    assert _FakeClient.instances[0].listed == 1

    _age_catalog_past_the_window()
    assert asyncio.run(mcp.ensure_mcp_catalog_fresh()) is True, "stale: re-discover"
    assert _FakeClient.instances[0].listed == 2, "the same server, a second discovery"
    assert mcp.mcp_catalog_is_stale() is False


def test_force_rediscovers_even_a_fresh_catalog():
    mcp.set_mcp_servers([_SPEC])
    asyncio.run(mcp.sync_mcp_tools())
    assert asyncio.run(mcp.ensure_mcp_catalog_fresh(force=True)) is True
    assert _FakeClient.instances[0].listed == 2


# serving — a stale catalogue is never served as current


def test_a_stale_read_rediscoveres_in_the_background():
    """The synchronous serving read (``get_mcp_tools``) fires a re-discovery on the
    loop that owns the catalogue, instead of leaving the recipe stale."""
    async def scenario():
        mcp.set_mcp_servers([_SPEC])
        await mcp.sync_mcp_tools()  # arms discovery on THIS loop
        assert mcp.mcp_catalog_is_stale() is False
        _age_catalog_past_the_window()
        assert mcp.mcp_catalog_is_stale() is True

        mcp.get_mcp_tools()  # the stale read
        task = mcp._MCP_REFRESH_TASK
        assert task is not None, "a stale read must trigger a re-discovery"
        await task
        assert mcp.mcp_catalog_is_stale() is False

    asyncio.run(scenario())
    assert _FakeClient.instances[0].listed == 2


def test_a_read_on_a_foreign_loop_never_spawns_a_refresh():
    """Only the loop that armed discovery refreshes; a foreign loop (a short-lived
    test loop, another worker) never spawns an MCP subprocess."""
    mcp.set_mcp_servers([_SPEC])
    asyncio.run(mcp.sync_mcp_tools())  # armed on a loop that is now closed
    _age_catalog_past_the_window()

    async def scenario():
        mcp.get_mcp_tools()  # stale, but on a different loop
        await asyncio.sleep(0)
        return mcp._MCP_REFRESH_TASK

    assert asyncio.run(scenario()) is None
    assert _FakeClient.instances[0].listed == 1, "no second discovery on a foreign loop"


def test_dispatch_re_discoveres_a_stale_catalog():
    async def scenario():
        mcp.set_mcp_servers([_SPEC])
        assert await mcp.sync_mcp_tools() == ["mcp_read_text"]
        _age_catalog_past_the_window()
        text, is_error = await mcp.call_registered_mcp_tool("mcp_read_text", {"path": "x"})
        assert is_error is False and text == "ok:read_text"
        return _FakeClient.instances[0].listed

    assert asyncio.run(scenario()) == 2, "the dispatch re-discovered before it ran"


def test_dispatch_on_a_fresh_catalog_does_not_re_discover():
    async def scenario():
        mcp.set_mcp_servers([_SPEC])
        await mcp.sync_mcp_tools()
        text, is_error = await mcp.call_registered_mcp_tool("mcp_read_text", {})
        assert is_error is False and text == "ok:read_text"
        return _FakeClient.instances[0].listed

    assert asyncio.run(scenario()) == 1


def test_a_sync_keeps_a_hand_registered_tool():
    """A catalogue sync clears what a previous sync found, never a hand-registered tool.

    Measured 2026-10-12 in the full suite: sync_mcp_tools() began with
    unregister_mcp_tools(), so the background refresh deleted a hand-registered tool while
    its call was in flight and the caller was told "unknown MCP tool".
    """

    async def scenario():
        mcp.unregister_mcp_tools()
        mcp.set_mcp_servers([_SPEC])
        await mcp.sync_mcp_tools()
        mcp.register_mcp_tool(
            "mcp_handmade", "hand", "probe",
            lambda arguments=None: ("ok", False), {"name": "mcp_handmade"},
        )
        # A refresh runs as a background task off a read; it must drop what the sync found
        # and leave the hand-registered tool alone.
        await mcp.sync_mcp_tools()
        kept = "mcp_handmade" in mcp.mcp_tool_names()
        assert "mcp_read_text" in mcp.mcp_tool_names(), "the sync's own tools should return"
        mcp.unregister_mcp_tools()
        return kept

    assert asyncio.run(scenario()) is True
