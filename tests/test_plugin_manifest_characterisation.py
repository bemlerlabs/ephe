"""Characterisation of the manifest contract before the v2 seam moves it.

`core/plugin_manifest.py` keeps the loading and scanning half; the contract half moves
to `core/plugin_manifest_contract.py` in the same change that adds
`capabilities.memory`. These tests were written and run green *before* that move: they
pin what a caller can observe — the exact refusal sentence per broken manifest, the
containment `_under` enforces, and the two scans a plugin's commands and skill packs ride
on — so the move is provably a move.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _write(root: Path, manifest: dict) -> Path:
    directory = root / str(manifest["name"])
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ephe-plugin.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    return directory


def _v1() -> dict:
    return {
        "manifest_version": 1,
        "name": "acme-tools",
        "version": "1.3.0",
        "description": "Acme tools",
        "permissions": {"tool_families": ["read"], "data_roots": []},
        "components": {
            "skills": ["acme-pack"],
            "commands": [
                {"name": "acme", "description": "Run acme", "template": "Use {input}"}
            ],
        },
    }


def _healthy(root: Path) -> Path:
    """The v1 manifest plus the skill pack it declares."""
    directory = _write(root, _v1())
    (directory / "skills" / "acme-pack").mkdir(parents=True)
    (directory / "skills" / "acme-pack" / "SKILL.md").write_text(
        "---\nname: acme-pack\ndescription: Acme\n---\n", encoding="utf-8"
    )
    return directory


@pytest.fixture()
def root(tmp_path):
    directory = tmp_path / "plugins"
    directory.mkdir()
    return directory


@pytest.fixture()
def scans(root, tmp_path, monkeypatch):
    """Scan fixtures with a config root of their own, so no real state is read."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "config"))
    from core import plugin_manifest, plugin_runtime

    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", root)
    plugin_runtime.invalidate_ownership_cache()
    yield root
    plugin_runtime.invalidate_ownership_cache()


class TestRefusals:
    def test_a_healthy_v1_manifest_loads(self, root) -> None:
        from core.plugin_manifest import load_manifest

        manifest, error = load_manifest(_healthy(root))
        assert error is None
        assert manifest["name"] == "acme-tools"

    @pytest.mark.parametrize(
        ("change", "expected"),
        [
            ({"manifest_version": 3}, "manifest_version: must be one of [1, 2]"),
            ({"name": "Acme_Tools"}, "name: lowercase slug expected (a-z0-9-)"),
            ({"version": "1.3"}, "version: semver X.Y.Z expected"),
            ({"description": "  "}, "description: non-empty string expected"),
            ({"surprise": 1}, "unknown top-level field(s): surprise"),
            (
                {"permissions": {"tool_families": ["telepathy"]}},
                "permissions.tool_families: unknown family 'telepathy' (fail-closed quarantine)",
            ),
            (
                {"permissions": {"data_roots": ["/etc"]}},
                "permissions.data_roots: '/etc' is not a usable directory",
            ),
            (
                {"components": {"nonsense": []}},
                "components: unknown component(s): nonsense",
            ),
            (
                {"components": {"skills": ["missing-pack"]}},
                "components.skills: declared pack 'missing-pack' does not ship a SKILL.md",
            ),
            (
                {"components": {"commands": [{"name": "ok"}]}},
                "components.commands.ok: description required",
            ),
            (
                {"icon": "../escape.svg", "components": {}},
                "icon: must be a relative path inside the plugin directory",
            ),
        ],
    )
    def test_the_refusal_sentence_per_broken_manifest(self, root, change, expected) -> None:
        from core.plugin_manifest import load_manifest

        manifest = _v1()
        manifest.update(change)
        if "permissions" in change:
            manifest["permissions"] = change["permissions"]
        if "components" in change:
            manifest["components"] = change["components"]
        _manifest, error = load_manifest(_write(root, manifest))
        assert error == expected

    def test_the_directory_name_has_to_match(self, root) -> None:
        from core.plugin_manifest import load_manifest

        directory = _write(root, _v1())
        other = directory.parent / "other-name"
        directory.rename(other)
        _manifest, error = load_manifest(other)
        assert error == "name: 'acme-tools' does not match directory 'other-name'"


class TestContainment:
    def test_under_keeps_a_child_inside(self, root) -> None:
        from core.plugin_manifest import _under

        (root / "file.txt").write_text("x", encoding="utf-8")
        assert _under(root, "file.txt") == (root / "file.txt").resolve()

    @pytest.mark.parametrize("parts", [("..", "outside.txt"), ("sub", "..", "..", "out.txt")])
    def test_under_refuses_a_way_out(self, root, parts) -> None:
        from core.plugin_manifest import _under

        assert _under(root, *parts) is None


class TestScans:
    def test_skill_packs_and_commands_of_an_active_plugin(self, scans) -> None:
        from core import plugin_manifest

        directory = _healthy(scans)
        assert plugin_manifest.active_skill_roots() == [
            (directory / "skills" / "acme-pack").resolve()
        ]
        commands = plugin_manifest.manifest_commands()
        assert commands == [
            {
                "name": "/acme",
                "description": "Run acme",
                "template": "Use {input}",
                "plugin": "acme-tools",
            }
        ]

    def test_a_broken_folder_does_not_break_the_scan(self, scans) -> None:
        from core import plugin_manifest

        _healthy(scans)
        broken = scans / "broken"
        broken.mkdir()
        (broken / "ephe-plugin.json").write_text("{not json", encoding="utf-8")
        scanned = plugin_manifest.scan_plugins()
        by_name = {entry["dir"].name: entry["error"] for entry in scanned}
        assert by_name["broken"] == "manifest unreadable"
        assert by_name["acme-tools"] is None
