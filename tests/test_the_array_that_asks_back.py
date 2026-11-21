"""The array that asks back: a turn that asks for media carries the media verbs.

The seven studio verbs sit outside ``CORE_TOOLS`` — 7 341 characters measured
2026-11-18 — because a chat turn has no use for a cutter. Before this rule a turn
asking for a clip spent five searches and two describes of a fourteen-round budget
reaching those same seven. Now the ask itself opens the door, by the same keyword
table ``tool_search`` uses, for the base array only and only for what was named.
"""

from __future__ import annotations

import json

import pytest

from core.tools.discovery import (
    REQUESTED_EXTRA_FAMILIES,
    admit_requested_tools,
    clear_search_memo,
    clear_session_tool_array,
)
from core.tools.session_ctx import reset_current_mode, set_current_mode

STUDIO = frozenset({
    "film_card", "film_sound", "film_music", "film_clip", "film_job",
    "film_status", "synthesize",
})
ALL_SEVEN_CHARS = 7_341

# The asks are product text: a user writes them in German, and the rule has to answer
# the language the user actually speaks.
CLIP_ASK = "mach einen clip mit musik und stimme"  # language-gate: ignore
TRAILER_ASK = "schneide mir einen trailer"  # language-gate: ignore
MUSIC_ASK = "leg eine ruhige musik darunter"  # language-gate: ignore
CARD_ASK = "mach eine titelkarte, einen effekt, eine musik, eine stimme und schneide den clip"  # language-gate: ignore
STATUS_ASK = "welche ausstattung hat die maschine"  # language-gate: ignore
CHAT_ASK = "was macht ihr heute so?"  # language-gate: ignore
SCENE_ASK = "mach einen clip mit musik"  # language-gate: ignore
SCENE_REPLY = "Ich habe zwei Standbilder gebaut."  # language-gate: ignore
LOUDER_ASK = "und jetzt lauter"  # language-gate: ignore
TITLE_ASK = "mach eine titelkarte fuer den anfang"  # language-gate: ignore
CUT_FROM_STILLS_ASK = "schneide einen clip aus den bildern"  # language-gate: ignore


def _names(messages: list, allowed_tool_names: list[str] | None = None) -> set[str]:
    from core.chat_context import _tools_for_messages

    return {
        entry["function"]["name"]
        for entry in _tools_for_messages(messages, allowed_tool_names=allowed_tool_names)
    }


def _user(text: str) -> list:
    return [{"role": "user", "content": text}]


def _studio(names: set[str]) -> set[str]:
    return names & STUDIO


@pytest.fixture(autouse=True)
def _no_inherited_turn_state():
    # Building an array records it for the session, and a search memo lives as long as
    # the turn: a worker that runs this file before another one's discovery test would
    # otherwise hand it a whitelisted session it never asked for.
    clear_search_memo()
    clear_session_tool_array()
    yield
    clear_search_memo()
    clear_session_tool_array()


@pytest.fixture(autouse=True)
def _no_studio_mode():
    token = set_current_mode("")
    yield
    reset_current_mode(token)


class TestATurnThatAsksForMediaCarriesItsVerbs:
    def test_a_german_clip_ask_ships_the_cutter_the_bed_and_the_voice(self):
        names = _names(_user(CLIP_ASK))
        assert {"film_clip", "film_music", "synthesize"} <= _studio(names), sorted(names)

    def test_an_english_ask_ships_the_same_three(self):
        names = _names(_user("make a video with music and a voice line"))
        assert {"film_clip", "film_music", "synthesize"} <= _studio(names), sorted(names)

    def test_the_two_verbs_that_report_on_a_render_join_a_making_verb(self):
        names = _names(_user(TRAILER_ASK))
        assert "film_clip" in _studio(names), sorted(names)
        assert {"film_job", "film_status"} <= _studio(names), sorted(names)

    def test_a_capability_question_ships_the_answer_not_the_making_verbs(self):
        names = _names(_user(STATUS_ASK))
        assert "film_status" in _studio(names), sorted(names)
        assert not _studio(names) & {"film_clip", "film_music", "film_card"}, sorted(names)

    def test_a_followup_turn_keeps_what_the_scene_started(self):
        messages = [
            {"role": "user", "content": SCENE_ASK},
            {"role": "assistant", "content": SCENE_REPLY},
            {"role": "user", "content": LOUDER_ASK},
        ]
        assert "film_music" in _studio(_names(messages))


class TestATurnThatAskedForNothingPaysNothing:
    def test_an_ordinary_chat_turn_ships_no_studio_verb(self):
        assert _studio(_names(_user(CHAT_ASK))) == set()

    def test_a_code_question_about_audio_is_not_a_media_request(self):
        assert _studio(_names(_user("why does the audio player stutter on seek"))) == set()

    def test_an_unrelated_document_ask_ships_no_studio_verb(self):
        assert _studio(_names(_user("make me a qr code for the site"))) == set()

    def test_only_what_was_named_arrives(self):
        names = _studio(_names(_user(MUSIC_ASK)))
        assert "film_music" in names
        assert "film_clip" not in names, sorted(names)

    def test_the_whole_family_stays_within_the_measured_seven(self):
        from core.chat_context import _tools_for_messages

        base = len(json.dumps(_tools_for_messages(_user(CHAT_ASK))))
        asked = len(json.dumps(_tools_for_messages(_user(CARD_ASK))))
        assert asked - base <= ALL_SEVEN_CHARS, (base, asked)


class TestTheDoorOpensWhereItOpenedBefore:
    def test_a_skill_that_named_its_tools_is_not_second_guessed(self):
        names = _names(_user(CLIP_ASK), allowed_tool_names=["read_file"])
        assert _studio(names) == set(), sorted(names)

    def test_an_admitted_verb_is_the_very_schema_the_registry_dispatches(self):
        from core.chat_context import _cached_tool_schemas, _tools_for_messages

        shipped = {
            entry["function"]["name"]: entry
            for entry in _tools_for_messages(_user("make a video with music"))
        }
        catalog = {
            entry["function"]["name"]: entry for entry in _cached_tool_schemas()
        }
        assert shipped["film_clip"] == catalog["film_clip"]

    def test_admission_adds_and_never_takes_away(self):
        plain = _names(_user(CHAT_ASK)) - STUDIO
        asked = _names(_user(CLIP_ASK)) - STUDIO
        assert asked == plain, (sorted(plain - asked), sorted(asked - plain))

    def test_a_plan_session_is_offered_no_verb_it_would_only_refuse(self):
        token = set_current_mode("plan")
        try:
            names = _names(_user(CLIP_ASK))
        finally:
            reset_current_mode(token)
        assert not _studio(names) & {
            "film_clip", "film_music", "film_card", "film_sound", "synthesize",
        }, sorted(names)


class TestTheTableIsTheOnlyVocabulary:
    def test_every_admittable_name_has_a_keyword_entry_or_a_hint(self):
        from core.tools.discovery import _TOOL_HINTS, _TOOL_KEYWORDS

        for names in REQUESTED_EXTRA_FAMILIES.values():
            for name in names:
                assert name in _TOOL_KEYWORDS or name in _TOOL_HINTS, name

    def test_admission_reads_the_shared_table_and_nothing_else(self):
        # A verb reachable only through a keyword stops; a word in the name still reaches.
        from core.tools import discovery

        saved = dict(discovery._TOOL_KEYWORDS)
        discovery._TOOL_KEYWORDS = {}
        try:
            keyword_only = _names(_user(TITLE_ASK))
            named_in_name = _names(_user(CUT_FROM_STILLS_ASK))
        finally:
            discovery._TOOL_KEYWORDS = saved
        assert "film_card" not in _studio(keyword_only), sorted(keyword_only)
        assert "film_clip" in _studio(named_in_name), sorted(named_in_name)

    def test_a_catalog_without_the_verb_admits_nothing(self):
        catalog = [{"function": {"name": "film_status", "description": "", "parameters": {}}}]
        out = admit_requested_tools([], _user(CLIP_ASK), catalog)
        assert [entry["function"]["name"] for entry in out] == []
