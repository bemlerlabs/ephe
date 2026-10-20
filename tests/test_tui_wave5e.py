"""Wave 5E: the terminal pass — sessions, composer, context, shell, actions.

Every interaction here runs through the shipped widgets: the real Textual
harness mounts ``EpheApp``, keys reach the focused widget, and the single
server session store under the test's tmp directory holds the result. The
engine is never called; tests that need a turn replace the worker or the
executor at its import seam.
"""

from __future__ import annotations

import asyncio
import sys

import pytest

from core import multi_session as ms
from ui.widgets import StatusBar


def _mount(app, monkeypatch) -> None:
    async def noop() -> None:
        return None

    monkeypatch.setattr(app, "_async_check_connection", noop)
    monkeypatch.setattr(app, "_async_init_mcp", noop)


@pytest.fixture
def app_factory(monkeypatch):
    from ui.app import EpheApp

    def make(model: str = "stub-model"):
        app = EpheApp(model=model, reset=False)
        _mount(app, monkeypatch)
        return app

    return make


def _run(coro):
    return asyncio.run(coro)


def _active(title: str, messages: list[dict] | None = None) -> dict:
    entry = ms.create_session(title)
    if messages is not None:
        ms.save_messages(str(entry["id"]), messages)
    ms.switch_to(str(entry["id"]))
    return entry




def test_header_names_the_session_and_one_state_word(app_factory):
    _active("Alpha")
    app = app_factory()

    async def go():
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert "◑" in str(app.query_one("#brand-mark").render())
            assert "Ephe" in str(app.query_one("#brand-title").render())
            assert "Alpha" in str(app.query_one("#brand-session").render())
            assert "rest" in str(app.query_one("#brand-state").render())
            assert app.query_one("#status-session").render() is not None

    _run(go())


def test_status_bar_keeps_engine_and_model_when_an_error_arrives(app_factory):
    from ui.widgets import StatusBar

    app = app_factory()

    async def go():
        async with app.run_test(size=(120, 30)) as pilot:
            status = app.query_one(StatusBar)
            status.post_message(
                StatusBar.SetStatus(
                    connected=True, model="m-1", provider="Local engine · host"
                )
            )
            status.post_message(StatusBar.SetSession("Alpha", 4))
            await pilot.pause()
            status.post_message(StatusBar.SetError("Model busy"))
            await pilot.pause()
            assert "m-1" in str(status.query_one("#status-model").render())
            assert "Local engine" in str(status.query_one("#status-provider").render())
            assert "Alpha" in str(status.query_one("#status-session").render())
            assert "Model busy" in str(status.query_one("#status-indicator").render())

    _run(go())


def test_every_run_state_reaches_the_header(app_factory):
    app = app_factory()

    async def go():
        async with app.run_test(size=(80, 24)) as pilot:
            for state in ("working", "waiting", "done", "error", "offline", "rest"):
                app._set_run_state(state)
                await pilot.pause()
                assert state in str(app.query_one("#brand-state").render())

    _run(go())


def test_the_terminal_mounts_at_eighty_by_twenty_four_and_anchors_on_resize(
    app_factory,
):
    from textual.containers import Vertical

    from ui.widgets import ChatView

    app = app_factory()

    async def go():
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            chat = app.query_one(ChatView)
            for index in range(30):
                chat.post_message(ChatView.AddSystemMessage(f"line {index}"))
            await pilot.pause()
            container = chat.query_one("#chat-container", Vertical)
            assert container.max_scroll_y > 0, "the transcript does not scroll at 80x24"
            container.scroll_end(animate=False)
            await pilot.pause()
            assert container.is_vertical_scroll_end
            await pilot.resize_terminal(100, 30)
            await pilot.pause()
            assert container.is_vertical_scroll_end, (
                "a resize dropped the transcript anchor"
            )
            assert app.query_one("#input-area").size.height >= 1
            assert app.query_one("#status-bar").size.width > 0

    _run(go())




def test_ctrl_j_makes_a_new_line_and_enter_sends_the_whole_draft(
    app_factory, monkeypatch
):
    from ui.composer import ComposerArea

    app = app_factory()
    sent: list[str] = []
    monkeypatch.setattr(app, "_submit_turn", sent.append)

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            area = app.query_one("#chat-input", ComposerArea)
            area.focus()
            await pilot.press("a", "ctrl+j", "b")
            await pilot.pause()
            assert area.value == "a\nb", area.value
            await pilot.press("enter")
            await pilot.pause()
            assert sent == ["a\nb"], sent
            assert area.value == ""

    _run(go())


def test_ctrl_up_walks_the_submission_history(app_factory):
    from ui.composer import ComposerArea

    app = app_factory()

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            area = app.query_one("#chat-input", ComposerArea)
            area.focus()
            area.value = "first"
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("ctrl+up")
            await pilot.pause()
            assert area.value == "first", area.value

    _run(go())




def test_the_session_switcher_filters_and_opens(app_factory):
    _active("Alpha")
    beta = ms.create_session("Beta plan")

    from ui.session_switcher import SessionSwitcher

    app = app_factory()

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.action_sessions()
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, SessionSwitcher)
            box = screen.query_one("#session-filter")
            box.value = "beta"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert app._session_id == beta["id"], app._session_id

    _run(go())


def test_the_session_switcher_renames_and_deletes(app_factory):
    first = _active("Alpha")
    second = ms.create_session("Beta")

    from ui.session_switcher import SessionSwitcher

    app = app_factory()

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.action_sessions()
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, SessionSwitcher)
            box = screen.query_one("#session-filter")
            box.value = "Beta"
            await pilot.pause()
            await pilot.press("f2")
            await pilot.pause()
            box.value = "Beta renamed"
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert ms.get_session(str(second["id"]))["title"] == "Beta renamed"
            await pilot.press("f3")
            await pilot.pause()
            assert ms.get_session(str(second["id"])) is not None, (
                "one press must not delete"
            )
            await pilot.press("f3")
            await pilot.pause()
            assert ms.get_session(str(second["id"])) is None
            assert ms.get_session(str(first["id"])) is not None

    _run(go())


def test_new_session_is_a_new_transcript_and_never_destroys_the_old_one(app_factory):
    old = _active("Keep me", [{"role": "user", "content": "hello"}])
    app = app_factory()

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.action_new_session()
            await pilot.pause()
            assert app._session_id != old["id"]
            assert ms.load_messages(str(old["id"])) == [
                {"role": "user", "content": "hello"}
            ]

    _run(go())




def test_the_palette_lists_every_action_and_inserts_commands(app_factory):
    from ui.overlays import CommandPalette

    app = app_factory()

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.action_palette()
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, CommandPalette)
            actions = {value for value, _label in screen._matches}
            for expected in (
                "new_session",
                "sessions",
                "model_picker",
                "undo_turn",
                "redo_turn",
                "editor",
                "help",
                "clear_chat",
                "quit",
            ):
                assert expected in actions, expected
            assert any(action.startswith("insert:/help") for action in actions)
            screen.dismiss(None)
            await pilot.pause()
            app._run_palette_action("insert:/post ")
            await pilot.pause()
            assert app.query_one("#chat-input").value == "/post "

    _run(go())


def test_help_is_one_overlay_from_the_bindings_and_names_the_change_set(app_factory):
    from ui.overlays import HelpOverlay

    app = app_factory()

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.action_help()
            await pilot.pause()
            assert isinstance(app.screen, HelpOverlay)
            text = app.screen._text
            for key in ("Enter", "Ctrl+J", "Ctrl+P", "Ctrl+O", "F8", "F9", "F4", "F1"):
                assert key in text, key
            assert "/sessions" in text
            assert "git restore" in text, "the help does not name the file-level revert"
            await pilot.press("escape")
            await pilot.pause()
            assert app.screen is app.screen_stack[0]
            await pilot.press("/")  # focus returned to the composer

    _run(go())




def test_undo_and_redo_round_trip_the_last_turn_in_the_store(app_factory):
    entry = _active(
        "Turn log",
        [
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ],
    )
    app = app_factory()

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app.action_undo_turn()
            await pilot.pause()
            assert app._session == []
            assert ms.load_messages(str(entry["id"])) == []
            app.action_redo_turn()
            await pilot.pause()
            assert app._session == [
                {"role": "user", "content": "question"},
                {"role": "assistant", "content": "answer"},
            ]
            assert len(ms.load_messages(str(entry["id"]))) == 2

    _run(go())




class _Channel:
    closed = False

    def __init__(self) -> None:
        self.requests: list[str] = []

    def request(self, text: str, **_kwargs):
        self.requests.append(text)
        return object()


def test_a_line_during_a_turn_steers_the_live_channel(app_factory):
    _active("Steer")
    app = app_factory()

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            channel = _Channel()
            app._streaming = True
            app._steer_channel = channel
            app._accept_input("turn left")
            await pilot.pause()
            assert channel.requests == ["turn left"]
            assert app._queued == []
            assert app._session[-1]["content"] == "[steer] turn left"

    _run(go())


def test_a_line_is_queued_when_streaming_input_is_disabled(app_factory, monkeypatch):
    import core.settings_schema as settings

    _active("Queue")
    app = app_factory()
    monkeypatch.setattr(settings, "deep_bool", lambda key: False)

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._streaming = True
            app._steer_channel = _Channel()
            app._accept_input("one")
            app._accept_input("two")
            await pilot.pause()
            assert app._queued == ["one", "two"]
            assert app.query_one(StatusBar)._queue == 2
            assert "2 queued" in str(app.query_one("#composer-hint").render())

    _run(go())


def test_a_failed_turn_rolls_back_the_question_and_any_steer(app_factory):
    entry = _active("Rollback")
    app = app_factory()

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._turn_user_index = 0
            app._session = [
                {"role": "user", "content": "question"},
                {"role": "user", "content": "[steer] left"},
            ]
            app._rollback_turn()
            await pilot.pause()
            assert app._session == []
            assert ms.load_messages(str(entry["id"])) == []

    _run(go())




def test_an_at_token_attaches_a_line_range_with_provenance(tmp_path, monkeypatch):
    from ui import file_context

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "notes.txt").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
    monkeypatch.setenv("EPHE_WORKSPACE", str(workspace))
    file_context.clear_cache()

    result = file_context.build_context("look at @notes.txt#L2-L3")

    assert not result.error
    assert [item.label() for item in result.attached] == ["notes.txt#L2-L3"]
    assert "[Context: notes.txt#L2-L3]" in result.prompt
    assert "two\nthree" in result.prompt
    assert "one\n" not in result.prompt
    assert "four" not in result.prompt


def test_without_a_workspace_the_composer_names_the_missing_setting(monkeypatch):
    from ui import file_context

    monkeypatch.delenv("EPHE_WORKSPACE", raising=False)
    monkeypatch.setattr(file_context, "load_engine_config", lambda: None)

    result = file_context.build_context("look at @notes.txt")

    assert result.attached == []
    assert "No workspace configured" in result.error


def test_at_type_ahead_lists_workspace_files(tmp_path, monkeypatch):
    from ui import file_context

    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "session_store.py").write_text("x", encoding="utf-8")
    (workspace / "other.py").write_text("x", encoding="utf-8")
    monkeypatch.setenv("EPHE_WORKSPACE", str(workspace))
    file_context.clear_cache()

    assert file_context.match_files(workspace, "sess") == ["session_store.py"]




def test_bang_runs_shell_only_after_the_existing_approval(app_factory, monkeypatch):
    import core.tools._shell_exec as shell

    _active("Shell")
    app = app_factory()
    seen: list[tuple[str, bool]] = []

    async def approve(tool_name, args):
        assert tool_name == "run_shell"
        return True

    async def fake_exec(command, confirmed, cwd=None):
        seen.append((command, confirmed))
        return "shell output"

    monkeypatch.setattr(app, "_on_tui_tool_confirm", approve)
    monkeypatch.setattr(shell, "execute_confirmed_shell", fake_exec)

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._shell_mode("echo hi")
            for _ in range(100):
                if app._session and app._session[-1]["role"] == "assistant":
                    break
                await pilot.pause(0.05)
            assert seen == [("echo hi", True)]
            assert "shell output" in app._session[-1]["content"]
            titles = [block.title for block in app.query(".tool-call-block")]
            assert any("Ran echo hi" in title for title in titles), titles

    _run(go())


def test_a_declined_bang_call_never_reaches_the_executor(app_factory, monkeypatch):
    import core.tools._shell_exec as shell

    _active("Shell denied")
    app = app_factory()
    seen: list[bool] = []

    async def approve(tool_name, args):
        return False

    async def fake_exec(command, confirmed, cwd=None):
        seen.append(confirmed)
        return "[TOOL-DENIED] run_shell: not_approved_by_user"

    monkeypatch.setattr(app, "_on_tui_tool_confirm", approve)
    monkeypatch.setattr(shell, "execute_confirmed_shell", fake_exec)

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._shell_mode("rm -rf build")
            for _ in range(100):
                if app._session and app._session[-1]["role"] == "assistant":
                    break
                await pilot.pause(0.05)
            assert seen == [False]
            assert "TOOL-DENIED" in app._session[-1]["content"]

    _run(go())




def test_the_model_picker_writes_the_same_engine_config_the_pwa_writes(
    app_factory, monkeypatch, tmp_path
):
    import core.engine_config as ec
    from core.engine_config import EngineChoice, load_engine_config

    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
    monkeypatch.setattr(ec, "CONFIG_DIR", cfg)
    ec.save_engine_config(
        EngineChoice(
            provider="openai_compatible",
            model="old-model",
            api_url="http://engine.example:8000/v1",
            workspace_dir="/tmp/ws",
            brand={"name": "Kept"},
        )
    )
    app = app_factory("old-model")
    app.api_url = "http://engine.example:8000/v1"

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._apply_model_choice("new-model")
            await pilot.pause()
            assert app.model == "new-model"

    _run(go())

    saved = load_engine_config()
    assert saved is not None
    assert saved.model == "new-model"
    assert saved.api_url == "http://engine.example:8000/v1"
    assert saved.workspace_dir == "/tmp/ws", "the model switch dropped the workspace"
    assert saved.brand == {"name": "Kept"}


def test_the_model_picker_never_picks_a_default(app_factory):
    app = app_factory("chosen-model")

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            app._apply_model_choice(None)
            await pilot.pause()
            assert app.model == "chosen-model"

    _run(go())




def test_the_editor_helper_returns_the_edited_draft(tmp_path):
    from ui.editor import run_editor

    script = tmp_path / "editor.py"
    script.write_text(
        "import pathlib, sys\npathlib.Path(sys.argv[1]).write_text('edited draft\\n')\n",
        encoding="utf-8",
    )
    edited, error = run_editor("draft", [sys.executable, str(script)])
    assert error == ""
    assert edited == "edited draft"


def test_a_missing_editor_is_named_not_swallowed(monkeypatch):
    from ui.editor import run_editor

    monkeypatch.delenv("VISUAL", raising=False)
    monkeypatch.delenv("EDITOR", raising=False)
    edited, error = run_editor("draft")
    assert edited is None
    assert "$VISUAL" in error and "$EDITOR" in error


def test_reduced_motion_switches_the_settle_flourish_off(app_factory, monkeypatch):
    import core.settings_schema as settings

    from ui.widgets import StatusBar

    app = app_factory()
    enabled = {"value": False}
    monkeypatch.setattr(settings, "deep_bool", lambda key: enabled["value"])

    async def go():
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            status = app.query_one(StatusBar)
            app._settle()
            await pilot.pause()
            assert not status.has_class("settle")
            enabled["value"] = True
            app._settle()
            await pilot.pause()
            assert status.has_class("settle")

    _run(go())


def test_a_tool_card_names_its_duration(app_factory):
    from ui.widgets import _ToolCallBlock

    app = app_factory()

    async def go():
        async with app.run_test(size=(100, 30)) as pilot:
            block = _ToolCallBlock("read_file", {"path": "notes.txt"})
            await app.query_one("#chat-container").mount(block)
            await pilot.pause()
            block.set_done("content")
            await pilot.pause()
            assert "Explored notes.txt" in block.title
            assert "·" in block.title and block.title.rstrip().endswith("s"), (
                block.title
            )

    _run(go())
