"""Capture the terminal surface in the six states Wave 5E names.

Real Textual screenshots of the shipped app: the compositor exports what it
painted, not a mock-up. The session store, config directory and workspace are
temporary, so a capture never reads or writes the operator's ~/.ephe.

    python scripts/tui_captures.py --out out/step6
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
from pathlib import Path

SIZES = ((80, 24), (140, 40))
STATES = ("idle", "streaming", "tool-card", "approval", "session-switcher", "error")


def _isolate(root: Path) -> None:
    sessions = root / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    config = root / "config"
    config.mkdir(parents=True, exist_ok=True)
    workspace = root / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "notes.txt").write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    os.environ["EPHE_SESSIONS_DIR"] = str(sessions)
    os.environ["EPHE_CONFIG_DIR"] = str(config)
    os.environ["EPHE_WORKSPACE"] = str(workspace)
    os.environ["EPHE_PROFILE_PATH"] = str(root / "profile.json")
    os.environ["EPHE_MEMORY_DIR"] = str(root / "chroma")
    os.environ["EPHE_FEEDBACK_DIR"] = str(root / "feedback")


def _seed_sessions() -> None:
    from core import multi_session as ms

    first = ms.create_session("Terminal pass")
    ms.save_messages(
        str(first["id"]),
        [
            {"role": "user", "content": "Check the release notes"},
            {
                "role": "assistant",
                "content": "The notes name the engine and the change set.",
            },
        ],
    )
    ms.switch_to(str(first["id"]))
    ms.create_session("Settings survey")
    ms.create_session("Bench follow-up")


async def _prepare(app, state: str, pilot) -> None:
    from ui.widgets import ChatView, StatusBar

    chat = app.query_one(ChatView)
    status = app.query_one(StatusBar)
    await pilot.pause()
    status.post_message(
        StatusBar.SetStatus(
            connected=True,
            model="capture-model",
            provider="OpenAI-compatible API · engine.example:8000",
        )
    )

    if state == "streaming":
        chat.clear_display()
        app._set_run_state("working")
        status.post_message(StatusBar.SetStreaming(True))
        chat.post_message(ChatView.BeginAssistantMessage())
        chat.post_message(
            ChatView.AppendThinking("Checking the session store and the engine config.")
        )
        chat.post_message(
            ChatView.AppendChunk(
                "The terminal reads the queue at each round boundary and "
            )
        )
        status.post_message(StatusBar.SetQueue(1))
    elif state == "tool-card":
        chat.clear_display()
        app._set_run_state("done")
        chat.post_message(ChatView.AddUserMessage("Update the release note"))
        chat.post_message(ChatView.BeginAssistantMessage())
        chat.post_message(ChatView.ToolCallStart("read_file", {"path": "notes.txt"}))
        chat.post_message(
            ChatView.ToolCallDone(
                "read_file",
                "--- a/notes.txt\n+++ b/notes.txt\n@@ -1,3 +1,3 @@\n alpha\n-beta\n+beta, revised\n gamma",
            )
        )
        chat.post_message(ChatView.AppendChunk("Updated the second line."))
        chat.post_message(ChatView.FinalizeAssistantMessage())
    elif state == "approval":
        app._set_run_state("waiting")
        await chat.show_confirm_prompt(
            "Run shell command?  git status --short", "run_shell"
        )
    elif state == "session-switcher":
        app.action_sessions()
        await pilot.pause()
    elif state == "error":
        app._set_run_state("offline")
        status.post_message(StatusBar.SetError("Engine not reachable"))
        chat.post_message(
            ChatView.AddSystemMessage(
                "⚠  Engine not reachable: http://engine.example:8000/v1\n"
                "   Check the service behind that URL, then the configured\n"
                "   endpoint (engine.json → api_url).",
                style="error-msg",
            )
        )
    await pilot.pause()
    if state in ("streaming", "tool-card"):
        container = chat.query_one("#chat-container")
        for _ in range(4):
            container.scroll_end(animate=False)
            await pilot.pause()


async def _capture(size: tuple[int, int], out: Path) -> list[Path]:
    from ui.app import EpheApp

    written: list[Path] = []

    async def noop() -> None:
        return None

    for state in STATES:
        # A fresh mount per state: one screenshot must not carry another
        # state's modal or transcript.
        app = EpheApp(model="capture-model", api_url="http://engine.example:8000/v1")
        setattr(app, "_async_check_connection", noop)
        setattr(app, "_async_init_mcp", noop)
        async with app.run_test(size=size) as pilot:
            await _prepare(app, state, pilot)
            name = f"{size[0]}x{size[1]}-{state}.svg"
            app.save_screenshot(name, path=str(out))
            written.append(out / name)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="directory for the captures")
    args = parser.parse_args(argv)
    out = Path(args.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="ephe-tui-capture-") as root:
        _isolate(Path(root))
        _seed_sessions()
        for size in SIZES:
            for svg in asyncio.run(_capture(size, out)):
                print(svg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
