"""
◑ Ephe – Thinking Stream Parser Tests
tests/test_thinking.py

TDD tests for the Gemma4 12B <|think|> mode.
Given/When/Then specifications.
"""
from __future__ import annotations

import pytest

from core.chat import ThinkingStreamParser, THINK_OPEN, THINK_CLOSE


# ThinkingStreamParser Unit Tests

class TestThinkingParser:
    """Parses Gemma4 <|think|> tags."""

    def test_GIVEN_stream_with_thinking_WHEN_parsed_THEN_separates_thought_from_answer(self):
        """
        GIVEN a stream output with <|think|>Ich überlege...<|/think|>Finale Antwort  # language-gate: ignore (verbatim fixture stream, fed to the parser below)
        WHEN  the ThinkingStreamParser processes the output
        THEN  thinking="Ich überlege...", answer="Finale Antwort"  # language-gate: ignore (verbatim asserted fixture values)
        """
        chunks: list[str] = []
        thinking: list[str] = []

        parser = ThinkingStreamParser(
            on_chunk=lambda c: chunks.append(c),
            on_thinking=lambda t: thinking.append(t),
        )

        parser.feed(f"{THINK_OPEN}Ich überlege...{THINK_CLOSE}Finale Antwort")
        parser.flush()

        assert "".join(thinking) == "Ich überlege..."
        assert "".join(chunks) == "Finale Antwort"
        assert parser.answer == "Finale Antwort"
        assert parser.thinking == "Ich überlege..."

    def test_GIVEN_stream_without_thinking_WHEN_parsed_THEN_returns_full_as_answer(self):
        """
        GIVEN a stream output without thinking tags
        WHEN  the ThinkingStreamParser processes the output
        THEN  thinking="", answer=the whole output
        """
        chunks: list[str] = []
        thinking: list[str] = []

        parser = ThinkingStreamParser(
            on_chunk=lambda c: chunks.append(c),
            on_thinking=lambda t: thinking.append(t),
        )

        parser.feed("Hallo, ich bin Ephe!")
        parser.flush()

        assert "".join(chunks) == "Hallo, ich bin Ephe!"
        assert "".join(thinking) == ""
        assert parser.answer == "Hallo, ich bin Ephe!"
        assert parser.thinking == ""

    def test_GIVEN_partial_thinking_tag_WHEN_streaming_chunk_by_chunk_THEN_buffers_correctly(self):
        """
        GIVEN thinking tags split across several chunks
        WHEN  the chunks are fed one at a time
        THEN  the tag boundaries are recognised correctly
        """
        chunks: list[str] = []
        thinking: list[str] = []

        parser = ThinkingStreamParser(
            on_chunk=lambda c: chunks.append(c),
            on_thinking=lambda t: thinking.append(t),
        )

        # simulate word-by-word streaming
        tokens = [
            "<|", "think", "|>",           # the opening tag arrives split
            "Denke ", "nach...",            # thinking content
            "<|/", "think", "|>",          # the closing tag arrives split
            "Die ", "Antwort ", "ist 42.",  # answer content
        ]

        for token in tokens:
            parser.feed(token)
        parser.flush()

        full_thought = "".join(thinking)
        full_answer = "".join(chunks)

        assert "Denke " in full_thought
        assert "nach..." in full_thought
        assert "42" in full_answer
        # No thinking tags left inside the answer!
        assert THINK_OPEN not in full_answer
        assert THINK_CLOSE not in full_answer

    def test_GIVEN_no_thinking_callback_WHEN_thinking_tags_present_THEN_strips_tags_silently(self):
        """
        GIVEN on_thinking=None (no callback)
        WHEN  the stream carries thinking tags
        THEN  the tags are stripped silently, only the answer comes through
        """
        chunks: list[str] = []

        parser = ThinkingStreamParser(
            on_chunk=lambda c: chunks.append(c),
            on_thinking=None,
        )

        parser.feed(f"{THINK_OPEN}Internes Denken{THINK_CLOSE}Sichtbare Antwort")
        parser.flush()

        assert "".join(chunks) == "Sichtbare Antwort"
        assert parser.thinking == "Internes Denken"
        assert parser.answer == "Sichtbare Antwort"

    def test_GIVEN_multiple_thinking_blocks_WHEN_parsed_THEN_all_collected(self):
        """
        GIVEN a stream with several thinking blocks
        WHEN  parsed
        THEN  all thinking blocks are collected
        """
        chunks: list[str] = []
        thinking: list[str] = []

        parser = ThinkingStreamParser(
            on_chunk=lambda c: chunks.append(c),
            on_thinking=lambda t: thinking.append(t),
        )

        text = (
            f"Intro {THINK_OPEN}Gedanke 1{THINK_CLOSE}"
            f"Mitte {THINK_OPEN}Gedanke 2{THINK_CLOSE}"
            f"Ende"
        )
        parser.feed(text)
        parser.flush()

        assert "Gedanke 1" in "".join(thinking)
        assert "Gedanke 2" in "".join(thinking)
        assert "Intro " in "".join(chunks)
        assert "Mitte " in "".join(chunks)
        assert "Ende" in "".join(chunks)

    def test_GIVEN_empty_thinking_block_WHEN_parsed_THEN_no_crash(self):
        """
        GIVEN an empty thinking block: <|think|><|/think|>
        WHEN  parsed
        THEN  no crash, thinking=""
        """
        chunks: list[str] = []

        parser = ThinkingStreamParser(
            on_chunk=lambda c: chunks.append(c),
            on_thinking=lambda _: None,
        )

        parser.feed(f"{THINK_OPEN}{THINK_CLOSE}Antwort")
        parser.flush()

        assert parser.thinking == ""
        assert parser.answer == "Antwort"
