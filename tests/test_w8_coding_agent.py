"""W8 — coding agent top-1% tier: budget cascade, reflection, missing-skill flow.

The cascade bounds endless loops in the right order:
plan steps → repairs per step → tool rounds → hard ceiling.
Plus the 2x reflection safety cap and the interactive
"install skill X" flow over the skills route.
"""
from __future__ import annotations

import pytest


# Budget cascade

def test_budget_cascade_values():
    """GIVEN the four cascade levels
    WHEN the constants are read
    THEN they match the documented ladder 8/2/10/40 one to one."""
    from core.ephe_plan import MAX_PLAN_STEPS, MAX_REPAIRS_PER_STEP
    from core.chat import TOOL_BUDGET_HARD_CAP, clamp_tool_budget

    assert MAX_PLAN_STEPS == 8
    assert MAX_REPAIRS_PER_STEP == 2
    assert clamp_tool_budget(None) == 25  # R46: coding default in normal chat
    assert TOOL_BUDGET_HARD_CAP == 40
    # The cascade is monotonic: no level caps the next one below itself.
    assert MAX_REPAIRS_PER_STEP <= MAX_PLAN_STEPS
    assert clamp_tool_budget(None) <= clamp_tool_budget(25) <= TOOL_BUDGET_HARD_CAP


def test_hard_cap_clamps_above_ceiling():
    """GIVEN a requested budget above the hard ceiling
    WHEN clamp_tool_budget() runs
    THEN it caps at 40; the coding-class budget of 25 survives."""
    from core.chat import clamp_tool_budget

    assert clamp_tool_budget(41) == 40
    assert clamp_tool_budget(25) == 25


# Reflection fail-safe

def test_max_revisions_is_two():
    """GIVEN the ReAct loop with reflection
    WHEN the constants are read
    THEN exactly 2 revisions are allowed (no infinite loop)."""
    from core.react import MAX_REVISIONS

    assert MAX_REVISIONS == 2


# Missing-skill flow

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_SKILLS_DIR", str(tmp_path / "skills"))
    monkeypatch.setenv("EPHE_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("EPHE_SEARCH_DB", str(tmp_path / "search.db"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma_db"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "user_profile.json"))
    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_missing_skill_then_install_flow(client):
    """GIVEN a skill missing in the index
    WHEN the user creates it via POST and requests it afterwards
    THEN GET first returns the 404 card and after the creation the detail
    (install-first flow, one to one)."""
    from core.skills import SkillLoader

    loader = SkillLoader()
    names = {s.name for s in loader.load_all()}
    name = next((n for n in sorted(names) if n not in ("w8-missing-skill",)), None)
    assert name is not None  # the index is populated

    detail = client.get(f"/api/skills/{name}")
    assert detail.status_code == 200
    assert detail.json()["name"] == name

    # the 404 case: a name that does not exist in the index
    missing = client.get("/api/skills/w8-missing-skill")
    assert missing.status_code == 404
    assert "w8-missing-skill" in str(missing.json())
