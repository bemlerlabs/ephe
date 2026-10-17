"""Ephe — the R38 chain: named-tool coverage, the file primitives in a whitelisted array, session-aware discovery.

Measured 2026-10-10 (docs/ENDSTATE_DELTA_2026-10-10.md): 33 of 37 endstate reps whose session array
lacked read_file failed, 2 of 42 reps whose array kept it failed. W3 and W4 below are the
benchmark's own prompt texts.

RULE: tests BEFORE implementation. Given / When / Then — strictly.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from core.chat import _tools_for_messages
from core.skills import SkillLoader
from core.tools import execute_tool
from core.tools.approval import classify_tool
from core.tools.discovery import (
    FILE_MUTATING_TOOLS,
    FILE_PRIMITIVE_TOOLS,
    META_TOOL_NAMES,
    NO_MATCH_CORE_ACTIVE,
    READ_ONLY_FILE_TOOLS,
    search,
)

REPO_SKILLS = Path(__file__).resolve().parents[1] / "skills"

API_TESTER_TOOLS = [
    "fetch_url", "execute_code", "validate_json", "write_file", "memory", "skill_manage",
]

W3_PROMPT = (
    "Read a.json and b.json in the workspace. Create merged.json containing "
    '{"keys": [...]} with the UNION of the keys of both files, sorted, each key exactly '
    "once (deduplicated). Use write_file (or edit_file with an empty old_string) to create it. "
    "End with a line 'FINAL ANSWER: done'."
)
W4_PROMPT = (
    "Rename-chain: a.txt exists in the workspace. Execute EVERY step below with a real tool call; "
    "do not stop at a plan, run all steps to the last one. Step 1: read a.txt. Step 2: write_file "
    "b.txt with the same content. Step 3: delete_file a.txt. Step 4: write_file c.txt with the "
    "same content. Step 5: delete_file b.txt. At the end only c.txt may exist. Emit the FINAL line "
    "only after step 5 returned. End with a line 'FINAL ANSWER: done'."
)


@pytest.fixture
def loader(tmp_path, monkeypatch):
    """The repo packs only, with no user dir and no disable state: routing is then the rule alone."""
    monkeypatch.setattr("core.skills.DISABLED_SKILLS_FILE", tmp_path / "skills_state.json")
    return SkillLoader(skills_dir=tmp_path / "skills", builtin_dir=REPO_SKILLS)


@pytest.fixture(autouse=True)
def fresh_session_array():
    """The session array is a ContextVar; a leaked value would route the next case's search()."""
    from core.tools.discovery import clear_session_tool_array

    clear_session_tool_array()
    yield
    clear_session_tool_array()


def _visible(allowed):
    messages = [{"role": "user", "content": "hi"}]
    return {entry["function"]["name"] for entry in _tools_for_messages(messages, allowed)}


def _declared(skill) -> set[str]:
    return set(skill.tools or []) | set(skill.allowed_tools or [])


# R38 coverage rule

def test_w3_prompt_no_longer_hands_the_session_to_a_partial_skill(loader):
    """GIVEN W3, which names write_file and edit_file
    WHEN resolve_for_message()
    THEN api-tester, which declares the first and not the second, does not take the session."""
    skill = loader.resolve_for_message(W3_PROMPT)
    assert skill is not None
    assert skill.name != "api-tester"


def test_named_tool_rule_still_lands_on_a_skill_covering_every_named_tool(loader):
    """GIVEN W3, which asks to read, to write_file and to edit_file
    WHEN resolve_for_message()
    THEN the winner declares all three (R38's deterministic route survives)."""
    skill = loader.resolve_for_message(W3_PROMPT)
    assert {"read_file", "write_file", "edit_file"} <= _declared(skill)


def test_prompt_naming_a_tool_no_skill_declares_falls_through(loader):
    """GIVEN W4, which names write_file and also delete_file (declared by no skill)
    WHEN resolve_for_message()
    THEN api-tester does not take the session, because the named-tool rule abstains
    whenever no candidate covers both names."""
    skill = loader.resolve_for_message(W4_PROMPT)
    assert skill is None or skill.name != "api-tester"


def test_single_named_tool_still_selects_the_declaring_skill(loader):
    """GIVEN a prompt naming one tool
    WHEN resolve_for_message()
    THEN the first skill declaring it still wins, so the score loop cannot hijack it."""
    assert loader.resolve_for_message("edit_file README.md").name == "api-designer"


def test_alias_names_count_as_their_canonical_tool(loader):
    """GIVEN a prompt that says "read" (a TOOL_MAP alias of read_file) plus write_file
    WHEN resolve_for_message()
    THEN coverage is measured on the canonical names, so the winner can do both."""
    skill = loader.resolve_for_message("read notes.md, then write_file summary.md with the gist")
    assert {"read_file", "write_file"} <= _declared(skill)


# The whitelist path keeps the file primitives

def test_file_working_whitelist_keeps_all_six_primitives():
    """GIVEN api-tester's declared list, which carries write_file
    WHEN the array is built
    THEN all six file primitives are in it beside the meta tools."""
    visible = _visible(API_TESTER_TOOLS)
    assert FILE_PRIMITIVE_TOOLS <= visible
    assert META_TOOL_NAMES <= visible


def test_whitelist_without_a_mutating_file_tool_keeps_the_read_trio():
    """GIVEN a whitelist that declares no write, edit or delete name
    WHEN the array is built
    THEN the read primitives join it and the mutating three stay out."""
    visible = _visible(["web_search", "execute_code", "validate_json"])
    assert READ_ONLY_FILE_TOOLS <= visible
    assert not FILE_MUTATING_TOOLS & visible


def test_restricted_shape_gains_no_mutating_name():
    """GIVEN the read-only list the restricted mode hands to the array builder
    WHEN the array is built
    THEN it holds exactly that list plus the meta tools plus the read trio, so the
    mode is not widened by a union that assumes a file-working session."""
    read_only_shape = ["read_file", "file_search", "list_directory", "web_search"]
    visible = _visible(read_only_shape)
    assert visible == set(read_only_shape) | META_TOOL_NAMES | READ_ONLY_FILE_TOOLS
    assert not FILE_MUTATING_TOOLS & visible


def test_empty_whitelist_stays_empty():
    """GIVEN ask_mode's empty whitelist
    WHEN the array is built
    THEN nothing is added, so the deliberate no-tool dialog holds."""
    assert _visible([]) == set()


def test_read_trio_is_classified_safe():
    """GIVEN the names every non-empty whitelist is given
    WHEN each is classified
    THEN all three are SAFE, so the unconditional half of the union adds no authority."""
    for name in sorted(READ_ONLY_FILE_TOOLS):
        assert classify_tool(name).category == "SAFE"


def test_w3_end_to_end_array_keeps_read_file(loader):
    """GIVEN W3 resolved and its skill list used as the session whitelist, the route the
    server takes in full-access mode
    WHEN the array is built
    THEN read_file is in it, which is the capability whose absence the bench measured."""
    skill = loader.resolve_for_message(W3_PROMPT)
    assert "read_file" in _visible(skill.tools if skill else None)


# The premise of the union: the array is visibility, the gate is authority

def test_tool_call_reaches_a_name_absent_from_the_array():
    """GIVEN get_datetime, omitted from a whitelisted array
    WHEN tool_call runs it
    THEN it executes, so the array was hiding a capability the session already had."""
    assert "get_datetime" not in _visible(["fetch_url"])
    out = asyncio.run(execute_tool("tool_call", {"name": "get_datetime", "arguments": "{}"}))
    assert not out.startswith("[tool_call]")


# Session-aware discovery

def test_search_does_not_claim_omitted_core_tools_are_active():
    """GIVEN a whitelisted session whose array omits core tools
    WHEN tool_search matches nothing
    THEN the answer states the omission and names the route instead of a dead end.

    The query is two strings no tool name, hint or description contains, so both
    index tiers come up empty the way the test means them to.
    """
    _visible(["fetch_url"])
    out = search("qqzz wwyymm")
    assert "tool_call" in out
    assert "not in this session's array" in out


def test_the_description_tier_does_not_widen_a_name_hit():
    """GIVEN the query "pdf", which the name-and-hint index already answers
    WHEN search runs
    THEN it returns the five lines that index gave before schema descriptions were
    readable at all (measured 2026-10-10); a sixth means the fallback tier is running
    as a second haystack, which costs ~35 lines per dead-end question."""
    assert len(search("pdf").splitlines()) == 5


def test_full_core_session_keeps_the_short_answer():
    """GIVEN an array built without a whitelist
    WHEN tool_search matches nothing
    THEN no omission is claimed, because nothing was omitted."""
    _visible(None)
    assert search("qqzz wwyymm") == NO_MATCH_CORE_ACTIVE


def test_search_sees_the_array_through_a_gathered_tool_task():
    """GIVEN the array built in the conversation task and the search run in a task
    gather creates afterwards, which is the route core/chat.py takes for a tool round
    WHEN tool_search answers
    THEN the session state still travels into that task."""
    _visible(["fetch_url"])

    async def tool_round():
        return await asyncio.gather(_one_search())

    async def _one_search():
        return search("qqzz wwyymm")

    out = asyncio.run(tool_round())[0]
    assert "not in this session's array" in out


def test_search_finds_the_rename_behaviour():
    """GIVEN a query naming no tool, matching only a schema description
    WHEN search("rename")
    THEN delete_file is listed, since that is where the rename behaviour is documented."""
    assert "delete_file" in search("rename")


def test_search_lists_an_omitted_core_tool_as_reachable():
    """GIVEN a whitelisted session without web_search in its array
    WHEN the model searches for the web
    THEN web_search is listed as reachable, not reported as missing."""
    _visible(["read_file", "execute_code"])
    assert "web_search" in search("web search")


def test_search_describes_a_tool_the_hint_table_does_not_cover():
    """GIVEN validate_json, a deferred tool with no entry in the hint table
    WHEN search lists it
    THEN the line carries its declared description, so the model is not offered a
    name with the placeholder for an explanation."""
    out = search("validate json")
    assert "validate_json" in out
    assert "(no hint)" not in out
