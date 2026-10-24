"""P1 — plugin ownership at the runtime boundary.

A plugin owns its tools, skills and commands through descriptors. Disabling it
removes all of them from the next turn, while kernel tools without an activation
owner stay visible. The legacy registry is imported once; its master bypass is
retired and explicit off entries win.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_manifest, plugin_runtime
from core.plugin_lifecycle import STATE_FILENAME, PluginLifecycle
from core.plugin_registry import PluginRegistry
from core.plugin_store import config_root

EXPECTED_ACTIVATIONS = {
    "analyze_image": "vision",
    "analyze_project": "code-shell",
    "browser_click": "browser-use",
    "browser_evaluate": "browser-use",
    "browser_exec": "browser-use",
    "browser_go": "browser-use",
    "browser_press": "browser-use",
    "browser_screenshot": "browser-use",
    "browser_scroll": "browser-use",
    "browser_type": "browser-use",
    "build_document": "documents",
    "create_diagram": "presentations",
    "create_docx": "documents",
    "create_pdf": "documents",
    "create_pitch_deck": "presentations",
    "create_pptx_deck": "presentations",
    "create_qrcode": "documents",
    "create_source_notebook": "documents",
    "create_svg": "presentations",
    "create_xlsx": "spreadsheets",
    "edit_file": "code-shell",
    "edit_pptx_template": "presentations",
    "export_source_brief": "documents",
    "extract_pdf_text": "documents",
    "fetch_url": "web-research",
    "file_search": "code-shell",
    "format_code": "code-shell",
    "generate_chart": "spreadsheets",
    "generate_image": "image-studio",
    "inspect_pptx_template": "presentations",
    "list_directory": "code-shell",
    "load_workspace": "code-shell",
    "memory": "memory",
    "qa_pptx_deck": "presentations",
    "query_source_notebook": "documents",
    "read_file": "code-shell",
    "run_linter": "code-shell",
    "run_shell": "code-shell",
    "run_tests": "code-shell",
    "scaffold_project": "code-shell",
    "verify_artifact": "documents",
    "vision_click": "vision",
    "vision_type": "vision",
    "web_search": "web-research",
    "write_file": "code-shell",
}


@pytest.fixture()
def device(tmp_path, monkeypatch):
    root = tmp_path / "cfg"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(root))
    plugin_runtime.invalidate_ownership_cache()
    yield root
    plugin_runtime.invalidate_ownership_cache()


def _versions() -> dict[str, str]:
    return {
        str(entry["manifest"]["name"]): str(entry["manifest"]["version"])
        for entry in plugin_manifest.scan_plugins()
        if entry["manifest"] and not entry["error"]
    }


def _lifecycle() -> PluginLifecycle:
    return PluginLifecycle(
        config_root() / STATE_FILENAME,
        versions=_versions(),
        audit_sink=lambda entry: None,
    )


def _schemas(*names: str) -> list[dict]:
    return [{"type": "function", "function": {"name": name}} for name in names]


def _write_user_plugin(root: Path) -> None:
    plugin = root / "plugins" / "acme-research"
    pack = plugin / "skills" / "acme-pack"
    pack.mkdir(parents=True)
    (pack / "SKILL.md").write_text(
        """---
name: acme-pack
version: "1.0.0"
trigger: /acme-pack
description: "Acme pack instructions."
tools: [create_video]
allowed_tools: [create_video]
---

# acme-pack

**Trigger**: /acme-pack
**Description**: Acme pack instructions.
**Tools**: create_video

## System Prompt
Use create_video.

## Test
**Input**: run acme
**Expect Tool**: create_video
**Expect Contains**: acme
""",
        encoding="utf-8",
    )
    (plugin / "ephe-plugin.json").write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "name": "acme-research",
                "version": "1.4.0",
                "description": "Acme research plugin",
                "permissions": {"tool_families": ["write"], "data_roots": []},
                "components": {
                    "skills": ["acme-pack"],
                    "commands": [
                        {
                            "name": "acme",
                            "description": "Run acme research",
                            "template": "Research: {input}",
                        }
                    ],
                    "tools": ["create_video"],
                },
            }
        ),
        encoding="utf-8",
    )


def test_the_manifests_cover_the_retired_family_map() -> None:
    registry = PluginRegistry.load(ROOT / "plugins", ROOT / "skills")
    assert dict(registry.tool_activations()) == EXPECTED_ACTIVATIONS


def test_disabling_a_plugin_removes_all_its_tools(device) -> None:
    _lifecycle().set_enabled("code-shell", False)
    visible = [
        entry["function"]["name"]
        for entry in plugin_runtime.filter_schemas(
            _schemas("read_file", "run_shell", "web_search", "ask_user")
        )
    ]
    assert visible == ["web_search", "ask_user"]
    gate = plugin_runtime.tool_gate("read_file")
    assert gate.visible is False
    assert gate.plugin == "code-shell"


def test_next_turn_removes_all(device) -> None:
    _write_user_plugin(device)
    plugin_runtime.invalidate_ownership_cache()
    assert any(
        "acme-pack" in str(path) for path in plugin_manifest.active_skill_roots()
    )
    assert any(
        command["name"] == "/acme" for command in plugin_manifest.manifest_commands()
    )
    assert plugin_runtime.is_tool_visible("create_video") is True

    _lifecycle().set_enabled("acme-research", False)
    assert not any(
        "acme-pack" in str(path) for path in plugin_manifest.active_skill_roots()
    )
    assert not any(
        command["name"] == "/acme" for command in plugin_manifest.manifest_commands()
    )
    assert plugin_runtime.is_tool_visible("create_video") is False


def test_the_mcp_namespace_follows_the_connector_switch(device) -> None:
    _lifecycle().set_enabled("mcp-connector", False)
    assert plugin_runtime.is_tool_visible("mcp_github_search") is False
    assert plugin_runtime.is_tool_visible("read_file") is True


def test_pause_all_hides_owned_tools_but_keeps_kernel_tools(device) -> None:
    _lifecycle().set_pause_all(True)
    visible = [
        entry["function"]["name"]
        for entry in plugin_runtime.filter_schemas(_schemas("web_search", "ask_user"))
    ]
    assert visible == ["ask_user"]


def test_the_runtime_keeps_one_lifecycle_instance(device) -> None:
    assert plugin_runtime.lifecycle() is plugin_runtime.lifecycle()


def test_legacy_off_is_imported_once_and_the_new_state_wins(device) -> None:
    legacy = device / "plugins.json"
    legacy.parent.mkdir(parents=True, exist_ok=True)
    legacy.write_text(
        json.dumps({"plugins": [{"name": "web-research", "enabled": False}]}),
        encoding="utf-8",
    )
    assert plugin_runtime.is_tool_visible("web_search") is False
    state = json.loads((device / STATE_FILENAME).read_text(encoding="utf-8"))
    assert state["legacy_imported"] is True
    assert state["plugins"]["web-research"]["user"]["committed"] == "disabled"

    legacy.write_text(
        json.dumps({"plugins": [{"name": "web-research", "enabled": True}]}),
        encoding="utf-8",
    )
    assert plugin_runtime.is_tool_visible("web_search") is False


def test_a_tool_declared_twice_is_hidden_for_everyone(device) -> None:
    for name in ("alpha", "beta"):
        plugin = device / "plugins" / name
        plugin.mkdir(parents=True)
        (plugin / "ephe-plugin.json").write_text(
            json.dumps(
                {
                    "manifest_version": 1,
                    "name": name,
                    "version": "1.0.0",
                    "description": name,
                    "permissions": {"tool_families": ["network"], "data_roots": []},
                    "components": {
                        "skills": [],
                        "commands": [],
                        "tools": ["web_search"],
                    },
                }
            ),
            encoding="utf-8",
        )
    plugin_runtime.invalidate_ownership_cache()
    assert plugin_runtime.is_tool_visible("web_search") is False
    assert plugin_runtime.is_tool_visible("read_file") is True


def test_runtime_passes_manifest_dependencies_into_the_lifecycle(device) -> None:
    plugin = device / "plugins" / "acme-research"
    plugin.mkdir(parents=True)
    (plugin / "ephe-plugin.json").write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "name": "acme-research",
                "version": "1.4.0",
                "description": "Needs the web research pack",
                "dependencies": ["web-research"],
                "permissions": {"tool_families": ["write"], "data_roots": []},
                "components": {"skills": [], "commands": [], "tools": ["create_video"]},
            }
        ),
        encoding="utf-8",
    )
    plugin_runtime.invalidate_ownership_cache()
    from core.plugin_lifecycle import LifecycleError

    lifecycle = plugin_runtime.lifecycle()
    lifecycle.set_enabled("acme-research", False)
    lifecycle.set_enabled("web-research", False)
    with pytest.raises(LifecycleError) as err:
        lifecycle.set_enabled("acme-research", True)
    assert err.value.code == "dependency_blocked"
    assert "web-research" in err.value.detail


def test_the_legacy_master_bypass_is_retired_and_explicit_off_wins(device) -> None:
    (device / "plugins.json").write_text(
        json.dumps(
            {
                "master_enabled": False,
                "plugins": [{"name": "web-research", "enabled": False}],
            }
        ),
        encoding="utf-8",
    )
    assert plugin_runtime.is_tool_visible("web_search") is False
    assert plugin_runtime.is_tool_visible("read_file") is True
