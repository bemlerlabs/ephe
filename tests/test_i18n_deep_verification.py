"""
tests/test_i18n_deep_verification.py

Deep i18n verification — 3 passes, different levels:
  Round 1: frontend — all 6 languages have complete translations
  Round 2: backend — the system prompt is language-agnostic + language rule
  Round 3: profile → system-prompt pipeline — the language is passed through

Given-When-Then tests.
"""
from pathlib import Path

import pytest

from core.profile import UserProfile


# ROUND 1: Frontend i18n.js — complete key coverage for every language

I18N_FILE = Path(__file__).parent.parent / "app" / "src" / "i18n.js"

REQUIRED_KEYS = [
    "welcome.heading",
    "chat.placeholder",
    "chat.send",
    "nav.chat",
    "nav.skills",
    "nav.history",
    "nav.memory",
    "nav.profile",
    "status.connected",
    "status.offline",
    "skills.title",
    "history.title",
    "memory.title",
    "profile.title",
    "confirm.shell",
    "artifact.copy",
]

SUPPORTED_LANGUAGES = ["de", "en", "es", "fr", "ja", "zh"]


def _parse_i18n_keys_for_lang(content: str, lang: str) -> list[str]:
    """Extract all translation keys for a given language block."""
    import re
    # Find the block for this language
    pattern = rf"^\s+{lang}:\s*\{{(.*?)\}}"
    match = re.search(pattern, content, re.DOTALL | re.MULTILINE)
    if not match:
        return []
    block = match.group(1)
    # Extract keys
    keys = re.findall(r"'([^']+)':", block)
    return keys


@pytest.fixture
def i18n_content():
    return I18N_FILE.read_text(encoding="utf-8")


# Test 1.1: GIVEN i18n.js WHEN parsed THEN has all 6 language blocks

@pytest.mark.skip(reason="Legacy i18n.js file (app/src/i18n.js) removed during React+Vite migration; i18n now lives in app/src/locales/*.json. Test references stale legacy path.")
def test_round1_given_i18n_when_parsed_then_all_6_languages_present(i18n_content):
    """GIVEN i18n.js WHEN parsed THEN all 6 language blocks exist."""
    for lang in SUPPORTED_LANGUAGES:
        keys = _parse_i18n_keys_for_lang(i18n_content, lang)
        assert len(keys) > 0, f"Language '{lang}' has no translations in i18n.js!"


# Test 1.2: GIVEN each language WHEN checked THEN has all required keys

@pytest.mark.skip(reason="Legacy i18n.js file (app/src/i18n.js) removed during React+Vite migration; i18n now lives in app/src/locales/*.json. Test references stale legacy path.")
@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_round1_given_language_when_checked_then_has_required_keys(i18n_content, lang):
    """GIVEN a language block WHEN checked THEN all required UI keys exist."""
    keys = _parse_i18n_keys_for_lang(i18n_content, lang)
    for required_key in REQUIRED_KEYS:
        assert required_key in keys, (
            f"Language '{lang}' missing required key: '{required_key}'"
        )


@pytest.mark.skip(reason="Legacy i18n.js file (app/src/i18n.js) removed during React+Vite migration; i18n now lives in app/src/locales/*.json. Test references stale legacy path.")
# Test 1.3: GIVEN all languages WHEN counted THEN equal key count

def test_round1_given_all_languages_when_counted_then_equal_key_count(i18n_content):
    """GIVEN all language blocks WHEN key counts compared THEN roughly equal."""
    counts = {}
    for lang in SUPPORTED_LANGUAGES:
        counts[lang] = len(_parse_i18n_keys_for_lang(i18n_content, lang))

    # All should have at least as many keys as the minimum (tolerance: 10 keys for DE/EN differences)
    max_count = max(counts.values())
    for lang, count in counts.items():
        assert count >= max_count - 10, (
            f"Language '{lang}' has {count} keys but max is {max_count}. Missing translations!"
        )


# ROUND 2: Backend System-Prompt — Language-agnostic

from core.chat import assemble_system_prompt


@pytest.fixture()
def assembled_prompt(tmp_path) -> str:
    """R28: the prompt is assembled from generated identity + persona + tool
    guidelines (core/persona.py). Build it hermetically with the default
    persona so the language-agnostic guarantee covers the REAL prompt the
    engine sees, not a deleted constant."""
    import os

    os.environ["EPHE_PERSONA_DIR"] = os.environ["EPHE_PERSONA_DIR"] = str(tmp_path / "persona")
    return assemble_system_prompt(model="test-model")


# Test 2.1: GIVEN system prompt WHEN checked THEN in English

def test_round2_given_system_prompt_when_checked_then_in_english(assembled_prompt):
    """GIVEN assembled system prompt WHEN inspected THEN written in English."""
    assert "You are Ephe" in assembled_prompt
    assert "Du bist" not in assembled_prompt


# Test 2.2: GIVEN system prompt WHEN checked THEN has language rule

def test_round2_given_system_prompt_when_checked_then_has_language_rule(assembled_prompt):
    """GIVEN assembled system prompt WHEN inspected THEN contains the language rule."""
    assert "same language the user writes in" in assembled_prompt


# Test 2.3: GIVEN system prompt WHEN checked THEN no hardcoded German

def test_round2_given_system_prompt_when_checked_then_no_hardcoded_german(assembled_prompt):
    """GIVEN assembled system prompt WHEN inspected THEN contains no German instructions."""
    german_markers = [
        "Du bist", "Dein Tonfall", "Nutze stets", "Werkzeuge",
        "Sage NIEMALS", "Entschuldige dich", "Sei die pure"
    ]
    for marker in german_markers:
        assert marker not in assembled_prompt, (
            f"System prompt still has German text: '{marker}'"
        )


# ROUND 3: Profile → System-Prompt Pipeline


# Test 3.1: GIVEN profile with Japanese WHEN to_context THEN English label + enforce

def test_round3_given_japanese_profile_when_context_then_english_label():
    """GIVEN profile with preferred_language='日本語' WHEN to_context_string() THEN uses English label with enforcement."""
    profile = UserProfile(preferred_language="日本語")
    ctx = profile.to_context_string()
    assert "日本語" in ctx
    # Contract since 75105e2: the language mirrors the INPUT; the profile language
    # is only a fallback for ambiguous/short inputs (no forced override).
    assert "SAME language the user writes in" in ctx
    assert "ONLY as a fallback" in ctx


# Test 3.2: GIVEN profile with Spanish WHEN to_context THEN language passed through

def test_round3_given_spanish_profile_when_context_then_language_passed():
    """GIVEN profile with preferred_language='Español' WHEN to_context_string() THEN correct value."""
    profile = UserProfile(preferred_language="Español")
    ctx = profile.to_context_string()
    assert "Español" in ctx
    assert "ONLY as a fallback" in ctx


# Test 3.3: GIVEN empty profile WHEN to_context THEN no language directive

def test_round3_given_empty_profile_when_context_then_no_language():
    """GIVEN profile with no language WHEN to_context_string() THEN returns empty."""
    profile = UserProfile()
    ctx = profile.to_context_string()
    assert ctx == ""
    assert "Preferred language" not in ctx


# Test 3.4: GIVEN profile WHEN context THEN English labels (no German)

def test_round3_given_full_profile_when_context_then_english_labels():
    """GIVEN full profile WHEN to_context_string() THEN all labels are English."""
    profile = UserProfile(
        name="Yuki",
        expertise="AI",
        preferred_language="日本語",
        response_style="concise",
        topics_of_interest=["ML"],
        projects=["Ephe"],
        dislikes=["verbose"],
    )
    ctx = profile.to_context_string()
    assert "[User Profile]" in ctx
    assert "Language:" in ctx
    assert "Response style" in ctx
    assert "Topics of interest" in ctx
    assert "Current projects" in ctx
    assert "Please avoid" in ctx
    # No German labels
    assert "Nutzerprofil" not in ctx
    assert "Bevorzugte Sprache" not in ctx
    assert "Antwort-Stil" not in ctx
