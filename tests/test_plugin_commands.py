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
from core.plugin_registry import DUPLICATE_COMMANDS, CapabilityKind, PluginRegistry


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
    assert expanded == (
        "Create a sourced briefing on: Q3 numbers. Read every local source "
        "first. Deliver a PDF with sections, figures and a source line, then "
        "verify the file. A URL you have not read is a gap."
    )
    assert "{input}" not in expanded


def test_an_unknown_command_passes_through(command_home) -> None:
    assert expand_plugin_command("/not-a-command x") == "/not-a-command x"
    assert expand_plugin_command("plain text") == "plain text"


def test_a_disabled_plugin_command_does_not_expand(command_home) -> None:
    from core import plugin_runtime

    plugin_runtime.lifecycle().set_enabled("documents", False)
    assert expand_plugin_command("/report Q3") == "/report Q3"


def _declared_commands() -> set[tuple[str, str]]:
    """The (bundle, command) pairs the shipped manifests declare, without the leading slash."""
    pairs: set[tuple[str, str]] = set()
    for path in sorted((ROOT / "plugins").glob("*/ephe-plugin.json")):
        manifest = json.loads(path.read_text(encoding="utf-8"))
        bundle = str(manifest["name"])
        assert bundle == path.parent.name, f"{path}: folder is {path.parent.name}"
        for entry in (manifest.get("components") or {}).get("commands") or []:
            pairs.add((bundle, str(entry["name"]).lstrip("/")))
    return pairs


def test_every_registered_command_carries_its_template(command_home) -> None:
    """Every command a bundle declares is registered and expands, except the collision rule.

    This test pinned a count (32, then 42) that mirrored how many command entries the manifests
    happen to carry: two bundles landed and it went red while every command still expanded
    correctly. What it was standing in for is kept and none of it moves with a bundle -- the
    registered (bundle, command) pairs are exactly the declared ones minus `DUPLICATE_COMMANDS`,
    the set the expander itself declines against, so a declared command that silently fails to
    register answers here instead of in a number nobody reads; and every registered command
    carries a template that the expander actually applies.
    """
    registry = PluginRegistry.load(ROOT / "plugins", ROOT / "skills")
    commands = registry.capabilities(CapabilityKind.COMMAND)
    registered = {(command.owner, command.name.lstrip("/")): command for command in commands}

    assert len(registered) == len(commands), "two bundles registered the same command name"
    assert set(registered) == _declared_commands() - set(DUPLICATE_COMMANDS)
    for (bundle, name), command in registered.items():
        assert command.template, f"{bundle}/{name} is registered without a template"
        expanded = expand_plugin_command(f"/{name} the topic")
        assert expanded not in (f"/{name} the topic", f"/{name}"), (
            f"{bundle}/{name} is registered but never expanded"
        )
