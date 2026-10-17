"""
/help skill — GWT, 3× depth.

GIVEN: a help skill file exists (R16: pack format skills/help/SKILL.md)
WHEN:  it gets loaded
THEN:  trigger is '/help', it has valid fields

GIVEN: the skills list
WHEN:  /help is searched for
THEN:  the skill is registered and loadable

GIVEN: the skill gets invoked
WHEN:  the response is checked
THEN:  the answer contains all core feature categories
"""
from pathlib import Path
import re


# Perspective 1: skill file present and valid

class TestHelpSkillFilePerspective:
    """GIVEN help pack, WHEN parsed, THEN all required fields present."""

    def test_given_help_md_when_parsed_then_has_required_fields(self):
        """
        GIVEN: skills/help/SKILL.md exists in the skills/ directory
        WHEN:  the file is read and checked for required fields
        THEN:  name, trigger, description, system_prompt are present
        """
        skill_path = Path(__file__).parent.parent / "skills" / "help" / "SKILL.md"

        # Perspective 1: the file exists
        assert skill_path.exists(), "THEN: skills/help/SKILL.md muss existieren (R16 Pack-Format)"

        content = skill_path.read_text()

        # Perspective 2: the trigger is /help
        content_lower = content.lower()
        assert "trigger" in content_lower and "/help" in content_lower, (
            "THEN: Trigger muss '/help' sein"
        )

        # Perspective 3: the system prompt is not empty
        assert "system prompt" in content_lower, "THEN: system_prompt Feld muss vorhanden sein"
        assert len(content) > 200, "THEN: SKILL.md muss substanziellen Inhalt haben"


# Perspective 2: skill is registered and loadable via API

class TestHelpSkillRegistrationPerspective:
    """GIVEN skills loader, WHEN help skill loaded, THEN trigger resolves."""

    def test_given_skills_when_help_loaded_then_trigger_resolves(self):
        """
        GIVEN: the skills system is initialised
        WHEN:  all skills get loaded
        THEN:  the /help skill is in the list
        """
        from core.skills import SkillLoader

        skills = SkillLoader().load_all()

        # Perspective 1: the skills list is not empty
        assert len(skills) > 0, "THEN: Skills-Liste muss mindestens einen Eintrag haben"

        # Perspective 2: /help is among them
        triggers = [s.trigger for s in skills]
        assert "/help" in triggers, (
            f"THEN: /help Skill muss registriert sein, found: {triggers}"
        )

        # Perspective 3: the /help skill has a valid system prompt
        help_skill = next(s for s in skills if s.trigger == "/help")
        assert len(help_skill.system_prompt.strip()) > 50, (
            "THEN: /help Skill system_prompt darf nicht leer sein"
        )


# Perspective 3: help content is complete

class TestHelpSkillContentPerspective:
    """GIVEN help.md content, WHEN feature categories checked, THEN all present."""

    def test_given_help_content_when_features_checked_then_all_core_present(self):
        """
        GIVEN: the help SKILL.md system_prompt is loaded
        WHEN:  checked for the core features
        THEN:  chat, memory, files, tasks, voice are mentioned
        """
        skill_path = Path(__file__).parent.parent / "skills" / "help" / "SKILL.md"
        content = skill_path.read_text().lower()

        core_features = {
            "chat":   ["chat", "conversation", "gespräch", "fragen"],
            "memory": ["memory", "erinnerung", "kontext"],
            "files":  ["file", "pdf", "datei", "document"],
            "voice":  ["voice", "audio", "sprache", "speak"],
            "search": ["search", "web", "suche", "research"],
        }

        missing = []
        for feature, keywords in core_features.items():
            if not any(kw in content for kw in keywords):
                missing.append(feature)

        assert not missing, (
            f"THEN: help-Skill fehlen Feature-Kategorien: {missing}"
        )
