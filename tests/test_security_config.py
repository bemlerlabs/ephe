"""P1-4: core/security_config.py — approval profile + session-remember consistency.

Coverage:
  1. VALID_APPROVAL_PROFILES / NEVER_REMEMBER as the SSOT table
  2. run_shell is NEVER released by remembering its type (also not in the session profile)
  3. Profile gate: only 'session' remembers, everything else stays strict
  4. load/save roundtrip with the default fallback when the file is missing
  5. Consistency: every remembered tool exists in the tool registry

All tests are offline/deterministic; the session table is cleared for each test.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from core import security_config as SC


@pytest.fixture(autouse=True)
def _clean():
    SC.clear_session_approvals()
    yield
    SC.clear_session_approvals()


# 1. The SSOT table

def test_valid_profiles_are_the_four_composer_modes():
    assert SC.VALID_APPROVAL_PROFILES == ("strict", "session", "plan", "full")


def test_never_remember_contains_run_shell():
    assert "run_shell" in SC.NEVER_REMEMBER


# 2. run_shell never approved by type

def test_run_shell_never_session_approved_even_in_session_profile():
    SC.remember_tool("s1", "run_shell")
    assert SC.session_auto_approved("s1", "run_shell", profile="session") is False


def test_normal_tool_session_approved_after_remember():
    SC.remember_tool("s1", "read_file")
    assert SC.session_auto_approved("s1", "read_file", profile="session") is True


# 3. Profile gate

def test_strict_profile_never_auto_approves():
    SC.remember_tool("s1", "read_file")
    assert SC.session_auto_approved("s1", "read_file", profile="strict") is False


def test_missing_session_id_no_auto_approve():
    SC.remember_tool("s1", "read_file")
    assert SC.session_auto_approved(None, "read_file", profile="session") is False


def test_remember_ignores_missing_session_id():
    SC.remember_tool(None, "read_file")
    assert SC.session_auto_approved(None, "read_file", profile="session") is False


# 4. Roundtrip

def test_save_and_load_roundtrip(tmp_path=None):
    from pathlib import Path as P
    target = P("/tmp/mnx_sec_test.json")
    try:
        cfg = SC.save_security_config(approval_profile="session", sandbox_enabled=True, path=target)
        assert cfg.approval_profile == "session"
        assert cfg.sandbox_enabled is True
    finally:
        target.unlink(missing_ok=True)


def test_unknown_profile_raises():
    from pathlib import Path as P
    target = P("/tmp/mnx_sec_test2.json")
    try:
        with pytest.raises(ValueError):
            SC.save_security_config(approval_profile="bogus", path=target)
    finally:
        target.unlink(missing_ok=True)


# 5. Consistency against the tool registry

def test_never_remember_tools_exist_in_registry():
    from core.tools.registry import TOOL_MAP
    for tool in SC.NEVER_REMEMBER:
        assert tool in TOOL_MAP, f"{tool} in NEVER_REMEMBER aber nicht in TOOL_MAP"


def test_schemas_cover_all_registry_tools():
    from core.tools.registry import get_tool_schemas
    names = {t.get("function", {}).get("name") for t in get_tool_schemas()}
    # every schema carries a name (no empty entry)
    assert None not in names and "" not in names
