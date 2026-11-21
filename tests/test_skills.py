"""
◑ Ephe – the core.skills loader (Phase 2 TDD)
tests/test_skills.py

RULE: tests BEFORE implementation.
Given / When / Then – strictly.

Markdown skill format:
  # skill-name
  **Trigger**: /trigger-name
  **Description**: short description
  **Tools**: tool1, tool2

  ## System Prompt
  You are a...

  ## Test
  **Input**: test question
  **Expect Tool**: tool_name
  **Expect Contains**: expected text
"""
from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from unittest.mock import AsyncMock, patch

import pytest

from core.skills import Skill, SkillLoadError, SkillLoader, SkillTestResult


VALID_SKILL_MD = dedent("""\
    # web-researcher

    **Trigger**: /research
    **Description**: Recherchiert Themen im Internet mit DuckDuckGo.
    **Tools**: web_search

    ## System Prompt

    Du bist ein präziser Recherche-Assistent.
    Nutze immer das web_search Tool für aktuelle Informationen.
    Antworte kurz, faktenbasiert und auf Deutsch.

    ## Test

    **Input**: Was ist Ollama?
    **Expect Tool**: web_search
    **Expect Contains**: lokal
""")

BROKEN_SKILL_MD = dedent("""\
    # Kaputtes Skill
    Kein Trigger-Block, kein System-Prompt.
    Einfach nur Text.
""")


class TestSkillLoader:

    @pytest.fixture
    def skills_dir(self, tmp_path):
        d = tmp_path / "skills"
        d.mkdir()
        return d

    @pytest.fixture
    def loader(self, skills_dir):
        return SkillLoader(skills_dir=skills_dir)

    def test_load_valid_skill(self, loader, skills_dir):
        """
        GIVEN  a valid skill file web_researcher.md in skills_dir
        WHEN   loader.load("web-researcher") is called
        THEN   the result is a Skill object
        AND    skill.name == "web-researcher"
        AND    skill.trigger == "/research"
        AND    skill.system_prompt is a non-empty string
        AND    "web_search" in skill.tools
        """
        (skills_dir / "web-researcher.md").write_text(VALID_SKILL_MD, encoding="utf-8")

        skill = loader.load("web-researcher")

        assert isinstance(skill, Skill)
        assert skill.name == "web-researcher"
        assert skill.trigger == "/research"
        assert isinstance(skill.system_prompt, str)
        assert len(skill.system_prompt) > 10
        assert "web_search" in skill.tools

    def test_load_nonexistent_raises_skill_load_error(self, loader):
        """
        GIVEN  no skill named "nicht-vorhanden"  # language-gate: ignore quoted fixture skill name
        WHEN   loader.load("nicht-vorhanden") is called  # language-gate: ignore quoted fixture skill name
        THEN   it raises SkillLoadError
        AND    the error text contains "nicht-vorhanden"  # language-gate: ignore quoted fixture skill name
        """
        with pytest.raises(SkillLoadError) as exc_info:
            loader.load("nicht-vorhanden")

        assert "nicht-vorhanden" in str(exc_info.value)

    def test_load_broken_skill_raises_skill_load_error(self, loader, skills_dir):
        """
        GIVEN  a markdown file without a valid skill structure (no trigger, no system prompt)
        WHEN   loader.load("broken") is called
        THEN   it raises SkillLoadError
        AND    the app does NOT crash
        """
        (skills_dir / "broken.md").write_text(BROKEN_SKILL_MD, encoding="utf-8")

        with pytest.raises(SkillLoadError):
            loader.load("broken")

    def test_load_all_returns_list(self, loader, skills_dir, tmp_path):
        """
        GIVEN  2 valid skill files in skills_dir
        WHEN   loader.load_all() is called
        THEN   the result is a list with 2 skill objects
        """
        (skills_dir / "web-researcher.md").write_text(VALID_SKILL_MD, encoding="utf-8")
        variant = VALID_SKILL_MD.replace("web-researcher", "web-researcher-copy").replace("/research", "/research2")
        (skills_dir / "web-researcher-copy.md").write_text(variant, encoding="utf-8")
        # Empty builtin_dir so only our 2 skills are counted
        empty_builtin = tmp_path / "empty_builtin"
        empty_builtin.mkdir()
        loader_isolated = SkillLoader(skills_dir=skills_dir, builtin_dir=empty_builtin, plugin_root=tmp_path / "plugins")

        skills = loader_isolated.load_all()

        assert isinstance(skills, list)
        assert len(skills) == 2

    def test_load_all_empty_dir_returns_empty_list(self, tmp_path):
        """
        GIVEN  an empty skills_dir AND an empty builtin_dir
        WHEN   loader.load_all() is called
        THEN   the result is an empty list (no crash)
        """
        empty_user = tmp_path / "user_skills"
        empty_user.mkdir()
        empty_builtin = tmp_path / "builtin_skills"
        empty_builtin.mkdir()
        loader_empty = SkillLoader(skills_dir=empty_user, builtin_dir=empty_builtin, plugin_root=tmp_path / "plugins")

        result = loader_empty.load_all()
        assert result == []

    def test_resolve_trigger_finds_matching_skill(self, loader, skills_dir):
        """
        GIVEN  a skill with trigger "/research" in skills_dir
        WHEN   loader.resolve_trigger("/research") is called
        THEN   the result is that skill object
        AND    skill.trigger == "/research"
        """
        (skills_dir / "web-researcher.md").write_text(VALID_SKILL_MD, encoding="utf-8")

        skill = loader.resolve_trigger("/research")

        assert skill is not None
        assert skill.trigger == "/research"

    def test_resolve_trigger_unknown_returns_none(self, loader):
        """
        GIVEN  no skill with trigger "/unbekannt"
        WHEN   loader.resolve_trigger("/unbekannt") is called
        THEN   the result is None (no crash)
        """
        result = loader.resolve_trigger("/unbekannt")
        assert result is None

    @pytest.mark.asyncio
    async def test_run_test_passes_when_tool_called(self, loader, skills_dir):
        """
        GIVEN  a skill with test: input="Was ist Ollama?", expect_tool="web_search"  # language-gate: ignore quoted German routing prompt under test
        WHEN   loader.run_test("web-researcher") with a mock of chat_with_tools
        THEN   the result is a SkillTestResult with passed=True
        """
        (skills_dir / "web-researcher.md").write_text(VALID_SKILL_MD, encoding="utf-8")

        with patch("core.chat.chat_with_tools", new=AsyncMock(
            return_value="Ollama ist lokal"
        )):
            result = await loader.run_test("web-researcher")

        assert isinstance(result, SkillTestResult)
        assert hasattr(result, "passed")
        assert hasattr(result, "skill_name")
        assert result.skill_name == "web-researcher"

    @pytest.mark.asyncio
    async def test_run_test_on_missing_skill_returns_failed_result(self, loader):
        """
        GIVEN  no skill named "ghost"
        WHEN   loader.run_test("ghost") is called
        THEN   the result is a SkillTestResult with passed=False
        AND    no crash
        """
        result = await loader.run_test("ghost")

        assert isinstance(result, SkillTestResult)
        assert result.passed is False
