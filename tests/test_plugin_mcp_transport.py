"""◑ Ephe · TDD — a bundle tool can ride the MCP rail its own manifest declares.

Measured on e1ec1e68: `descriptors_for` hard-codes TRANSPORT_PLUGIN, so no manifest
can reach the MCP rail. TRANSPORT_MCP exists only in the registry vocabulary and in
tests that build a descriptor by hand. `components.mcp` is accepted structurally and
never read. That is blocker (1) of #50 at the descriptor layer.

The served name keeps the MCP rail's `mcp_` prefix: the registry's namespace rule
requires it for an MCP-transport descriptor, and the bundle declares the full name.
Ownership is still the bundle's, because `_gate_with` reads `activations.get(name)`
before the blanket connector rule — a name a manifest declares is answered by that
manifest, and the connector rule only fires for a name no manifest owns. These tests
pin the transport path and the server entry it needs; the confined server and the
live call are the next slice.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.plugin_tools_contract import descriptors_for, tool_claims, validate_tools


def _manifest(tools: list, mcp: object = None) -> dict:
    components: dict = {"tools": tools}
    if mcp is not None:
        components["mcp"] = mcp
    return {
        "manifest_version": 2,
        "name": "countdown",
        "version": "1.0.0",
        "description": "A timer the agent can set and read back.",
        "publisher": {"name": "Ephe"},
        "license": "MIT",
        "origin": "first-party",
        "permissions": {"tool_families": ["read"], "data_roots": []},
        "components": components,
    }


def _mcp_tool(name: str = "mcp_countdown_set", **extra) -> dict:
    return {
        "name": name,
        "transport": "mcp",
        "family": "read",
        "description": "Start a countdown.",
        **extra,
    }


SERVER = {"entry": "server.py:main"}


def test_an_mcp_tool_validates_and_carries_the_transport(tmp_path: Path):
    """GIVEN a bundle that declares a server and one tool riding it
    WHEN the manifest validates and the descriptors are built
    THEN the tool is accepted and its descriptor carries the MCP transport."""
    manifest = _manifest([_mcp_tool()], SERVER)

    assert validate_tools(manifest, tmp_path) is None
    descriptors = descriptors_for(manifest)

    assert len(descriptors) == 1
    assert descriptors[0].transport == "mcp"
    assert descriptors[0].entry is None
    assert descriptors[0].name == "mcp_countdown_set"
    assert descriptors[0].plugin_id == "countdown"


def test_an_mcp_tool_without_a_server_is_quarantined(tmp_path: Path):
    """GIVEN a tool that claims the MCP rail and no server to ride
    WHEN the manifest validates
    THEN it is refused and the sentence names the missing declaration."""
    error = validate_tools(_manifest([_mcp_tool()]), tmp_path)

    assert error is not None
    assert "components.mcp" in error


def test_an_unknown_transport_is_quarantined(tmp_path: Path):
    """GIVEN a transport outside the two the registry carries
    WHEN the manifest validates
    THEN it is refused rather than defaulted."""
    error = validate_tools(
        _manifest([_mcp_tool(transport="carrier-pigeon")], SERVER), tmp_path
    )

    assert error is not None
    assert "transport" in error


def test_an_mcp_tool_carrying_an_entry_is_quarantined(tmp_path: Path):
    """GIVEN an MCP tool that also names a plugin callable
    WHEN the manifest validates
    THEN it is refused: the server owns the callable, not two authorities."""
    error = validate_tools(
        _manifest([_mcp_tool(entry="handlers.py:run")], SERVER), tmp_path
    )

    assert error is not None
    assert "entry" in error


def test_a_plugin_tool_still_requires_its_entry(tmp_path: Path):
    """GIVEN a tool with no transport field, which is the plugin rail
    WHEN the manifest validates without an entry
    THEN the existing refusal stands."""
    tool = {"name": "tick", "family": "read", "description": "Tick."}

    error = validate_tools(_manifest([tool]), tmp_path)

    assert error is not None
    assert "entry" in error
    assert validate_tools(_manifest([{**tool, "entry": "handlers.py:run"}]), tmp_path) is None


def test_the_server_entry_may_not_escape_the_bundle(tmp_path: Path):
    """GIVEN a server entry that leaves the plugin directory
    WHEN the manifest validates
    THEN it is refused by the same lexical rule a tool entry uses."""
    error = validate_tools(
        _manifest([_mcp_tool()], {"entry": "../outside.py:main"}), tmp_path
    )

    assert error is not None
    assert "components.mcp" in error


def test_the_server_declaration_needs_an_entry(tmp_path: Path):
    """GIVEN a server declaration that is not a dict with an entry
    WHEN the manifest validates
    THEN it is refused."""
    for bad in ({}, {"entry": ""}, "stdio:server.py", []):
        error = validate_tools(_manifest([_mcp_tool()], bad), tmp_path)
        assert error is not None, bad
        assert "components.mcp" in error


def test_the_served_name_stays_declared_and_the_scan_owns_it(tmp_path: Path):
    """GIVEN a mounted-shape bundle whose tool rides the MCP rail
    WHEN the activation scan reads the portfolio
    THEN the declared name is owned by the bundle."""
    from core.plugin_registry import scan_tool_activations

    bundle = tmp_path / "plugins" / "countdown"
    bundle.mkdir(parents=True)
    (bundle / "ephe-plugin.json").write_text(
        json.dumps(_manifest([_mcp_tool()], SERVER)), encoding="utf-8"
    )

    activations = scan_tool_activations(tmp_path / "plugins")

    assert dict(activations.owners).get("mcp_countdown_set") == "countdown"
    assert "mcp_countdown_set" not in activations.conflicts
    claims = tool_claims(_manifest([_mcp_tool()], SERVER))
    assert claims[0].name == "mcp_countdown_set"