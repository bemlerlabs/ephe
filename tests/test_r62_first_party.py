"""R62 — First-party plugin catalog (Extensions wave E3).

The catalog stops being empty slots: the repo ships `plugins/` directories
with real manifests (commands, permissions, metadata), the scanner knows the
builtin root, catalog entries carry manifest/version/sha256 of those
directories, and the product-plugin families (documents/code-shell/etc.)
gate their tool families like every other plugin.

1. repo plugins/ ship 14 valid manifests (v2 portfolio).
2. scan_plugins merges builtin + user roots; builtin first.
3. dir_sha256 is deterministic over sorted relative paths + bytes.
4. Catalog view: every builtin entry carries manifest=true, its version and
   a CORRECT sha256.
5. documents gates create_pdf; code-shell gates write_file (same
   E1 semantics: explicit registry entries only; legacy slugs migrate).
6. /research and /report surface via manifest_commands.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_manifest, plugin_runtime  # noqa: E402

BUILTIN_PLUGINS_DIR = ROOT / "plugins"
EXPECTED_IDS = {
    "web-research", "memory", "vision", "voice", "image-studio",
    "mcp-connector", "browser-use", "code-shell",
    "documents", "spreadsheets", "presentations",
    "plugin-creator", "skill-creator", "guide",
    "local-document-factory", "private-research-notebook",
}


class TestBuiltinManifests:

    def test_repo_ships_fourteen_valid_manifests(self):
        """G: repo plugins/ W: scan T: every builtin dir is a valid manifest."""
        found = {}
        for entry in plugin_manifest.scan_plugins():
            if entry["dir"].parent == BUILTIN_PLUGINS_DIR:
                found[entry["dir"].name] = entry
        assert set(found.keys()) == EXPECTED_IDS
        for name, entry in found.items():
            assert entry["error"] is None, f"{name}: {entry['error']}"
            assert entry["manifest"]["description"].strip()


class TestDirHash:

    def test_dir_sha256_deterministic_and_content_bound(self):
        h1 = plugin_manifest.dir_sha256(BUILTIN_PLUGINS_DIR / "web-research")
        h2 = plugin_manifest.dir_sha256(BUILTIN_PLUGINS_DIR / "web-research")
        assert h1 == h2 and len(h1) == 64
        other = plugin_manifest.dir_sha256(BUILTIN_PLUGINS_DIR / "memory")
        assert h1 != other


class TestCatalogReality:

    def test_catalog_entries_declare_manifest_version_and_correct_sha256(self):
        catalog = json.loads((ROOT / "plugin-catalog.json").read_text(encoding="utf-8"))
        entries = {e["name"]: e for seg in ("public", "personal") for e in catalog[seg]}
        assert EXPECTED_IDS <= set(entries.keys()), sorted(set(entries.keys()) - EXPECTED_IDS)
        for name in EXPECTED_IDS:
            entry = entries[name]
            assert entry.get("manifest") is True, name
            assert entry.get("version"), name
            expected = plugin_manifest.dir_sha256(BUILTIN_PLUGINS_DIR / name)
            assert entry.get("sha256") == expected, name


class TestNewFamilies:

    def test_document_plugin_gates_docs_tools(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        registry = tmp_path / "cfg" / "plugins.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({"plugins": [{"name": "documents", "enabled": False}]}))
        assert plugin_runtime.is_tool_visible("create_pdf") is False
        assert plugin_runtime.is_tool_visible("web_search") is True

    def test_legacy_document_factory_registry_migrates(self, tmp_path, monkeypatch):
        """E1: the old document-factory entry gates the split successors."""
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        registry = tmp_path / "cfg" / "plugins.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({"plugins": [{"name": "document-factory", "enabled": False}]}))
        assert plugin_runtime.is_tool_visible("create_pdf") is False
        assert plugin_runtime.is_tool_visible("create_xlsx") is False
        assert plugin_runtime.is_tool_visible("create_pptx_deck") is False

    def test_code_shell_gates_coding_tools(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        registry = tmp_path / "cfg" / "plugins.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({"plugins": [{"name": "code-shell", "enabled": False}]}))
        assert plugin_runtime.is_tool_visible("write_file") is False
        assert plugin_runtime.is_tool_visible("web_search") is True


class TestCommands:

    def test_first_party_commands_surface(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        cmds = {c["name"]: c for c in plugin_manifest.manifest_commands()}
        assert "/research" in cmds and cmds["/research"]["plugin"] == "web-research"
        assert "/report" in cmds and cmds["/report"]["plugin"] == "documents"
        assert "/fix" in cmds and cmds["/fix"]["plugin"] == "code-shell"
        assert "/memorize" in cmds and cmds["/memorize"]["plugin"] == "memory"

    def test_disabled_builtin_plugin_hides_command(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        registry = tmp_path / "cfg" / "plugins.json"
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text(json.dumps({"plugins": [{"name": "web-research", "enabled": False}]}))
        cmds = {c["name"] for c in plugin_manifest.manifest_commands()}
        assert "/research" not in cmds
        assert "/report" in cmds
