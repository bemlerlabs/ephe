"""CAP-04 / CAP-05 — server-side command expansion and the collision rule.

The client sends `/command text`; the server expands the manifest's template.
The five command/skill pairs keep the skill's native name: the plugin command
does not replace it. A disabled plugin's command does not expand.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.plugin_commands import expand_plugin_command
from core.plugin_registry import CapabilityKind, PluginRegistry


@pytest.fixture()
def command_home(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    workspace = tmp_path / "workspace"
    config.mkdir()
    workspace.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_WORKSPACE", str(workspace))
    from core import plugin_runtime

    plugin_runtime.invalidate_ownership_cache()
    yield config
    plugin_runtime.invalidate_ownership_cache()


def _write_command_plugin(config: Path) -> None:
    plugin = config / "plugins" / "acme-research"
    plugin.mkdir(parents=True)
    (plugin / "ephe-plugin.json").write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "name": "acme-research",
                "version": "1.0.0",
                "description": "Acme research",
                "permissions": {"tool_families": [], "data_roots": []},
                "components": {
                    "skills": [],
                    "commands": [
                        {
                            "name": "acme",
                            "description": "Run acme research",
                            "template": "Research {input}",
                        }
                    ],
                    "tools": [],
                },
            }
        ),
        encoding="utf-8",
    )


def test_server_expands_template(command_home) -> None:
    _write_command_plugin(command_home)
    assert expand_plugin_command("/acme the topic") == "Research the topic"
    assert "Usage: /acme" in expand_plugin_command("/acme")


def test_the_five_collisions_keep_the_skill_name(command_home) -> None:
    for command in ("pdf", "docx", "deck", "xlsx", "research"):
        text = f"/{command} the input"
        assert expand_plugin_command(text) == text


def test_a_non_colliding_command_expands(command_home) -> None:
    expanded = expand_plugin_command("/report Q3 numbers")
    assert expanded.startswith("Create a McKinsey-style report on: Q3 numbers.")
    assert "{input}" not in expanded


def test_an_unknown_command_passes_through(command_home) -> None:
    assert expand_plugin_command("/not-a-command x") == "/not-a-command x"
    assert expand_plugin_command("plain text") == "plain text"


def test_a_disabled_plugin_command_does_not_expand(command_home) -> None:
    from core import plugin_runtime

    plugin_runtime.lifecycle().set_enabled("documents", False)
    assert expand_plugin_command("/report Q3") == "/report Q3"


def test_every_registered_command_carries_its_template() -> None:
    registry = PluginRegistry.load(ROOT / "plugins", ROOT / "skills")
    commands = registry.capabilities(CapabilityKind.COMMAND)
    assert len(commands) == 10
    assert all(command.template for command in commands)
