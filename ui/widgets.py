"""
◑ Ephe – Widgets

Four focused, reusable Textual widgets:

    HistoryInput      – Input with ↑/↓ history navigation + command completions
    ChatView          – Scrollable chat display with structured agent messages
    AgentMessageCard  – one assistant turn: thinking (collapsible) + tool calls + markdown answer
    StatusBar         – live status: engine · model · tagline

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
import json
import re
import time
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message as TextualMessage
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Collapsible, Input, Static
from rich.console import Group
from rich.markdown import Markdown
from rich.markup import escape as markup_escape
from rich.text import Text

from core.commands import get_completions
from ui.context_meter import ContextUsage, meter_text
from ui.palette import ACCENT, DIM, ERROR, OK, TEXT, WARN


# ===========================================================================
# HistoryInput
# ===========================================================================


class HistoryInput(Widget):
    """
    Input widget with ↑/↓ navigation through submission history.

    Also handles:
    - Command mode detection when first character is '/'
    - Tab-completion for slash commands
    - Emitting HistoryInput.Submitted for the App to handle
    """

    #: The keys this widget answers to, grouped as the greeting prints them:
    #: key names, hint glyph, action label. `KEYS` is what `on_key` filters on,
    #: so a key the hint names is a key this widget handles.
    KEYS: tuple[tuple[tuple[str, ...], str, str], ...] = (
        (("tab",), "Tab", "Autocomplete"),
        (("up", "down"), "↑↓", "History"),
    )

    @classmethod
    def key_hints(cls) -> str:
        """The widget's key row for the greeting, one 'glyph = action' per group."""
        return "  ·  ".join(f"{glyph} = {label}" for _keys, glyph, label in cls.KEYS)

    DEFAULT_CSS = """
    HistoryInput {
        height: 3;
        layout: vertical;
    }
    """

    class Submitted(TextualMessage):
        """Posted when the user submits (Enter). Contains the raw input value."""

        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    # ── State ────────────────────────────────────────────────────────────────

    _history: list[str]
    _history_index: int  # len(history) = "no history entry active"
    _saved_draft: str    # saves current text when navigating up

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._history = []
        self._history_index = 0
        self._saved_draft = ""

    def compose(self) -> ComposeResult:
        yield Static("", id="command-hint")
        yield Input(
            placeholder="› Type a message or /command…",
            id="chat-input",
        )

    def on_mount(self) -> None:
        self._history_index = 0

    # ── Key handling ─────────────────────────────────────────────────────────

    def on_key(self, event: object) -> None:  # type: ignore[override]
        from textual.events import Key

        if not isinstance(event, Key):
            return

        declared = {key for keys, _glyph, _label in self.KEYS for key in keys}
        if event.key not in declared:
            return

        input_widget = self.query_one("#chat-input", Input)

        if event.key == "up":
            event.prevent_default()
            self._navigate_history(-1, input_widget)

        elif event.key == "down":
            event.prevent_default()
            self._navigate_history(+1, input_widget)

        elif event.key == "tab":
            event.prevent_default()
            self._try_complete(input_widget)

    def _navigate_history(self, direction: int, input_widget: Input) -> None:
        """direction: -1 = older, +1 = newer"""
        if not self._history:
            return

        # Save draft before first upward navigation
        if self._history_index == len(self._history) and direction == -1:
            self._saved_draft = input_widget.value

        new_index = self._history_index + direction
        new_index = max(0, min(len(self._history), new_index))
        self._history_index = new_index

        if new_index == len(self._history):
            input_widget.value = self._saved_draft
        else:
            # new_index counts from the end: 0 = len-1 (newest), 1 = len-2, etc.
            # Pressing UP once → most recent entry (history[-1])
            input_widget.value = self._history[len(self._history) - 1 - new_index]

        # Move cursor to end
        input_widget.cursor_position = len(input_widget.value)

    def _try_complete(self, input_widget: Input) -> None:
        """Tab-complete slash commands."""
        text = input_widget.value
        if not text.startswith("/"):
            return

        # Only complete if it's a single-word prefix (no space yet)
        if " " in text:
            return

        completions = get_completions(text)
        if len(completions) == 1:
            input_widget.value = completions[0] + " "
            input_widget.cursor_position = len(input_widget.value)
        elif len(completions) > 1:
            hint = self.query_one("#command-hint", Static)
            hint.update("  ".join(completions))
            hint.add_class("visible")

    # ── Input change ─────────────────────────────────────────────────────────

    def on_input_changed(self, event: Input.Changed) -> None:
        hint = self.query_one("#command-hint", Static)
        text = event.value

        if text.startswith("/") and " " not in text:
            completions = get_completions(text)
            if completions:
                hint.update("  ".join(completions))
                hint.add_class("visible")
                self.add_class("command-mode")
                return

        hint.remove_class("visible")
        self.remove_class("command-mode")

    # ── Submission ───────────────────────────────────────────────────────────

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if not value:
            return

        # Add to history (avoid duplicates at tip)
        if not self._history or self._history[-1] != value:
            self._history.append(value)

        # Reset index
        self._history_index = len(self._history)
        self._saved_draft = ""

        # Clear input + hint
        event.input.value = ""
        hint = self.query_one("#command-hint", Static)
        hint.remove_class("visible")
        self.remove_class("command-mode")

        # Notify App
        self.post_message(HistoryInput.Submitted(value))

    # ── Public API ────────────────────────────────────────────────────────────

    def disable(self) -> None:
        """Disable input during streaming."""
        self.query_one("#chat-input", Input).disabled = True

    def enable(self) -> None:
        """Re-enable input after streaming."""
        inp = self.query_one("#chat-input", Input)
        inp.disabled = False
        inp.focus()

    def focus_input(self) -> None:
        self.query_one("#chat-input", Input).focus()


# ===========================================================================
# ChatView
# ===========================================================================


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
    run = {"run_shell", "execute_code", "spawn_swarm", "terminate_self"}
    edit = {
        "create_pdf", "create_svg", "create_pptx_deck", "create_pitch_deck",
        "edit_pptx_template", "create_source_notebook", "generate_chart",
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


def _tool_verb_present(name: str) -> str:
    return _TOOL_COPY[_tool_category(name)]["present"]


def _tool_verb_past(name: str) -> str:
    return _TOOL_COPY[_tool_category(name)]["past"]


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
        self._args_static = Static("", id=f"tool-args-{id(self)}", markup=True)
        # Live title: present-tense verb (Ephe convention)
        super().__init__(self._args_static, title=f"{_tool_verb_present(name)}…", collapsed=True)
        self.add_class("tool-call-block")
        self.add_class("tool-pending")
        target = _tool_target(name, args)
        if target:
            self._args_static.update(f"[{DIM}]{_tool_verb_present(name).lower()}[/{DIM}]  {markup_escape(target)}")
        else:
            self._args_static.update(f"[{DIM}]{_tool_verb_present(name).lower()}[/{DIM}]")
        self._output: Static | None = None

    def set_done(self, result: str) -> None:
        """Tool done: past-tense verb + target, full output Static in the body."""
        target = _tool_target(self._tool_name, self._args)
        past = _tool_verb_past(self._tool_name)
        self.title = f"{past} {target}".rstrip() if target else past
        self.remove_class("tool-pending")
        self._output = Static("", id=f"tool-out-{id(self)}", markup=True)
        self._output.add_class("tool-output")
        preview = result if len(result) <= 4000 else result[:4000] + "\n[… truncated]"
        self._output.update(f"[{DIM}]output[/{DIM}]\n{markup_escape(preview)}")
        self.compose_add_child(self._output)
        self.refresh()


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
        def __init__(self, name: str, result: str) -> None:
            super().__init__()
            self.name = name
            self.result = result

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

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.add_class("agent-message-card")
        self._thinking_acc = ""
        self._answer_acc = ""
        self._thinking_started = False
        self._thinking_t0 = 0.0
        self._blocks = []
        self._streaming_answer = False

    DEFAULT_CSS = """
    AgentMessageCard {
        layout: vertical;
        width: 1fr;
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

    def on_agent_message_card_tool_done(self, event: "AgentMessageCard.ToolDone") -> None:
        """Close the last still-open tool block (FIFO over the 'tool-pending' class)."""
        for block in reversed(self._blocks):
            if block.has_class("tool-pending"):
                block.set_done(event.result)
                break

    def on_agent_message_card_answer_chunk(self, event: "AgentMessageCard.AnswerChunk") -> None:
        self._answer_acc += event.chunk
        if not self._streaming_answer:
            self._streaming_answer = True
            self._answer_live.visible = True
            self._answer_md.visible = False
            # The status line is redundant once the content streams
            self._phase_line.visible = False
        self._answer_live.update(
            f"[bold {ACCENT}]Assistant[/bold {ACCENT}]\n[{TEXT}]{markup_escape(self._answer_acc)}[/{TEXT}]▌"
        )

    def on_agent_message_card_reset_answer(self, event: "AgentMessageCard.ResetAnswer") -> None:
        """Revision reset: empty the answer accumulator + the live block.

        Iteration 1 answered insufficiently; reflect() demands a revision.
        The new (improved) answer streams anew from here — without this reset
        iteration 2 would append to iteration 1 and the user would see the
        answer twice."""
        self._answer_acc = ""
        self._streaming_answer = False
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
            self._answer_md = self.query_one("#answer-md", Static)
            self._answer_md.update(
                Group(
                    Text("Assistant", style=f"bold {ACCENT}"),
                    Markdown(self._answer_acc),
                )
            )
            self._answer_md.visible = True
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
        block = Static(markup, markup=True)
        block.add_class("static-block")
        self._container().mount(block)

    # ── Message Handlers ────────────────────────────────────────────────────

    def on_chat_view_add_user_message(self, event: "ChatView.AddUserMessage") -> None:
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

    def on_chat_view_begin_assistant_message(self, event: "ChatView.BeginAssistantMessage") -> None:
        card = AgentMessageCard()
        self._active_card = card
        self._container().mount(card)
        card.post_message(AgentMessageCard.Begin())

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
            self._active_card.post_message(AgentMessageCard.ToolDone(event.name, event.result))

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
        prompt = ConfirmPrompt(question, tool_name)
        await self._container().mount(prompt)
        self._confirm_prompt = prompt
        return prompt

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

    def compose(self) -> ComposeResult:
        yield Static(
            f"[bold {ERROR}]⚠  {markup_escape(self._question)}[/bold {ERROR}]\n"
            f"[{DIM}]y[/{DIM}]=Yes  [{DIM}]n[/{DIM}]=No  "
            f"[{ACCENT}]a[/{ACCENT}]=Always (this tool, this session)",
            id="confirm-question",
            markup=True,
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


# ===========================================================================
# StatusBar
# ===========================================================================


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

        def __init__(self, usage: ContextUsage | None) -> None:
            super().__init__()
            self.usage = usage

    # ── State ────────────────────────────────────────────────────────────────

    _connected: bool = False
    _model: str = "–"
    _provider: str = ""
    _streaming: bool = False
    _error: str = ""
    _meter: ContextUsage | None = None

    def compose(self) -> ComposeResult:
        yield Static("", id="status-indicator", markup=True)
        yield Static("", id="status-provider", markup=True)
        yield Static("", id="status-model", markup=True)
        yield Static("", id="status-meter", markup=True)
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
        self._update_display()

    # ── Rendering ────────────────────────────────────────────────────────────

    def _update_display(self) -> None:
        indicator = self.query_one("#status-indicator", Static)
        provider_label = self.query_one("#status-provider", Static)
        model_label = self.query_one("#status-model", Static)
        meter_label = self.query_one("#status-meter", Static)

        if self._error:
            indicator.update(f"[bold {ERROR}]⚠  {self._error}[/bold {ERROR}]")
            provider_label.update("")
            model_label.update("")
            meter_label.update("")
            return

        if self._streaming:
            indicator.update(f"[{ACCENT}]⏳ Generating…[/{ACCENT}]")
        elif self._connected:
            indicator.update(f"[{OK}]●  Engine: connected[/{OK}]")
        else:
            indicator.update(f"[{ERROR}]✗  Engine: offline[/{ERROR}]")

        provider_label.update(
            f"[{ACCENT}]  │  {self._provider}[/{ACCENT}]" if self._provider else ""
        )
        model_label.update(f"[{DIM}]  │  {self._model}[/{DIM}]")
        meter_label.update(self._meter_markup())

    def _meter_markup(self) -> str:
        """Empty when no fill was measured; the warning colour at/over the threshold."""
        if self._meter is None:
            return ""
        color = WARN if self._meter.warn else DIM
        return f"[{color}]  │  {meter_text(self._meter)}[/{color}]"
