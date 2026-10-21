"""MIG-01..05, MIG-07 — legacy registry import and the portfolio counts.

The import maps the legacy slugs once, keeps an explicit off, retires the old
global bypass with a notice, and preserves unrelated state. The shipped
portfolio is 14 plugins, 51 skills, 7 MCP entries and three legacy marketplace
ids; no plugin is deleted.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import mcp_catalog, plugin_manifest
from core.plugin_lifecycle import PluginLifecycle, PluginState
from core.plugin_registry import CapabilityKind, PluginRegistry
from core.plugin_store import migrate_registry_items


def _lifecycle(tmp_path, versions):
    return PluginLifecycle(
        tmp_path / "plugin-state.json",
        versions=versions,
        audit_sink=lambda entry: None,
    )


def _legacy(tmp_path, body: dict) -> Path:
    path = tmp_path / "plugins.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def test_legacy_map(tmp_path) -> None:
    out = migrate_registry_items(
        [
            {"name": "web-search", "enabled": False},
            {"name": "document-factory", "enabled": False},
            {"name": "coding-suite", "enabled": True},
            {"name": "mcp", "enabled": True},
        ]
    )
    by_name = {entry["name"]: entry["enabled"] for entry in out}
    assert by_name["web-research"] is False
    assert by_name["code-shell"] is True
    assert by_name["mcp-connector"] is True
    assert {
        "documents",
        "spreadsheets",
        "presentations",
    } <= set(by_name)
    assert all(by_name[name] is False for name in ("documents", "spreadsheets", "presentations"))


def test_explicit_off_survives_and_the_new_state_wins(tmp_path) -> None:
    lifecycle = _lifecycle(
        tmp_path, {"web-research": "1.0.0", "mcp-connector": "1.0.0"}
    )
    legacy = _legacy(
        tmp_path,
        {"plugins": [{"name": "web-search", "enabled": False}]},
    )
    assert lifecycle.import_legacy(legacy) == ("web-research",)
    assert lifecycle.effective("web-research").state is PluginState.DISABLED
    assert lifecycle.import_legacy(legacy) == ()

    legacy.write_text(
        json.dumps({"plugins": [{"name": "web-search", "enabled": True}]}),
        encoding="utf-8",
    )
    assert lifecycle.effective("web-research").state is PluginState.DISABLED


def test_missing_state_keeps_the_current_behavior(tmp_path) -> None:
    lifecycle = _lifecycle(tmp_path, {"web-research": "1.0.0"})
    assert lifecycle.effective("web-research").state is PluginState.ENABLED
    lifecycle.set_enabled("web-research", False)
    assert lifecycle.effective("web-research").state is PluginState.DISABLED


def test_legacy_master_false_retires_the_bypass_and_writes_a_notice(tmp_path) -> None:
    lifecycle = _lifecycle(tmp_path, {"web-research": "1.0.0", "memory": "1.0.0"})
    legacy = _legacy(
        tmp_path,
        {
            "master_enabled": False,
            "plugins": [{"name": "web-search", "enabled": False}],
        },
    )
    lifecycle.import_legacy(legacy)
    assert lifecycle.pause_all() is False
    assert lifecycle.effective("memory").state is PluginState.ENABLED
    assert lifecycle.effective("web-research").state is PluginState.DISABLED
    notices = lifecycle.notices()
    assert [notice["code"] for notice in notices] == [
        "legacy_master_bypass_retired"
    ]

    from core import plugin_runtime

    path = tmp_path / "plugin-state.json"
    assert any(
        notice["code"] == "legacy_master_bypass_retired"
        for notice in plugin_runtime.notices(path)
    )


def test_master_true_has_no_notice(tmp_path) -> None:
    lifecycle = _lifecycle(tmp_path, {"web-research": "1.0.0"})
    legacy = _legacy(
        tmp_path,
        {"master_enabled": True, "plugins": [{"name": "web-search", "enabled": True}]},
    )
    lifecycle.import_legacy(legacy)
    assert lifecycle.pause_all() is False
    assert lifecycle.notices() == ()


def test_atomic_merge_preserves_unrelated_state(tmp_path) -> None:
    lifecycle = _lifecycle(
        tmp_path, {"web-research": "1.0.0", "memory": "1.0.0"}
    )
    lifecycle.set_pause_all(True)
    lifecycle.set_enabled("web-research", False)
    lifecycle.set_enabled("memory", False)
    raw = json.loads((tmp_path / "plugin-state.json").read_text(encoding="utf-8"))
    assert raw["pause_all"] is True
    assert raw["plugins"]["web-research"]["user"]["committed"] == "disabled"
    assert raw["plugins"]["memory"]["user"]["committed"] == "disabled"


def test_portfolio_counts_and_no_deletion() -> None:
    registry = PluginRegistry.load(ROOT / "plugins", ROOT / "skills")
    assert len(registry.plugins) == 14
    assert len(registry.capabilities(CapabilityKind.SKILL)) == 51
    assert len(registry.capabilities(CapabilityKind.MCP_SERVER)) == 7
    assert len(mcp_catalog.catalog_entries()) == 7
    legacy = json.loads((ROOT / "plugin-marketplace.json").read_text(encoding="utf-8"))
    assert {
        entry["name"] for entry in legacy["plugins"]
    } == {"web-search", "document-factory", "coding-suite"}
    assert all((ROOT / "plugins" / name).is_dir() for name in {p.id for p in registry.plugins})
