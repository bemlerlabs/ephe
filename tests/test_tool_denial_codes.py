"""The chat gate denies once: an English sentence for the engine, a code for the card.

Driven on 2026-10-11: `denial_message` returned a single string that both sinks consumed —
the tool message the model is conditioned on and the tool card the owner reads — and it was
German prose with no code, so the card could only repeat that prose and the engine was
instructed in a language no developer artifact of this repo uses. The split pinned here:
`[TOOL-DENIED]` byte-intact at the head because `core.quality` classifies on it, the
sentence in English, and `Denied.code` travelling beside it for a surface that localises.
"""
from __future__ import annotations

import asyncio
import re

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.chat import chat_with_tools
from core.quality import BLOCKED_RESULT_PREFIXES, result_decision
from core.tools.chat_gate import DENIAL_PREFIX, DENIAL_REASONS, confirm_for_chat, denial_message

#: what the engine is instructed with, per gate outcome. A wording change here is a change
#: to model input, so it is decided in the open instead of inside a template.
ENGINE_SENTENCES = {
    "no_approval_channel": (
        "[TOOL-DENIED] write_file was not executed: no approval channel is active "
        "(nobody is asking the user). Ask, or choose a read-only path."
    ),
    "not_approved_by_user": (
        "[TOOL-DENIED] write_file was not executed: the user did not approve the run. "
        "Ask, or choose a read-only path."
    ),
    "approval_channel_failed": (
        "[TOOL-DENIED] write_file was not executed: the approval channel failed "
        "(RuntimeError). Ask, or choose a read-only path."
    ),
    "not_approved": (
        "[TOOL-DENIED] write_file was not executed. Ask, or choose a read-only path."
    ),
    "mode_read_only": (
        "[TOOL-DENIED] write_file was not executed: this mode is read-only (Plan) and that "
        "tool writes — leave Plan mode to run it. Ask, or choose a read-only path."
    ),
    "mode_no_tools": (
        "[TOOL-DENIED] write_file was not executed: this mode (Ask) runs without tools. "
        "Ask, or choose a read-only path."
    ),
    "secret_path_denied": (
        "[TOOL-DENIED] write_file was not executed: the path is inside a protected root "
        "(~/.ssh/id_rsa). Ask, or choose a read-only path."
    ),
}

PARAMS = {
    "no_approval_channel": {},
    "not_approved_by_user": {},
    "approval_channel_failed": {"error": "RuntimeError"},
    "not_approved": {},
    "mode_read_only": {},
    "mode_no_tools": {},
    "secret_path_denied": {"path": "~/.ssh/id_rsa"},
}


def test_every_outcome_heads_with_the_marker_the_audit_reads():
    for code, expected in ENGINE_SENTENCES.items():
        denial = denial_message("write_file", code, **PARAMS[code])
        assert denial.startswith(f"{DENIAL_PREFIX} "), code
        assert str(denial) == expected, code


def test_a_denied_run_is_still_classified_as_blocked():
    for code in ENGINE_SENTENCES:
        denial = denial_message("write_file", code, **PARAMS[code])
        assert result_decision(denial) == "blocked", code


def test_a_code_is_a_stable_identifier_and_never_a_sentence():
    assert set(DENIAL_REASONS) == set(ENGINE_SENTENCES)
    for code in DENIAL_REASONS:
        assert re.fullmatch(r"[a-z][a-z0-9_]*", code), code


def test_the_producer_and_the_detector_read_one_marker():
    """`quality.py` matches a literal and the gate formats from a constant; nothing else
    ties the two, which is how the German wording broke classification once."""
    assert DENIAL_PREFIX in BLOCKED_RESULT_PREFIXES
    assert DENIAL_PREFIX == "[TOOL-DENIED]"


def test_a_broken_dialog_names_the_exception_that_broke_it():
    """The gate knew the failure class and dropped it: `params` was built, never returned."""

    async def _boom(name: str, args: dict) -> bool:
        raise RuntimeError("dialog gone")

    approved, denial = asyncio.run(confirm_for_chat("write_file", {}, on_confirm=_boom))
    assert approved is False
    assert denial.code == "approval_channel_failed"
    assert denial.params == {"error": "RuntimeError"}
    assert "RuntimeError" in denial
    assert "{error}" not in denial


def test_a_slot_that_never_got_its_value_fails_at_the_build():
    with pytest.raises(KeyError):
        denial_message("write_file", "approval_channel_failed")


def test_the_denial_wears_the_two_spellings_the_stream_frame_reads():
    """`server/routes/chat.py` builds `reason_code` from `getattr(result, "code")` and
    `reason_params` from `getattr(result, "params")`; nothing else ties a rename to the
    frame that would silently stop carrying the code."""
    denial = denial_message("write_file", "approval_channel_failed", error="RuntimeError")
    assert (getattr(denial, "code", "") or "") == "approval_channel_failed"
    assert dict(getattr(denial, "params", {}) or {}) == {"error": "RuntimeError"}


def _ollama_response(content: str = "", tool_calls: list | None = None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    out = MagicMock()
    out.message = msg
    return out


def _tool_call(name: str, arguments: dict):
    func = MagicMock()
    func.name = name
    func.arguments = arguments
    call = MagicMock()
    call.function = func
    return call


def _model_side_tool_messages(client) -> list[dict]:
    """The `role: tool` entries the second provider call conditions the model on."""
    for entry in client.chat.call_args_list[1:]:
        msgs = entry.kwargs.get("messages") or []
        hits = [m for m in msgs if isinstance(m, dict) and m.get("role") == "tool"]
        if hits:
            return hits
    return []


@pytest.mark.asyncio
async def test_one_denial_feeds_the_model_and_the_card_carries_its_code():
    """The dual sink in one run: without a confirm callback the gate denies, and the string
    in the model's tool message is the string the done frame hands to the surface."""
    card = []
    first = _ollama_response(
        tool_calls=[_tool_call("write_file", {"path": "x.txt", "content": "hi"})]
    )
    second = _ollama_response(content="Understood.")

    with patch("core.chat.ollama.AsyncClient") as MockClient:
        client = AsyncMock()
        client.chat = AsyncMock(side_effect=[first, second])
        MockClient.return_value = client
        executor = AsyncMock(return_value="written")
        with patch.dict("core.tools.registry.TOOL_MAP", {"write_file": executor}, clear=False):
            answer = await chat_with_tools(
                model="phi4-mini",
                history=[{"role": "user", "content": "Write x.txt"}],
                on_chunk=lambda t: None,
                on_tool_done=lambda name, result, call_id: card.append(result),
            )

    executor.assert_not_awaited()
    assert answer == "Understood."
    expected = ENGINE_SENTENCES["no_approval_channel"]
    assert card == [expected]
    assert getattr(card[0], "code", None) == "no_approval_channel"
    tool_msgs = _model_side_tool_messages(client)
    assert tool_msgs and tool_msgs[0]["content"] == expected
