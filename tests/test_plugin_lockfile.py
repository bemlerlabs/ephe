"""P1 — the plugin lockfile, dependency order and one-shot legacy import.

The lockfile is the reviewable record of what is installed: version, source,
hash, signature hash, dependencies and the effective scope. It is deterministic,
written atomically and compared against the disk before a release or a start.
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.plugin_lifecycle import PluginLifecycle
from core.plugin_lockfile import (
    LockfileError,
    build_lockfile,
    dependency_order,
    diff_lockfile,
    read_lockfile,
    write_lockfile,
)
from core.plugin_manifest import SIG_FILENAME, load_manifest


def _write_plugin(
    root: Path,
    name: str,
    version: str = "1.0.0",
    dependencies: list[str] | None = None,
) -> Path:
    plugin_dir = root / name
    plugin_dir.mkdir(parents=True)
    manifest = {
        "manifest_version": 1,
        "name": name,
        "version": version,
        "description": f"{name} test plugin",
        "permissions": {"tool_families": [], "data_roots": []},
        "components": {"skills": [], "commands": []},
    }
    if dependencies is not None:
        manifest["dependencies"] = dependencies
    (plugin_dir / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / "README.md").write_text(f"{name} {version}\n", encoding="utf-8")
    return plugin_dir


def test_lockfile_records_a_deterministic_install_set(tmp_path) -> None:
    _write_plugin(tmp_path, "base-pack")
    _write_plugin(
        tmp_path, "acme-research", version="1.4.0", dependencies=["base-pack"]
    )
    first = build_lockfile(tmp_path)
    second = build_lockfile(tmp_path)
    assert first == second
    assert first["schema"] == 1
    assert [entry["name"] for entry in first["plugins"]] == [
        "acme-research",
        "base-pack",
    ]
    acme = first["plugins"][0]
    assert acme["version"] == "1.4.0"
    assert acme["dependencies"] == ["base-pack"]
    assert acme["scope"] == "user"
    assert len(acme["sha256"]) == 64
    assert acme["signature_sha256"] == ""


def test_an_invalid_manifest_is_not_locked(tmp_path) -> None:
    _write_plugin(tmp_path, "broken")
    (tmp_path / "broken" / "ephe-plugin.json").write_text("{not json", encoding="utf-8")
    lock = build_lockfile(tmp_path)
    assert lock["plugins"] == []
    assert len(lock["quarantined"]) == 1
    assert lock["quarantined"][0]["name"] == "broken"
    assert lock["quarantined"][0]["error"].startswith("manifest unreadable:")


def test_a_declared_dependency_validates_and_a_bad_list_fails_closed(tmp_path) -> None:
    good = _write_plugin(tmp_path, "good", dependencies=["base-pack"])
    manifest, error = load_manifest(good)
    assert error is None
    assert manifest["dependencies"] == ["base-pack"]

    bad = _write_plugin(tmp_path, "bad", dependencies=["Not A Slug"])
    manifest, error = load_manifest(bad)
    assert manifest is None
    assert error is not None and "dependencies" in error


def test_drift_is_reported_by_kind(tmp_path) -> None:
    _write_plugin(tmp_path, "base-pack")
    acme = _write_plugin(
        tmp_path, "acme-research", version="1.4.0", dependencies=["base-pack"]
    )
    lock = build_lockfile(tmp_path)

    (acme / "README.md").write_text("edited\n", encoding="utf-8")
    drift = diff_lockfile(lock, tmp_path)
    assert {"name": "acme-research", "kind": "sha256"} in drift

    manifest = json.loads((acme / "ephe-plugin.json").read_text(encoding="utf-8"))
    manifest["version"] = "1.5.0"
    (acme / "ephe-plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
    drift = diff_lockfile(lock, tmp_path)
    assert {
        "name": "acme-research",
        "kind": "version",
        "expected": "1.4.0",
        "actual": "1.5.0",
    } in drift

    (tmp_path / "base-pack" / "ephe-plugin.json").unlink()
    drift = diff_lockfile(lock, tmp_path)
    assert {"name": "base-pack", "kind": "missing"} in drift


def test_signature_drift_is_distinct_from_content_drift(tmp_path) -> None:
    plugin = _write_plugin(tmp_path, "acme-research")
    sig = plugin / SIG_FILENAME
    sig.write_text('{"key_id": "k1", "signature": "abc"}', encoding="utf-8")
    lock = build_lockfile(tmp_path)
    entry = lock["plugins"][0]
    assert len(entry["signature_sha256"]) == 64

    sig.write_text('{"key_id": "k1", "signature": "def"}', encoding="utf-8")
    drift = diff_lockfile(lock, tmp_path)
    assert {"name": "acme-research", "kind": "signature"} in drift
    assert all(item["kind"] != "sha256" for item in drift)


def test_dependency_order_is_deterministic_and_cycles_fail() -> None:
    entries = [
        {"name": "app", "dependencies": ["ui", "core"]},
        {"name": "ui", "dependencies": ["core"]},
        {"name": "core", "dependencies": []},
    ]
    assert dependency_order(entries) == ("core", "ui", "app")

    with pytest.raises(LockfileError) as missing:
        dependency_order([{"name": "app", "dependencies": ["absent"]}])
    assert missing.value.code == "missing_dependency"

    with pytest.raises(LockfileError) as cycle:
        dependency_order(
            [
                {"name": "a", "dependencies": ["b"]},
                {"name": "b", "dependencies": ["a"]},
            ]
        )
    assert cycle.value.code == "dependency_cycle"


def test_lockfile_write_is_atomic_and_owner_only(tmp_path) -> None:
    _write_plugin(tmp_path, "base-pack")
    lock = build_lockfile(tmp_path)
    target = tmp_path / "state" / "plugin-lock.json"
    write_lockfile(target, lock)
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert read_lockfile(target) == lock


def test_legacy_state_is_imported_once_and_explicit_off_wins(tmp_path) -> None:
    legacy = tmp_path / "plugins.json"
    legacy.write_text(
        json.dumps(
            {
                "master_enabled": False,
                "plugins": [
                    {"name": "web-search", "enabled": False},
                    {"name": "mcp", "enabled": True},
                    {"name": "memory", "enabled": False},
                ],
            }
        ),
        encoding="utf-8",
    )
    audit: list[dict] = []
    calls: list[str] = []
    lifecycle = PluginLifecycle(
        tmp_path / "plugin-state.json",
        versions={"web-research": "1.0.0", "mcp-connector": "1.0.0", "memory": "1.0.0"},
        activator=calls.append,
        audit_sink=audit.append,
    )
    applied = lifecycle.import_legacy(legacy)
    assert applied == ("mcp-connector", "memory", "web-research")
    assert lifecycle.effective("web-research").enabled is False
    assert lifecycle.effective("mcp-connector").enabled is True
    assert lifecycle.effective("memory").enabled is False
    assert lifecycle.pause_all() is False
    assert calls == []
    assert [entry["action"] for entry in audit] == ["migrate", "migrate", "migrate"]

    assert lifecycle.import_legacy(legacy) == ()
    assert len(audit) == 3


def test_an_explicit_new_slug_beats_a_legacy_alias(tmp_path) -> None:
    legacy = tmp_path / "plugins.json"
    legacy.write_text(
        json.dumps(
            {
                "plugins": [
                    {"name": "web-search", "enabled": False},
                    {"name": "web-research", "enabled": True},
                ]
            }
        ),
        encoding="utf-8",
    )
    lifecycle = PluginLifecycle(
        tmp_path / "plugin-state.json",
        versions={"web-research": "1.0.0"},
        audit_sink=lambda entry: None,
    )
    assert lifecycle.import_legacy(legacy) == ("web-research",)
    assert lifecycle.effective("web-research").enabled is True
