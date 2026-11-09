"""Waterfall listeners: one plugin's events feed another's subscription.

The pub/sub bus filters by plugin_id and event type, so Plugin A can subscribe to
Plugin B's tool_registered events without receiving noise from Plugin C. The waterfall
is the chain: B registers a tool → A receives the event → A reacts (logs, transforms,
triggers its own tool, etc.).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from core.plugin_lifecycle import PluginLifecycle
from core.plugin_lifecycle_events import subscribe_filtered, unsubscribe


@pytest.fixture
def lifecycle(tmp_path: Path) -> PluginLifecycle:
    state = tmp_path / "lifecycle.json"
    state.write_text("{}")
    return PluginLifecycle(state, versions={})


@pytest.fixture
def plugin_a_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "plugin-a"
    bundle.mkdir()
    manifest = {
        "manifest_version": 2,
        "name": "plugin-a",
        "version": "1.0.0",
        "description": "Plugin A",
        "publisher": {"name": "Test"},
        "license": "MIT",
        "permissions": {"tool_families": ["read"], "data_roots": []},
        "components": {
            "skills": [],
            "commands": [],
            "tools": [
                {
                    "name": "tool_a1",
                    "entry": "handlers.py:tool_a1",
                    "family": "read",
                    "description": "A's tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            ],
        },
    }
    (bundle / "ephe-plugin.json").write_text(json.dumps(manifest))
    (bundle / "handlers.py").write_text("# stub")
    return bundle


@pytest.fixture
def plugin_b_bundle(tmp_path: Path) -> Path:
    bundle = tmp_path / "plugin-b"
    bundle.mkdir()
    manifest = {
        "manifest_version": 2,
        "name": "plugin-b",
        "version": "1.0.0",
        "description": "Plugin B",
        "publisher": {"name": "Test"},
        "license": "MIT",
        "permissions": {"tool_families": ["read"], "data_roots": []},
        "components": {
            "skills": [],
            "commands": [],
            "tools": [
                {
                    "name": "tool_b1",
                    "entry": "handlers.py:tool_b1",
                    "family": "read",
                    "description": "B's tool",
                    "parameters": {"type": "object", "properties": {}},
                },
            ],
        },
    }
    (bundle / "ephe-plugin.json").write_text(json.dumps(manifest))
    (bundle / "handlers.py").write_text("# stub")
    return bundle


def test_waterfall_subscriber_receives_only_filtered_events(
    lifecycle, plugin_a_bundle, plugin_b_bundle
):
    """Plugin A subscribes to Plugin B's events; Plugin A's own events don't loop back."""
    # Subscribe to plugin-b events only
    subscriber = subscribe_filtered(lifecycle._path, plugin_id="plugin-b")
    try:
        # Mount plugin-a — its events should NOT reach the subscriber
        with patch("core.plugin_lifecycle_mount.plugin_directory", return_value=plugin_a_bundle):
            lifecycle.mount("plugin-a")

        events_a = []
        while not subscriber.empty():
            events_a.append(subscriber.get_nowait())
        assert len(events_a) == 0, f"plugin-a events leaked to plugin-b subscriber: {events_a}"

        # Mount plugin-b — its events SHOULD reach the subscriber
        with patch("core.plugin_lifecycle_mount.plugin_directory", return_value=plugin_b_bundle):
            lifecycle.mount("plugin-b")

        events_b = []
        while not subscriber.empty():
            events_b.append(subscriber.get_nowait())
        assert len(events_b) >= 1, f"plugin-b events did not reach subscriber"

        # All received events are from plugin-b
        for event in events_b:
            assert event["data"].get("plugin") == "plugin-b" or event["data"].get("name") == "plugin-b"
    finally:
        unsubscribe(subscriber)


def test_waterfall_subscriber_filters_by_event_type(lifecycle, plugin_a_bundle):
    """Subscribe to a specific event type, receive only that type."""
    subscriber = subscribe_filtered(
        lifecycle._path, event_type="plugin.tool_registered"
    )
    try:
        with patch("core.plugin_lifecycle_mount.plugin_directory", return_value=plugin_a_bundle):
            lifecycle.mount("plugin-a")

        events = []
        while not subscriber.empty():
            events.append(subscriber.get_nowait())

        # Only tool_registered events, not the batch mount event
        for event in events:
            assert event["event"] == "plugin.tool_registered"
        assert len(events) >= 1, "expected at least one tool_registered event"
    finally:
        unsubscribe(subscriber)
