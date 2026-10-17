"""
G1 — the ask gate: a run that pauses on a question and goes on with the answer.

Four things are pinned here, one per level of the path:

  1. ``core.tools.ask_gate.ask_user`` is a real tool call — it does not return before
     the answer exists, and the answer comes back as its result, which is what the
     running tool loop reads;
  2. a turn with no dialog channel (CLI, cron, a test) continues on the default the
     run stated instead of parking on an Event nobody sets;
  3. ``server/routes/chat.py::_ask_confirm`` emits the ``ask_user`` frame, keeps the
     stream byte-active while it waits, and ends an unanswered wait with the
     ``ask_timeout`` frame plus the empty answer that turns into the continuation;
  4. one SSE stream carries the question AND the continuation — the answer goes back
     into the same run, so no second request is involved anywhere.

Endpoint contract of ``POST /api/ask/answer``: 200 for a waiting token, 404 for a
token nobody waits on, 422 for an empty answer (the empty string already means
"nobody answered" on the waiting side).
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from core.tools import ask_gate
from server.routes import chat as chat_route


@pytest.fixture(autouse=True)
def _clean_ask_gate():
    """The registry and the callback are process-wide; a left-over entry from another
    test would answer a later turn."""
    ask_gate.set_ask_cb(None)
    ask_gate._ACTIVE_ASKS.clear()
    yield
    ask_gate.set_ask_cb(None)
    ask_gate._ACTIVE_ASKS.clear()


# 1 + 2: the tool

def test_the_call_does_not_return_before_the_answer_exists():
    """The pause is a real await: with the question open the task is parked, and the
    answer that resolves it is the result the tool returns."""

    async def _run() -> tuple[bool, str, int]:
        box: dict = {}

        async def _dialog(**kwargs) -> str:
            token, entry = ask_gate.register_ask(kwargs["question"])
            box["token"] = token
            try:
                await entry["event"].wait()
                return str(entry["answer"])
            finally:
                ask_gate.discard_ask(token)

        ask_gate.set_ask_cb(_dialog)
        task = asyncio.create_task(
            ask_gate.ask_user("Which branch?", options="main;wt/n1-ask", default="main")
        )
        for _ in range(200):
            await asyncio.sleep(0)
            if box.get("token"):
                break
        parked = not task.done()
        await asyncio.sleep(0.02)
        still_parked = not task.done()
        assert ask_gate.resolve_ask(box["token"], "wt/n1-ask") is True
        answer = await task
        return parked and still_parked, answer, ask_gate.active_ask_count()

    stayed_parked, answer, remaining = asyncio.run(_run())
    assert stayed_parked is True
    assert answer == '[ask_user] The user answered: "wt/n1-ask"'
    assert remaining == 0


def test_without_a_dialog_the_run_continues_on_its_stated_default():
    out = asyncio.run(ask_gate.ask_user("Which branch?", default="main"))
    assert "no interactive channel" in out
    assert '"main"' in out


def test_without_a_dialog_and_without_a_default_the_run_names_its_assumption():
    out = asyncio.run(ask_gate.ask_user("Which branch?"))
    assert "name the assumption" in out


def test_an_empty_answer_is_read_as_the_timeout_and_keeps_the_default():
    async def _run() -> str:
        async def _dialog(**_kwargs) -> str:
            return ""

        ask_gate.set_ask_cb(_dialog)
        return await ask_gate.ask_user("Which branch?", default="main", timeout_seconds=7)

    out = asyncio.run(_run())
    assert "nobody answered within 7s" in out
    assert '"main"' in out


def test_a_question_that_was_never_asked_is_refused():
    out = asyncio.run(ask_gate.ask_user("   "))
    assert "0 characters" in out


def test_options_parse_on_lines_semicolons_and_pipes():
    assert ask_gate.parse_options("main\nwt/n1-ask") == ["main", "wt/n1-ask"]
    assert ask_gate.parse_options("main;wt/n1-ask") == ["main", "wt/n1-ask"]
    assert ask_gate.parse_options("main|wt/n1-ask") == ["main", "wt/n1-ask"]
    assert ask_gate.parse_options("") == []


def test_resolving_an_unknown_token_is_refused():
    assert ask_gate.resolve_ask("no-such-token", "x") is False


# 3: the route's wait

def _ask_confirm(emit: list, raw: list, *, timeout_seconds: float):
    return chat_route._ask_confirm(
        question="Which branch?",
        options=["main", "wt/n1-ask"],
        recommendation="main",
        default="main",
        multi_select=False,
        timeout_seconds=timeout_seconds,
        emit=emit.append,
        emit_raw=raw.append,
    )


def test_the_route_emits_the_question_and_returns_the_answer():
    events: list = []
    raw: list = []

    async def _run() -> str:
        task = asyncio.create_task(_ask_confirm(events, raw, timeout_seconds=5.0))
        for _ in range(200):
            await asyncio.sleep(0)
            if events:
                break
        token = next(iter(ask_gate._ACTIVE_ASKS))
        assert ask_gate.resolve_ask(token, "wt/n1-ask") is True
        return await task

    answer = asyncio.run(_run())
    frame = events[0]
    assert frame["type"] == "ask_user"
    assert frame["token"] in ask_gate._ACTIVE_ASKS or frame["token"]
    assert frame["question"] == "Which branch?"
    assert frame["options"] == ["main", "wt/n1-ask"]
    assert frame["default"] == "main"
    assert frame["timeout_s"] == 5.0
    assert answer == "wt/n1-ask"
    assert ask_gate.active_ask_count() == 0


def test_an_unanswered_wait_ends_with_the_timeout_frame_and_no_answer():
    events: list = []
    raw: list = []
    answer = asyncio.run(_ask_confirm(events, raw, timeout_seconds=0.05))

    assert answer == ""
    assert [e["type"] for e in events] == ["ask_user", "ask_timeout"]
    assert events[-1]["default"] == "main"
    assert ask_gate.active_ask_count() == 0


def test_the_late_answer_finds_no_open_wait():
    events: list = []
    raw: list = []
    answer = asyncio.run(_ask_confirm(events, raw, timeout_seconds=0.05))

    token = events[0]["token"]
    assert answer == ""
    assert ask_gate.resolve_ask(token, "main") is False


# 4: one stream, question and continuation

def _sse_frames(text: str) -> list[dict]:
    import json

    frames = []
    for block in text.split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                frames.append(json.loads(line[6:]))
    return frames


def _drive(monkeypatch, *, answer: str, fake, ready=None):
    """Run the real /chat/stream generator to completion, answering the first open ask
    as soon as ``ready`` holds for the bytes that arrived (default: the ask frame is on
    the wire). The wait itself is what a slow human exercises, so the condition is a
    parameter rather than a fixed point.
    """
    seen_frame = ready or (lambda text: '"type": "ask_user"' in text)
    monkeypatch.setattr(chat_route, "chat_with_tools", fake)
    req = chat_route.StreamRequest(message="please ask me", session_id="s-ask-gate")

    async def _run() -> str:
        resp = await chat_route.chat_stream(req)
        text = ""
        answered = False
        async for chunk in resp.body_iterator:
            text += chunk
            if not answered and seen_frame(text):
                for token in list(ask_gate._ACTIVE_ASKS):
                    assert ask_gate.resolve_ask(token, answer) is True
                answered = True
        return text

    return asyncio.run(_run())


def test_the_same_stream_asks_and_continues_with_the_answer(monkeypatch):
    seen: list[str] = []

    async def _fake_chat(*, on_chunk=None, on_tool_start=None, **kwargs):
        # The real tool loop reaches the gate the same way: through the ContextVar the
        # route set for this request. Nothing here sends a second HTTP request.
        if on_tool_start:
            on_tool_start("ask_user", {"question": "Which branch?"}, "call-1")
        answer = await ask_gate.ask_user(
            "Which branch?", options="main;wt/n1-ask", default="main", timeout_seconds=5.0
        )
        seen.append(answer)
        if on_chunk:
            on_chunk(f"CONTINUED:{answer}")
        return "done"

    text = _drive(monkeypatch, answer="wt/n1-ask", fake=_fake_chat)
    frames = _sse_frames(text)

    ask_frames = [f for f in frames if f.get("type") == "ask_user"]
    assert len(ask_frames) == 1
    assert ask_frames[0]["timeout_s"] == 5.0
    # The answer reached the tool call inside the running turn, which is what makes the
    # same run continue instead of a new one starting.
    assert seen == ['[ask_user] The user answered: "wt/n1-ask"']
    assert any("CONTINUED:" in str(f.get("data", "")) for f in frames)
    assert ask_gate.active_ask_count() == 0


def test_the_wait_keeps_the_stream_byte_active(monkeypatch):
    """A human who takes their time must not lose the turn to the reader's idle
    detector: SSE comments flow while the question is open."""
    monkeypatch.setattr(chat_route, "SANDBOX_KEEPALIVE_SECONDS", 0.01)

    async def _fake_chat(*, on_chunk=None, **kwargs):
        answer = await ask_gate.ask_user("Which branch?", default="main", timeout_seconds=5.0)
        if on_chunk:
            on_chunk(f"CONTINUED:{answer}")
        return "done"

    text = _drive(
        monkeypatch,
        answer="main",
        fake=_fake_chat,
        ready=lambda text: ": keepalive" in text,
    )
    assert ": keepalive" in text
    # The turn went on with the answer after the comment: the same stream carries both.
    assert any("CONTINUED:" in f for f in text.split("data: "))


def test_the_stream_reports_the_timeout_and_the_default_it_used(monkeypatch):
    async def _fake_chat(*, on_chunk=None, **kwargs):
        answer = await ask_gate.ask_user("Which branch?", default="main", timeout_seconds=0.05)
        if on_chunk:
            on_chunk(f"CONTINUED:{answer}")
        return "done"

    # Nobody answers: the driver never resolves the token, so the route's own timeout
    # has to end the wait and name what the run continued on.
    text = _drive(monkeypatch, answer="main", fake=_fake_chat, ready=lambda _text: False)
    frames = _sse_frames(text)

    timeout_frames = [f for f in frames if f.get("type") == "ask_timeout"]
    assert len(timeout_frames) == 1
    assert timeout_frames[0]["default"] == "main"
    assert any("nobody answered" in str(f.get("data", "")) for f in frames)


# The endpoint

def test_answer_endpoint_wakes_the_waiting_turn():
    model = chat_route.AskAnswerRequest(token="ask-1", answer="wt/n1-ask")
    token, entry = ask_gate.register_ask("Which branch?")

    out = asyncio.run(chat_route.answer_ask(
        chat_route.AskAnswerRequest(token=token, answer="wt/n1-ask")
    ))
    assert out == {"status": "ok"}
    assert entry["event"].is_set() is True
    assert entry["answer"] == "wt/n1-ask"
    assert model.token == "ask-1"


def test_answer_endpoint_refuses_an_unknown_token():
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chat_route.answer_ask(
            chat_route.AskAnswerRequest(token="gone", answer="main")
        ))
    assert exc.value.status_code == 404


def test_answer_endpoint_refuses_an_empty_answer():
    token, _entry = ask_gate.register_ask("Which branch?")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(chat_route.answer_ask(
            chat_route.AskAnswerRequest(token=token, answer="   ")
        ))
    assert exc.value.status_code == 422


# Registration: the tool is reachable where a running turn looks for it

def test_ask_user_is_a_registered_tool_with_a_schema():
    from core.tools.registry import TOOL_MAP, get_tool_schemas

    assert TOOL_MAP.get("ask_user") is ask_gate.ask_user
    names = [entry["function"]["name"] for entry in get_tool_schemas()]
    assert "ask_user" in names


def test_ask_user_runs_without_a_second_confirmation_dialog():
    from core.tools.approval import chat_tool_requires_confirm

    assert chat_tool_requires_confirm("ask_user") is False


def test_ask_user_is_allowed_in_the_read_only_modes():
    """Plan mode is exactly where a run should be able to ask before it writes."""
    from core.tools.chat_gate import READ_ONLY_MODE_TOOLS, mode_denial

    assert "ask_user" in READ_ONLY_MODE_TOOLS
    assert mode_denial("ask_user") is None
    assert "ask_user" in chat_route._READ_ONLY_TOOL_NAMES
