"""R61 — Plugin manifest v1 (Extensions wave E2).

Format contract for `ephe-plugin.json` (docs/PLUGINS.md):

1. A valid manifest loads: name (slug), version (semver), description,
   optional permissions (tool_families ⊆ known families, data_roots),
   optional components (skills, commands; agents/hooks/mcp reserved).
2. Fail-closed validation: unknown tool family, missing skill pack dir,
   bad slug/semver, or a name/directory mismatch is an ERROR — the plugin
   is quarantined (never half-loaded).
3. Fail-soft scan: one broken plugin directory never breaks the others.
4. Plugin enablement integrates: skills of a registry-disabled plugin are
   not loaded; master off = stock (no plugin skills).
5. Manifest commands surface as normalized slash commands with plugin id.
6. Catalog entries pass through declared `manifest`/`version`/`sha256`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_manifest  # noqa: E402
from core.plugin_store import REGISTRY_FILENAME  # noqa: E402

VALID_MANIFEST = {
    "manifest_version": 1,
    "name": "research-suite",
    "version": "1.0.0",
    "description": "Deep research bundle",
    "permissions": {"tool_families": ["read", "network"], "data_roots": []},
    "components": {
        "skills": ["deep-dive"],
        "commands": [{"name": "research", "description": "Run deep research", "template": "Research: {input}"}],
    },
}


def _make_plugin(root: Path, dirname: str, manifest: dict | None = VALID_MANIFEST, with_skill: bool = True) -> Path:
    pdir = root / dirname
    pdir.mkdir(parents=True, exist_ok=True)
    if manifest is not None:
        (pdir / plugin_manifest.MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
    if with_skill and manifest is not None:
        for skill in manifest.get("components", {}).get("skills", []):
            sdir = pdir / "skills" / skill
            sdir.mkdir(parents=True, exist_ok=True)
            (sdir / "SKILL.md").write_text(
                (
                    f"---\nname: {skill}\nversion: 1.0.0\ntrigger: /{skill}\n"
                    f"description: {skill} pack\n---\n"
                    f"# {skill}\n\n"
                    "## System Prompt\n"
                    "You are a focused assistant for this bundled pack. "
                    "Produce real artifact output, never simulated placeholders.\n"
                ),
                encoding="utf-8",
            )
    return pdir


@pytest.fixture
def proot(tmp_path, monkeypatch):
    root = tmp_path / "plugins"
    root.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", root)
    return root


class TestValidation:

    def test_valid_manifest_loads(self, proot):
        _make_plugin(proot, "research-suite")
        manifest, err = plugin_manifest.load_manifest(proot / "research-suite")
        assert err is None
        assert manifest["name"] == "research-suite"
        assert manifest["components"]["skills"] == ["deep-dive"]

    def test_bad_json_is_error(self, proot):
        pdir = proot / "broken"
        pdir.mkdir()
        (pdir / plugin_manifest.MANIFEST_FILENAME).write_text("{nope", encoding="utf-8")
        manifest, err = plugin_manifest.load_manifest(pdir)
        assert manifest is None and err

    def test_bad_semver_rejected(self, proot):
        bad = {**VALID_MANIFEST, "version": "1.0"}
        _make_plugin(proot, "research-suite", bad)
        _, err = plugin_manifest.load_manifest(proot / "research-suite")
        assert err and "version" in err.lower()

    def test_name_dir_mismatch_rejected(self, proot):
        _make_plugin(proot, "other-name")
        _, err = plugin_manifest.load_manifest(proot / "other-name")
        assert err and "name" in err.lower()

    def test_unknown_tool_family_fails_closed(self, proot):
        bad = {**VALID_MANIFEST, "permissions": {"tool_families": ["read", "root-everything"]}}
        _make_plugin(proot, "research-suite", bad)
        _, err = plugin_manifest.load_manifest(proot / "research-suite")
        assert err and "root-everything" in err

    def test_declared_skill_must_exist(self, proot):
        _make_plugin(proot, "research-suite", with_skill=False)
        _, err = plugin_manifest.load_manifest(proot / "research-suite")
        assert err and "deep-dive" in err

    def test_reserved_components_accepted(self, proot):
        m = {
            **VALID_MANIFEST,
            "components": {
                **VALID_MANIFEST["components"],
                "agents": [{"name": "scout", "tools": ["read_file"]}],
                "hooks": {"turn_end": []},
                "mcp": {"servers": []},
            },
        }
        manifest, err = plugin_manifest.load_manifest(_make_plugin(proot, "research-suite", m))
        assert err is None
        assert manifest["components"]["agents"]


class TestScanAndIntegration:

    def test_scan_is_fail_soft(self, proot):
        _make_plugin(proot, "research-suite")
        broken = proot / "broken"
        broken.mkdir()
        (broken / plugin_manifest.MANIFEST_FILENAME).write_text("{", encoding="utf-8")
        no_manifest = proot / "naked"
        no_manifest.mkdir()
        found = {entry["dir"].name: entry for entry in plugin_manifest.scan_plugins()}
        assert "research-suite" in found and found["research-suite"]["error"] is None
        assert found["broken"]["error"]
        assert found["naked"]["manifest"] is None

    def test_disabled_plugin_excluded_from_skill_roots(self, proot):
        _make_plugin(proot, "research-suite")
        (proot.parent / "cfg").mkdir(parents=True, exist_ok=True)
        (proot.parent / "cfg" / REGISTRY_FILENAME).write_text(
            json.dumps({"plugins": [{"name": "research-suite", "enabled": False}]}), encoding="utf-8"
        )
        assert plugin_manifest.active_skill_roots() == []

    def test_active_plugin_skill_root_listed(self, proot):
        _make_plugin(proot, "research-suite")
        roots = plugin_manifest.active_skill_roots()
        assert roots == [proot / "research-suite" / "skills" / "deep-dive"]

    def test_skill_loader_loads_plugin_pack(self, proot):
        """G: manifest plugin with skill pack W: SkillLoader T: trigger resolves."""
        from core.skills import SkillLoader

        _make_plugin(proot, "research-suite")
        loader = SkillLoader(plugin_root=proot)
        skill = loader.resolve_trigger("/deep-dive")
        assert skill is not None and skill.name == "deep-dive"

    def test_skill_loader_skips_disabled_plugin_pack(self, proot):
        from core.skills import SkillLoader

        _make_plugin(proot, "research-suite")
        (proot.parent / "cfg").mkdir(parents=True, exist_ok=True)
        (proot.parent / "cfg" / REGISTRY_FILENAME).write_text(
            json.dumps({"plugins": [{"name": "research-suite", "enabled": False}]}), encoding="utf-8"
        )
        loader = SkillLoader(plugin_root=proot)
        assert loader.resolve_trigger("/deep-dive") is None

    def test_manifest_commands_normalized(self, proot):
        _make_plugin(proot, "research-suite")
        cmds = plugin_manifest.manifest_commands()
        assert cmds == [
            {"name": "/research", "description": "Run deep research", "template": "Research: {input}", "plugin": "research-suite"}
        ]


class TestCatalogPassthrough:

    def test_view_carries_manifest_fields(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        from core import plugin_store

        catalog = tmp_path / "catalog.json"
        catalog.write_text(
            json.dumps({
                "version": 1,
                "public": [{
                    "name": "research-suite", "description": "d", "tags": [], "enabled": True,
                    "sha256": "abc", "url": "", "manifest": True, "version": "1.0.0",
                }],
                "personal": [],
            }),
            encoding="utf-8",
        )
        view = plugin_store.plugins_view(catalog_file=catalog)
        entry = view["public"][0]
        assert entry["manifest"] is True
        assert entry["sha256"] == "abc"
        assert entry["version"] == "1.0.0"
