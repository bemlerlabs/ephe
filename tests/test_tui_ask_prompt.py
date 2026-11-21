"""The terminal's answer field for a question the run asked (finding #66).

Two things are held here. The card: a number picks an option, free text stays the reader's own
sentence, and a question full of Rich's bracket shapes must not crash the transcript the way the
approval prompt once did. And the wiring: the gate's callback resolves with what the card got,
and with nothing when the reader walked away.
"""
from __future__ import annotations

import asyncio

import pytest
from textual.app import App, ComposeResult
from textual.containers import Vertical
from textual.events import Key
from textual.widgets import Input, Static
from rich.markup import render

from ui.app import EpheApp
from ui.widgets import AskPrompt

SPEC = {
    "question": "Which report should the summary lead with?",
    "options": [{"label": "Revenue first"}, {"label": "Churn first"}],
    "recommendation": "Revenue first",
    "default": "Revenue first",
    "multi_select": True,
}


class Host(App):
    """One mounted card in a container the tests can add to."""

    CSS = "Vertical { height: auto; }"

    def compose(self) -> ComposeResult:
        with Vertical(id="host"):
            yield AskPrompt(SPEC, from_tool=True, id="ask")


async def send(prompt: AskPrompt, value: str) -> None:
    field = prompt.query_one("#ask-input", Input)
    field.value = value
    field.post_message(Input.Submitted(value=value, input=field))
    await asyncio.wait_for(prompt.answered.wait(), timeout=2.0)


@pytest.mark.asyncio
async def test_a_number_picks_the_option_it_is_written_against():
    app = Host()
    async with app.run_test():
        await send(app.query_one("#ask", AskPrompt), "2")
        assert app.query_one("#ask", AskPrompt).result == "Churn first"


@pytest.mark.asyncio
async def test_several_numbers_answer_a_multi_select():
    app = Host()
    async with app.run_test():
        prompt = app.query_one("#ask", AskPrompt)
        await send(prompt, "2, 1")
        assert prompt.result == "Revenue first, Churn first"


@pytest.mark.asyncio
async def test_an_own_sentence_is_kept_as_the_reader_wrote_it():
    app = Host()
    async with app.run_test():
        prompt = app.query_one("#ask", AskPrompt)
        await send(prompt, "Lead with the margin, it moved more")
        assert prompt.result == "Lead with the margin, it moved more"


@pytest.mark.asyncio
async def test_escape_is_no_answer_at_all():
    app = Host()
    async with app.run_test():
        prompt = app.query_one("#ask", AskPrompt)
        prompt.on_key(Key(key="escape", character=None))
        await asyncio.wait_for(prompt.answered.wait(), timeout=2.0)
        assert prompt.result == ""


@pytest.mark.asyncio
async def test_a_question_of_bracket_shapes_renders():
    """The ConfirmPrompt crash class, closed for this card too.

    The body is assembled as a Rich `Text`, so it never reaches a markup parser — the only
    thing that survives a question quoting a path like `[$@3cg]`.
    """
    nasty = {**SPEC, "question": "run rm -rf build/? (target: [build]/out) [$@3cg]"}

    class NastyHost(Host):
        def compose(self) -> ComposeResult:
            with Vertical(id="host"):
                yield AskPrompt(nasty, from_tool=True, id="ask")

    app = NastyHost()
    async with app.run_test():
        body = app.query_one("#ask", AskPrompt).query_one("#ask-body", Static)
        render(body.content.plain)
        assert "[build]/out" in body.content.plain


@pytest.mark.asyncio
async def test_the_gate_callback_waits_for_the_card_and_returns_the_answer():
    """`ask_user` in the terminal: the run pauses here, and the answer is the tool's result."""

    class FakeChat:
        def __init__(self, app: Host) -> None:
            self.app = app

        async def show_ask_prompt(self, spec: dict, *, from_tool: bool) -> AskPrompt:
            prompt = AskPrompt(spec, from_tool=from_tool, id="ask-live")
            await self.app.query_one("#host", Vertical).mount(prompt)
            return prompt

    app = Host()
    async with app.run_test():
        cb = EpheApp._tui_ask_cb(object(), FakeChat(app))
        running = asyncio.ensure_future(
            cb(
                question="Which one?",
                options=["Revenue first", "Churn first"],
                recommendation="",
                default="",
                multi_select=False,
                timeout_seconds=5.0,
            )
        )
        await asyncio.sleep(0.05)
        await send(app.query_one("#ask-live", AskPrompt), "1")
        assert await running == "Revenue first"


@pytest.mark.asyncio
async def test_the_gate_callback_returns_empty_when_nobody_answers():
    class NeverAnswered:
        def __init__(self) -> None:
            self.answered = asyncio.Event()
            self.result = ""
            self.dismissed = False

        def dismiss(self) -> None:
            self.dismissed = True

    class SilentChat:
        card = NeverAnswered()

        async def show_ask_prompt(self, spec: dict, *, from_tool: bool):
            return self.card

    chat = SilentChat()
    cb = EpheApp._tui_ask_cb(object(), chat)
    answer = await cb(
        question="Which one?",
        options=["a", "b"],
        recommendation="",
        default="",
        multi_select=False,
        timeout_seconds=0.05,
    )
    assert answer == ""
    assert chat.card.dismissed is True
