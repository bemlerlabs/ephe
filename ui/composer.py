"""The multi-line composer and the two key tables a terminal can promise.

Enter sends. Ctrl+J starts a new line, and Shift+Enter does the same where the
terminal reports it; a terminal that cannot tell Shift+Enter from Enter still
has Ctrl+J. Tab completes a slash command or the file named after ``@``.
Up/Down move the cursor in a multi-line draft and walk the submission history
while the draft is one line; Ctrl+Up/Ctrl+Down always walk the history.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.events import Key
from textual.message import Message as TextualMessage
from textual.widget import Widget
from textual.widgets import Static, TextArea

from core.commands import get_completions
from ui import file_context
from ui.palette import DIM


class ComposerArea(TextArea):
    """TextArea with the product's key table instead of the editor defaults."""

    class Submit(TextualMessage):
        pass

    class Newline(TextualMessage):
        pass

    class Complete(TextualMessage):
        pass

    class History(TextualMessage):
        def __init__(self, direction: int) -> None:
            super().__init__()
            self.direction = direction

    async def _on_key(self, event: Key) -> None:
        if self.read_only:
            await super()._on_key(event)
            return
        single_line = "\n" not in self.text
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            self.post_message(self.Submit())
            return
        if event.key in ("ctrl+j", "shift+enter"):
            event.stop()
            event.prevent_default()
            self.post_message(self.Newline())
            return
        if event.key == "tab":
            event.stop()
            event.prevent_default()
            self.post_message(self.Complete())
            return
        if event.key in ("ctrl+up", "ctrl+down") or (
            event.key in ("up", "down") and single_line
        ):
            event.stop()
            event.prevent_default()
            self.post_message(self.History(-1 if event.key.endswith("up") else 1))
            return
        await super()._on_key(event)

    @property
    def value(self) -> str:
        return self.text

    @value.setter
    def value(self, text: str) -> None:
        self.load_text(text)
        self.move_cursor(self.document.end)


class Composer(Widget):
    """Three lines at most: the draft, the hint, and the queued-turn count."""

    KEYS: tuple[tuple[tuple[str, ...], str, str], ...] = (
        (("enter",), "Enter", "Send"),
        (("ctrl+j", "shift+enter"), "Ctrl+J", "New line"),
        (("tab",), "Tab", "Complete"),
        (("up", "down", "ctrl+up", "ctrl+down"), "↑↓", "History"),
    )

    class Submitted(TextualMessage):
        def __init__(self, value: str) -> None:
            super().__init__()
            self.value = value

    @classmethod
    def key_hints(cls) -> str:
        return "  ·  ".join(f"{glyph} = {label}" for _keys, glyph, label in cls.KEYS)

    DEFAULT_CSS = """
    Composer {
        height: auto;
        layout: vertical;
    }
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._history: list[str] = []
        self._history_index = 0
        self._saved_draft = ""
        self._queued = 0

    def compose(self) -> ComposeResult:
        yield Static("", id="composer-hint", markup=True)
        yield ComposerArea(
            id="chat-input",
            placeholder="› Type a message, /command, @file or !command…",
            soft_wrap=True,
            show_line_numbers=False,
            tab_behavior="focus",
            compact=True,
            highlight_cursor_line=False,
        )

    def on_mount(self) -> None:
        self._history_index = 0
        self._render_hint("")

    # ── Area messages ────────────────────────────────────────────────────────

    def on_composer_area_submit(self, event: "ComposerArea.Submit") -> None:
        value = self.value.strip()
        if not value:
            return
        if not self._history or self._history[-1] != value:
            self._history.append(value)
        self._history_index = len(self._history)
        self._saved_draft = ""
        self.set_text("")
        self.post_message(Composer.Submitted(value))

    def on_composer_area_newline(self, event: "ComposerArea.Newline") -> None:
        area = self.query_one("#chat-input", ComposerArea)
        area.insert("\n")

    def on_composer_area_complete(self, event: "ComposerArea.Complete") -> None:
        self._complete()

    def on_composer_area_history(self, event: "ComposerArea.History") -> None:
        self._navigate_history(event.direction)

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        area = self.query_one("#chat-input", ComposerArea)
        self._render_hint(area.text)

    # ── History ──────────────────────────────────────────────────────────────

    def _navigate_history(self, direction: int) -> None:
        if not self._history:
            return
        area = self.query_one("#chat-input", ComposerArea)
        if self._history_index == len(self._history) and direction == -1:
            self._saved_draft = area.text
        index = max(0, min(len(self._history), self._history_index + direction))
        self._history_index = index
        if index == len(self._history):
            self.set_text(self._saved_draft)
        else:
            self.set_text(self._history[len(self._history) - 1 - index])

    # ── Completion ───────────────────────────────────────────────────────────

    def _complete(self) -> None:
        area = self.query_one("#chat-input", ComposerArea)
        text = area.text
        if text.startswith("/") and " " not in text:
            completions = get_completions(text)
            if len(completions) == 1:
                self.set_text(completions[0] + " ")
            elif completions:
                self._render_hint(text)
            return
        token = file_context.current_token(text, area.cursor_location)
        if token is None:
            return
        root, reason = file_context.workspace_root()
        if root is None:
            self._set_hint_text(reason)
            return
        matches = file_context.match_files(root, token, limit=1)
        if matches:
            updated, cursor = file_context.replace_token(
                text, area.cursor_location, matches[0]
            )
            self.set_text_at(updated, cursor)

    def _render_hint(self, text: str) -> None:
        if self._queued:
            self._set_hint_text(
                f"{self._queued} queued — the running turn takes them in order."
            )
            return
        if text.startswith("/") and " " not in text:
            completions = get_completions(text)
            if completions:
                self._set_hint_text("  ".join(completions))
                return
        area = self.query_one("#chat-input", ComposerArea)
        token = file_context.current_token(text, area.cursor_location)
        if token is not None:
            root, reason = file_context.workspace_root()
            if root is None:
                self._set_hint_text(reason)
                return
            matches = file_context.match_files(root, token)
            if matches:
                self._set_hint_text("  ".join(f"@{path}" for path in matches))
                return
        self._set_hint_text(
            "Enter = send  ·  Ctrl+J = new line  ·  @ = attach a file  ·  ! = shell"
        )

    def _set_hint_text(self, text: str) -> None:
        hint = self.query_one("#composer-hint", Static)
        hint.update(f"[{DIM}]{text}[/{DIM}]" if text else "")

    # ── Public API ───────────────────────────────────────────────────────────

    @property
    def value(self) -> str:
        return self.query_one("#chat-input", ComposerArea).text

    def set_text(self, text: str) -> None:
        area = self.query_one("#chat-input", ComposerArea)
        area.value = text
        self._render_hint(text)

    def set_text_at(self, text: str, cursor: tuple[int, int]) -> None:
        area = self.query_one("#chat-input", ComposerArea)
        area.load_text(text)
        area.move_cursor(cursor)
        self._render_hint(text)

    def set_queue(self, count: int) -> None:
        self._queued = max(0, count)
        area = self.query_one("#chat-input", ComposerArea)
        self._render_hint(area.text)

    def disable(self) -> None:
        self.query_one("#chat-input", ComposerArea).read_only = True

    def enable(self) -> None:
        area = self.query_one("#chat-input", ComposerArea)
        area.read_only = False
        area.focus()

    def focus_input(self) -> None:
        self.query_one("#chat-input", ComposerArea).focus()
