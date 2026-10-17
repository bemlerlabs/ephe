"""
P4 - the four composer modes are first-class and differently effective.

Ask        -> no tools (read-only Q&A, anti-hallucination guard)
Plan       -> read-only inspection + numbered plan (PLAN_MODE_GUARD)
Edit auto  -> edit family auto-released, the rest follows the profile guess
Full access-> all tools automatically (autonomous)
"""
from __future__ import annotations

from core.persona import ASK_MODE_GUARD, PLAN_MODE_GUARD, COMPUTE_GUARD
from server.routes.chat import (
    _resolve_mode,
    _mode_context,
    _EDIT_TOOL_NAMES,
    _READ_ONLY_TOOL_NAMES,
)


def test_ask_mode_only_ask_flag():
    f = _resolve_mode("ask")
    assert f == {"ask": True, "plan": False, "edit_auto": False, "full_access": False}


def test_mode_flags_hyphen_tolerant():
    assert _resolve_mode("plan")["plan"] is True
    assert _resolve_mode("edit-auto")["edit_auto"] is True
    assert _resolve_mode("edit_auto")["edit_auto"] is True
    assert _resolve_mode("full-access")["full_access"] is True
    assert _resolve_mode("full_access")["full_access"] is True


def test_legacy_agent_is_all_off():
    assert _resolve_mode("agent") == {"ask": False, "plan": False, "edit_auto": False, "full_access": False}
    assert _resolve_mode("")["ask"] is False


def test_plan_allowed_tools_are_read_only_subset():
    base = list(_READ_ONLY_TOOL_NAMES) + sorted(_EDIT_TOOL_NAMES)
    allowed = [t for t in base if t in _READ_ONLY_TOOL_NAMES]
    assert set(allowed) == _READ_ONLY_TOOL_NAMES
    assert not ({"edit_file", "write_file"} & set(allowed))


def test_edit_auto_set_is_the_editing_family():
    assert _EDIT_TOOL_NAMES == {"edit_file", "write_file"}


def test_guards_present_for_ask_and_plan():
    assert "ASK-MODE GUARD" in ASK_MODE_GUARD
    assert "PLAN-MODE GUARD" in PLAN_MODE_GUARD
    assert "DATA-COMPUTATION GUARD" in COMPUTE_GUARD


def test_mode_context_shared_helper_semantics():
    # ask: no tools
    es, tools, flags = _mode_context("ask", skill=None, message="hallo")
    assert tools == [] and flags["ask"] is True
    # plan: read-only inspection + the plan guard in the system block
    es, tools, flags = _mode_context("plan", skill=None, message="hallo")
    assert set(tools) == _READ_ONLY_TOOL_NAMES
    assert "PLAN-MODE GUARD" in es
    # edit-auto/full-access: the tool list follows skill/profile (None here)
    _es, tools, _f = _mode_context("full-access", skill=None, message="hallo")
    assert tools is None
