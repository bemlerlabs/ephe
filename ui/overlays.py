"""Two modal surfaces: the action palette (Ctrl+P) and the key help (F1).

Both take their content from the app, so a binding or command that exists is
listed and a listing cannot drift from the thing it lists. The palette returns
an action id; the app runs it. The help overlay only reads.
"""

from __future__ import annotations

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from ui.palette import ACCENT, DIM, TEXT


@dataclass(frozen=True)
class PaletteEntry:
    action: str
    label: str
    key: str = ""
    detail: str = ""


class _ListScreen(ModalScreen[str | None]):
    """Shared shape: a filter field over a highlighted list, Enter chooses."""

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
        Binding("up", "previous", "Up", show=False, priority=True),
        Binding("down", "next", "Down", show=False, priority=True),
    ]

    def __init__(self, title: str, entries: list[tuple[str, str]]) -> None:
        super().__init__()
        self._title = title
        self._entries = entries
        self._matches = list(entries)
        self._index = 0

    def compose(self) -> ComposeResult:
        with Vertical(classes="overlay-card"):
            yield Static(
                f"[bold {TEXT}]{self._title}[/bold {TEXT}]", classes="overlay-title"
            )
            yield Input(placeholder="Filter…", id="overlay-filter")
            yield Static("", id="overlay-list", markup=True)

    def on_mount(self) -> None:
        self.query_one("#overlay-filter", Input).focus()
        self._render_list()

    def on_input_changed(self, event: Input.Changed) -> None:
        needle = event.value.strip().lower()
        if needle:
            self._matches = [
                entry
                for entry in self._entries
                if needle in entry[0].lower() or needle in entry[1].lower()
            ]
        else:
            self._matches = list(self._entries)
        self._index = 0
        self._render_list()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._choose()

    def on_key(self, event: object) -> None:
        from textual.events import Key

        if not isinstance(event, Key):
            return
        if (
            event.key == "enter"
            and not self.query_one("#overlay-filter", Input).has_focus
        ):
            event.prevent_default()
            self._choose()

    def action_close(self) -> None:
        self.dismiss(None)

    def action_next(self) -> None:
        if self._matches:
            self._index = (self._index + 1) % len(self._matches)
            self._render_list()

    def action_previous(self) -> None:
        if self._matches:
            self._index = (self._index - 1) % len(self._matches)
            self._render_list()

    def _choose(self) -> None:
        if not self._matches:
            return
        self.dismiss(self._matches[self._index][0])

    def _render_list(self) -> None:
        rows: list[str] = []
        if not self._matches:
            rows.append(f"[{DIM}]No match.[/{DIM}]")
        start = max(0, self._index - 6)
        visible = self._matches[start : start + 12]
        for offset, (value, label) in enumerate(visible):
            position = start + offset
            marker = (
                f"[bold {ACCENT}]›[/bold {ACCENT}]" if position == self._index else " "
            )
            rows.append(f"{marker} {label}")
        hidden = len(self._matches) - start - len(visible)
        if hidden > 0:
            rows.append(f"[{DIM}]… {hidden} more — type to filter[/{DIM}]")
        self.query_one("#overlay-list", Static).update("\n".join(rows))


class CommandPalette(_ListScreen):
    """Every action the terminal can run, filtered as you type."""

    def __init__(self, entries: list[PaletteEntry]) -> None:
        super().__init__(
            "Actions",
            [
                (
                    entry.action,
                    f"{entry.label}"
                    + (f"  [{DIM}]{entry.key}[/{DIM}]" if entry.key else "")
                    + (f"  [{DIM}]· {entry.detail}[/{DIM}]" if entry.detail else ""),
                )
                for entry in entries
            ],
        )


class ModelPicker(_ListScreen):
    """The models the resolved engine lists. Picking one writes the config."""

    def __init__(self, models: list[str], current: str) -> None:
        self._current = current
        super().__init__(
            "Models",
            [
                (
                    model,
                    f"{model}"
                    + (f"  [{DIM}]· current[/{DIM}]" if model == current else ""),
                )
                for model in models
            ],
        )


class HelpOverlay(ModalScreen[None]):
    """Every binding and command on one scrollable page."""

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
        Binding("f1", "close", "Close", priority=True),
    ]

    def __init__(self, text: str) -> None:
        super().__init__()
        self._text = text

    def compose(self) -> ComposeResult:
        with Vertical(classes="overlay-card help-card"):
            yield Static(
                f"[bold {TEXT}]Keys and commands[/bold {TEXT}]", classes="overlay-title"
            )
            yield VerticalScroll(
                Static(self._text, markup=False), classes="help-scroll"
            )

    def action_close(self) -> None:
        self.dismiss(None)
