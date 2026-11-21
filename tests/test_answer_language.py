"""The answer language follows the question.

Two causes stay apart, and this file guards the one that is ours. `core/persona.py:46-47` tells the
engine "ALWAYS respond in the same language the user writes in … Non-negotiable", and the persona in
use on the owner's machine carries that line (`persona_source()` names `~/.ephe/persona.md`, 1341
chars, measured 2026-10-11). A German turn answered in English is then either the instruction not
reaching the model -- an assembly or persona change, testable without an engine and held by
`TestTheInstructionReachesTheModel` -- or a pass that ignores it, which is only visible by spending a
turn, and `TestOneRealTurn` does that behind a switch.

`TestTheRevisionKeepsTheUsersLanguage` guards the third cause the receipts showed: the reflect/revise
loop appends its own critique under the role `user`, so the newest turn of the thread is our English
sentence, and the stored turn `62c693670866` answers *that* instead of the request.

The live leg reads the engine the user chose with `ephe configure` (`~/.ephe/engine.json` through
`EngineChoice.apply_env`, then `core.model_provider.build_provider_client`), so no endpoint and no
token appear in this repository, and a machine without a persisted engine skips instead of passing on
nothing:

    EPHE_ANSWER_LANGUAGE_LIVE=1 .venv/bin/python -m pytest tests/test_answer_language.py -q
"""
from __future__ import annotations

import asyncio
import os

import pytest

from core.chat import _assemble_system_prompt_into, assemble_system_prompt
from core.persona import DEFAULT_PERSONA, write_persona
from tests.test_react import GOOD_ANSWER, QUESTION

RULE_FRAGMENT = "same language the user writes in"
#: The turn the plan-surface probe typed (`out/plan-surface/measure2.mjs:10`), kept because it is the
#: input the defect was seen on: an explicit instruction that names German as the wanted language.
GERMAN_TURN = "Ephe, unser eigenes Produkt. Reine Marketing-Landingpage, dunkel & techy, Deutsch."  # language-gate: ignore
SHORT_GERMAN_TURN = "Kannst du mir in zwei Sätzen erklären, was eine Hashmap ist?"  # language-gate: ignore
ENGLISH_TURN = "Can you explain in two sentences what a hashmap is?"

#: Function words, not cognates: "Hashmap" and "erklären"/"explain" appear in a reply in either  # language-gate: ignore
#: language and would make the two lists agree with each other. These are instrument data, so each
#: German line carries the same pragma the detector in `scripts/language_inventory.py:27-34` carries on
#: its own marker list -- the gate scores developer prose, and a test that could not name the languages
#: it tells apart would guard nothing.
GERMAN_MARKERS = frozenset({
    "und", "ist", "dir", "mir", "eine", "einem", "ein", "die", "der", "das", "nicht",  # language-gate: ignore
    "kann", "kannst", "gerne", "kurz", "wenn", "dass", "haben", "wie", "auch", "aber",  # language-gate: ignore
    "oder", "zwei", "sätzen", "was", "ich", "du", "werden", "man", "es", "auf", "vom",  # language-gate: ignore
    "von", "zur", "im", "diese", "speichert", "über", "dein", "deine", "für", "mit",     # language-gate: ignore
})
ENGLISH_MARKERS = frozenset({
    "the", "and", "is", "a", "an", "of", "to", "i", "you", "your", "for", "with", "that", "this",
    "it", "can", "in", "sentences", "what", "here", "sure", "happy", "stores", "lookup", "when",
    "are", "we", "our", "has", "have", "will", "would", "about", "as", "explain",
})
UMLAUTS = set("äöüÄÖÜß")
LIVE = os.environ.get("EPHE_ANSWER_LANGUAGE_LIVE") == "1"


def language_scores(text: str) -> tuple[int, int]:
    """(german, english) counts over the distinct words of a reply, plus its umlauts."""
    words = {w.strip(".,:;!?()\"'”“") for w in text.lower().split()}
    german = len(words & GERMAN_MARKERS) + sum(1 for ch in text if ch in UMLAUTS)
    return german, len(words & ENGLISH_MARKERS)


def answered_in(text: str, language: str) -> bool:
    """True when the reply is in `language` by a two-marker margin; a mix earns neither label."""
    german, english = language_scores(text)
    if language == "de":
        return german >= english + 2
    if language == "en":
        return english >= german + 2
    raise ValueError(f"unknown language code {language!r}")


@pytest.fixture()
def persona_home(tmp_path, monkeypatch):
    """A redirected persona dir: `assemble_system_prompt` materialises the default persona on first
    use, and a test suite has no business writing into the owner's `~/.ephe`."""
    home = tmp_path / "ephe-home"
    home.mkdir()
    monkeypatch.setenv("EPHE_PERSONA_DIR", str(home))
    return home


class TestTheInstructionReachesTheModel:
    def test_the_default_persona_carries_the_rule_verbatim(self, persona_home):
        write_persona(DEFAULT_PERSONA)
        text = assemble_system_prompt(model="qwen3.8-flash-next")
        assert RULE_FRAGMENT in text, "the language rule left the composed system text"
        assert "Non-negotiable" in text

    def test_the_rule_survives_the_context_blocks_the_product_injects(self, persona_home):
        """The context blocks are what make the rule a small share of a long message: measured on the
        owner's machine the same composition is 3867 chars bare and 17945 chars with the workspace
        rules, profile, memory, corrections and feedback in it, and the rule keeps its byte offset --
        39 % through the first, 8 % through the second, with 46 blocks behind it."""
        write_persona(DEFAULT_PERSONA)
        messages = [
            {"role": "user", "content": SHORT_GERMAN_TURN},
            {"role": "assistant", "content": GOOD_ANSWER},
            {"role": "tool", "content": "155\nexit status 0"},
            {"role": "user", "content": SHORT_GERMAN_TURN},
        ]
        _assemble_system_prompt_into(messages, "qwen3.8-flash-next", None, None)
        text = messages[0]["content"]
        assert RULE_FRAGMENT in text, (
            f"a context block replaced the persona, so the language rule no longer reaches the "
            f"model ({len(text)} chars composed)"
        )

    def test_the_one_persona_edit_that_removes_the_guarantee_is_visible(self, persona_home):
        """Nothing else in the chain re-states the rule, so a user editing it out is the change that
        silently ends the guarantee -- named here rather than met as an English answer a week later."""
        write_persona("## Personality\n- Warm, direct, concise.\n")
        assert RULE_FRAGMENT not in assemble_system_prompt(model="qwen3.8-flash-next")

    @pytest.mark.parametrize(
        ("reply", "language"),
        [
            (GOOD_ANSWER, "de"),
            ("A hashmap stores key-value pairs and looks them up by hashing the key.", "en"),
            ("Sure — here is the short version: keys hash to buckets, lookups are near constant.", "en"),
        ],
    )
    def test_the_classifier_fires_on_the_shapes_it_judges(self, reply: str, language: str):
        """Without this the live leg could pass by matching nothing at all."""
        assert answered_in(reply, language), language_scores(reply)

    def test_the_reply_that_opened_this_item_is_judged_english(self):
        """Pinned against the observed defect rather than only against plants written here: the stored
        answer of session `be44cacd…`, turn `1c21e9ae5cd2`, to the German request above."""
        reply = (
            "Got it — that last command just returned a count of 155. "
            "What would you like me to do with that?"
        )
        assert answered_in(reply, "en"), language_scores(reply)
        assert not answered_in(reply, "de"), language_scores(reply)

    def test_a_reply_that_is_half_and_half_wears_neither_label(self):
        """A German turn answered half in each language must not read as German, and the margin is
        what keeps it honest: 3-to-3 here, so neither side clears it."""
        mixed = f"{GOOD_ANSWER.split('.')[0]}. It stores them by hashing the key and reads them back."
        assert not answered_in(mixed, "de"), language_scores(mixed)


class TestTheRevisionKeepsTheUsersLanguage:
    """The reflect/revise loop writes the newest message of the thread, in English, as `user`.

    `core/react.py:306-320` appends the assistant answer and then a critique of it under the role
    `user`. That message is the last thing the model reads before it revises, so the revision answers
    our sentence rather than the request, and the stored turn says so twice: session `f138394e…`, turn
    `62c693670866` first answered in German that it could see no question and no task from the user,
    then in English that the input looked like a tool-run trace -- while `~/.ephe/sessions/` holds a
    German request two lines above it asking for a landing page.
    """

    @pytest.mark.asyncio
    async def test_the_critique_is_marked_as_ours_and_names_the_request_language(self, monkeypatch):
        from core.react import ReflexionResult, react_loop

        seen: list[list[dict]] = []

        async def fake_chat(**kwargs):
            seen.append([dict(m) for m in (kwargs.get("history") or [])])
            return GOOD_ANSWER

        async def fake_reflect(**_kwargs):
            return ReflexionResult(needs_revision=True, reason="It omits the offline install path.")

        monkeypatch.setattr("core.react.chat_with_tools", fake_chat)
        monkeypatch.setattr("core.react.reflect", fake_reflect)
        await react_loop(question=QUESTION, model="qwen3.8-flash-next")

        injection = seen[1][-1]
        assert injection["role"] == "user", seen[1]
        assert "not a message from the user" in injection["content"], injection
        assert "language that request is written in" in injection["content"], (
            "the revision instruction let the answer follow its own language instead of the user's: "
            + injection["content"]
        )

    @pytest.mark.asyncio
    async def test_the_user_request_stays_behind_the_critique(self, monkeypatch):
        """The appended message goes after the request, never in place of it: user, assistant, user."""
        from core.react import ReflexionResult, react_loop

        seen: list[list[dict]] = []

        async def fake_chat(**kwargs):
            seen.append([dict(m) for m in (kwargs.get("history") or [])])
            return GOOD_ANSWER

        async def fake_reflect(**_kwargs):
            return ReflexionResult(needs_revision=True, reason="Too brief to cover the offline install.")

        monkeypatch.setattr("core.react.chat_with_tools", fake_chat)
        monkeypatch.setattr("core.react.reflect", fake_reflect)
        await react_loop(question=QUESTION, model="qwen3.8-flash-next")

        assert [m["role"] for m in seen[1][-3:]] == ["user", "assistant", "user"], seen[1]
        assert seen[1][-3]["content"] == QUESTION


def _live_engine():
    """The persisted engine, or a skip: no endpoint and no token ever appear in this file."""
    from core.engine_config import load_engine_config
    from core.model_provider import build_provider_client, get_active_provider

    choice = load_engine_config()
    if choice is None:
        pytest.skip("no persisted engine (~/.ephe/engine.json): run `ephe configure` first")
    choice.apply_env()
    active = get_active_provider()
    if not active.model:
        pytest.skip(f"engine.json names no model for provider {active.provider}")
    return active, build_provider_client(active)


async def _answer(system_text: str, user_text: str) -> tuple[str, str]:
    active, client = _live_engine()
    response = await client.chat(
        model=active.model,
        messages=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
    )
    message = getattr(response, "message", None)
    return str(getattr(message, "content", "") or ""), f"{active.provider}/{active.model}"


@pytest.mark.skipif(
    not LIVE,
    reason="set EPHE_ANSWER_LANGUAGE_LIVE=1 to spend real turns on the persisted engine",
)
class TestOneRealTurn:
    @pytest.mark.asyncio
    async def test_a_german_turn_comes_back_in_german(self, persona_home):
        write_persona(DEFAULT_PERSONA)
        reply, engine = await _answer(
            assemble_system_prompt(model="qwen3.8-flash-next"), SHORT_GERMAN_TURN
        )
        german, english = language_scores(reply)
        assert reply.strip(), (
            f"no answer text came back on {engine}: a reasoning pass that spends the whole budget on "
            f"thinking is not a reply, and this leg must not count it as one"
        )
        assert answered_in(reply, "de"), (
            f"a German turn came back in another language on {engine} "
            f"(german markers {german}, english markers {english}): {reply[:240]!r}"
        )

    @pytest.mark.asyncio
    async def test_an_english_turn_comes_back_in_english(self, persona_home):
        """Judged the other way round: a rule that only ever produced German would pass the leg above."""
        write_persona(DEFAULT_PERSONA)
        reply, engine = await _answer(
            assemble_system_prompt(model="qwen3.8-flash-next"), ENGLISH_TURN
        )
        german, english = language_scores(reply)
        assert answered_in(reply, "en"), (
            f"an English turn came back in another language on {engine} "
            f"(german markers {german}, english markers {english}): {reply[:240]!r}"
        )
