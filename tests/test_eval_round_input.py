"""The request has to be in the model input of every round (creation eval, class 4c).

Six of the 24 paid Creator turns answered "I don't see an actual request". A turn is a
sequence of model calls, and only the first one carries the user's words by construction:
every later round is the product's own message assembly, and a round whose messages no
longer hold the request grades a model that was never asked the question.

It proves two things:

* the harness can see it — `evals.creation_transcript.rounds_without_request` reads the
  captured model inputs of a turn and names the rounds that lost the request, which is
  what `evals.creation_offer_probe.describe` now reports for the request it probed with;
* the product loses it — `core.chat_context._fit_messages_to_window` trims the front of
  the message list after the system block, and the user's request is the first thing
  there, so a turn that outgrows its window drops the request before it drops a tool
  result. The strict xfail below states the behaviour the eval needs and is expected to
  go red the day the product keeps it.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REQUEST = "Build a sticky-note window I can pin to the top of the screen."


def _round(messages: list[dict]) -> dict:
    """One captured model call: the shape the probe keeps and the provider receives."""
    return {"model": "probe-model", "messages": messages}


def _turn(request_in_rounds: tuple[bool, ...]) -> list[dict]:
    """A turn of N rounds; the flag says whether that round still holds the request."""
    rounds: list[dict] = []
    for kept in request_in_rounds:
        messages = [{"role": "system", "content": "IDENTITY:\n- You are Ephe."}]
        if kept:
            messages.append({"role": "user", "content": REQUEST})
        messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "c1", "type": "function",
                            "function": {"name": "create_plugin_scaffold", "arguments": "{}"}}],
        })
        messages.append({"role": "tool", "tool_call_id": "c1", "content": "ok"})
        rounds.append(_round(messages))
    return rounds


def test_a_round_that_keeps_the_request_is_not_reported() -> None:
    """GIVEN every round of a turn carrying the user's words WHEN the turn is read
    THEN no round is named, so a green reading is a measurement and not a default."""
    from evals.creation_transcript import rounds_without_request

    assert rounds_without_request(_turn((True, True, True)), REQUEST) == []


def test_the_round_that_lost_the_request_is_named_with_what_it_carries() -> None:
    """GIVEN a turn whose second round dropped the request WHEN the turn is read
    THEN that round is named with the roles it does carry, so the reader sees what the
    engine was handed instead of the question."""
    from evals.creation_transcript import rounds_without_request

    lost = rounds_without_request(_turn((True, False, True)), REQUEST)
    assert [row["round"] for row in lost] == [1]
    assert "system" in lost[0]["roles"] and "user" not in lost[0]["roles"]
    assert lost[0]["messages"] == 3


def test_a_turn_that_never_reached_an_engine_has_no_round_to_judge() -> None:
    """Zero captured calls is not a lost request: there is no model input to read."""
    from evals.creation_transcript import rounds_without_request

    assert rounds_without_request([], REQUEST) == []


def test_the_offer_probe_reports_the_rounds_that_lost_the_request() -> None:
    """GIVEN the probe's own reading of a turn WHEN the request is asked about
    THEN the lost rounds arrive with it, so an offer reading cannot be printed for a
    turn the engine was never asked to run."""
    from evals.creation_offer_probe import describe

    reading = describe(_turn((True, False)), ["files"], prompt=REQUEST)
    assert reading["prompt_rounds_lost"] == [1]
    assert reading["prompt_rounds"] == 2

    kept = describe(_turn((True, True)), ["files"], prompt=REQUEST)
    assert kept["prompt_rounds_lost"] == []


def test_the_window_fit_takes_the_request_before_it_takes_a_tool_result() -> None:
    """GIVEN a turn whose messages outgrow the window WHEN they are fitted to it
    THEN the user's request leaves the input while the tool result stays: the request is
    the first unit after the system block, and `_front_unit_end` cuts it first. This is
    the mechanism behind the six transcripts that answered "I don't see an actual request".
    """
    from core.chat_context import _fit_messages_to_window, _front_unit_end
    from evals.creation_transcript import rounds_without_request

    messages = [
        {"role": "system", "content": "S" * 20_000},
        {"role": "user", "content": REQUEST},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "create_plugin_scaffold", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "x" * 40_000},
    ]
    assert _front_unit_end(messages) == 2, (
        "the unit after the system block is the user message alone; a change here "
        "would change which message the window fit takes first"
    )
    trimmed = _fit_messages_to_window(messages, 8_192)
    assert trimmed >= 1
    assert not any(m.get("role") == "user" for m in messages), (
        "the fit kept the user message; the defect this file pins is gone and the "
        "strict xfail below has to be removed with it"
    )
    assert any(m.get("role") == "tool" for m in messages), (
        "the tool result left as well, so the reading is not about what the fit prefers"
    )
    assert rounds_without_request([_round(messages)], REQUEST), (
        "the harness did not report the round the fit emptied of the request"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "core.chat_context._fit_messages_to_window trims from the system block forward, "
        "so the user's request is the first message a Creator turn outgrows its window "
        "with - the six transcripts that answered 'I don't see an actual request'. The "
        "product has to keep the request (or fail the turn) before this pin can go."
    ),
)
def test_the_request_survives_every_round_of_a_creator_turn(tmp_path, monkeypatch) -> None:
    """GIVEN a Creator turn whose messages outgrow the window WHEN the round is assembled
    THEN the model input still holds the user's request. Expected to fail today; the day
    it passes, the xfail is strict and goes red, which is when the pin comes out."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    from core.chat_context import _fit_messages_to_window
    from core.tools import session_ctx

    session_ctx.set_current_mode("creator")
    session_ctx.set_current_session("creation-round-input")
    messages = [
        {"role": "system", "content": "S" * 20_000},
        {"role": "user", "content": REQUEST},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function",
             "function": {"name": "create_plugin_scaffold", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "x" * 40_000},
    ]
    _fit_messages_to_window(messages, 8_192)
    assert any(
        m.get("role") == "user" and REQUEST in str(m.get("content")) for m in messages
    ), "the request left the model input"
