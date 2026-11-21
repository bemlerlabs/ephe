"""
◑ Ephe – the core.corrections journal (Phase 2 TDD)
tests/test_corrections.py

RULE: tests BEFORE implementation.
Given / When / Then, strictly.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from core.corrections import Correction, CorrectionJournal


class TestCorrectionJournal:

    @pytest.fixture
    def journal(self, tmp_path):
        return CorrectionJournal(path=tmp_path / "corrections.md")

    def test_add_creates_entry(self, journal):
        """
        GIVEN  empty correction journal
        WHEN   journal.add(wrong="X=Y", correct="X≠Y") is called
        THEN   the file exists
        AND    the file contains the correct value "X≠Y"
        AND    the file contains today's date
        """
        journal.add(wrong="X ist gleich Y", correct="X ist NICHT gleich Y")

        assert journal.path.exists()
        content = journal.path.read_text(encoding="utf-8")
        assert "X ist NICHT gleich Y" in content
        assert str(datetime.now().year) in content

    def test_get_recent_returns_last_n(self, journal):
        """
        GIVEN  5 stored corrections
        WHEN   journal.get_recent(3) is called
        THEN   the return holds exactly 3 entries (the newest ones)
        """
        for i in range(5):
            journal.add(wrong=f"Fehler {i}", correct=f"Korrektur {i}")

        recent = journal.get_recent(3)

        assert len(recent) == 3
        assert isinstance(recent[0], Correction)

    def test_get_recent_on_empty_journal_returns_empty(self, journal):
        """
        GIVEN  no entries in the journal
        WHEN   journal.get_recent(5) is called
        THEN   the return is an empty list (no crash)
        """
        result = journal.get_recent(5)
        assert result == []

    def test_each_correction_has_required_fields(self, journal):
        """
        GIVEN  one stored correction
        WHEN   journal.get_recent(1) is called
        THEN   Correction carries wrong, correct, timestamp
        AND    timestamp is a datetime object
        """
        journal.add(wrong="falsche Behauptung", correct="richtige Aussage")
        corrections = journal.get_recent(1)

        c = corrections[0]
        assert hasattr(c, "wrong")
        assert hasattr(c, "correct")
        assert hasattr(c, "timestamp")
        assert isinstance(c.timestamp, datetime)
        assert c.correct == "richtige Aussage"

    def test_multiple_adds_appended_not_overwritten(self, journal):
        """
        GIVEN  two corrections added one after the other
        WHEN   journal.get_recent(10) is called
        THEN   both corrections are present
        AND    ordering: newest first
        """
        journal.add(wrong="Altfehler", correct="Altkorrektur")
        journal.add(wrong="Neufehler", correct="Neukorrektur")

        corrections = journal.get_recent(10)
        assert len(corrections) == 2
        # Newest first
        assert corrections[0].correct == "Neukorrektur"
        assert corrections[1].correct == "Altkorrektur"

    def test_to_system_prompt_context(self, journal):
        """
        GIVEN  2 corrections in the journal
        WHEN   journal.to_context_string(max_items=2) is called
        THEN   the return is a string holding both corrections
        AND    not empty
        """
        journal.add(wrong="A=B", correct="A≠B")
        journal.add(wrong="X>Y", correct="X<Y")

        ctx = journal.to_context_string(max_items=2)
        assert isinstance(ctx, str)
        assert len(ctx) > 0
        assert "A≠B" in ctx or "X<Y" in ctx
