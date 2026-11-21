"""The discovery meta tools answer in English.

The runtime strings of `tool_search`, `tool_describe` and `tool_call` reach a model as
output; every branch of those three calls is scored here against the vocabulary the
pre-wave answers used.

GIVEN / WHEN / THEN, strictly.
"""
from __future__ import annotations

import asyncio
import re

import pytest

from core.tools.discovery import (
    clear_search_memo,
    clear_session_tool_array,
    describe,
    search,
    set_session_tool_array,
    tool_call,
)

#: The German each branch could hand a model before this wave, verbatim. They are the
#: positive control for the vocabulary below: a zero that these five cannot pass would
#: be an empty matcher, not a measurement.
@pytest.fixture(autouse=True)
def _no_inherited_turn_state():
    """The repeat answer is a per-turn memory, the recorded array a per-session fact.

    Under `-n auto` a worker runs several files in one process, and a file that built
    an array leaves the request-gated families out of it — which turns the next file's
    core-active no-match into the whitelisted one.
    """
    clear_search_memo()
    clear_session_tool_array()
    yield
    clear_search_memo()
    clear_session_tool_array()


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


class TestAGermanTurnFindsItsVerb:
    """The index lines are English; a user's request is not always.

    `search()` matched the English hint and nothing else in the name tier, so a German
    turn got "No matching deferred tools" from a machine that holds the verb it asked
    for — measured on ``musik effekt`` before the keyword table existed."""

    def test_a_german_ask_names_the_verbs_that_make_its_material(self):
        """GIVEN a German ask for music and an effect
        THEN the two synthesiser verbs answer, and not the empty index."""
        clear_search_memo()
        try:
            hits = search("musik effekt")
        finally:
            clear_search_memo()

        assert "film_music" in hits
        assert "film_sound" in hits
        assert "No matching" not in hits

    def test_a_german_film_ask_reaches_the_cut_and_the_voice(self):
        """GIVEN a German sentence asking for a clip with music and a voice
        THEN the cutter and the speech verb are both in the answer."""
        clear_search_memo()
        try:
            hits = search("mach einen clip mit musik und stimme")  # language-gate: ignore
        finally:
            clear_search_memo()

        assert "film_clip" in hits
        assert "synthesize" in hits

    def test_a_german_document_ask_finds_the_word_processor(self):
        """GIVEN a German ask for a document
        THEN the .docx verb is offered beside the pdf verbs, because "dokument" is a
        word the English hint for create_docx does not contain."""
        clear_search_memo()
        try:
            hits = search("erzeuge ein pdf dokument")
        finally:
            clear_search_memo()

        assert "create_docx" in hits


class TestAQueryAnswersWhatItAsked:
    """Function words are not a topic.

    The name tier matched by substring over all query terms, so ``with`` — a term in
    "make a video with music and voice" — matched every hint that happened to contain
    the word and answered a four-word question with nine tools including a PDF and a
    swarm message."""

    def test_function_words_do_not_bring_in_the_shelf(self):
        clear_search_memo()
        try:
            hits = search("make a video with music and voice")
        finally:
            clear_search_memo()

        listed = [line.split(":")[0].removeprefix("- ") for line in hits.splitlines() if line.startswith("- ")]
        assert "create_pdf" not in listed
        assert "agent_message" not in listed
        assert "create_pitch_deck" not in listed
        assert "film_clip" in listed

    def test_a_word_that_only_starts_the_same_is_not_a_hit(self):
        """GIVEN the single term ``tab``
        THEN no tool is offered for whose description ``tab`` is merely the head of a
        longer word — the boundary the description tier has honoured all along."""
        clear_search_memo()
        try:
            hits = search("tab")
        finally:
            clear_search_memo()

        for line in hits.splitlines():
            if not line.startswith("- "):
                continue
            body = line.split(":", 1)[1]
            assert "table" not in body.lower() or "tab" in line.split(":")[0]


class TestAHitCarriesHowToCallIt:
    """A tool the model cannot call is a tool it searches again.

    `tool_describe` answers one tool's whole schema — 2 333 characters for
    ``film_clip`` — so a turn that reaches for five verbs pays five describes on top of
    its searches. The index line now names the arguments from the tool's own schema."""

    def test_the_required_argument_is_marked_and_the_optional_named(self):
        clear_search_memo()
        try:
            hits = search("film clip")
        finally:
            clear_search_memo()

        line = next(l for l in hits.splitlines() if l.startswith("- film_clip:"))
        assert "args:" in line
        assert "shots*" in line
        assert "music" in line
        assert "tool_call" in hits
        assert "* = required" in hits

    def test_the_whole_index_stays_at_its_old_footprint(self):
        """GIVEN the query that asks for everything
        THEN no argument list is attached — the budget pays for a verb that was found,
        not for the shelf."""
        clear_search_memo()
        try:
            everything = search("")
            one = search("film clip")
        finally:
            clear_search_memo()

        assert "args:" not in everything
        assert len(one) < len(everything)


class TestASearchAskedTwiceIsAnsweredOnce:
    """The round a model spends re-asking is a round off its budget."""

    def test_the_second_identical_query_names_the_tools_without_the_listing(self):
        clear_search_memo()
        try:
            first = search("musik effekt")
            second = search("musik effekt")
        finally:
            clear_search_memo()

        assert "film_music" in first and "film_sound" in first
        assert len(second) < len(first)
        assert "Same as your earlier search" in second
        assert "film_music" in second and "film_sound" in second

    def test_a_different_query_is_answered_in_full(self):
        clear_search_memo()
        try:
            search("musik effekt")
            other = search("film clip")
        finally:
            clear_search_memo()

        assert "Same as your earlier search" not in other
        assert "film_clip" in other

    def test_a_fresh_turn_answers_in_full_again(self):
        """GIVEN a turn that already searched and got the short repeat answer
        THEN the next turn's identical query is listed in full — the memo belongs to a
        turn, and a new turn re-reads the index the way its own messages ask."""
        clear_search_memo()
        search("musik effekt")
        search("musik effekt")
        clear_search_memo()
        try:
            again = search("musik effekt")
        finally:
            clear_search_memo()

        assert "Same as your earlier search" not in again
        assert "film_music" in again

    def test_an_empty_repeat_points_at_the_index_instead_of_repeating_nothing(self):
        clear_search_memo()
        try:
            search("zzzz qqqq wwwww")
            second = search("zzzz qqqq wwwww")
        finally:
            clear_search_memo()

        assert "No matching deferred tools" in search("qqqqzzzz wwwww xyyy")
        assert "nothing matched" in second
        assert "tool_search with an empty query" in second
