"""The engine's tool-block contract survives every history this repo builds.

Reported from a product run (not from a test): an open-ended multi-step task that
had run 25-60 tool steps died four times with the provider's HTTP 400

    Messages with role "tool" must be a response to a preceding message with "tool_calls"

A ``role: "tool"`` message is only legal when the assistant message owning it —
the one whose ``tool_calls`` array names that exact ``tool_call_id`` — stands in
front of it, and every ``tool_calls`` entry has to be answered before the next
other-role message. The history assemblers (the tool loop, the window trim, the
compactor, the request builder) each have to keep an assistant ``tool_calls``
block and the tool messages answering it together; this file asserts that on the
wire messages the provider actually receives, with no engine and no network.

The histories here are built through the real code path — ``_run_tool_loop`` with
a scripted client and a stubbed executor — and converted with the real
``OpenAICompatibleAsyncClient._convert_messages``, so a shape the tests never
imagined still shows up if the loop can build it. The invariant checker has its
own sensitivity test at the bottom, so a passing run cannot be a vacuous one.
"""
from __future__ import annotations

from core.chat_context import _fit_messages_to_window
from core.chat_tools import _run_tool_loop
from core.conversation_compactor import compact_history

ROUNDS = 25


def _mp():
    """``core.model_provider``, resolved per call.

    Other tests in the suite reload that module (tests/test_model_provider.py,
    tests/test_openai_provider_tools.py, tests/test_generation_reaches_request_i25.py).
    A class object bound at import time then no longer matches the one
    ``_convert_messages`` tests with ``isinstance`` — every provider message built
    here would be read as a plain dict and the stub would raise instead of
    recording a frame. Resolving at call time keeps the objects and the check on
    one class.
    """
    from core import model_provider

    return model_provider


class _LocalProvider:
    """The loop's provider marker; the trim under test is provider-independent."""

    provider = "local_ollama"


def _wire_violations(wire: list[dict]) -> list[str]:
    """Every way the request body can break the engine's tool-block contract.

    Two directions, because the engine rejects both: a tool message without the
    assistant block that owns its id, and an assistant block not fully answered
    by the tool messages following it. A repeated ``tool_call_id`` is named too —
    the engine keys the pairing on that id.
    """
    violations: list[str] = []
    seen: list[str | None] = []
    for i, msg in enumerate(wire):
        role = msg.get("role")
        if role == "assistant" and msg.get("tool_calls"):
            expected = [call["id"] for call in msg["tool_calls"]]
            following = wire[i + 1 : i + 1 + len(expected)]
            answered = [m.get("tool_call_id") for m in following if m.get("role") == "tool"]
            if answered != expected:
                violations.append(f"assistant at {i} declares {expected}, answered by {answered}")
        elif role == "tool":
            owner = None
            for prev in reversed(wire[:i]):
                if prev.get("role") == "assistant" and prev.get("tool_calls"):
                    owner = prev
                    break
                if prev.get("role") == "tool":
                    continue
                break
            cid = msg.get("tool_call_id")
            if not cid:
                violations.append(f"tool at {i} carries no tool_call_id")
            elif owner is None:
                violations.append(f"tool at {i} ({cid}) has no preceding assistant tool_calls")
            elif cid not in [call["id"] for call in owner["tool_calls"]]:
                violations.append(f"tool at {i} ({cid}) is not named by the preceding block")
            if cid in seen:
                violations.append(f"tool at {i} repeats the tool_call_id {cid!r}")
            seen.append(cid)
    return violations


def _converted(messages: list) -> list[dict]:
    """The wire body for ``messages``, as the openai_compatible client builds it."""
    client = _mp().OpenAICompatibleAsyncClient(base_url="http://engine.invalid/v1")
    return client._convert_messages(list(messages))


def _assert_contract(messages: list, where: str) -> None:
    wire = _converted(messages)
    violations = _wire_violations(wire)
    assert not violations, f"{where}: {violations}"


class _RecordingClient:
    """Serves scripted responses and records each request as the engine sees it.

    The real client converts the history with ``_convert_messages`` immediately
    before the wire, so the frame recorded here is the body the provider refuses.
    """

    def __init__(self, responses: list) -> None:
        self._responses = list(responses)
        self.frames: list[list[dict]] = []
        self._converter = _mp().OpenAICompatibleAsyncClient(base_url="http://engine.invalid/v1")

    async def chat(self, *, model: str, messages: list, **_kwargs):
        self.frames.append(self._converter._convert_messages(list(messages)))
        return self._responses.pop(0)


def _engine_call(index: int):
    """One assistant round carrying the call id the engine handed out."""
    return _mp().ProviderChatResponse(
        _mp().ProviderMessage(
            content="",
            tool_calls=[
                _mp().ProviderToolCall(
                    function=_mp().ProviderFunctionCall(
                        name="read_file", arguments={"path": f"src/module_{index}.py"}
                    ),
                    id=f"call-engine-{index}",
                )
            ],
        )
    )


def _noop(*_args, **_kwargs) -> None:
    return None


async def _drive_loop(monkeypatch, *, rounds: int = ROUNDS, window: int | None = None):
    """Run the real tool loop for ``rounds`` rounds; return (messages, client).

    The executor is stubbed (no real tool runs, no filesystem), the engine is a
    scripted client (no network), and ``window`` — when given — is what the loop
    sees as the active context window, which is what makes the trim engage.
    """

    async def executor(name: str, args: dict, policy=None) -> str:
        return f"[{name} {args.get('path')}] " + "content line for the transcript\n" * 40

    monkeypatch.setattr("core.chat.execute_tool", executor)
    if window is not None:
        monkeypatch.setattr("core.chat_tools._active_context_window", lambda _model: window)

    responses = [_engine_call(i) for i in range(rounds)]
    responses.append(_mp().ProviderChatResponse(_mp().ProviderMessage(content="done")))
    client = _RecordingClient(responses[1:])
    messages: list = [{"role": "system", "content": "sys"}, {"role": "user", "content": "task"}]

    await _run_tool_loop(
        client=client,
        provider=_LocalProvider(),
        model="ephe-test-model",
        messages=messages,
        tools=[],
        response=responses[0],
        detection_streamed=False,
        on_chunk=_noop,
        on_thinking=None,
        on_tool_start=_noop,
        on_tool_done=_noop,
        on_phase=_noop,
        on_shell_confirm=None,
        on_tool_confirm=None,
        approval_policy=None,
        budget_cap=rounds + 5,
        turn_id="t",
    )
    return messages, client


def _appended(rounds: int) -> int:
    """Messages a round appends: the assistant block, the result, the evidence."""
    return 2 + 3 * rounds


async def test_the_contract_holds_on_every_request_a_long_loop_sends(monkeypatch):
    """The reproduction: 25 rounds with windows small enough to force the trim.

    The failed product runs sat at 25-60 tool steps, which is exactly the range
    where the prompt no longer fits and the trim starts cutting the front. The
    window decides where the trim stops, so the sweep covers the stop points.
    """
    trimmed_any = False
    for window in range(2100, 4600, 250):
        messages, client = await _drive_loop(monkeypatch, window=window)
        if len(messages) < _appended(ROUNDS):
            trimmed_any = True
        assert client.frames, "the loop sent no request at all"
        for n, frame in enumerate(client.frames):
            violations = _wire_violations(frame)
            assert not violations, (
                f"window {window}, request {n + 1} of {len(client.frames)}: {violations}"
            )

    assert trimmed_any, "no window trimmed anything — the reproduction is vacuous"


async def test_no_window_size_can_orphan_a_tool_result(monkeypatch):
    """Sweep the window: wherever the trim stops, the front stays inside a block.

    The trim deletes one unit at a time from the front, so the stop point is set
    by the window and the history length. A unit of one message lands between an
    assistant block and its answers for a fraction of windows — which is what
    turned four attempts of the same task into four different failures.
    """
    messages, _client = await _drive_loop(monkeypatch)
    trimmed = 0
    for window in range(2000, 9000, 100):
        probe = list(messages)
        if _fit_messages_to_window(probe, window):
            trimmed += 1
        _assert_contract(probe, f"window {window}")

    assert trimmed, "no window in the sweep trimmed anything — the sweep is vacuous"


async def test_a_mid_loop_interrupt_hands_over_a_contract_clean_history(monkeypatch):
    """The history a stop hands on (steer/budget finalize) is still sendable.

    The finalize paths send the loop's messages with one more message appended,
    so the last block of the loop has to survive the trim in the same request.
    """
    messages, _client = await _drive_loop(monkeypatch)
    for hand_off in (
        {"role": "user", "content": "stop here and summarise what you have"},
        {"role": "system", "content": "[Ephe] Tool budget exhausted after 30 rounds."},
    ):
        probe = [*messages, hand_off]
        _fit_messages_to_window(probe, 3000)
        _assert_contract(probe, f"hand-off {hand_off['role']}")


def _as_replayed(messages: list) -> list[dict]:
    """The same conversation in the shape a stored/served history carries.

    A resumed session or an OpenAI-protocol client replays dicts: an assistant
    message holding ``tool_calls`` in wire shape and tool messages naming the id
    they answer. The loop's own history holds ProviderMessage objects, so this is
    also the only way to drive the assemblers that receive a replayed history.
    """
    replayed: list[dict] = []
    for msg in messages:
        if isinstance(msg, _mp().ProviderMessage):
            replayed.append(
                {
                    "role": "assistant",
                    "content": msg.content,
                    "tool_calls": [
                        {
                            "id": call.id,
                            "type": "function",
                            "function": {
                                "name": call.function.name,
                                "arguments": call.function.arguments,
                            },
                        }
                        for call in (msg.tool_calls or [])
                    ],
                }
            )
            continue
        replayed.append(dict(msg))
    # The answers carry the id the engine assigned, as a stored transcript would.
    block_id: str | None = None
    for msg in replayed:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            block_id = msg["tool_calls"][0]["id"]
        elif msg.get("role") == "tool" and block_id:
            msg["tool_call_id"] = block_id
    return replayed


async def test_a_resumed_replay_does_not_orphan_a_stored_tool_message(monkeypatch):
    """The wire shape a resumed session replays has to keep its blocks.

    Dropping the block on the way to the wire orphans every answer of the
    conversation at once — the provider refuses the request, not the message.
    """
    messages, _client = await _drive_loop(monkeypatch)
    replayed = _as_replayed(messages)

    _fit_messages_to_window(replayed, 3000)
    _assert_contract(replayed, "resumed replay")


async def test_the_compactor_never_splits_a_tool_block(monkeypatch):
    """Compaction cuts the middle; the cut may not land inside a tool block.

    The kept tail starts where the cut ends, so a boundary between an assistant
    ``tool_calls`` message and the answers directly behind it leaves the answers
    at the head of the kept part with their owner summarised away.
    """
    messages, _client = await _drive_loop(monkeypatch)
    replayed = _as_replayed(messages)
    split_any = False
    for keep_recent in range(1, 25):
        compacted = compact_history(list(replayed), max_messages=6, keep_recent=keep_recent)
        if any(m.get("role") == "tool" for m in compacted[-keep_recent:]):
            split_any = True
        _fit_messages_to_window(compacted, 3000)
        _assert_contract(compacted, f"compact_history(keep_recent={keep_recent})")

    assert split_any, "no keep_recent put a tool message at the cut — the sweep is vacuous"


def test_the_contract_checker_rejects_a_broken_frame():
    """Sensitivity: the checker above must fail on the shapes the engine 400s on."""
    block = {
        "role": "assistant",
        "content": "",
        "tool_calls": [{"id": "call-engine-0", "type": "function", "function": {"name": "f"}}],
    }
    orphan = [{"role": "system", "content": "s"}, block, {"role": "tool", "tool_call_id": "call-0", "content": "x"}]
    assert _wire_violations(orphan)
    detached = [{"role": "system", "content": "s"}, {"role": "tool", "tool_call_id": "call-0", "content": "x"}]
    assert _wire_violations(detached)
    unanswered = [{"role": "system", "content": "s"}, block]
    assert _wire_violations(unanswered)
    healthy = [
        {"role": "system", "content": "s"},
        block,
        {"role": "tool", "tool_call_id": "call-engine-0", "content": "x"},
    ]
    assert _wire_violations(healthy) == []
