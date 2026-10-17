"""
◑ Ephe – core.profile load + save (Phase 2 TDD)
tests/test_profile.py

RULE: tests before implementation.
Given / When / Then – strictly.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.profile import UserProfile, load_profile, save_profile, update_profile


class TestUserProfile:

    @pytest.fixture
    def profile_path(self, tmp_path):
        return tmp_path / "user_profile.json"

    def test_load_returns_default_when_no_file(self, profile_path):
        """
        GIVEN  no profile file exists
        WHEN   load_profile(path) is called
        THEN   the return is a UserProfile with None defaults
        AND    no crash
        """
        profile = load_profile(path=profile_path)

        assert isinstance(profile, UserProfile)
        assert profile.name is None
        assert profile.expertise is None
        assert profile.preferred_language is None
        assert isinstance(profile.topics_of_interest, list)

    def test_save_and_load_roundtrip(self, profile_path):
        """
        GIVEN  UserProfile with name="Max", expertise="Python"
        WHEN   save_profile() and then load_profile() are called
        THEN   the loaded profile has name="Max", expertise="Python"
        AND    every stored field is restored
        """
        profile = UserProfile(
            name="Max",
            expertise="Python-Entwickler",
            preferred_language="Deutsch",
            response_style="kurz und direkt",
            topics_of_interest=["KI", "Python", "Datenschutz"],
        )
        save_profile(profile, path=profile_path)
        loaded = load_profile(path=profile_path)

        assert loaded.name == "Max"
        assert loaded.expertise == "Python-Entwickler"
        assert loaded.preferred_language == "Deutsch"
        assert loaded.response_style == "kurz und direkt"
        assert "KI" in loaded.topics_of_interest

    def test_update_changes_only_specified_fields(self, profile_path):
        """
        GIVEN  stored profile with name="Max", expertise="Python"
        WHEN   update_profile(preferred_style="ausführlich") is called  # language-gate: ignore quoted value the test passes
        THEN   name and expertise unchanged
        AND    preferred_language="ausführlich"  # language-gate: ignore same quoted value asserted back
        """
        profile = UserProfile(name="Max", expertise="Python")
        save_profile(profile, path=profile_path)

        update_profile({"response_style": "ausführlich"}, path=profile_path)
        loaded = load_profile(path=profile_path)

        assert loaded.name == "Max"
        assert loaded.expertise == "Python"
        assert loaded.response_style == "ausführlich"

    def test_load_handles_corrupt_json_gracefully(self, profile_path):
        """
        GIVEN  a corrupt JSON file at the profile path
        WHEN   load_profile(path) is called
        THEN   no crash
        AND    the return is the default UserProfile
        """
        profile_path.write_text("{ dieser json ist kaputt !!!", encoding="utf-8")
        profile = load_profile(path=profile_path)

        assert isinstance(profile, UserProfile)
        assert profile.name is None

    def test_save_creates_parent_directory(self, tmp_path):
        """
        GIVEN  profile path in a directory that does not exist
        WHEN   save_profile() is called
        THEN   the directory gets created
        AND    the file gets written
        """
        deep_path = tmp_path / "deep" / "nested" / "profile.json"
        profile = UserProfile(name="Test")
        save_profile(profile, path=deep_path)

        assert deep_path.exists()
        assert json.loads(deep_path.read_text())["name"] == "Test"

    def test_profile_to_context_string(self, profile_path):
        """
        GIVEN  UserProfile with several fields
        WHEN   profile.to_context_string() is called
        THEN   the return is a non-empty string
        AND    it contains the user's name
        """
        profile = UserProfile(
            name="Anna",
            expertise="Grafikdesignerin",
            preferred_language="Deutsch",
        )
        ctx = profile.to_context_string()

        assert isinstance(ctx, str)
        assert "Anna" in ctx

    def test_preferred_language_is_fallback_not_override(self):
        """
        GIVEN  profile with a set preferred_language (round 14: English
               is the UI default, DE is opt-in)
        WHEN   to_context_string() is built
        THEN   no "ALWAYS respond in this language" override anymore — that
               would have forced English questions to be answered in German
        AND    language mirrors the INPUT language; profile language only a fallback
        """
        profile = UserProfile(name="Ben", preferred_language="Deutsch")
        ctx = profile.to_context_string()

        assert "ALWAYS respond in this language" not in ctx
        assert "SAME language the user writes in" in ctx
        assert "ONLY as a fallback" in ctx
        assert "Deutsch" in ctx

    def test_no_language_line_without_preferred_language(self):
        """
        GIVEN  profile without preferred_language
        WHEN   to_context_string() is built
        THEN   no Language line (no hidden language mandate)
        """
        ctx = UserProfile(name="Cara").to_context_string()

        assert "Language:" not in ctx
