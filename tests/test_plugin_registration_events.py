"""Registrations produce observable effects on the SSE bus.

A mount emits one event per tool registered, so a surface watching a plugin sees each
tool arrive individually — not one batch event the surface has to decompose.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core.plugin_lifecycle import PluginLifecycle
from core.plugin_lifecycle_events import subscribe, unsubscribe


@pytest.fixture
def lifecycle(tmp_path: Path) -> PluginLifecycle:
    state = tmp_path / "lifecycle.json"
    state.write_text("{}")
    return PluginLifecycle(state, versions={})


@pytest.fixture
def plugin_bundle(tmp_path: Path) -> Path:
    """A minimal v2 plugin bundle with two tools."""
    bundle = tmp_path / "test-plugin"
    bundle.mkdir()
    manifest = {
        "manifest_version": 2,
        "name": "test-plugin",
        "version": "1.0.0",
        "description": "Test plugin for registration events",
        "publisher": {"name": "Test"},
        "license": "MIT",
        "permissions": {
            "tool_families": ["read"],
            "data_roots": [],
        },
        "components": {
            "skills": [],
            "commands": [],
            "tools": [
                {
                    "name": "tool_a",
                    "entry": "handlers.py:tool_a",
                    "family": "read",
                    "description": "First tool",
                    "parameters": {"type": "object", "properties": {}},
                },
                {
                    "name": "tool_b",
                    "entry": "handlers.py:tool_b",
                    "family": "read",
                    "description": "Second tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            ],
        },
    }
    (bundle / "ephe-plugin.json").write_text(json.dumps(manifest))
    (bundle / "handlers.py").write_text("# stub")
    return bundle


def test_mount_emits_one_event_per_tool(lifecycle, plugin_bundle, tmp_path):
    """The registration effect: each tool produces its own observable event."""
    subscriber = subscribe(lifecycle._path)
    try:
        with patch("core.plugin_lifecycle_mount.plugin_directory", return_value=plugin_bundle):
            lifecycle.mount("test-plugin")

        events = []
        while not subscriber.empty():
            events.append(subscriber.get_nowait())

        # One event per tool, not one batch event
        tool_events = [e for e in events if e["event"] == "plugin.tool_registered"]
        assert len(tool_events) == 2, f"expected 2 tool events, got {len(tool_events)}: {events}"

        tool_names = {e["data"]["tool"] for e in tool_events}
        assert tool_names == {"tool_a", "tool_b"}

        # Each event carries the plugin id
        for event in tool_events:
            assert event["data"]["plugin"] == "test-plugin"
    finally:
        unsubscribe(subscriber)
