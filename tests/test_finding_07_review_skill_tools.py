"""
tests/test_finding_07_review_skill_tools.py

Finding 7: the /review skill had only read_file as a tool.
Fix: tools extended to read_file, load_workspace, file_search, run_shell.

Given-When-Then Tests:
  1. GIVEN /review skill loaded WHEN checking tools THEN has 4 tools
  2. GIVEN /review skill loaded WHEN checking tools THEN includes load_workspace
  3. GIVEN /review skill loaded WHEN checking tools THEN includes run_shell
"""
from pathlib import Path

import pytest

from core.skills import SkillLoader, BUILTIN_SKILLS_DIR


@pytest.fixture
def loader():
    return SkillLoader()


# Test 1: GIVEN review skill WHEN loaded THEN has 4 tools

def test_given_review_skill_when_loaded_then_has_4_tools(loader):
    """GIVEN /review skill WHEN loaded THEN has exactly 4 tools."""
    skill = loader.load("code-reviewer")
    assert len(skill.tools) >= 4, f"Expected 4 tools, got {skill.tools}"


# Test 2: GIVEN review skill WHEN loaded THEN includes load_workspace

def test_given_review_skill_when_loaded_then_includes_load_workspace(loader):
    """GIVEN /review skill WHEN loaded THEN load_workspace is in tools list."""
    skill = loader.load("code-reviewer")
    assert "load_workspace" in skill.tools


# Test 3: GIVEN review skill WHEN loaded THEN includes run_shell

def test_given_review_skill_when_loaded_then_includes_run_shell(loader):
    """GIVEN /review skill WHEN loaded THEN run_shell is in tools list."""
    skill = loader.load("code-reviewer")
    assert "run_shell" in skill.tools


# Test 4: GIVEN review skill WHEN loaded THEN includes file_search

def test_given_review_skill_when_loaded_then_includes_file_search(loader):
    """GIVEN /review skill WHEN loaded THEN file_search is in tools list."""
    skill = loader.load("code-reviewer")
    assert "file_search" in skill.tools
