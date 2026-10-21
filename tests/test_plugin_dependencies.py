"""DEP-01..04 — exact versions, private-first resolution and fail-closed order.

The lockfile pins the exact version each plugin resolves to; the user root wins
over a built-in identity of the same name; a missing dependency or a cycle is
refused, and a disabled dependency blocks enable.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.plugin_lifecycle import LifecycleError, PluginLifecycle
from core.plugin_lockfile import LockfileError, build_lockfile, dependency_order


def _manifest(name: str, version: str, dependencies: list[str] | None = None) -> dict:
    return {
        "manifest_version": 1,
        "name": name,
        "version": version,
        "description": name,
        "permissions": {"tool_families": [], "data_roots": []},
        "components": {"skills": [], "commands": [], "tools": []},
        **({"dependencies": dependencies} if dependencies is not None else {}),
    }


def _write(root: Path, manifest: dict) -> Path:
    plugin = root / manifest["name"]
    plugin.mkdir(parents=True)
    (plugin / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    return plugin


def test_lockfile_pins_exact_versions_and_dependencies(tmp_path) -> None:
    _write(tmp_path, _manifest("base-pack", "1.0.0"))
    _write(tmp_path, _manifest("acme-research", "1.4.0", ["base-pack"]))
    lock = build_lockfile(tmp_path)
    entries = {entry["name"]: entry for entry in lock["plugins"]}
    assert entries["base-pack"]["version"] == "1.0.0"
    assert entries["acme-research"]["version"] == "1.4.0"
    assert entries["acme-research"]["dependencies"] == ["base-pack"]
    assert dependency_order(lock["plugins"]) == ("base-pack", "acme-research")


def test_private_resolution_wins_over_a_builtin_name(tmp_path, monkeypatch) -> None:
    config = tmp_path / "cfg"
    _write(config / "plugins", _manifest("web-research", "9.0.0"))
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    lock = build_lockfile(None)
    entry = next(item for item in lock["plugins"] if item["name"] == "web-research")
    assert entry["version"] == "9.0.0"
    assert entry["source"] == "user"


def test_cycles_and_missing_dependencies_fail_closed() -> None:
    with pytest.raises(LockfileError) as cycle:
        dependency_order(
            [
                {"name": "a", "dependencies": ["b"]},
                {"name": "b", "dependencies": ["a"]},
            ]
        )
    assert cycle.value.code == "dependency_cycle"
    with pytest.raises(LockfileError) as missing:
        dependency_order([{"name": "a", "dependencies": ["absent"]}])
    assert missing.value.code == "missing_dependency"


def test_a_disabled_dependency_blocks_enable(tmp_path) -> None:
    lifecycle = PluginLifecycle(
        tmp_path / "state.json",
        versions={"acme-research": "1.4.0", "base-pack": "1.0.0"},
        dependencies={"acme-research": ("base-pack",)},
        audit_sink=lambda entry: None,
    )
    lifecycle.set_enabled("acme-research", False)
    lifecycle.set_enabled("base-pack", False)
    with pytest.raises(LifecycleError) as err:
        lifecycle.set_enabled("acme-research", True)
    assert err.value.code == "dependency_blocked"
