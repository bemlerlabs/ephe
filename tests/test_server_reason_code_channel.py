"""Server prose that reaches a reader has to carry a code the surface can translate by.

The measured reason this file exists: two sentences in `server/routes/chat.py` are German, they arrive in the chat's
error display, and nothing beside them names what they are — so the only way to make an English reader
see English was to rewrite the sentence and take the German reader's text with it. That is the defect
this repo already hit with 23 receipt lines that lost their language on the way to English.

The frame convention is M's, from `f5d88653`: `reason_code` and `reason_params` travel beside the
sentence, and only when a code is known — `tool_done` adds neither key for an uncoded result, and the
error frame here is held to the same rule. The sentence itself is pinned byte-for-byte, because a
channel is a promise to leave the text alone until the surface asks for something else.

2026-11-24, the day the surface asked: both bundles already carried `serverError.silent_engine_turn`
and `silent_after_tools_turn`, so the two sentences in `server/routes/chat.py` became English
fallbacks and the German the chat panel shows is the bundle's. The pin moved along to the pair that
has to agree now — the English leaf and the server's sentence.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from server.routes.chat import (
    SILENT_AFTER_TOOLS_TURN,
    SILENT_ENGINE_TURN,
    silent_turn_event,
    silent_turn_message,
)

#: every coded server sentence the chat stream can emit, with the code the surface will read
CODED_SENTENCES = {
    "silent_engine_turn": SILENT_ENGINE_TURN,
    "silent_after_tools_turn": SILENT_AFTER_TOOLS_TURN,
}

TOOLS = [{"tool": "create_pdf", "result": "ok"}]


def test_a_silent_turn_becomes_an_event_with_a_code_beside_its_sentence():
    event = silent_turn_event("", [])
    assert event is not None
    assert event["type"] == "error"
    assert event["reason_code"] == "silent_engine_turn"
    assert event["msg"] == SILENT_ENGINE_TURN


def test_a_turn_that_ran_tools_and_then_said_nothing_codes_differently():
    event = silent_turn_event("   \n ", TOOLS)
    assert event is not None
    assert event["reason_code"] == "silent_after_tools_turn"
    assert event["msg"] == SILENT_AFTER_TOOLS_TURN


def test_a_turn_with_content_emits_no_error_event():
    assert silent_turn_event("Hier ist der Bericht.", TOOLS) is None


def test_the_code_is_a_stable_identifier_and_not_a_sentence():
    for code in CODED_SENTENCES:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", code), code


def test_the_channel_covers_every_coded_sentence_the_module_can_emit():
    """A new silent-turn sentence has to arrive with its code, or this file does not know it."""
    assert set(CODED_SENTENCES.values()) == {SILENT_ENGINE_TURN, SILENT_AFTER_TOOLS_TURN}
    for code, sentence in CODED_SENTENCES.items():
        answer = "" if code == "silent_engine_turn" else ""
        tools = [] if code == "silent_engine_turn" else TOOLS
        event = silent_turn_event(answer, tools)
        assert event is not None and event["reason_code"] == code
        assert event["msg"] == sentence


def test_the_older_helper_still_answers_with_the_sentence_alone():
    """`silent_turn_message` keeps its contract: text in, sentence or None out.

    It is imported by `tests/test_r3_silent_engine_turn.py` and stays the readable form; the event is
    what the stream needs on top of it.
    """
    assert silent_turn_message("", []) is SILENT_ENGINE_TURN
    assert silent_turn_message("", TOOLS) is SILENT_AFTER_TOOLS_TURN
    assert silent_turn_message("a finished answer", []) is None


# strings a browser loads or a user reads, checked for the language they arrive in
#
# The markers are written as escapes on purpose: a file whose job is to notice German
# must not itself raise the language ratchet it enforces.
_GERMAN_MARKERS = (
    "\xe4", "\xf6", "\xfc", "\xc4", "\xd6", "\xdc", "\xdf",  # umlauts and the sharp s
    "nicht ", "und ", "f\xfcr ", "mit ", "ausserhalb", "keine ",  # language-gate: ignore (the detector's own vocabulary)
)


def _gerkish(text: str) -> list[str]:
    """Lines carrying a marker this repository's English prose never uses."""
    return [line.strip() for line in text.splitlines() if any(m in line for m in _GERMAN_MARKERS)]


def test_the_mobile_redirect_page_arrives_in_the_language_it_declares():
    """`_MOBILE_HTML` says `<html lang="en">` and is served verbatim to a phone."""
    from server.main import _MOBILE_HTML

    assert 'lang="en"' in _MOBILE_HTML
    assert _gerkish(_MOBILE_HTML) == []


def test_the_adoption_refusal_names_its_setting_in_one_language():
    """The 422 asks for a destination and points at the setting that holds one.

    It used to point there with the German bundle's label inside an English sentence, which
    addresses nothing in an English interface; the name it uses now is the setting's own key
    in the register, so the hint survives a language switch.
    """
    from server.routes.artifacts import NO_DESTINATION_HINT

    assert _gerkish(NO_DESTINATION_HINT) == []
    assert "output_dir" in NO_DESTINATION_HINT, "the hint has to name the field the setting writes"



# The two silent-turn sentences, after the surface asked for its own text

def _bundle(language: str) -> dict[str, str]:
    """The `serverError` half of one locale bundle, as the client reads it."""
    path = Path(__file__).resolve().parents[1] / "app" / "src" / "locales" / f"{language}.json"
    return json.loads(path.read_text(encoding="utf-8"))["serverError"]


def test_the_fallback_a_client_reads_is_english():
    """The sentence beside the code is what an untranslated client shows, so it is English.

    Measured 2026-11-24: these two were the last German sentences in the server's chat path,
    and both bundles already carried the code, so the fallback could become what AGENTS.md
    asks for without a reader losing their text.
    """
    for sentence in (SILENT_ENGINE_TURN, SILENT_AFTER_TOOLS_TURN):
        assert _gerkish(sentence) == [], sentence
        assert len(sentence) > 40, "a fallback has to say something to a reader"


def test_both_bundles_hold_the_sentence_the_code_names():
    """Given the two codes, When both bundles are read, Then each reader's sentence is there and agrees with the fallback.

    The English leaf is the server's sentence byte for byte — one fact, one home — and the
    German leaf differs from it, which is the whole of what the German surface shows. The
    German lives here and nowhere in the server, which is what let the fallback turn English.
    """
    de, en = _bundle("de"), _bundle("en")
    for code, fallback in CODED_SENTENCES.items():
        assert en.get(code) == fallback, f"serverError.{code} in en drifted from the server's sentence"
        assert de.get(code) and de[code].strip(), f"serverError.{code} missing from de"
        assert de[code] != en[code], f"serverError.{code}: the German surface shows the English sentence"
        assert len(de[code]) > 40, f"serverError.{code} in de is not a sentence"
