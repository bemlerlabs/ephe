"""
◑ Ephe – Widgets

The transcript side of the terminal:

    ChatView          – Scrollable chat display with structured agent messages
    AgentMessageCard  – one assistant turn: thinking (collapsible) + tool calls + markdown answer
    ConfirmPrompt     – the in-terminal approval for a mutating tool
    StatusBar         – live status: engine · model · context · session

Streaming architecture (2026-08-22, "Structured Agent Message"):
    - ChatView keeps all turn containers (#chat-container, vertical, scrollbar)
    - An assistant turn is one AgentMessageCard:
        * 🧠 Thinking: collapsible, streamed live, auto-collapses after finalize
        * 🔧 Tool calls: one collapsible per call (▶ pending → ✅ done), full input/output
        * Answer: rendered as markdown (not flat Rich text)
    - System/user messages stay Static blocks
    That replaced the flat RichLog design: you now see WHAT the AI thinks and does.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message as TextualMessage
from textual.widget import Widget
from textual.widgets import Collapsible, Input, Static
from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.markup import escape as markup_escape
from rich.text import Text

from core.ask_block import split_block
from ui.context_meter import ContextUsage, meter_text
from ui.palette import ACCENT, DIM, ERROR, OK, TEXT, WARN

# Diff lines keep the two signal tokens the palette already measured: additions
# in the connected green, deletions in the failure red. Both hold their ratio on
# the ink ground (7.02:1 and 4.94:1); tests/test_tui_black_forest.py pins them.
DIFF_ADD = OK
DIFF_DEL = ERROR


# ===========================================================================
# Tool phrasings — Ephe agent timeline convention
# ===========================================================================
# The TUI does NOT render tool calls as "▶/✅ tool", but as clean verb
# phrasings: live "Exploring… / Running…", done "Explored X / Ran Y".
# It even merges several calls of one category into a single line.


def _format_elapsed(seconds: float) -> str:
    """Time format: '5s' / '1m 5s' / '2h 3m'."""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def _tool_category(name: str) -> str:
    """Category of a tool: run/explore/edit/other (Ephe timeline convention)."""
    run = {
        "run_shell", "run_tests", "execute_code", "spawn_swarm", "terminate_self",
    }
    edit = {
        "create_pdf", "create_svg", "create_pptx_deck", "create_pitch_deck",
        "edit_pptx_template", "create_source_notebook", "generate_chart",
        "edit_file",
    }
    explore = {
        "read_file", "file_search", "web_search", "list_directory",
        "analyze_image", "analyze_project", "discover_projects",
        "query_source_notebook", "export_source_brief", "take_screenshot",
        "vision_click", "vision_type", "browser_go", "browser_screenshot",
        "browser_click", "browser_type", "browser_press",
    }
    if name in run or name.startswith("browser_") or name.startswith("vision_"):
        return "run" if name in run else "explore"
    if name in edit:
        return "edit"
    if name in explore or name.startswith("browser_") or name.startswith("vision_"):
        return "explore"
    return "other"


_TOOL_COPY = {
    "delegate": {"present": "Delegating", "past": "Delegated"},
    "edit": {"present": "Editing", "past": "Edited"},
    "explore": {"present": "Exploring", "past": "Explored"},
    "other": {"present": "Using", "past": "Used"},
    "run": {"present": "Running", "past": "Ran"},
}

#: A tool whose row would otherwise read "Used x.md" when it wrote the file.
_TOOL_VERBS = {
    "write_file": {"present": "Writing", "past": "Wrote"},
}


def _tool_verb_present(name: str) -> str:
    return _TOOL_VERBS.get(name, _TOOL_COPY[_tool_category(name)])["present"]


def _tool_verb_past(name: str) -> str:
    return _TOOL_VERBS.get(name, _TOOL_COPY[_tool_category(name)])["past"]


def _tool_target(name: str, args: dict) -> str:
    """What the tool call acts on — named as in the header (Ephe convention)."""
    if _tool_category(name) == "run":
        cmd = args.get("command") or args.get("code") or ""
        cmd = str(cmd).strip().splitlines()[0] if str(cmd).strip() else ""
        return cmd[:44] + "…" if len(cmd) > 44 else cmd
    path = args.get("path") or args.get("file") or args.get("filepath")
    if path:
        return str(path).rsplit("/", 1)[-1]
    q = args.get("query") or args.get("url")
    return str(q)[:40] if q else ""


class _ToolCallBlock(Collapsible):
    """
    One tool call as a collapsible in the Ephe agent style:
        live : "Exploring…" / "Running…" / "Editing…"   (args in the body)
        done : "Explored foo.txt" / "Ran ls -la"         (output in the body)

    No ▶/✅ emojis — verb phrasing + target, exactly like the Ephe chat interface.
    """

    _tool_name: str
    _args: dict
    _output: Static | None

    def __init__(self, name: str, args: dict) -> None:
        # Careful: `self._name` is an INTERNAL widget attribute (Textual) —
        # hence `_tool_name`, otherwise super().__init__() overwrites the value.
        self._tool_name = name
        self._args = args
        self._started = time.monotonic()
        self._args_static = Static("", id=f"tool-args-{id(self)}", markup=True)
        # Live title: present-tense verb (Ephe convention)
        super().__init__(self._args_static, title=f"{_tool_verb_present(name)}…", collapsed=True)
        self.add_class("tool-call-block")
        self.add_class("tool-pending")
        target = _tool_target(name, args)
        if target:
            self._args_static.update(
                Text.assemble(
                    (_tool_verb_present(name).lower(), DIM),
                    "  " + target,
                )
            )
        else:
            self._args_static.update(f"[{DIM}]{_tool_verb_present(name).lower()}[/{DIM}]")
        self._output: Static | None = None

    def set_waiting(self) -> None:
        """The approval prompt is open: nothing runs until a person answers."""
        target = _tool_target(self._tool_name, self._args)
        self.title = f"Waiting for approval · {target}".rstrip(" ·")
        self.add_class("tool-waiting")

    def set_running(self) -> None:
        """Approved: the clock starts here, so the wait is not billed as work."""
        self._started = time.monotonic()
        self.remove_class("tool-waiting")
        self.title = f"{_tool_verb_present(self._tool_name)}…"

    def set_refused(self, result: str) -> None:
        """A declined call is never shown as one that ran."""
        target = _tool_target(self._tool_name, self._args)
        self.title = f"Declined {target}".rstrip()
        self.remove_class("tool-pending")
        self.remove_class("tool-waiting")
        self.add_class("tool-refused")
        self._output = Static("", id=f"tool-out-{id(self)}", markup=True)
        self._output.add_class("tool-output")
        reason = str(result or "").replace("[TOOL-DENIED]", "").strip()
        self._output.update(Text.assemble(("not executed\n", DIM), reason))
        self.compose_add_child(self._output)
        self.refresh()

    def set_done(self, result: str) -> None:
        """Tool done: past-tense verb + target + duration, output in the body."""
        target = _tool_target(self._tool_name, self._args)
        past = _tool_verb_past(self._tool_name)
        elapsed = _format_elapsed(time.monotonic() - self._started)
        title = f"{past} {target}".rstrip() if target else past
        self.title = f"{title} · {elapsed}"
        self.remove_class("tool-pending")
        self._output = Static("", id=f"tool-out-{id(self)}", markup=True)
        self._output.add_class("tool-output")
        preview = result if len(result) <= 4000 else result[:4000] + "\n[… truncated]"
        if _looks_like_diff(preview):
            self._output.update(Group(Text("output", style=DIM), _diff_lines(preview)))
        else:
            # A Text carries styles as spans and never reaches a markup parser.
            # Tool output is arbitrary text, and both rich's and Textual's escape
            # leave bracket shapes that Textual's tokenizer still reads as a tag —
            # one such result crashed the block.
            self._output.update(Text.assemble(("output\n", DIM), preview))
        self.compose_add_child(self._output)
        self.refresh()


def _looks_like_diff(text: str) -> bool:
    return any(
        line.startswith(("@@ ", "+++ ", "--- "))
        for line in text.splitlines()[:8]
    )


def _diff_lines(text: str) -> Group:
    """Colour a unified diff by line role; the default ink for context lines."""
    rendered: list[Text] = []
    for line in text.splitlines():
        if line.startswith(("+++ ", "--- ")):
            style = DIM
        elif line.startswith("+"):
            style = DIFF_ADD
        elif line.startswith("-"):
            style = DIFF_DEL
        elif line.startswith("@@"):
            style = ACCENT
        else:
            style = TEXT
        rendered.append(Text(line, style=style))
    return Group(*rendered)


class AgentMessageCard(Widget):
    """
    One assistant turn as a container:
        [🧠 Thinking – collapsible, live]
        [🔧 Tool call blocks – one collapsible each]
        [Assistant – markdown answer (live + final)]

    Phases:
        begin    → the card gets mounted (thinking block open, '…thinking')
        thinking → tokens flow into the thinking block
        tool_start / tool_done → tool call blocks
        chunk    → answer accumulation (live view: '▌')
        finalize → markdown rendering, thinking auto-collapsed, spinner off
    """

    # ── Textual Messages ────────────────────────────────────────────────────

    class Begin(TextualMessage):
        pass

    class ThinkingChunk(TextualMessage):
        def __init__(self, chunk: str) -> None:
            super().__init__()
            self.chunk = chunk

    class ToolStart(TextualMessage):
        def __init__(self, name: str, args: dict) -> None:
            super().__init__()
            self.name = name
            self.args = args

    class ToolDone(TextualMessage):
        def __init__(self, name: str, result: str, refused: bool = False) -> None:
            super().__init__()
            self.name = name
            self.result = result
            self.refused = refused

    class ToolWaiting(TextualMessage):
        def __init__(self, name: str) -> None:
            super().__init__()
            self.name = name

    class ToolResume(TextualMessage):
        def __init__(self, name: str) -> None:
            super().__init__()
            self.name = name

    class AnswerChunk(TextualMessage):
        def __init__(self, chunk: str) -> None:
            super().__init__()
            self.chunk = chunk

    class ResetAnswer(TextualMessage):
        """Revision signal: empty the answer accumulator before iteration 2 streams."""

        pass

    class Finalize(TextualMessage):
        pass

    class SetPhase(TextualMessage):
        """Intermediate phases of the agent (loading/retrying/tool round n…)."""

        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    # ── State ───────────────────────────────────────────────────────────────

    _thinking_acc: str
    _answer_acc: str
    _thinking_started: bool
    _thinking_t0: float
    _blocks: list[_ToolCallBlock]
    _streaming_answer: bool
    _round_break: bool

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.add_class("agent-message-card")
        self._thinking_acc = ""
        self._answer_acc = ""
        self._thinking_started = False
        self._thinking_t0 = 0.0
        self._blocks = []
        self._streaming_answer = False
        self._round_break = False

    DEFAULT_CSS = """
    AgentMessageCard {
        layout: vertical;
        width: 1fr;
        height: auto;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        # The thinking block starts HIDDEN — it appears only when the model
        # actually sends thinking tokens (Ephe behaviour). An empty
        # "Thinking…" box would otherwise be orphaned (e.g. with models
        # without a reasoning phase such as qwen3.8-flash-next).
        self._thinking_block = Collapsible(
            Static("", id="thinking-body", markup=True), title="Thinking…", collapsed=False
        )
        self._thinking_block.add_class("thinking-block")
        self._thinking_block.visible = False
        yield self._thinking_block
        self._tool_area = Vertical(id="tool-area", classes="tool-area")
        yield self._tool_area
        # ONE status line (Ephe standard): updated IN-PLACE,
        # never stacked. Disappears as soon as the answer streams.
        self._phase_line = Static("", id="phase-line", markup=True)
        self._phase_line.add_class("phase-line")
        self._phase_line.visible = False
        yield self._phase_line
        self._answer_live = Static("", id="answer-live", markup=True)
        self._answer_md = Static("", id="answer-md", markup=False)
        self._answer_md.visible = False
        yield self._answer_live
        yield self._answer_md

    # ── Message Handlers ────────────────────────────────────────────────────

    def on_agent_message_card_begin(self, event: "AgentMessageCard.Begin") -> None:
        """Card active. Thinking block + status line in the idle state."""
        self._thinking_block = self.query_one(".thinking-block", Collapsible)
        self._thinking_block.visible = False

    def on_agent_message_card_thinking_chunk(self, event: "AgentMessageCard.ThinkingChunk") -> None:
        if not self._thinking_started:
            self._thinking_started = True
            self._thinking_t0 = time.monotonic()
            self._thinking_block = self.query_one(".thinking-block", Collapsible)
            self._thinking_block.title = "Thinking"
            self._thinking_block.visible = True
            self._phase_line.visible = False
        self._thinking_acc += event.chunk
        body = self.query_one("#thinking-body", Static)
        tail = self._thinking_acc[-2000:]  # Cap: rendering cost, the full log stays in the model
        body.update(Text(markup_escape(tail), style=DIM))

    def on_agent_message_card_tool_start(self, event: "AgentMessageCard.ToolStart") -> None:
        block = _ToolCallBlock(event.name, event.args)
        self._blocks.append(block)
        self._tool_area.mount(block)
        self._round_break = True

    def on_agent_message_card_tool_done(self, event: "AgentMessageCard.ToolDone") -> None:
        """Close the last still-open tool block (FIFO over the 'tool-pending' class)."""
        for block in reversed(self._blocks):
            if block.has_class("tool-pending"):
                if event.refused:
                    block.set_refused(event.result)
                else:
                    block.set_done(event.result)
                break

    def on_agent_message_card_tool_waiting(self, event: "AgentMessageCard.ToolWaiting") -> None:
        for block in reversed(self._blocks):
            if block.has_class("tool-pending"):
                block.set_waiting()
                break

    def on_agent_message_card_tool_resume(self, event: "AgentMessageCard.ToolResume") -> None:
        for block in reversed(self._blocks):
            if block.has_class("tool-waiting"):
                block.set_running()
                break

    def on_agent_message_card_answer_chunk(self, event: "AgentMessageCard.AnswerChunk") -> None:
        if self._round_break and self._answer_acc:
            self._answer_acc += "\n\n"
        self._round_break = False
        self._answer_acc += event.chunk
        if not self._streaming_answer:
            self._streaming_answer = True
            self._answer_live.visible = True
            self._answer_md.visible = False
            # The status line is redundant once the content streams
            self._phase_line.visible = False
        self._answer_live.update(
            Text.assemble(
                ("Assistant\n", f"bold {ACCENT}"),
                (self._answer_acc + "▌", TEXT),
            )
        )

    def on_agent_message_card_reset_answer(self, event: "AgentMessageCard.ResetAnswer") -> None:
        """Revision reset: empty the answer accumulator + the live block.

        Iteration 1 answered insufficiently; reflect() demands a revision.
        The new (improved) answer streams anew from here — without this reset
        iteration 2 would append to iteration 1 and the user would see the
        answer twice."""
        self._answer_acc = ""
        self._streaming_answer = False
        self._round_break = False
        self._answer_live.update("")
        self._answer_live.visible = False

    def on_agent_message_card_set_phase(self, event: "AgentMessageCard.SetPhase") -> None:
        """Phase hint in ONE line, updated in place (Ephe standard).

        No stacking: the current phase replaces the previous one; as soon as
        thinking tokens or the answer flow, the line disappears."""
        if self._streaming_answer or self._thinking_started:
            return
        self._phase_line = self.query_one("#phase-line", Static)
        self._phase_line.update(f"[italic {DIM}]{event.text}[/italic {DIM}]")
        self._phase_line.visible = True

    def on_agent_message_card_finalize(self, event: "AgentMessageCard.Finalize") -> None:
        # Thinking: collapse, visible only if it had content.
        # Ephe labels: live "Thinking", done "Thought for 3s" / "Thought briefly".
        thinking = self.query_one(".thinking-block", Collapsible)
        if self._thinking_started:
            thinking.collapsed = True
            dur = time.monotonic() - self._thinking_t0
            if dur < 1:
                thinking.title = "Thought briefly"
            else:
                thinking.title = f"Thought for {_format_elapsed(dur)}"
        else:
            thinking.visible = False
        # Status line: done is done — get rid of it
        self._phase_line.visible = False
        # Live text → markdown-rendered final answer
        if self._answer_acc:
            # The block convention (finding #66): a question the model wrote as JSON is
            # rendered as a card and leaves the answer text. A block this reader cannot
            # turn into a question stays in the text — showing nothing would be the
            # quieter loss.
            cleaned, spec = split_block(self._answer_acc)
            self._answer_md = self.query_one("#answer-md", Static)
            self._answer_md.update(
                Group(
                    Text("Assistant", style=f"bold {ACCENT}"),
                    Markdown(cleaned),
                )
            )
            self._answer_md.visible = True
            if spec is not None:
                self.post_message(ChatView.AskRequested(spec))
        live = self.query_one("#answer-live", Static)
        live.visible = False
        live.update("")
        self._streaming_answer = False


# ===========================================================================
# ChatView
# ===========================================================================


class ChatView(Widget):
    """
    Scrollable chat area with structured agent messages.

    - User messages: Static block (green 'You' label)
    - System messages: Static block (style-dependent)
    - Assistant turns: AgentMessageCard (thinking + tool calls + markdown)

    Every element lands in one #chat-container (Vertical, scrollbar).
    """

    DEFAULT_CSS = """
    ChatView {
        layout: vertical;
        height: 1fr;
    }
    #chat-container {
        layout: vertical;
        height: 1fr;
        width: 1fr;
        overflow-y: auto;
    }
    """

    # ── Textual Messages (the older app API stays compatible) ────────────────

    class AddUserMessage(TextualMessage):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    class AddSystemMessage(TextualMessage):
        def __init__(self, text: str, style: str = "system-msg") -> None:
            super().__init__()
            self.text = text
            self.style = style

    class AddSystemVisual(TextualMessage):
        """A system block handed over as a renderable.

        Text carries its styles as spans and never meets a markup parser, which is
        what a block built from a user's own session title has to be. ``ident``
        names the block for a later handler; the greeting uses it to retire
        itself as soon as the first message arrives."""

        def __init__(self, visual: RenderableType, ident: str = "") -> None:
            super().__init__()
            self.visual = visual
            self.ident = ident

    class BeginAssistantMessage(TextualMessage):
        pass

    class AppendChunk(TextualMessage):
        def __init__(self, chunk: str) -> None:
            super().__init__()
            self.chunk = chunk

    class AppendThinking(TextualMessage):
        def __init__(self, chunk: str) -> None:
            super().__init__()
            self.chunk = chunk

    class ToolCallStart(TextualMessage):
        def __init__(self, name: str, args: dict) -> None:
            super().__init__()
            self.name = name
            self.args = args

    class ToolCallDone(TextualMessage):
        def __init__(self, name: str, result: str) -> None:
            super().__init__()
            self.name = name
            self.result = result

    class ToolCallWaiting(TextualMessage):
        """The confirmation prompt opened; the tool has not started."""

        def __init__(self, name: str) -> None:
            super().__init__()
            self.name = name

    class ToolCallResume(TextualMessage):
        """The prompt was answered with yes; execution starts now."""

        def __init__(self, name: str) -> None:
            super().__init__()
            self.name = name

    class AskRequested(TextualMessage):
        """A finished turn ended on the block convention: the question needs its card.

        The run is no longer waiting, so the answer travels as the next message (the
        `ask_user` tool path resolves the waiting call instead).
        """

        def __init__(self, spec: dict) -> None:
            super().__init__()
            self.spec = spec

    class SetPhase(TextualMessage):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    class FinalizeAssistantMessage(TextualMessage):
        pass

    class ResetAnswer(TextualMessage):
        """Revision signal: the active card empties its answer (accumulator + live
        block) before the improved iteration 2 streams anew (the PWA 'revision'
        event in the TUI)."""

        pass

    # ── State ───────────────────────────────────────────────────────────────

    _active_card: AgentMessageCard | None

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._active_card = None

    def compose(self) -> ComposeResult:
        yield Vertical(id="chat-container")

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _container(self) -> Vertical:
        return self.query_one("#chat-container", Vertical)

    def _add_static_block(self, markup: str) -> None:
        container = self._container()
        anchored = container.is_vertical_scroll_end
        block = Static(markup, markup=True)
        block.add_class("static-block")
        container.mount(block)
        if anchored:
            self.call_after_refresh(container.scroll_end, animate=False)

    # ── Message Handlers ────────────────────────────────────────────────────

    def on_chat_view_add_user_message(self, event: "ChatView.AddUserMessage") -> None:
        # The greeting describes a session with nothing in it yet. The first
        # message makes that untrue, and leaving it above the conversation put a
        # stale count and a key legend in front of every turn.
        for greeting in self.query("#welcome-card"):
            greeting.remove()
        text = event.text.replace("[", "\\[").replace("]", "\\]")
        self._add_static_block(f"[bold {ACCENT}]You[/bold {ACCENT}]\n[{TEXT}]{text}[/{TEXT}]")

    def on_chat_view_add_system_message(self, event: "ChatView.AddSystemMessage") -> None:
        style_map = {
            "welcome": f"{DIM} italic",
            "system-msg": DIM,
            "error-msg": f"bold {ERROR}",
            "fallback-hint": f"{DIM} italic",
        }
        rich_style = style_map.get(event.style, DIM)
        # event.text may itself contain markup (App uses [bold …])
        self._add_static_block(f"[{rich_style}]{event.text}[/{rich_style}]")

    def on_chat_view_add_system_visual(self, event: "ChatView.AddSystemVisual") -> None:
        container = self._container()
        anchored = container.is_vertical_scroll_end
        block = Static(event.visual)
        block.add_class("static-block")
        if event.ident:
            block.id = event.ident
        container.mount(block)
        if anchored:
            self.call_after_refresh(container.scroll_end, animate=False)

    def on_chat_view_begin_assistant_message(self, event: "ChatView.BeginAssistantMessage") -> None:
        container = self._container()
        anchored = container.is_vertical_scroll_end
        card = AgentMessageCard()
        self._active_card = card
        container.mount(card)
        card.post_message(AgentMessageCard.Begin())
        if anchored:
            self.call_after_refresh(container.scroll_end, animate=False)

    def on_chat_view_append_chunk(self, event: "ChatView.AppendChunk") -> None:
        if self._active_card is not None:
            self._active_card.post_message(AgentMessageCard.AnswerChunk(event.chunk))

    def on_chat_view_append_thinking(self, event: "ChatView.AppendThinking") -> None:
        if self._active_card is not None:
            self._active_card.post_message(AgentMessageCard.ThinkingChunk(event.chunk))

    def on_chat_view_tool_call_start(self, event: "ChatView.ToolCallStart") -> None:
        if self._active_card is not None:
            self._active_card.post_message(AgentMessageCard.ToolStart(event.name, event.args))

    def on_chat_view_tool_call_done(self, event: "ChatView.ToolCallDone") -> None:
        if self._active_card is not None:
            refused = str(event.result or "").startswith("[TOOL-DENIED]")
            self._active_card.post_message(
                AgentMessageCard.ToolDone(event.name, event.result, refused=refused)
            )

    def on_chat_view_tool_call_waiting(self, event: "ChatView.ToolCallWaiting") -> None:
        if self._active_card is not None:
            self._active_card.post_message(AgentMessageCard.ToolWaiting(event.name))

    def on_chat_view_tool_call_resume(self, event: "ChatView.ToolCallResume") -> None:
        if self._active_card is not None:
            self._active_card.post_message(AgentMessageCard.ToolResume(event.name))

    def on_chat_view_set_phase(self, event: "ChatView.SetPhase") -> None:
        if self._active_card is not None:
            self._active_card.post_message(AgentMessageCard.SetPhase(event.text))
        else:
            # No active turn (e.g. an error before the card mounts): show as a system flash.
            self._add_static_block(f"[italic {DIM}]⏳ {event.text}[/italic {DIM}]")

    def on_chat_view_reset_answer(self, event: "ChatView.ResetAnswer") -> None:
        if self._active_card is not None:
            self._active_card.post_message(AgentMessageCard.ResetAnswer())

    def on_chat_view_finalize_assistant_message(
        self, event: "ChatView.FinalizeAssistantMessage"
    ) -> None:
        if self._active_card is not None:
            self._active_card.post_message(AgentMessageCard.Finalize())
        self._active_card = None

    # ── Public API ──────────────────────────────────────────────────────────

    _confirm_prompt: ConfirmPrompt | None

    async def show_confirm_prompt(self, question: str, tool_name: str) -> ConfirmPrompt:
        """Create the in-TUI confirmation prompt for a mutating tool.

        The worker waits on ``prompt.answered`` (asyncio.Event) and reads the
        result directly from the widget (``prompt.result``). The mount is awaited
        so that ``on_mount`` (focus) is guaranteed to run before the first keystroke.
        """
        container = self._container()
        prompt = ConfirmPrompt(question, tool_name)
        await container.mount(prompt)
        self._confirm_prompt = prompt
        # A prompt the reader cannot see is a prompt that never gets an answer:
        # the worker holds the turn for 300 s. Streaming keeps the reader's place,
        # this one does not — it is the last thing in the transcript and it asks
        # for a decision now.
        self.call_after_refresh(container.scroll_end, animate=False)
        return prompt

    _ask_prompt: "AskPrompt | None" = None

    async def show_ask_prompt(self, spec: dict, *, from_tool: bool) -> "AskPrompt":
        """Mount the answer field for a question the run asked (finding #66).

        Same contract as the confirmation above: the worker waits on `prompt.answered`
        and reads `prompt.result`. It mounts at the end of the transcript and scrolls
        into view, because a question the reader cannot see is a question that times out.
        """
        container = self._container()
        prompt = AskPrompt(spec, from_tool=from_tool)
        await container.mount(prompt)
        self._ask_prompt = prompt
        self.call_after_refresh(container.scroll_end, animate=False)
        return prompt

    async def on_chat_view_ask_requested(self, event: "ChatView.AskRequested") -> None:
        await self.show_ask_prompt(event.spec, from_tool=False)

    def on_resize(self, event: object) -> None:
        """A resize keeps the transcript where the reader left it."""
        container = self._container()
        if container.is_vertical_scroll_end:
            self.call_after_refresh(container.scroll_end, animate=False)

    def clear_display(self) -> None:
        """Ctrl+L: clear the display. Session data stays untouched."""
        container = self._container()
        container.remove_children()
        self._active_card = None
        self._confirm_prompt = None


# ===========================================================================
# ConfirmPrompt
# ===========================================================================


class ConfirmPrompt(Widget):
    """
    In-TUI confirmation prompt for mutating tools (state-of-the-art standard).

    Instead of remembering CLI flags, the user confirms the tool call directly in
    the session — the way leading coding agents do it:

        Run 'rm -rf build'?  y=yes · n=no · a=always (session)

    - `y` → approved once
    - `n` → rejected
    - `a` → approve this tool for the whole session, always

    The worker waits on `await prompt.answered` (asyncio.Event).
    """

    # A plain Widget cannot hold focus, and Textual delivers key events only to
    # the focused widget — without this the y/n/a never reaches on_key.
    can_focus = True

    DEFAULT_CSS = f"""
    ConfirmPrompt {{
        height: 5;
        width: 100%;
        padding: 0 1;
        border: round {ERROR};
    }}
    """

    # ── Message (to the App) ─────────────────────────────────────────────────

    class Answered(TextualMessage):
        """Posted to the App as soon as the user answers.

        - answer: True/False
        - always: True for 'a' (approve the tool for the whole session)
        - tool_name: the tool concerned (for the session allowlist)
        """

        def __init__(self, answer: bool, always: bool, tool_name: str) -> None:
            super().__init__()
            self.answer = answer
            self.always = always
            self.tool_name = tool_name

    # ── State ───────────────────────────────────────────────────────────────

    _question: str
    _tool_name: str
    _answered: bool
    result: tuple[bool, bool]  # (approved, always) — set synchronously in on_key

    def __init__(self, question: str, tool_name: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._question = question
        self._tool_name = tool_name
        self._answered = False
        self.result = (False, False)
        self.answered = asyncio.Event()

    # The box is five rows: two borders, the question, the legend, one spare. A
    # question that wraps past its row pushes the legend out of the box, and a
    # prompt without its keys looks like a frozen screen.
    QUESTION_MAX_CHARS = 92

    def compose(self) -> ComposeResult:
        question = " ".join(self._question.split())
        if len(question) > self.QUESTION_MAX_CHARS:
            question = question[: self.QUESTION_MAX_CHARS - 1].rstrip() + "…"
        yield Static(
            Text.assemble(
                (f"⚠  {question}\n", f"bold {ERROR}"),
                ("y", DIM),
                "=Yes  ",
                ("n", DIM),
                "=No  ",
                ("a", ACCENT),
                "=Always (this tool, this session)",
            ),
            id="confirm-question",
        )

    def on_mount(self) -> None:
        self.focus()

    def on_key(self, event: object) -> None:
        from textual.events import Key

        if not isinstance(event, Key) or self._answered:
            return
        key = event.key
        event.stop()
        event.prevent_default()
        if key in ("y", "Y"):
            self._finish(True, False)
        elif key in ("a", "A"):
            self._finish(True, True)
        elif key in ("n", "N", "escape", "enter"):
            self._finish(False, False)

    def _finish(self, answer: bool, always: bool) -> None:
        self._answered = True
        self.result = (answer, always)
        self.post_message(ConfirmPrompt.Answered(answer, always, self._tool_name))
        self.answered.set()
        self.remove()


class AskPrompt(Widget):
    """The answer field for a question the run asked (finding #66).

    The browser has had this since the card in `assistantExtras.tsx`; the terminal printed the
    block's JSON, so the reader met a question in its wire format:

        Which report should the summary lead with?
          1. Revenue first  (recommended)
          2. Churn first
        1-2 · or type your own answer · Enter sends · Esc leaves it unanswered

    A number picks the option, anything else is the reader's own sentence, and several numbers
    ("1,3") answer a multi-select. The card answers in two directions at once: `answered`
    resolves the tool call that is still waiting inside the run, and `Answered` lets the app
    send the same text as the next message when the question came from a finished turn.
    """

    can_focus = True

    DEFAULT_CSS = f"""
    AskPrompt {{
        height: auto;
        width: 100%;
        padding: 0 1;
        border: round {ACCENT};
    }}
    AskPrompt > Input {{
        width: 1fr;
    }}
    """

    class Answered(TextualMessage):
        """Posted when the reader answers. `from_tool` marks the waiting run."""

        def __init__(self, text: str, from_tool: bool) -> None:
            super().__init__()
            self.text = text
            self.from_tool = from_tool

    def __init__(self, spec: dict, *, from_tool: bool = False, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._spec = spec
        self._from_tool = from_tool
        self._answered = False
        self.result = ""
        self.answered = asyncio.Event()

    # ── Rendering ────────────────────────────────────────────────────────────

    def _labels(self) -> list[str]:
        return [str(option.get("label") or "") for option in self._spec.get("options") or []]

    def _body(self) -> Text:
        out = Text()
        out.append("?  ", style=f"bold {ACCENT}")
        out.append(" ".join(str(self._spec.get("question") or "").split()), style=f"bold {TEXT}")
        out.append("\n")
        labels = self._labels()
        recommended = str(self._spec.get("recommendation") or "")
        for index, label in enumerate(labels, start=1):
            out.append(f"  {index}. ", style=DIM)
            out.append(label)
            if recommended and label == recommended:
                out.append("  (recommended)", style=f"italic {OK}")
            description = (self._spec.get("options") or [])[index - 1].get("description")
            if description:
                out.append(f" — {description}", style=DIM)
            out.append("\n")
        if self._spec.get("default"):
            out.append("  if nobody answers: ", style=DIM)
            out.append(str(self._spec["default"]))
            out.append("\n")
        out.append(
            "  ".join(
                filter(
                    None,
                    [
                        f"1-{len(labels)}" if labels else "",
                        "or type an answer",
                        "Enter sends",
                        "Esc leaves it unanswered",
                    ],
                )
            )
            + (" · multi: 1,3" if self._spec.get("multi_select") else ""),
            style=DIM,
        )
        return out

    def compose(self) -> ComposeResult:
        yield Static(self._body(), id="ask-body")
        yield Input(placeholder="your answer", id="ask-input")

    def on_mount(self) -> None:
        # The field, not the card, takes the keystrokes: the reader types an answer or a
        # number, and Esc still reaches the card through the bubbling key event.
        self.query_one("#ask-input", Input).focus()

    # ── The answer ───────────────────────────────────────────────────────────

    def _resolve(self, raw: str) -> str:
        """A number picks an option; anything else is the reader's own sentence."""
        value = (raw or "").strip()
        if not value:
            return ""
        labels = self._labels()
        picked = {part.strip() for part in re.split(r"[,+]| and ", value) if part.strip()}
        digits = {str(index) for index in range(1, len(labels) + 1)}
        if picked and picked <= digits:
            return ", ".join(labels[int(part) - 1] for part in sorted(picked, key=int))
        return value

    def on_input_submitted(self, event: "Input.Submitted") -> None:
        self._finish(self._resolve(event.value))

    def on_key(self, event: object) -> None:
        from textual.events import Key

        if not isinstance(event, Key) or self._answered:
            return
        if event.key == "escape":
            event.stop()
            self._finish("")

    def _finish(self, text: str) -> None:
        if self._answered:
            return
        self._answered = True
        self.result = text
        self.post_message(AskPrompt.Answered(text, self._from_tool))
        self.answered.set()
        self.remove()

    def dismiss(self) -> None:
        """The run stopped waiting (its timeout came first): the card goes, unanswered."""
        if self._answered:
            return
        self._answered = True
        self.remove()


# ===========================================================================
# StatusBar
# ===========================================================================


def agents_label(active: int, total: int) -> str:
    """K3: the footer's swarm chip — empty until a wave actually spawned."""
    if total <= 0:
        return ""
    return f"◈ {active}/{total}"


def seal_label(problems: "list[str] | None") -> str:
    """K3: the audit chain's own state; empty until it was checked once."""
    if problems is None:
        return ""
    return "⛓ ok" if not problems else f"⛓ {len(problems)} broken"


class StatusBar(Widget):
    """
    Single-line status bar docked at the bottom.

    Shows: [●/✗/⏳ engine status] │ [● provider] │ [model] │ [context meter] │ [tagline]

    The provider label makes visible which engine is active right now
    (the provider's own label, its host) — instead of only showing "connected".
    """

    # ── Textual Messages ─────────────────────────────────────────────────────

    class SetStatus(TextualMessage):
        def __init__(self, connected: bool, model: str, provider: str = "") -> None:
            super().__init__()
            self.connected = connected
            self.model = model
            self.provider = provider

    class SetStreaming(TextualMessage):
        def __init__(self, streaming: bool) -> None:
            super().__init__()
            self.streaming = streaming

    class SetError(TextualMessage):
        def __init__(self, message: str) -> None:
            super().__init__()
            self.message = message

    class SetMeter(TextualMessage):
        """Push the session's context fill; ``None`` clears the chip."""

        def __init__(self, usage: ContextUsage | None, source: str = "legacy") -> None:
            super().__init__()
            self.usage = usage
            self.source = source

    class SetSession(TextualMessage):
        """Name the active session and how many messages it holds."""

        def __init__(self, title: str, count: int) -> None:
            super().__init__()
            self.title = title
            self.count = count

    class SetQueue(TextualMessage):
        """Show how many submitted turns wait for the running one."""

        def __init__(self, count: int) -> None:
            super().__init__()
            self.count = count

    class SetAgents(TextualMessage):
        """K3: the running swarm's own count — active helpers of the wave."""

        def __init__(self, active: int, total: int) -> None:
            super().__init__()
            self.active = active
            self.total = total

    class SetSeal(TextualMessage):
        """K3: the audit chain's verdict, or None before it was checked."""

        def __init__(self, problems: "list[str] | None") -> None:
            super().__init__()
            self.problems = problems

    # ── State ────────────────────────────────────────────────────────────────

    _connected: bool = False
    _model: str = "–"
    _provider: str = ""
    _streaming: bool = False
    _error: str = ""
    _meter: ContextUsage | None = None
    _meter_source: str = "legacy"
    _session: str = ""
    _session_count: int = 0
    _queue: int = 0
    _agents_active: int = 0
    _agents_total: int = 0
    _seal: "list[str] | None" = None

    def compose(self) -> ComposeResult:
        yield Static("", id="status-indicator", markup=True)
        yield Static("", id="status-provider", markup=True)
        yield Static("", id="status-model", markup=True)
        yield Static("", id="status-session", markup=True)
        yield Static("", id="status-meter", markup=True)
        yield Static("", id="status-queue", markup=True)
        yield Static("", id="status-agents", markup=True)
        yield Static("", id="status-seal", markup=True)
        yield Static(
            f"[{DIM}]Runs locally on the engine you choose.[/{DIM}]",
            id="status-tagline",
            markup=True,
        )

    # ── Message Handlers ─────────────────────────────────────────────────────

    def on_status_bar_set_status(self, event: "StatusBar.SetStatus") -> None:
        self._connected = event.connected
        self._model = event.model
        self._provider = event.provider
        self._error = ""
        self.remove_class("error")
        self._update_display()

    def on_status_bar_set_streaming(self, event: "StatusBar.SetStreaming") -> None:
        self._streaming = event.streaming
        if event.streaming:
            self.add_class("streaming")
        else:
            self.remove_class("streaming")
        self._update_display()

    def on_status_bar_set_error(self, event: "StatusBar.SetError") -> None:
        self._error = event.message
        self._streaming = False
        self.remove_class("streaming")
        self.add_class("error")
        self._update_display()

    def on_status_bar_set_meter(self, event: "StatusBar.SetMeter") -> None:
        self._meter = event.usage
        self._meter_source = event.source
        self._update_display()

    def on_status_bar_set_session(self, event: "StatusBar.SetSession") -> None:
        self._session = event.title
        self._session_count = event.count
        self._update_display()

    def on_status_bar_set_queue(self, event: "StatusBar.SetQueue") -> None:
        self._queue = event.count
        self._update_display()

    def on_status_bar_set_agents(self, event: "StatusBar.SetAgents") -> None:
        self._agents_active = event.active
        self._agents_total = event.total
        self._update_display()

    def on_status_bar_set_seal(self, event: "StatusBar.SetSeal") -> None:
        self._seal = event.problems
        self._update_display()

    def on_resize(self, event: object) -> None:
        """The bar re-fits itself: narrow wins when the facts would not fit."""
        self._update_display()

    # ── Rendering ────────────────────────────────────────────────────────────

    def _update_display(self) -> None:
        indicator = self.query_one("#status-indicator", Static)
        provider_label = self.query_one("#status-provider", Static)
        model_label = self.query_one("#status-model", Static)
        session_label = self.query_one("#status-session", Static)
        meter_label = self.query_one("#status-meter", Static)
        queue_label = self.query_one("#status-queue", Static)
        agents_cell = self.query_one("#status-agents", Static)
        seal_cell = self.query_one("#status-seal", Static)

        meter = (
            meter_text(self._meter, known=self._meter_source != "legacy")
            if self._meter is not None
            else ""
        )
        agents = agents_label(self._agents_active, self._agents_total)
        seal = seal_label(self._seal)

        def cells(narrow: bool, title: str, session: bool = True) -> dict[str, str]:
            """Markup per cell; a hidden cell is absent, never shifted."""
            if self._error:
                head, tone = f"⚠  {self._error}", ERROR
            elif self._streaming:
                head = "⏳ working" if narrow else "⏳ Generating…"
                tone = ACCENT
            elif self._connected:
                head = "● connected" if narrow else "●  Engine: connected"
                tone = OK
            else:
                head = "✗ offline" if narrow else "✗  Engine: offline"
                tone = ERROR
            out = {"indicator": f"[{tone}]{head}[/{tone}]"}
            if self._provider and not narrow:
                out["provider"] = f"[{ACCENT}] │ {self._provider}[/{ACCENT}]"
            out["model"] = f"[{DIM}] │ {self._model}[/{DIM}]"
            if title and session:
                out["session"] = (
                    f"[{DIM}] │ {title} ({self._session_count})[/{DIM}]"
                )
            if meter:
                warn = (
                    self._meter is not None
                    and self._meter.warn
                    and self._meter_source != "legacy"
                )
                colour = WARN if warn else DIM
                out["meter"] = f"[{colour}] │ {meter}[/{colour}]"
            if self._queue:
                out["queue"] = f"[{WARN}] │ {self._queue} queued[/{WARN}]"
            if agents:
                colour = ACCENT if self._agents_active else DIM
                out["agents"] = f"[{colour}] │ {agents}[/{colour}]"
            if seal:
                colour = ERROR if (self._seal or []) else OK
                out["seal"] = f"[{colour}] │ {seal}[/{colour}]"
            return out

        def plain_of(rendered: dict[str, str]) -> int:
            """Width a cell takes on screen: markup for nothing, its own padding counted."""
            total = 0
            for cell in rendered.values():
                total += len(re.sub(r"\[/?[^\]]*\]", "", cell)) + 2
            return total

        title = self._session
        width = self.size.width or 0
        # A fixed 80/110 cut let the meter's tail be clipped at 120–140 columns
        # (seen 2026-10-31): the provider cell alone is ~44. Fit the facts, and
        # give up the session first — the masthead carries its title already.
        full = cells(False, title)
        compact = cells(False, title, session=False)
        if not width or plain_of(full) + 2 <= width:
            tier = "wide"
        elif width >= 110 and plain_of(compact) + 2 <= width:
            tier = "compact"
        else:
            tier = "narrow"
        self.set_class(tier == "narrow", "narrow")
        self.set_class(tier == "compact", "compact")
        if tier == "narrow" and len(title) > 18:
            title = title[:17] + "…"
        if tier == "wide":
            visible = cells(False, title)
        elif tier == "compact":
            visible = cells(False, title, session=False)
        else:
            visible = cells(True, title)
        indicator.update(visible.get("indicator", ""))
        provider_label.update(visible.get("provider", ""))
        model_label.update(visible.get("model", ""))
        session_label.update(visible.get("session", ""))
        meter_label.update(visible.get("meter", ""))
        queue_label.update(visible.get("queue", ""))
        agents_cell.update(visible.get("agents", ""))
        seal_cell.update(visible.get("seal", ""))
