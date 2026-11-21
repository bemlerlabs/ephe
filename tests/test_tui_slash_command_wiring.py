"""tests/test_tui_slash_command_wiring.py — every advertised slash command has a handler.

Measured 2026-10-15: `core/commands.py` listed `/learn` and `/goal` in COMMANDS, in the
descriptions and in Tab completion, and `is_learn_command` / `is_goal_command` sat next to
`is_swarm_command` — but `ui/app.py` only branched for `/swarm`. The TUI resolved the two
others through `resolve_command`, which returns their sentinel template, so the literal
`__learn__:x` was appended to the session and handed to the model as the user's message.

These cases type into the real input widget of a live app: the command reaches the worker
that serves it, no sentinel reaches the conversation, and a bare command gets its usage
hint before anything is sent.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

APP_SOURCE = Path(__file__).resolve().parent.parent / "ui" / "app.py"


@pytest.fixture
def app(tmp_path, monkeypatch):
    """A real TUI whose session file lives in a tmp dir, never in the operator's ~/.ephe."""
    import core.session as session_module

    session_dir = tmp_path / "sessions"
    session_dir.mkdir()
    monkeypatch.setattr(session_module, "SESSION_DIR", session_dir)
    monkeypatch.setattr(session_module, "SESSION_FILE", session_dir / "default.json")

    from ui.app import EpheApp

    return EpheApp(model="stub-model", reset=False)


def _stub(app, name: str) -> list:
    """Replace one worker with a recorder, so no engine is ever called."""
    seen: list = []
    setattr(app, name, lambda *args: seen.append(args))
    return seen


def _drive(app, text: str) -> tuple[list[str], list, list]:
    """Submit ``text`` typed into the real input widget.

    Returns the blocks the chat view renders, and the session state afterwards.
    """
    from textual.containers import Vertical
    from textual.widgets import Static

    from ui.composer import ComposerArea
    from ui.widgets import ChatView

    shown: list[str] = []

    async def go():
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            box = app.query_one("#chat-input", ComposerArea)
            box.focus()
            box.value = text
            await pilot.press("enter")
            await pilot.pause()
            container = app.query_one(ChatView).query_one("#chat-container", Vertical)
            shown.extend(str(block.content) for block in container.query(Static))

    asyncio.run(go())
    return shown, list(app._session), list(app._pending_history)


def test_learn_reaches_the_skill_builder_and_sends_no_sentinel(app):
    """
    GIVEN `/learn How we structure FastAPI routes`
    WHEN the user submits it
    THEN the skill builder gets the topic and nothing enters the conversation.
    """
    seen = _stub(app, "_run_learn")

    _, session, pending = _drive(app, "/learn How we structure FastAPI routes")

    assert seen == [("How we structure FastAPI routes",)]
    assert session == [] and pending == []
    assert not any("__learn__" in str(message.content) for message in pending)


def test_goal_reaches_the_loop_with_the_flags_it_parsed(app):
    """
    GIVEN `/goal Fix the login bug --max-turns 2`
    WHEN the user submits it
    THEN the loop gets the target and the parsed ceiling, and no sentinel is sent.
    """
    seen = _stub(app, "_run_goal")

    _, session, pending = _drive(app, "/goal Fix the login bug --max-turns 2")

    assert len(seen) == 1
    spec = seen[0][0]
    assert (spec.task, spec.check, spec.max_turns) == ("Fix the login bug", "pytest -q", 2)
    assert session == [] and pending == []
    assert not any("__goal__" in str(message.content) for message in pending)


@pytest.mark.parametrize("verb", ["/learn", "/goal"])
def test_a_bare_command_asks_for_its_argument_instead_of_calling_a_worker(app, verb):
    """
    GIVEN `/learn` or `/goal` with no argument
    WHEN it is submitted
    THEN the usage hint is shown, neither worker runs, and nothing is sent.
    """
    seen = _stub(app, "_run_learn") + _stub(app, "_run_goal")

    shown, session, pending = _drive(app, verb)

    assert seen == []
    assert session == [] and pending == []
    assert any(f"Usage: {verb}" in block for block in shown), shown


def test_the_swarm_command_still_behaves_the_same_way(app):
    """
    GIVEN `/swarm` with no task
    WHEN it is submitted
    THEN its usage hint is shown and no pipeline starts — the branch this work sits next to.
    """
    seen = _stub(app, "_run_swarm")

    shown, session, pending = _drive(app, "/swarm")

    assert seen == []
    assert session == [] and pending == []
    assert any("Usage: /swarm" in block for block in shown), shown


def test_every_advertised_sentinel_command_is_handled_in_the_app():
    """
    GIVEN the commands the TUI offers in Tab completion
    WHEN each sentinel command is checked against the app's own branches
    THEN every advertised command with a sentinel template has a branch that consumes it.
    """
    import core.commands as commands

    source = APP_SOURCE.read_text(encoding="utf-8")
    sentinels = {
        name: template
        for name, template in commands.COMMANDS.items()
        if template.startswith("__") and ":" in template
    }

    assert sentinels, "the registry no longer marks a command with a sentinel template"
    for name in sentinels:
        handler = f"is_{name.lstrip('/')}_command"
        assert handler in source, f"{name} is advertised but ui/app.py never calls {handler}"
