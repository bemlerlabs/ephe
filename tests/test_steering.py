"""N1 steering: a direction change reaches a turn that is already running.

Pins:
1. Where a steer can land — at a round boundary, after the finished round's tool
   results are recorded, so it can never sit between a side effect and its record.
2. What the model reads on its next step (a user message carrying the boundary and
   the direction), and what a stop steer ends the turn with.
3. What the transcript says: the round, the actor, the text — live as an SSE frame
   and persisted as a trajectory step.
4. That the innermost consumer drains, so a subagent running inside a tool call
   takes the steer meant for the work in front of the user.
5. That a steer nobody takes up is reported as unlanded instead of vanishing.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core import trajectory  # noqa: E402
from core.chat_tools import _run_tool_loop  # noqa: E402
from core.model_provider import (  # noqa: E402
    ProviderChatResponse,
    ProviderFunctionCall,
    ProviderMessage,
    ProviderToolCall,
)
from core.steering import (  # noqa: E402
    MAX_PENDING,
    STEER_TOKEN,
    SteeringChannel,
    bind_channel,
    register_turn,
    reset_registry_for_test,
    resolve_turn,
    take_up,
)
from core.subagent import Subagent  # noqa: E402


class _FakeProvider:
    provider = "local_ollama"


def _tool_call(name, arguments=None):
    return ProviderChatResponse(
        ProviderMessage(
            tool_calls=[
                ProviderToolCall(
                    function=ProviderFunctionCall(name=name, arguments=arguments or {"path": "x"})
                )
            ]
        )
    )


def _answer(text="done"):
    return ProviderChatResponse(ProviderMessage(content=text))


class _ScriptedClient:
    """A scripted engine. ``hook`` fires during a call, like a user typing."""

    def __init__(self, responses, hook=None):
        self._responses = list(responses)
        self.hook = hook
        self.calls: list[dict] = []

    async def chat(self, *, model, messages, stream=False, tools=None, **_):
        assert stream is False
        self.calls.append({"model": model, "messages": list(messages)})
        if self.hook is not None:
            self.hook(len(self.calls))
        return self._responses.pop(0)


def _channel(frames, *, turn_id="t1", session_id="s1"):
    channel = SteeringChannel(turn_id=turn_id, session_id=session_id, on_steer=frames.append)
    bind_channel(channel)
    return channel


async def _drive(messages, monkeypatch, responses, *, client=None, chunks=None, budget_cap=4):
    async def executor(name, args, policy=None):
        return f"result-of-{name}"

    monkeypatch.setattr("core.chat.execute_tool", executor)
    client = client or _ScriptedClient(responses[1:])
    outcome = await _run_tool_loop(
        client=client,
        provider=_FakeProvider(),
        model="gemma4:12b",
        messages=messages,
        tools=[],
        response=responses[0],
        detection_streamed=False,
        on_chunk=(chunks if chunks is not None else []).append,
        on_thinking=None,
        on_tool_start=None,
        on_tool_done=None,
        on_phase=None,
        on_shell_confirm=None,
        on_tool_confirm=None,
        approval_policy=None,
        budget_cap=budget_cap,
        turn_id="t1",
    )
    return messages, client, outcome


def _start_messages():
    return [{"role": "system", "content": "sys"}, {"role": "user", "content": "q"}]


def _steer_messages(messages):
    return [
        m
        for m in messages
        if isinstance(m, dict) and str(m.get("content", "")).startswith(STEER_TOKEN)
    ]


@pytest.fixture(autouse=True)
def _clean_registry():
    reset_registry_for_test()
    yield
    reset_registry_for_test()


def test_a_steer_needs_text_unless_it_is_a_stop():
    channel = SteeringChannel(turn_id="t1")
    assert channel.request("   ") is None
    assert channel.queued == 0
    # A stop carries its own direction: end this turn here.
    assert channel.request("", stop=True) is not None
    assert channel.queued == 1


def test_the_actor_is_recorded_as_a_token():
    channel = SteeringChannel(turn_id="t1")
    steer = channel.request("read the other file", actor="  Operator #2 ")
    assert steer is not None
    assert steer.actor == "operator2"


def test_a_full_queue_is_refused_rather_than_silently_dropped():
    channel = SteeringChannel(turn_id="t1")
    for i in range(MAX_PENDING):
        assert channel.request(f"change {i}") is not None
    assert channel.request("one too many") is None
    assert channel.queued == MAX_PENDING


def test_a_closed_turn_refuses_further_steers():
    channel = SteeringChannel(turn_id="t1")
    channel.close()
    assert channel.request("too late") is None


def test_the_registry_finds_a_live_turn_by_id_and_by_session():
    channel = SteeringChannel(turn_id="t9", session_id="s1")
    register_turn(channel)
    assert resolve_turn(turn_id="t9") is channel
    assert resolve_turn(session_id="s1") is channel
    assert resolve_turn(turn_id="other") is None
    assert resolve_turn(session_id="other") is None
    channel.close()
    assert resolve_turn(session_id="s1") is None


async def test_a_steer_lands_between_rounds_after_the_tools_are_recorded(monkeypatch):
    frames: list[dict] = []
    channel = _channel(frames)

    # The steer arrives while the model works on the follow-up call of round 1.
    # That call asks for one more tool, so the turn reaches a second boundary
    # before the model speaks again — the boundary the steer lands on.
    client = _ScriptedClient(
        [_tool_call("read_file"), _answer("redirected")],
        hook=lambda n: channel.request("Read config/ instead, then answer.") if n == 1 else None,
    )
    messages, client, _ = await _drive(
        _start_messages(), monkeypatch, [_tool_call("read_file")], client=client
    )

    steers = _steer_messages(messages)
    assert len(steers) == 1
    assert steers[0]["role"] == "user"
    assert "Read config/ instead" in steers[0]["content"]

    # The safety property: the steer sits after every result of the round it
    # interrupted, so it can never land between a side effect and its record.
    last_tool = max(
        i for i, m in enumerate(messages) if isinstance(m, dict) and m.get("role") == "tool"
    )
    assert messages.index(steers[0]) > last_tool

    # The model reads it on its next step, and the transcript says it landed.
    second_call = client.calls[1]["messages"]
    assert _steer_messages(second_call)
    assert frames and frames[0]["status"] == "landed" and frames[0]["round"] == 2


async def test_the_steer_message_names_the_boundary_and_carries_the_direction(monkeypatch):
    channel = _channel([])
    client = _ScriptedClient(
        [_tool_call("read_file"), _answer()],
        hook=lambda n: channel.request("Stop exploring, write the summary.") if n == 1 else None,
    )
    messages, _, _ = await _drive(
        _start_messages(), monkeypatch, [_tool_call("read_file")], client=client
    )

    body = _steer_messages(messages)[0]["content"]
    assert STEER_TOKEN in body
    assert "after tool round 2" in body
    assert "Stop exploring, write the summary." in body


async def test_the_transcript_line_names_who_changed_it_and_where(monkeypatch):
    frames: list[dict] = []
    channel = _channel(frames)
    client = _ScriptedClient(
        [_tool_call("read_file"), _answer()],
        hook=lambda n: channel.request("Use the second source.", actor="operator") if n == 1 else None,
    )
    await _drive(_start_messages(), monkeypatch, [_tool_call("read_file")], client=client)

    assert len(frames) == 1
    frame = frames[0]
    assert frame["type"] == "steer"
    assert frame["status"] == "landed"
    assert frame["actor"] == "operator"
    assert frame["round"] == 2
    assert frame["text"] == "Use the second source."
    assert frame["msg"] == "Direction changed by the operator (after tool round 2)"


async def test_a_stop_ends_the_turn_at_the_boundary_and_says_where(monkeypatch):
    frames: list[dict] = []
    chunks: list[str] = []
    channel = _channel(frames)

    # The stop arrives while the model is on the follow-up call of round 1. The
    # round its answer asked for still runs to its record — a steer does not cut
    # a call in half — and the turn ends at the boundary after that record.
    client = _ScriptedClient(
        [_tool_call("read_file"), _answer("never reached")],
        hook=lambda n: channel.request("", stop=True) if n == 1 else None,
    )
    messages, client, (iteration, _streamed, _response) = await _drive(
        _start_messages(), monkeypatch, [_tool_call("read_file")], client=client, chunks=chunks
    )

    assert len(client.calls) == 1, "the stop must not spend another model call"
    tool_messages = [
        m for m in messages if isinstance(m, dict) and m.get("role") == "tool"
    ]
    assert len(tool_messages) == 2, "both rounds are recorded"
    note = chunks[-1]
    assert "Stopped at the user's request after tool round 2" in note
    assert "No tool call was cut off mid-write" in note
    assert iteration == 2
    assert frames[0]["stop"] is True and frames[0]["status"] == "landed"


async def test_a_steer_arriving_while_the_answer_is_written_reopens_the_turn(monkeypatch):
    frames: list[dict] = []
    channel = _channel(frames)

    # The model has stopped asking for tools and is writing its answer while the
    # steer arrives. Without the re-open the new direction would never be read.
    client = _ScriptedClient(
        [_answer("first answer"), _answer("second answer")],
        hook=lambda n: channel.request("Answer in three bullets instead.") if n == 1 else None,
    )
    messages, client, _ = await _drive(
        _start_messages(), monkeypatch, [_tool_call("read_file")], client=client
    )

    assert len(client.calls) == 2, "the turn re-opened once for the steer"
    assert _steer_messages(client.calls[1]["messages"])
    assert frames[0]["status"] == "landed"


async def test_a_steer_the_turn_never_reaches_is_reported_as_unlanded(monkeypatch):
    frames: list[dict] = []
    channel = _channel(frames)

    # The budget is spent on the round the steer arrives in: the turn ends with no
    # boundary left to land on, and the transcript has to say so.
    client = _ScriptedClient(
        [_answer("only answer")],
        hook=lambda n: channel.request("Too late, change direction.") if n == 1 else None,
    )
    messages, _, _ = await _drive(
        _start_messages(), monkeypatch, [_tool_call("read_file")], client=client, budget_cap=1
    )

    assert not _steer_messages(messages), "an unlanded steer must not enter the context"
    assert frames and frames[-1]["status"] == "unlanded"
    assert frames[-1]["text"] == "Too late, change direction."


def test_take_up_is_a_no_op_without_a_bound_channel():
    messages = _start_messages()
    assert take_up(messages, boundary=1) == []
    assert len(messages) == 2


def test_an_unlanded_steer_says_the_turn_ended_before_it_landed():
    channel = SteeringChannel(turn_id="t1")
    channel.request("Too late to matter.", actor="operator")
    frames = channel.announce_unlanded(0)
    assert len(frames) == 1
    assert frames[0]["status"] == "unlanded"
    assert frames[0]["text"] == "Too late to matter."
    assert frames[0]["msg"] == "Direction change by the operator — the turn ended before it landed"


def test_the_parent_turn_takes_nothing_while_a_helper_holds_the_channel():
    frames: list[dict] = []
    channel = _channel(frames)
    channel.enter_focus("subagent-7")
    try:
        channel.request("Look at the tests/ directory instead.")
        # The turn's own boundary takes nothing: the work in front of the user is
        # the helper's, so the message waits for the helper's boundary.
        assert take_up(_start_messages(), boundary=1) == []
        assert channel.queued == 1

        messages = _start_messages()
        taken = take_up(messages, boundary=1, consumer="subagent-7", channel=channel)
        assert [s.text for s in taken] == ["Look at the tests/ directory instead."]
        assert _steer_messages(messages)[0]["role"] == "user"
        assert frames[0]["status"] == "landed"
    finally:
        channel.leave_focus("subagent-7")

    # Free again: an untargeted steer reaches the turn once more.
    channel.request("Now do the other thing.")
    assert len(take_up(_start_messages(), boundary=2, channel=channel)) == 1


async def test_a_subagent_reads_a_steer_addressed_to_it_and_releases_the_channel(monkeypatch):
    frames: list[dict] = []
    channel = _channel(frames)

    async def fake_execute_tool(name, args, *a, **k):
        return f"result-of-{name}"

    monkeypatch.setattr("core.tools.execute_tool", fake_execute_tool)
    client = _ScriptedClient(
        [_tool_call("read_file"), _answer("report")],
        hook=lambda n: channel.request("Narrow it to one file.", agent_id="a1") if n == 1 else None,
    )
    monkeypatch.setattr("core.model_provider.build_provider_client", lambda: client)

    sub = Subagent(agent_id="a1", role="researcher", task="find it", model="pinned", steering=channel)
    result = await sub.run()

    assert result.status == "ok"
    # The helper read the direction on its next step; it is in its own transcript.
    assert _steer_messages(client.calls[1]["messages"])
    assert frames[0]["agent_id"] == "a1"
    # The channel is free again: the turn takes an untargeted steer once more.
    channel.request("Back to the main task.")
    assert len(take_up(_start_messages(), boundary=3, channel=channel)) == 1


def test_the_direction_change_is_persisted_as_a_transcript_step(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    trajectory.begin_turn("s1", model="m", turn_id="t1")
    channel = SteeringChannel(turn_id="t1", session_id="s1")
    channel.on_steer = lambda frame: trajectory.record("s1", frame)

    channel.request("Switch to the German docs.", actor="operator")
    take_up([{"role": "user", "content": "q"}], boundary=2, channel=channel)

    steps = trajectory.get_turns("s1")[0]["steps"]
    assert steps[0]["type"] == "STEER"
    assert steps[0]["title"] == "Direction changed by the operator (after tool round 2)"
    assert steps[0]["text"] == "Switch to the German docs."
    assert steps[0]["state"] == "landed"


async def test_the_endpoint_answers_404_when_no_turn_is_running():
    from fastapi import HTTPException

    from server.routes.chat import SteerRequest, chat_steer

    with pytest.raises(HTTPException) as exc:
        await chat_steer(SteerRequest(text="do something else", session_id="s1"))
    assert exc.value.status_code == 404


async def test_the_endpoint_queues_into_the_running_turn():
    from server.routes.chat import SteerRequest, chat_steer

    channel = SteeringChannel(turn_id="t1", session_id="s1")
    register_turn(channel)

    answer = await chat_steer(
        SteerRequest(text="Take the other branch.", session_id="s1", actor="operator")
    )
    assert answer == {"status": "queued", "turn_id": "t1", "seq": 1, "stop": False, "queued": 1}
    assert take_up([], boundary=1, channel=channel)[0].actor == "operator"


async def test_the_endpoint_refuses_an_empty_direction_change():
    from fastapi import HTTPException

    from server.routes.chat import SteerRequest, chat_steer

    register_turn(SteeringChannel(turn_id="t1", session_id="s1"))
    with pytest.raises(HTTPException) as exc:
        await chat_steer(SteerRequest(text="   ", session_id="s1"))
    assert exc.value.status_code == 400
