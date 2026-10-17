"""
tests/test_finding_02_i18n_skill_prompts.py

Finding 2: the skill prompts had a hardcoded "Antworte auf Deutsch".
Fix: Replaced with "Always respond in the same language the user writes in."

Given-When-Then Tests:
  1. GIVEN any skill WHEN loaded THEN prompt does NOT contain "Antworte auf Deutsch"
  2. GIVEN any skill WHEN loaded THEN prompt contains language-neutral instruction
  3. GIVEN all 9 built-in skills WHEN loaded THEN none has hardcoded German language
"""
import pytest

from core.skills import SkillLoader


@pytest.fixture
def loader():
    return SkillLoader()


@pytest.fixture
def all_skills(loader):
    return loader.load_all()


# Test 1: GIVEN any skill WHEN loaded THEN no "Antworte auf Deutsch"

def test_given_any_skill_when_loaded_then_no_hardcoded_german(all_skills):
    """GIVEN all built-in skills WHEN loaded THEN none contains 'Antworte auf Deutsch'."""
    for skill in all_skills:
        assert "Antworte auf Deutsch" not in skill.system_prompt, (
            f"Skill '{skill.name}' still has hardcoded 'Antworte auf Deutsch'"
        )


# Test 2: GIVEN skills with former German instruction WHEN loaded THEN has language-neutral

def test_given_formerly_german_skills_when_loaded_then_language_neutral(loader):
    """GIVEN the 4 skills that had 'Antworte auf Deutsch' WHEN loaded THEN have language-neutral instruction."""
    skill_names = ["chart-creator", "file-assistant", "pdf-creator", "web-researcher"]

    for name in skill_names:
        skill = loader.load(name)
        assert "same language the user writes in" in skill.system_prompt, (
            f"Skill '{name}' missing language-neutral instruction"
        )


# Test 3: GIVEN all skills WHEN loaded THEN count >= 9 built-in

def test_given_all_skills_when_loaded_then_at_least_9(all_skills):
    """GIVEN builtin skills dir WHEN load_all() THEN >= 9 skills loaded."""
    assert len(all_skills) >= 9, f"Expected >= 9 skills, got {len(all_skills)}"
