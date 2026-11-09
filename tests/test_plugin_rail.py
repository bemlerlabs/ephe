"""#96 — which rail a bundle runs on, decided from its own manifest.

The Extensions row said a plugin is switched on. It did not say what kind of on: a version 1
bundle lists names of tools the host implements, so the bundle is a switch, while a version 2
bundle carries an entry per tool that the confined worker resolves inside the plugin
directory. Ruling A1 of the platform order is precisely that nothing here imports a plugin,
so a surface that blurs the two states something a reader can act on wrongly.

These tests pin the classifier and one invariant that keeps it honest while #94 and #95 move
bundles across: a version 1 manifest cannot be a worker, and a version 2 manifest that
declares entries cannot be a switch on kernel tools. The census of the shipped tree is
read and reported, never asserted, because the census is the thing the migration is about to
change.
"""
from __future__ import annotations

import pytest

from core import plugin_manifest
from core.plugin_rail import (
    RAIL_DECLARATIVE,
    RAIL_KERNEL,
    RAIL_WORKER,
    RAILS,
    rail_fact,
    rail_of,
)

V2_TOOLS = {
    "name": "demo",
    "manifest_version": plugin_manifest.MANIFEST_VERSION_V2,
    "publisher": "someone",
    "license": "MIT",
    "version": "1.0.0",
    "permissions": {"tool_families": ["read"]},
    "components": {
        "tools": [
            {
                "name": "tick",
                "entry": "tools/tick.py:run",
                "family": "read",
                "description": "counts",
            },
            {
                "name": "tock",
                "entry": "tools/tock.py:run",
                "family": "read",
                "description": "counts back",
            },
        ]
    },
}

V1_TOOLS = {
    "name": "switch",
    "manifest_version": plugin_manifest.MANIFEST_VERSION,
    "version": "1.0.0",
    "components": {"tools": ["vision_describe", "browser_go"]},
}


def test_a_version_two_entry_is_the_workers_own_rail() -> None:
    fact = rail_fact(V2_TOOLS)
    assert fact["rail"] == RAIL_WORKER
    assert fact["contributed"] == 2
    assert fact["activated"] == 0


def test_a_version_one_list_switches_the_kernels_tools() -> None:
    fact = rail_fact(V1_TOOLS)
    assert fact["rail"] == RAIL_KERNEL
    assert fact["activated"] == 2
    assert fact["contributed"] == 0


def test_a_bundle_that_declares_no_tool_runs_on_no_code_at_all() -> None:
    manifest = {
        "name": "quiet",
        "manifest_version": plugin_manifest.MANIFEST_VERSION,
        "components": {"skills": [], "commands": []},
    }
    assert rail_of(manifest) == RAIL_DECLARATIVE
    assert rail_fact(manifest) == {
        "rail": RAIL_DECLARATIVE,
        "contributed": 0,
        "activated": 0,
    }


@pytest.mark.parametrize("unreadable", [None, {}, "not a manifest", [], 7])
def test_a_manifest_nobody_could_read_is_no_rail_rather_than_a_guess(unreadable: object) -> None:
    """The rail of a bundle nobody read is not a fact the surface may state.

    It answers `declarative` here because that is the only rail that claims no code of its
    own; the store keeps the column off the payload entirely when no manifest was found, and
    that absence is what the row renders as nothing.
    """
    assert rail_fact(unreadable) == {
        "rail": RAIL_DECLARATIVE,
        "contributed": 0,
        "activated": 0,
    }


def test_the_version_alone_decides_whether_a_tool_is_the_bundles_own() -> None:
    """The invariant the migration runs on, in both directions.

    A `kernel` row means Ephe's code ran. If a version 1 manifest could ever be reported as
    a worker, the surface would credit a bundle with code it does not carry — so the shape of
    the entry, not a flag a bundle sets, is what the rail is read from.
    """
    assert rail_of(V1_TOOLS) != RAIL_WORKER
    upgraded = dict(V2_TOOLS, manifest_version=plugin_manifest.MANIFEST_VERSION)
    # v1 grammar takes strings, so the same objects declare nothing a v1 reader accepts.
    assert rail_of(upgraded) == RAIL_DECLARATIVE


def test_every_shipped_bundle_classifies_and_the_census_is_printed() -> None:
    """Every first-party manifest lands on one rail, and the split is shown rather than claimed."""
    census: dict[str, int] = {rail: 0 for rail in RAILS}
    counted = 0
    for entry in plugin_manifest.scan_plugins():
        if entry["error"] or not entry["manifest"]:
            continue
        rail = rail_of(entry["manifest"])
        assert rail in RAILS, entry["manifest"].get("name")
        census[rail] += 1
        counted += 1
    assert counted > 0, "no bundle was read, so the census proves nothing"
    # Printed rather than asserted. This is the number #94 and #95 move, and a test that
    # pinned the census would go red for the migration working.
    print(f"rail census over {counted} bundles: {census}")


def test_the_store_view_names_the_rail_where_a_manifest_was_read() -> None:
    """The payload the surface renders: a rail per entry whose manifest was found, and its two counts."""
    from core.plugin_store import plugins_view

    view = plugins_view()
    entries = [*view["public"], *view["personal"]]
    assert entries, "the catalogue is empty, so this read proves nothing"
    rails = [entry.get("rail") for entry in entries if entry.get("rail")]
    assert rails, "no entry carried a rail; the classification never reached the payload"
    for entry in entries:
        if "rail" not in entry:
            continue
        assert entry["rail"] in RAILS
        assert isinstance(entry["contributed_tools"], int)
        assert isinstance(entry["activated_tools"], int)
        # A rail is a fact about the entries, so it must agree with the counts beside it.
        if entry["rail"] == RAIL_WORKER:
            assert entry["contributed_tools"] > 0
        elif entry["rail"] == RAIL_KERNEL:
            assert entry["activated_tools"] > 0
        else:
            assert entry["contributed_tools"] == 0 and entry["activated_tools"] == 0
