"""P1 — one plugin/capability registry over the shipped portfolio.

The registry is the first P1 slice: it reads the 14 manifests, the 51 built-in
skills and the 7 curated MCP entries into descriptors without moving files or
wiring the runtime. The five duplicate command/skill pairs are already dropped
from the command side; the skill side keeps the native name.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.plugin_registry import (
    BuiltinToolAdapter,
    CapabilityKind,
    ManifestV1Adapter,
    McpAdapter,
    PluginDescriptor,
    PluginRegistry,
    SkillAdapter,
)
from core.skills import Skill


def _registry() -> PluginRegistry:
    return PluginRegistry.load(
        plugins_root=ROOT / "plugins",
        skills_root=ROOT / "skills",
    )


def test_registry_represents_the_whole_portfolio() -> None:
    registry = _registry()
    assert len(registry.plugins) == 14
    assert len(registry.capabilities(CapabilityKind.SKILL)) == 51
    assert len(registry.capabilities(CapabilityKind.MCP_SERVER)) == 7
    assert len(registry.capabilities(CapabilityKind.COMMAND)) == 10


def test_the_five_duplicate_commands_are_not_registered() -> None:
    command_ids = {cap.id for cap in _registry().capabilities(CapabilityKind.COMMAND)}
    assert {
        "documents.pdf",
        "documents.docx",
        "presentations.deck",
        "spreadsheets.xlsx",
        "web-research.research",
    }.isdisjoint(command_ids)
    assert "documents.report" in command_ids


def test_every_capability_has_exactly_one_owner() -> None:
    registry = _registry()
    capabilities = list(registry.capabilities())
    ids = [cap.id for cap in capabilities]
    assert len(ids) == len(set(ids))
    assert {cap.owner for cap in capabilities} <= registry.owner_ids()
    assert registry.owner_of("skill:pdf-creator") == "core-skills"
    assert registry.owner_of("mcp:mcp-git") == "mcp-catalog"
    assert registry.owner_of("documents.report") == "documents"


def test_registry_order_is_deterministic() -> None:
    first = [(cap.kind.value, cap.id, cap.owner) for cap in _registry().capabilities()]
    second = [(cap.kind.value, cap.id, cap.owner) for cap in _registry().capabilities()]
    assert first == second


def test_manifest_adapter_drops_duplicate_commands() -> None:
    manifest = {
        "components": {
            "commands": [
                {"name": "pdf", "description": "duplicate of the skill"},
                {"name": "report", "description": "keep this command"},
            ]
        }
    }
    plugin = PluginDescriptor(
        id="documents",
        version="1.0.0",
        manifest=manifest,
        source="plugins/documents",
    )
    capabilities = ManifestV1Adapter(plugin).capabilities()
    assert [cap.id for cap in capabilities] == ["documents.report"]
    assert capabilities[0].owner == "documents"
    assert capabilities[0].kind is CapabilityKind.COMMAND


def test_skill_adapter_keeps_the_core_skills_owner() -> None:
    skills = [
        Skill(name="pdf-creator", trigger="/pdf", description="PDF", system_prompt="x")
    ]
    capabilities = SkillAdapter(skills, source_root=Path("skills")).capabilities()
    assert [cap.id for cap in capabilities] == ["skill:pdf-creator"]
    assert capabilities[0].owner == "core-skills"
    assert capabilities[0].kind is CapabilityKind.SKILL


def test_mcp_adapter_keeps_the_catalog_owner() -> None:
    capabilities = McpAdapter(
        [{"id": "mcp-git", "name": "Git", "description_en": "Git server"}],
        source="core/mcp_catalog.py",
    ).capabilities()
    assert [cap.id for cap in capabilities] == ["mcp:mcp-git"]
    assert capabilities[0].owner == "mcp-catalog"
    assert capabilities[0].kind is CapabilityKind.MCP_SERVER


def test_builtin_tool_adapter_uses_the_kernel_owner() -> None:
    capabilities = BuiltinToolAdapter(["read_file", "run_shell"]).capabilities()
    assert [cap.id for cap in capabilities] == ["tool:read_file", "tool:run_shell"]
    assert {cap.owner for cap in capabilities} == {"kernel"}
    assert {cap.kind for cap in capabilities} == {CapabilityKind.BUILTIN_TOOL}


def test_every_declared_tool_has_one_activation_owner() -> None:
    registry = _registry()
    activations = dict(registry.tool_activations())
    assert len(activations) == 46
    assert activations["web_search"] == "web-research"
    assert activations["read_file"] == "code-shell"
    assert activations["create_pdf"] == "documents"
    assert len(registry.capabilities(CapabilityKind.BUILTIN_TOOL)) == 46
    assert {
        cap.owner for cap in registry.capabilities(CapabilityKind.BUILTIN_TOOL)
    } == {"kernel"}
    from core.tools.registry import TOOL_MAP

    assert set(activations) <= set(TOOL_MAP)


def test_a_tool_declared_by_two_plugins_fails_closed(tmp_path) -> None:
    for name in ("alpha", "beta"):
        plugin_dir = tmp_path / name
        plugin_dir.mkdir()
        (plugin_dir / "ephe-plugin.json").write_text(
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
    from core.plugin_registry import RegistryError, load_tool_activations

    with pytest.raises(RegistryError) as err:
        load_tool_activations(tmp_path)
    assert err.value.code == "duplicate_tool_activation"
    assert "web_search" in err.value.detail
