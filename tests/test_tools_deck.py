"""
◑ Ephe – core.tools.deck_tools (Phase 0.8 TDD)
tests/test_tools_deck.py

Covers helpers, slide parsing, safe download filenames.

Given / When / Then – strictly observed.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.tools.deck_tools import (
    _default_deck_slides,
    _enterprise_clean_text,
    _normalize_enterprise_slides,
    _normalize_hex_color,
    _parse_deck_slides,
    _pdf_escape,
    _safe_download_filename,
    _split_lines,
)


class TestSafeDownloadFilename:

    def test_replaces_spaces_with_underscores(self):
        result = _safe_download_filename("my deck.pdf", "default.pdf", ".pdf")
        assert " " not in result
        assert result.endswith(".pdf")

    def test_removes_special_chars(self):
        result = _safe_download_filename("bad/name?.pptx", "default.pptx", ".pptx")
        assert "/" not in result
        assert "?" not in result

    def test_uses_default_if_empty(self):
        result = _safe_download_filename("", "default.pptx", ".pptx")
        assert result == "default.pptx"

    def test_appends_suffix_if_missing(self):
        result = _safe_download_filename("deck", "default.pdf", ".pdf")
        assert result.endswith(".pdf")


class TestSplitLines:

    def test_splits_long_text(self):
        result = _split_lines("hello world this is a long text", max_chars=10, max_lines=4)
        assert isinstance(result, list)
        assert len(result) >= 2

    def test_limits_to_max_lines(self):
        result = _split_lines("one two three four five six", max_chars=4, max_lines=3)
        assert len(result) <= 3

    def test_returns_single_line_for_short_text(self):
        result = _split_lines("hello", max_chars=72, max_lines=4)
        assert result == ["hello"]

    def test_returns_empty_list_for_empty_text(self):
        result = _split_lines("", max_chars=72, max_lines=4)
        assert result == [""]


class TestEnterpriseCleanText:

    def test_removes_emojis(self):
        result = _enterprise_clean_text("awesome 😎 cool 🚀")
        assert "😎" not in result
        assert "🚀" not in result

    def test_replaces_amateur_words(self):
        result = _enterprise_clean_text("This is awesome and cool!")
        assert "awesome" not in result
        assert "cool" not in result
        assert "strong" in result
        assert "credible" in result

    def test_replaces_multi_word_phrases(self):
        result = _enterprise_clean_text("A game changer for the industry")
        assert "game changer" not in result
        assert "strategic shift" in result

    def test_normalizes_whitespace(self):
        result = _enterprise_clean_text("  too   much  space  ")
        assert result == "too much space"

    def test_handles_empty_text(self):
        assert _enterprise_clean_text("") == ""
        assert _enterprise_clean_text(None) == ""


class TestNormalizeEnterpriseSlides:

    def test_cleans_all_slide_fields(self):
        raw = [{"title": "Product 😎", "claim": "Our cool solution", "body": "Really awesome features", "proof": "Great results"}]
        result = _normalize_enterprise_slides(raw)
        assert "😎" not in result[0]["title"]
        assert "cool" not in result[0]["claim"]
        assert "awesome" not in result[0]["body"]
        assert "great" not in result[0]["proof"] or "strong" in result[0]["body"]

    def test_adds_missing_fields(self):
        raw = [{}]
        result = _normalize_enterprise_slides(raw)
        assert result[0]["title"] == "Slide 1"
        assert result[0]["proof"] == "Proof object"


class TestDefaultDeckSlides:

    def test_returns_11_slides(self):
        slides = _default_deck_slides("Ephe", "investors", "Thesis")
        assert len(slides) == 11

    def test_first_slide_contains_topic(self):
        slides = _default_deck_slides("My Product", "investors", "Thesis")
        assert "My Product" in slides[0]["title"]

    def test_each_slide_has_required_keys(self):
        slides = _default_deck_slides("Test", "audience", "Thesis")
        for s in slides:
            assert "title" in s
            assert "claim" in s
            assert "body" in s
            assert "visual" in s
            assert "proof" in s


class TestParseDeckSlides:

    def test_parses_markdown_blocks(self):
        text = "# Slide 1\nThis is the claim\nBody text here\n\n# Slide 2\nSecond claim\nMore body"
        result = _parse_deck_slides(text, "Topic", "Audience", "Thesis")
        assert len(result) == 2
        assert result[0]["title"] == "Slide 1"

    def test_falls_back_to_defaults_for_empty_input(self):
        result = _parse_deck_slides("", "Topic", "Audience", "Thesis")
        assert len(result) == 11

    def test_falls_back_to_defaults_for_none(self):
        result = _parse_deck_slides(None, "Topic", "Audience", "Thesis")
        assert len(result) == 11

    def test_normalizes_dict_slides(self):
        slides = [{"title": "Hello", "claim": "Claim", "body": "Body"}]
        result = _parse_deck_slides(slides, "Topic", "Audience", "Thesis")
        assert len(result) == 1
        assert result[0]["title"] == "Hello"


class TestPdfEscape:

    def test_escapes_backslashes(self):
        assert _pdf_escape("a\\b") == "a\\\\b"

    def test_escapes_parentheses(self):
        assert _pdf_escape("a(b)") == "a\\(b\\)"

    def test_replaces_newlines_with_spaces(self):
        result = _pdf_escape("line1\nline2")
        assert "\n" not in result

    def test_handles_empty_string(self):
        assert _pdf_escape("") == ""


class TestNormalizeHexColor:

    def test_normalizes_valid_hex(self):
        assert _normalize_hex_color("#16a34a", "") == "16A34A"

    def test_returns_fallback_for_invalid(self):
        assert _normalize_hex_color("invalid", "DEFAULT") == "DEFAULT"

    def test_returns_fallback_for_empty(self):
        assert _normalize_hex_color("", "FALLBACK") == "FALLBACK"
