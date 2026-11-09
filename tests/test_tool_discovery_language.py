"""The discovery meta tools answer in English.

The runtime strings of `tool_search`, `tool_describe` and `tool_call` reach a model as
output; every branch of those three calls is scored here against the vocabulary the
pre-wave answers used.

GIVEN / WHEN / THEN, strictly.
"""
from __future__ import annotations

import asyncio
import re

from core.tools.discovery import (
    clear_session_tool_array,
    describe,
    search,
    set_session_tool_array,
    tool_call,
)

#: The German each branch could hand a model before this wave, verbatim. They are the
#: positive control for the vocabulary below: a zero that these five cannot pass would
#: be an empty matcher, not a measurement.
PRE_WAVE_ANSWERS = (
    "Keine passende Deferred-Tools. Kern-Tools sind bereits aktiv.",  # language-gate: ignore
    "Verfuegbare Deferred-Tools:",  # language-gate: ignore
    "[tool_describe] kein Tool 'create_pdf' gefunden",  # language-gate: ignore
    "[tool_call] ungueltiges JSON in 'arguments': bad",  # language-gate: ignore
    "[tool_call] 'arguments' muss ein JSON-Objekt sein",  # language-gate: ignore
)

#: Every German token those five answers used, one list and no detector. The boundaries
#: keep `ein` out of an English word while still catching `ein JSON-Objekt`.
GERMAN_TOKENS = (
    "keine", "passende", "kern-tools", "sind", "bereits", "aktiv",  # language-gate: ignore
    "verfuegbare", "kein", "gefunden", "ungueltiges", "muss",  # language-gate: ignore
    "json-objekt", "ein",  # language-gate: ignore
)

GERMAN = re.compile(
    r"(?<![A-Za-z])(" + "|".join(sorted(GERMAN_TOKENS, key=len, reverse=True)) + r")(?![A-Za-z])",
    re.IGNORECASE,
)


def _armed_session() -> list[str]:
    """The answers a full-core session gets: the index, the empty query, the dead end."""
    clear_session_tool_array()
    return [search("pdf"), search(""), search("qqzz wwyymm"), describe("no_such_tool_qqzz")]


def _whitelisted_session() -> list[str]:
    """The answers a session with a narrowed array gets, plus both tool_call refusals."""
    set_session_tool_array(["fetch_url"])
    try:
        answers = [search("qqzz wwyymm"), search("web search")]
    finally:
        clear_session_tool_array()
    answers.append(asyncio.run(tool_call("get_datetime", "{not json")))
    answers.append(asyncio.run(tool_call("get_datetime", '["not", "an", "object"]')))
    return answers


def test_the_discovery_answers_carry_no_german_word():
    """GIVEN every answer tool_search, tool_describe and tool_call can produce
    WHEN each is scored against the vocabulary the pre-wave answers used
    THEN none holds a German word, and that vocabulary still sees the pre-wave text."""
    missed = [text for text in PRE_WAVE_ANSWERS if not GERMAN.search(text)]
    assert missed == [], f"the vocabulary lost the German it was drawn from: {missed}"

    answers = _armed_session() + _whitelisted_session()
    found = [(GERMAN.findall(text), text) for text in answers if GERMAN.search(text)]

    assert found == [], "German in the discovery output: " + "; ".join(
        f"{words} in {text[:120]!r}" for words, text in found
    )
