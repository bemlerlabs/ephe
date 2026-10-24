"""
◑ Ephe – r70 (Extensions v2, E1): portfolio rebuild + legacy migration.
tests/test_r70_portfolio_v2.py

Pins:
1. 14 product plugins (v2 portfolio) with valid manifests; each carries
   `origin: first-party`.
2. The runtime mapping covers ALL 14 slugs (no orphaned catalog entry).
3. Legacy migration: the old slugs (web-search/image-gen/tts/mcp/shell/
   coding-suite/document-factory) map onto the new ones — document-factory
   splits into documents+spreadsheets+presentations; explicitly new
   entries win; no downgrade.
4. plugin-catalog.json agrees with plugins/ (sha256 = dir_sha256).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_runtime  # noqa: E402
from core.plugin_manifest import dir_sha256, load_manifest  # noqa: E402
from core.plugin_store import migrate_registry_items  # noqa: E402

PLUGINS = ROOT / "plugins"
EXPECTED_V2 = {
    "documents", "spreadsheets", "presentations", "web-research", "memory",
    "browser-use", "vision", "image-studio", "voice", "code-shell",
    "mcp-connector", "plugin-creator", "skill-creator", "guide",
    "local-document-factory", "private-research-notebook",
}


class TestPortfolio:

    def test_repo_ships_the_v2_portfolio(self):
        found = {
            d.name for d in PLUGINS.iterdir() if d.is_dir()
        }
        assert found == EXPECTED_V2, sorted(found ^ EXPECTED_V2)

    def test_every_manifest_valid_and_first_party(self):
        for d in sorted(PLUGINS.iterdir()):
            if not d.is_dir():
                continue
            manifest, err = load_manifest(d)
            assert manifest is not None, f"{d.name}: {err}"
            assert manifest["origin"] == "first-party", d.name

    def test_runtime_mapping_covers_whole_portfolio(self):
        from core.plugin_registry import PluginRegistry

        registry = PluginRegistry.load(PLUGINS, ROOT / "skills")
        assert {plugin.id for plugin in registry.plugins} == EXPECTED_V2
        for plugin in registry.plugins:
            for tool in plugin.manifest.get("components", {}).get("tools", []):
                assert registry.activation_owner(tool) == plugin.id

    def test_catalog_matches_disk(self):
        catalog = json.loads((ROOT / "plugin-catalog.json").read_text(encoding="utf-8"))
        entries = {e["name"]: e for e in catalog["public"]}
        assert set(entries.keys()) == EXPECTED_V2
        for name in EXPECTED_V2:
            assert entries[name]["sha256"] == dir_sha256(PLUGINS / name), name
            assert entries[name]["origin"] == "first-party", name


class TestLegacyMigration:

    def test_renames_map_one_to_one(self):
        out = migrate_registry_items([
            {"name": "web-search", "enabled": True},
            {"name": "image-gen", "enabled": False},
            {"name": "tts", "enabled": True},
            {"name": "mcp", "enabled": True},
            {"name": "shell", "enabled": True},
        ])
        by_name = {e["name"]: e["enabled"] for e in out}
        assert by_name == {
            "web-research": True, "image-studio": False, "voice": True,
            "mcp-connector": True, "code-shell": True,
        }

    def test_document_factory_splits_to_three(self):
        out = migrate_registry_items([{"name": "document-factory", "enabled": False}])
        assert {e["name"] for e in out} == {"documents", "spreadsheets", "presentations"}
        assert all(e["enabled"] is False for e in out)

    def test_explicit_new_slug_wins_over_legacy(self):
        out = migrate_registry_items([
            {"name": "coding-suite", "enabled": True},
            {"name": "code-shell", "enabled": False},
        ])
        assert len([e for e in out if e["name"] == "code-shell"]) == 1
        assert [e for e in out if e["name"] == "code-shell"][0]["enabled"] is False

    def test_runtime_gate_reads_legacy_registry(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        registry = tmp_path / "cfg" / "plugins.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({"plugins": [{"name": "shell", "enabled": False}]}))
        assert plugin_runtime.is_tool_visible("run_shell") is False
        assert plugin_runtime.is_tool_visible("write_file") is False

    def test_migration_never_breaks_on_garbage(self):
        assert migrate_registry_items([]) == []
        assert migrate_registry_items([{"nope": 1}, {"name": ""}]) == [{"nope": 1}]
