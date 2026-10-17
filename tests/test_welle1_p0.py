"""Tests for wave 1 (P0): core integrity fixes.

Acceptance edges (each one with an assert):
  P0-1: get_filtered_tool_schemas() includes META_TOOLS + memory + skill_manage
  P0-2: all 47 skills have memory + skill_manage in allowed_tools
  P0-3: evidence-gate post-hook pins the evidence chain
  P0-4a: mcp_* → NETWORK in classify_tool()
  P0-4b: the skill loader cache is invalidated after save()/delete()
"""
from __future__ import annotations

import pathlib

import pytest


# P0-1: Meta-tools in the filtered schema

def test_p0_1_filtered_schemas_inject_meta_tools():
    from core.tools.registry import get_filtered_tool_schemas
    from core.tools.discovery import META_TOOL_NAMES
    schemas = get_filtered_tool_schemas(["read_file", "run_shell"])
    names = {s["function"]["name"] for s in schemas}
    assert set(META_TOOL_NAMES).issubset(names), "META_TOOL_NAMES must be in filtered schemas"
    assert "memory" in names
    assert "skill_manage" in names


def test_p0_1_filtered_schemas_minimal():
    from core.tools.registry import get_filtered_tool_schemas
    schemas = get_filtered_tool_schemas([])
    names = {s["function"]["name"] for s in schemas}
    assert {"tool_search", "tool_describe", "tool_call", "memory", "skill_manage"}.issubset(names)


# P0-2: memory + skill_manage in all 47 skill frontmatters

def test_p0_2_all_skills_have_persistence_tools():
    from core.skills import BUILTIN_SKILLS_DIR, _parse_skill
    for md in sorted(BUILTIN_SKILLS_DIR.glob("*/SKILL.md")):
        s = _parse_skill(md.parent.name, md.read_text(encoding="utf-8"), skill_dir=md.parent)
        assert "memory" in s.allowed_tools, f"{s.name}: missing memory"
        assert "skill_manage" in s.allowed_tools, f"{s.name}: missing skill_manage"


def test_p0_2_non_tool_fields_clean():
    """when_to_use/when_not_to_use/artifact_types must NOT contain memory/skill_manage."""
    from core.skills import BUILTIN_SKILLS_DIR, _parse_skill
    for md in sorted(BUILTIN_SKILLS_DIR.glob("*/SKILL.md")):
        s = _parse_skill(md.parent.name, md.read_text(encoding="utf-8"), skill_dir=md.parent)
        assert "memory" not in s.when_to_use, f"{s.name}: memory in when_to_use"
        assert "memory" not in s.when_not_to_use, f"{s.name}: memory in when_not_to_use"
        assert "memory" not in s.artifact_types, f"{s.name}: memory in artifact_types"


# P0-3: Evidence gate post-hook

def test_p0_3_evidence_gate_appends_verified_for_marker():
    from core.tools.registry import _evidence_gate_post_hook
    result = "PDF_FILE: /tmp/test.pdf\nPAGES: 3"
    out = _evidence_gate_post_hook("create_pdf", {}, result)
    assert out is not None
    assert "ARTIFACT_VERIFIED" in out
    assert "/tmp/test.pdf" in out


def test_p0_3_evidence_gate_noop_without_marker():
    from core.tools.registry import _evidence_gate_post_hook
    result = "Search results: example.com\nMore: test.com"
    out = _evidence_gate_post_hook("web_search", {}, result)
    assert out is None


def test_p0_3_evidence_gate_no_duplicate_artifact_verified():
    from core.tools.registry import _evidence_gate_post_hook
    result = "PDF_FILE: /tmp/test.pdf\nARTIFACT_VERIFIED: /tmp/test.pdf"
    out = _evidence_gate_post_hook("create_pdf", {}, result)
    assert out is None  # already present → no duplicate


# P0-4a: MCP tools → NETWORK

def test_p0_4a_mcp_tools_classified_as_network():
    from core.tools.approval import classify_tool
    cls = classify_tool("mcp_example_tool")
    assert cls.category == "NETWORK"


def test_p0_4a_mcp_tools_not_mutating():
    from core.tools.approval import classify_tool
    cls = classify_tool("mcp_websearch")
    assert cls.category == "NETWORK"
    # NETWORK is not DANGEROUS and not local mutating
    assert cls.category != "DANGEROUS"


# P0-4b: Cache invalidation

def _cache_key(loader):
    """Cache key shape since E2: (user, builtin, plugin_root) via workspace_key."""
    from core.skills import workspace_key

    return (workspace_key(loader._user_dir), workspace_key(loader._builtin_dir), workspace_key(loader._plugin_root))


def test_p0_4b_save_invalidates_cache(tmp_path):
    from core.skills import SkillLoader, _SKILL_LIST_CACHE
    user_dir = tmp_path / "skills"
    user_dir.mkdir()
    loader = SkillLoader(skills_dir=user_dir)
    # The first load fills the cache
    loader.load_all()
    key = _cache_key(loader)
    assert key in _SKILL_LIST_CACHE, "Cache should be populated"
    loader.save(name="test-skill", trigger="/test", description="Test",
               tools=["read_file"], system_prompt="Test.")
    assert key not in _SKILL_LIST_CACHE, "Cache must be cleared after save"


def test_p0_4b_delete_invalidates_cache(tmp_path):
    from core.skills import SkillLoader, _SKILL_LIST_CACHE
    user_dir = tmp_path / "skills"
    user_dir.mkdir()
    loader = SkillLoader(skills_dir=user_dir)
    loader.save(name="del-test", trigger="/del", description="D",
               tools=["read_file"], system_prompt="D.")
    loader.load_all()  # fills the cache
    key = _cache_key(loader)
    assert key in _SKILL_LIST_CACHE
    loader.delete("del-test")
    assert key not in _SKILL_LIST_CACHE, "Cache must be cleared after delete"
