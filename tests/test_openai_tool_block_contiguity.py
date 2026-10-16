"""The 400 a two-call tool round produced, pinned as a shape.

Root cause (proven live 2026-10-13, bus note w10-1): the shared tool loop
(``core/chat_tools.py``, the two branches around lines 487 and 671) appends a
``system`` "Tool evidence summary" after EVERY tool result. A round of two or more
calls therefore reached the engine as

    assistant(tool_calls=[c0, c1]), tool(c0), user(evidence c0), tool(c1), user(evidence c1)

and an OpenAI-compatible engine refused the request with

    "An assistant message with 'tool_calls' must be followed by tool messages responding
     to each 'tool_call_id'. (insufficient tool messages following tool_calls message)"

The fix is in ``core/model_provider.py::_convert_messages``: a message that would
interrupt an assistant ``tool_calls`` block which is not yet fully answered is held back
and re-emitted once the last tool result has closed the block, so the tool messages stay
contiguous and keep the ids the engine delivered.

What these tests pin is the CONTRACT, not one recorded history:

  * every converted request satisfies ``_tool_block_violations`` — the invariant the
    engine enforces — for any number of calls and any spacing of the evidence messages;
  * the ids stay in the order the results arrived (the block is reordered in place);
  * nothing is dropped: a fix that deleted the evidence messages would trade the 400 for a
    silently different conversation, and that is a failure here too.

A future change that lets a non-tool message back in between an assistant ``tool_calls``
block and its tool answers fails these tests, whatever history it is fed.
"""
from __future__ import annotations

import json

import core.model_provider as mp


def _client() -> mp.OpenAICompatibleAsyncClient:
    return mp.OpenAICompatibleAsyncClient(base_url="http://engine.test/v1", api_key="sk-test")


def _tool_block_violations(converted: list[dict]) -> list[str]:
    """Every way a converted request can break the engine's tool_calls contract.

    The engine's rule: an assistant message carrying ``tool_calls`` must be followed
    immediately by one ``role="tool"`` message per call, carrying that call's id, in the
    order the calls were listed. Anything else in between is the 400 this file exists for.
    """
    violations: list[str] = []
    for i, msg in enumerate(converted):
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            expected = [call["id"] for call in msg["tool_calls"]]
            following = converted[i + 1 : i + 1 + len(expected)]
            if len(following) != len(expected):
                violations.append(
                    f"block at {i} lists {len(expected)} calls but the request ends after "
                    f"{len(following)} message(s)"
                )
                continue
            answered = [m.get("tool_call_id") for m in following if m.get("role") == "tool"]
            if answered != expected:
                shape = [m.get("role") for m in following]
                violations.append(
                    f"block at {i} lists {expected} but the next {len(expected)} message(s) "
                    f"are {shape} answering {answered}"
                )
        if msg.get("role") == "tool" and not msg.get("tool_call_id"):
            violations.append(f"tool message at {i} carries no tool_call_id")
    return violations


def _round(
    n: int,
    *,
    evidence_role: str = "system",
    evidence_per_result: int = 1,
    extra_user_between: bool = False,
    rounds: int = 1,
) -> list:
    """The exact shape ``core/chat_tools.py`` builds, parameterised.

    Per tool result it appends ``{"role": "tool"}`` and then ``evidence_per_result``
    evidence messages (role ``system`` in the product; ``evidence_role`` here so the
    variant survives a future change of the emitting role). Every one of ``rounds``
    blocks starts with an assistant ``ProviderMessage`` carrying ``n`` calls, with ids
    ``call_<round>_<index>``.
    """
    messages: list = [{"role": "system", "content": "sys"}, {"role": "user", "content": "do it"}]
    for r in range(rounds):
        calls = [
            mp.ProviderToolCall(
                function=mp.ProviderFunctionCall(name=f"tool_{r}_{j}", arguments={"j": j}),
                id=f"call_{r}_{j}",
            )
            for j in range(n)
        ]
        messages.append(mp.ProviderMessage(content="", tool_calls=calls))
        for j in range(n):
            messages.append({"role": "tool", "content": f"result {r}-{j}"})
            for k in range(evidence_per_result):
                messages.append(
                    {"role": evidence_role, "content": f"Tool evidence summary: tool_{r}_{j} #{k}"}
                )
            if extra_user_between:
                messages.append({"role": "user", "content": f"note {r}-{j}"})
        messages.append(mp.ProviderMessage(content=f"answer of round {r}"))
    return messages


def _sent_multiset(converted: list[dict]) -> dict[tuple[str, str], int]:
    """What actually goes on the wire: (role, content) counts."""
    out: dict[tuple[str, str], int] = {}
    for msg in converted:
        key = (msg["role"], msg["content"] if isinstance(msg["content"], str) else str(msg["content"]))
        out[key] = out.get(key, 0) + 1
    return out


def _expected_multiset(history: list) -> dict[tuple[str, str], int]:
    """The same counts for the input, after the one remap the converter is allowed.

    ``_convert_messages`` maps a ``system`` message to ``user`` when it is not the first
    message (the engine only accepts ``system`` at the start) and an assistant
    ``ProviderMessage`` to ``role="assistant"``. Nothing else may change, and nothing may
    go missing.
    """
    out: dict[tuple[str, str], int] = {}
    for idx, msg in enumerate(history):
        if isinstance(msg, mp.ProviderMessage):
            key = ("assistant", str(msg.content or ""))
        else:
            role = msg.get("role", "user")
            if role == "system" and idx > 0:
                role = "user"
            key = (role, str(msg.get("content", "")))
        out[key] = out.get(key, 0) + 1
    return out


def _block_index(converted: list[dict]) -> int:
    return next(i for i, m in enumerate(converted) if m.get("role") == "assistant" and m.get("tool_calls"))


# The invariant itself: the shape, kept for any history.


def test_two_call_round_with_interleaved_evidence_is_contiguous():
    """The exact regression: two calls, one evidence message after each result."""
    converted = _client()._convert_messages(_round(2))

    assert _tool_block_violations(converted) == []
    block = converted[_block_index(converted)]
    assert [c["id"] for c in block["tool_calls"]] == ["call_0_0", "call_0_1"]
    # Both tool messages answer the block before any evidence message is emitted.
    assert [m["role"] for m in converted[_block_index(converted) + 1 : _block_index(converted) + 3]] == [
        "tool",
        "tool",
    ]
    assert [m["tool_call_id"] for m in converted if m["role"] == "tool"] == ["call_0_0", "call_0_1"]


def test_more_calls_than_two_are_held_back_too():
    """A round is not special-cased at two; the property holds for any call count."""
    for n in (1, 2, 3, 5):
        converted = _client()._convert_messages(_round(n))
        assert _tool_block_violations(converted) == [], f"n={n} broke the block"
        assert [m["tool_call_id"] for m in converted if m["role"] == "tool"] == [
            f"call_0_{j}" for j in range(n)
        ]


def test_wider_spacing_of_the_interrupting_messages_still_cannot_park_in_the_block():
    """The product emits one evidence message per result; more of them must not reopen the hole."""
    for spacing in (1, 2, 3):
        converted = _client()._convert_messages(
            _round(3, evidence_per_result=spacing, extra_user_between=True)
        )
        assert _tool_block_violations(converted) == [], f"spacing={spacing} broke the block"


def test_the_evidence_role_does_not_change_the_outcome():
    """The product emits the evidence as ``system`` (remapped to ``user``); pin both."""
    for role in ("system", "user"):
        converted = _client()._convert_messages(_round(2, evidence_role=role))
        assert _tool_block_violations(converted) == [], f"role={role} broke the block"


def test_two_consecutive_rounds_are_each_contiguous():
    """A second tool round in the same turn must be closed the same way as the first."""
    converted = _client()._convert_messages(_round(2, rounds=2))
    assert _tool_block_violations(converted) == []
    assert [m["tool_call_id"] for m in converted if m["role"] == "tool"] == [
        "call_0_0",
        "call_0_1",
        "call_1_0",
        "call_1_1",
    ]
    assert converted[-1] == {"role": "assistant", "content": "answer of round 1"}


# The fix must reorder and keep every message.


def test_nothing_is_dropped_and_the_evidence_survives_after_the_block():
    """Holding the messages back may not lose them: everything in is still sent out."""
    history = _round(3)
    converted = _client()._convert_messages(history)

    assert _sent_multiset(converted) == _expected_multiset(history)

    # And the evidence arrives after the block, in the order it was produced.
    block = _block_index(converted)
    evidence = [
        m["content"]
        for m in converted
        if isinstance(m.get("content"), str) and m["content"].startswith("Tool evidence summary:")
    ]
    assert evidence == [f"Tool evidence summary: tool_0_{j} #0" for j in range(3)]
    assert converted[block + 4]["content"] == evidence[0]
    assert converted[-1] == {"role": "assistant", "content": "answer of round 0"}


# The failure mode, reproduced in-file so the guard cannot pass by accident.


def _unfixed_convert_messages(messages: list[dict]) -> list[dict]:
    """``_convert_messages`` as it stood before the fix: no deferral, evidence inline.

    Kept as the counter-example these tests are written against. If the live converter
    ever produces this output again, the tests above fail with the engine's own 400.
    """
    converted: list[dict] = []
    pending_tool_call_ids: list[str] = []
    for msg in messages:
        if isinstance(msg, mp.ProviderMessage):
            tool_calls_out = []
            for i, tc in enumerate(msg.tool_calls or []):
                tool_call_id = tc.id or f"call_{i}"
                pending_tool_call_ids.append(tool_call_id)
                tool_calls_out.append(
                    {
                        "id": tool_call_id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": json.dumps(tc.function.arguments or {}, ensure_ascii=False),
                        },
                    }
                )
            out: dict = {"role": "assistant", "content": msg.content or ""}
            if tool_calls_out:
                out["tool_calls"] = tool_calls_out
            converted.append(out)
            continue
        role = getattr(msg, "role", None) or msg.get("role", "user")
        content = getattr(msg, "content", None) or msg.get("content", "")
        if role == "tool" and isinstance(msg, dict):
            tool_call_id = (
                pending_tool_call_ids.pop(0) if pending_tool_call_ids else f"call_{len(converted)}"
            )
            converted.append({"role": "tool", "tool_call_id": tool_call_id, "content": str(content)})
            continue
        if role == "system" and converted:
            role = "user"
        converted.append({"role": role, "content": str(content)})
    return converted


def test_the_guard_actually_catches_the_interruption():
    """Sanity for the guard itself: the pre-fix converter must trip it on the same input.

    Without this, an invariant too weak to notice the bug would make every test above pass
    vacuously — and this is also the check that the live converter is the fixed one.
    """
    history = _round(2)
    broken = _tool_block_violations(_unfixed_convert_messages(history))
    assert broken, "the invariant must flag the pre-fix output"
    assert "answering ['call_0_0']" in broken[0]

    unfixed = _unfixed_convert_messages(history)
    idx = next(i for i, m in enumerate(unfixed) if m.get("tool_calls"))
    assert [m["role"] for m in unfixed[idx + 1 : idx + 5]] == ["tool", "user", "tool", "user"]

    # And the live converter, on that same history, does not.
    fixed = _client()._convert_messages(history)
    fixed_idx = _block_index(fixed)
    assert [m["role"] for m in fixed[fixed_idx + 1 : fixed_idx + 5]] == [
        "tool",
        "tool",
        "user",
        "user",
    ]
    assert _tool_block_violations(fixed) == []
