"""What the terminal shows a person who comes back to a session.

Four surfaces were wrong on 2026-10-31 and are pinned here: a resumed session
opened on a greeting instead of its transcript, the greeting stayed above every
turn, the status bar clipped its meter at 120–140 columns, and a declined tool
rendered as one that ran.
"""
from __future__ import annotations

import asyncio

import pytest

from core import multi_session as ms
from ui.context_meter import ContextUsage
from ui.widgets import AgentMessageCard, ChatView, StatusBar


def _message(role: str, text: str) -> dict[str, str]:
    return {"role": role, "content": text}


async def _idle(*_args, **_kwargs) -> None:
    return None


def _quiet(app) -> None:
    """Keep the boot workers off the engine, MCP servers and the network."""
    for name in ("_async_check_connection", "_async_init_mcp", "_async_check_update"):
        setattr(app, name, _idle)


def test_a_resumed_session_opens_on_its_transcript() -> None:
    """GIVEN a stored session with turns
    WHEN the terminal starts
    THEN the turns are on screen and no empty-session greeting stands above them."""
    sid = ms.create_session("Resume me")["id"]
    ms.save_messages(
        sid, [_message("user", "question one"), _message("assistant", "answer one")]
    )
    ms.switch_to(sid)

    from ui.app import EpheApp

    async def run() -> tuple[str, int]:
        app = EpheApp(model="test-model", reset=False)
        _quiet(app)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.pause()
            return app.export_screenshot(), len(app.query("#welcome-card"))

    shown, greetings = asyncio.run(run())
    assert "Resumed" in shown
    assert "question" in shown
    assert "answer" in shown
    assert greetings == 0


def test_the_greeting_retires_after_the_first_message() -> None:
    """GIVEN a fresh session
    WHEN the first message is posted
    THEN the greeting block leaves the transcript."""
    sid = ms.create_session("Fresh")["id"]
    ms.switch_to(sid)

    from ui.app import EpheApp

    async def run() -> tuple[int, int]:
        app = EpheApp(model="test-model", reset=False)
        _quiet(app)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            before = len(app.query("#welcome-card"))
            app.query_one(ChatView).post_message(ChatView.AddUserMessage("hello"))
            await pilot.pause()
            after = len(app.query("#welcome-card"))
            return before, after

    before, after = asyncio.run(run())
    assert before == 1
    assert after == 0


def test_the_status_bar_fits_its_facts_at_120_columns() -> None:
    """GIVEN provider, model, session and meter on a 120-column terminal
    WHEN the bar renders
    THEN it drops the provider cell instead of clipping the meter."""
    from textual.app import App, ComposeResult

    class _Harness(App):
        def compose(self) -> ComposeResult:
            yield StatusBar(id="status-bar")

    async def run() -> tuple[bool, str, str]:
        app = _Harness()
        async with app.run_test(size=(120, 10)) as pilot:
            status = app.query_one(StatusBar)
            status.post_message(
                StatusBar.SetStatus(
                    True, "deepseek-flash", "OpenAI-compatible API · api.deepseek.com"
                )
            )
            status.post_message(StatusBar.SetSession("beecard3", 19))
            status.post_message(
                StatusBar.SetMeter(ContextUsage(user=3200, window=8192), "engine")
            )
            await pilot.pause()
            return (
                status.has_class("narrow"),
                str(status.query_one("#status-provider").render()),
                str(status.query_one("#status-meter").render()),
            )

    narrow, provider, meter = asyncio.run(run())
    assert narrow is True
    assert provider == ""
    assert "ctx 39%" in meter
    assert "tok" in meter


@pytest.mark.asyncio
async def test_a_declined_tool_never_renders_as_a_run() -> None:
    """GIVEN a tool call that waits for approval and is then declined
    THEN its row says so — 'Ran <cmd>' claimed an execution nobody allowed."""
    from textual.app import App, ComposeResult

    class _Harness(App):
        def compose(self) -> ComposeResult:
            yield AgentMessageCard()

    async with _Harness().run_test(size=(100, 30)) as pilot:
        app = pilot.app
        card = app.query_one(AgentMessageCard)
        card.post_message(AgentMessageCard.ToolStart("run_shell", {"command": "echo hi"}))
        await pilot.pause()
        card.post_message(AgentMessageCard.ToolWaiting("run_shell"))
        await pilot.pause()
        assert "Waiting for approval" in card._blocks[0].title
        card.post_message(AgentMessageCard.ToolResume("run_shell"))
        await pilot.pause()
        assert card._blocks[0].title.startswith("Running")
        card.post_message(
            AgentMessageCard.ToolDone(
                "run_shell",
                "[TOOL-DENIED] run_shell was not executed: the user did not approve the run.",
                refused=True,
            )
        )
        await pilot.pause()
        assert card._blocks[0].title.startswith("Declined")
        assert not card._blocks[0].title.startswith("Ran")
        assert card._blocks[0].has_class("tool-refused")


def test_help_rows_keep_their_gutter_when_a_description_wraps() -> None:
    from ui.app import _help_rows

    rows = _help_rows(
        [("Ctrl+O, /sessions", "session switcher (Ctrl+N new, F2 rename, F3 delete)")]
    )
    assert len(rows) == 2
    assert rows[0].startswith("  Ctrl+O, /sessions")
    assert rows[1].startswith(" " * 21)
    assert max(len(row) for row in rows) <= 66


@pytest.mark.asyncio
async def test_the_delete_confirmation_sits_in_the_footer() -> None:
    """GIVEN a session list
    WHEN F3 arms a deletion
    THEN the footer states it; the row stays inside the card."""
    from textual.app import App, ComposeResult

    from ui.session_switcher import SessionSwitcher

    sid = ms.create_session("Long enough to matter")["id"]
    ms.save_messages(sid, [_message("user", "hi")])

    class _Harness(App):
        def compose(self) -> ComposeResult:
            yield from ()

        def on_mount(self) -> None:
            self.push_screen(SessionSwitcher(sid))

    app = _Harness()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        screen = app.screen
        screen.action_delete()
        await pilot.pause()
        footer = str(screen.query_one("#session-footer").render())
        rows = str(screen.query_one("#session-list").render())
    assert "F3 again deletes “Long enough to matter”" in footer
    assert "F3 again" not in rows


def test_a_missing_model_is_reported_and_not_replaced() -> None:
    """The tag is the user's choice. A startup that switches it on its own
    wrote a config the next start could not use (2026-10-31)."""
    from pathlib import Path

    source = Path("ui/app.py").read_text(encoding="utf-8")
    assert "Model auto-corrected" not in source
    assert "_heal_model_drift" not in source
    assert "the product never picks one for" in source
