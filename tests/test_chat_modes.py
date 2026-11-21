"""
P4 - the four composer modes are first-class and differently effective.
The A2b rename: Analyst (was Ask), Architect (was Plan), Operator (was Full
access); Edit auto retired into the edit-family compatibility factor.

Analyst  -> no tools (read-only Q&A, anti-hallucination guard)
Architect-> read-only inspection + numbered plan (ARCHITECT_MODE_GUARD)
Operator -> all tools automatically (autonomous)
"""
from __future__ import annotations

from core.persona import ANALYST_MODE_GUARD, ARCHITECT_MODE_GUARD, COMPUTE_GUARD
from server.routes.chat import (
    _resolve_mode,
    _mode_context,
    _EDIT_TOOL_NAMES,
    _READ_ONLY_TOOL_NAMES,
)


def test_legacy_ask_resolves_to_the_analyst_flag_only():
    f = _resolve_mode("ask")
    assert f == {"analyst": True, "architect": False, "operator": False,
                 "creator": False, "edit_family_compat": False}


def test_mode_flags_hyphen_tolerant():
    assert _resolve_mode("plan")["architect"] is True
    assert _resolve_mode("edit-auto")["edit_family_compat"] is True
    assert _resolve_mode("edit_auto")["edit_family_compat"] is True
    assert _resolve_mode("full-access")["operator"] is True
    assert _resolve_mode("full_access")["operator"] is True


def test_legacy_agent_is_all_off():
    assert _resolve_mode("agent") == {"analyst": False, "architect": False,
                                      "operator": False, "creator": False,
                                      "edit_family_compat": False}
    assert _resolve_mode("")["analyst"] is False


def test_plan_allowed_tools_are_read_only_subset():
    base = list(_READ_ONLY_TOOL_NAMES) + sorted(_EDIT_TOOL_NAMES)
    allowed = [t for t in base if t in _READ_ONLY_TOOL_NAMES]
    assert set(allowed) == _READ_ONLY_TOOL_NAMES
    assert not ({"edit_file", "write_file"} & set(allowed))


def test_edit_auto_set_is_the_editing_family():
    assert _EDIT_TOOL_NAMES == {"edit_file", "write_file"}


def test_guards_present_for_analyst_and_architect():
    assert "ANALYST-MODE GUARD" in ANALYST_MODE_GUARD
    assert "ARCHITECT-MODE GUARD" in ARCHITECT_MODE_GUARD
    assert "DATA-COMPUTATION GUARD" in COMPUTE_GUARD


def test_mode_context_shared_helper_semantics():
    # ask: no tools
    es, tools, flags = _mode_context("ask", skill=None, message="hallo")
    assert tools == [] and flags["analyst"] is True
    # plan: read-only inspection + the plan guard in the system block
    es, tools, flags = _mode_context("plan", skill=None, message="hallo")
    assert set(tools) == _READ_ONLY_TOOL_NAMES
    assert "ARCHITECT-MODE GUARD" in es
    # edit-auto/full-access: the tool list follows skill/profile (None here)
    _es, tools, _f = _mode_context("full-access", skill=None, message="hallo")
    assert tools is None
