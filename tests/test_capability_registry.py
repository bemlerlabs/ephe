"""GAP-08 — declared permissions become runtime behaviour.

The declarative tool list is checked against one kernel mapping: a tool without a
family, or a declared tool whose family the manifest does not grant, is refused
at validation. Data roots are resolved into the plugin's file scope; the home
directory and system roots are refused as roots.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.plugin_manifest import load_manifest
from core.plugin_registry import (
    CapabilityDescriptor,
    CapabilityKind,
    PluginRegistry,
)


def _write(
    root: Path,
    name: str,
    *,
    families: list[str] | None = None,
    tools: list[str] | None = None,
    data_roots: list[str] | None = None,
) -> Path:
    plugin = root / name
    plugin.mkdir(parents=True)
    (plugin / "ephe-plugin.json").write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "name": name,
                "version": "1.0.0",
                "description": name,
                "permissions": {
                    "tool_families": families or [],
                    "data_roots": data_roots or [],
                },
                "components": {
                    "skills": [],
                    "commands": [],
                    "tools": tools or [],
                },
            }
        ),
        encoding="utf-8",
    )
    return plugin


def test_unique_owner_and_tool_owner_from_the_descriptor() -> None:
    registry = PluginRegistry.load(ROOT / "plugins", ROOT / "skills")
    ids = [capability.id for capability in registry.capabilities()]
    assert len(ids) == len(set(ids))
    assert {capability.owner for capability in registry.capabilities()} <= set(
        registry.owner_ids()
    )
    assert registry.activation_owner("web_search") == "web-research"
    assert registry.activation_owner("read_file") == "code-shell"
    tool = next(
        capability
        for capability in registry.capabilities(CapabilityKind.BUILTIN_TOOL)
        if capability.name == "web_search"
    )
    assert tool.owner == "kernel"


def test_an_orphan_capability_owner_is_refused() -> None:
    with pytest.raises(ValueError) as err:
        PluginRegistry(
            plugins=(),
            _capabilities=(
                CapabilityDescriptor(
                    id="tool:ghost",
                    kind=CapabilityKind.BUILTIN_TOOL,
                    owner="ghost",
                    name="ghost",
                    description="",
                    source="",
                ),
            ),
            _owners=frozenset({"kernel"}),
            _activations=(),
        )
    assert "orphan" in str(err.value)


def test_a_tool_needs_its_declared_family(tmp_path) -> None:
    good = _write(tmp_path / "good", "good", families=["read"], tools=["read_file"])
    manifest, error = load_manifest(good)
    assert error is None and manifest is not None

    bad = _write(tmp_path / "bad", "bad", families=[], tools=["read_file"])
    manifest, error = load_manifest(bad)
    assert manifest is None
    assert error is not None and "requires" in error


def test_an_unmapped_tool_is_refused(tmp_path) -> None:
    plugin = _write(
        tmp_path / "unknown",
        "unknown",
        families=["read"],
        tools=["not_a_kernel_tool"],
    )
    manifest, error = load_manifest(plugin)
    assert manifest is None
    assert error is not None and "no kernel permission mapping" in error


def test_data_roots_stay_relative_or_valid_and_never_cover_home(tmp_path) -> None:
    relative = _write(
        tmp_path / "relative",
        "relative",
        data_roots=["outputs"],
    )
    assert load_manifest(relative)[1] is None

    escaping = _write(
        tmp_path / "escaping",
        "escaping",
        data_roots=["../outside"],
    )
    manifest, error = load_manifest(escaping)
    assert manifest is None
    assert error is not None and "must not leave" in error

    home = _write(tmp_path / "home", "home", data_roots=[str(Path.home())])
    manifest, error = load_manifest(home)
    assert manifest is None
    assert error is not None and "home directory" in error


@pytest.mark.asyncio
async def test_a_declared_data_root_extends_only_that_plugins_file_scope(
    tmp_path, monkeypatch
) -> None:
    workspace = tmp_path / "workspace"
    declared = tmp_path / "declared"
    denied = tmp_path / "denied"
    config = tmp_path / "config"
    for directory in (workspace, declared, denied, config):
        directory.mkdir()
    (declared / "note.txt").write_text("declared", encoding="utf-8")
    (denied / "note.txt").write_text("denied", encoding="utf-8")
    _write(
        config / "plugins",
        "acme-research",
        data_roots=[str(declared)],
    )
    monkeypatch.setenv("EPHE_WORKSPACE", str(workspace))
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    from core.tools import file_ops
    from core.tools.base import FileNotAllowedError, PLUGIN_FILE_SCOPE

    token = PLUGIN_FILE_SCOPE.set("acme-research")
    try:
        assert "declared" in await file_ops.read_file(str(declared / "note.txt"))
        with pytest.raises(FileNotAllowedError) as err:
            await file_ops.read_file(str(denied / "note.txt"))
        assert "access denied" in str(err.value).lower()
    finally:
        PLUGIN_FILE_SCOPE.reset(token)
