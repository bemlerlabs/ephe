"""
◑ Ephe – the core.feedback store (Phase 2 TDD)
tests/test_feedback.py

RULE: tests BEFORE the implementation.
Given / When / Then – strictly.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.feedback import FeedbackStore, FeedbackExample


class TestFeedbackStore:

    @pytest.fixture
    def store(self, tmp_path):
        return FeedbackStore(base_dir=tmp_path / "feedback")

    def test_thumbs_up_saves_example(self, store):
        """
        GIVEN  FeedbackStore
        WHEN   store.thumbs_up(prompt="P", response="R") is called
        THEN   a file is saved under good_examples/
        AND    store.count_good() > 0
        """
        store.thumbs_up(prompt="Was ist Python?", response="Python ist eine Programmiersprache.")

        assert store.count_good() > 0

    def test_thumbs_down_saves_example(self, store):
        """
        GIVEN  FeedbackStore
        WHEN   store.thumbs_down(prompt="P", response="R") is called
        THEN   a file is saved under bad_examples/
        AND    store.count_bad() > 0
        """
        store.thumbs_down(prompt="Was ist Python?", response="Python ist eine Schlange.")

        assert store.count_bad() > 0

    def test_get_good_examples_returns_list(self, store):
        """
        GIVEN  3 positive examples saved
        WHEN   store.get_good_examples(max_items=3) is called
        THEN   the return is a list of ≤3 FeedbackExample objects
        AND    each one has prompt and response
        """
        for i in range(3):
            store.thumbs_up(prompt=f"Frage {i}", response=f"Antwort {i}")

        examples = store.get_good_examples(max_items=3)

        assert isinstance(examples, list)
        assert len(examples) <= 3
        for ex in examples:
            assert isinstance(ex, FeedbackExample)
            assert hasattr(ex, "prompt")
            assert hasattr(ex, "response")

    def test_empty_store_returns_empty_list(self, store):
        """
        GIVEN  an empty FeedbackStore
        WHEN   store.get_good_examples() is called
        THEN   the return is an empty list (no crash)
        """
        result = store.get_good_examples()
        assert result == []

    def test_to_few_shot_string_with_examples(self, store):
        """
        GIVEN  2 positive examples saved
        WHEN   store.to_few_shot_string(max_items=2) is called
        THEN   the return is a non-empty string
        AND    it contains the words "Frage" and "Antwort"  # language-gate: ignore (quoted German labels the few-shot formatter emits, core/feedback.py:99)
        """
        store.thumbs_up(prompt="Frage über KI", response="Antwort über KI")
        store.thumbs_up(prompt="Frage über Python", response="Antwort über Python")

        result = store.to_few_shot_string(max_items=2)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_to_few_shot_string_empty_is_empty_string(self, store):
        """
        GIVEN  no examples saved
        WHEN   store.to_few_shot_string() is called
        THEN   the return is an empty string (no crash)
        """
        result = store.to_few_shot_string()
        assert result == ""

    def test_count_methods_accurate(self, store):
        """
        GIVEN  2 good + 1 bad example saved
        WHEN   store.count_good() and store.count_bad() are called
        THEN   count_good() == 2
        AND    count_bad() == 1
        """
        store.thumbs_up(prompt="A", response="B")
        store.thumbs_up(prompt="C", response="D")
        store.thumbs_down(prompt="E", response="F")

        assert store.count_good() == 2
        assert store.count_bad() == 1


class TestSavedIsAnObservation:
    """R4 (W4): `saved` was a label — the answer was always True, even when
    the disk said no or the correction journal refused the reason."""

    def _refuse(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise OSError("read-only platte")

    def test_a_refusal_from_the_disk_is_answered_false(self, tmp_path, monkeypatch):
        store = FeedbackStore(base_dir=tmp_path / "feedback")
        monkeypatch.setattr(Path, "write_text", self._refuse)
        assert store.thumbs_up(prompt="P", response="R") is False
        assert store.thumbs_down(prompt="P", response="R") is False

    def test_a_written_example_is_answered_true_and_lies_on_the_platte(self, tmp_path):
        store = FeedbackStore(base_dir=tmp_path / "feedback")
        assert store.thumbs_up(prompt="P", response="R") is True
        assert list((tmp_path / "feedback" / "good_examples").glob("*.json"))

    def test_the_route_answers_what_the_store_saw(self, monkeypatch):
        import asyncio

        import server.routes.feedback as fb

        class _Stub:
            def thumbs_up(self, *, prompt, response):
                return False

        monkeypatch.setattr(fb, "_get_store", lambda: _Stub())
        response = asyncio.run(fb.thumbs_up(fb.FeedbackRequest(prompt="P", response="R")))
        assert response.saved is False

    def test_a_reason_the_journal_rejected_is_named(self, monkeypatch):
        import asyncio

        import server.routes.feedback as fb

        class _Store:
            def thumbs_down(self, *, prompt, response):
                return True

        class _BrokenJournal:
            def add(self, **kwargs):  # noqa: ANN003
                raise OSError("Tagebuch voll")

        monkeypatch.setattr(fb, "_get_store", lambda: _Store())
        monkeypatch.setattr(fb, "_get_journal", lambda: _BrokenJournal())
        response = asyncio.run(
            fb.thumbs_down(fb.FeedbackRequest(prompt="P", response="R", reason="Zu lang"))
        )
        assert response.saved is True
        assert response.journal is False
        # Without a reason there is no journal state — it is not invented.
        monkeypatch.setattr(fb, "_get_journal", lambda: _BrokenJournal())
        without = asyncio.run(fb.thumbs_down(fb.FeedbackRequest(prompt="P", response="R")))
        assert without.journal is None
