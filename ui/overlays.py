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
            [(entry.action, _palette_label(entry)) for entry in entries],
        )


#: A palette row wider than this puts its detail on a hanging second line.
#: Static would otherwise wrap it flush against the card's left border.
_PALETTE_WIDTH = 64


def _palette_label(entry: PaletteEntry) -> str:
    key = f"  {entry.key}" if entry.key else ""
    head = entry.label + key
    if entry.key:
        head = entry.label + f"  [{DIM}]{entry.key}[/{DIM}]"
    plain = entry.label + key
    if not entry.detail:
        return head
    tail = f"· {entry.detail}"
    if len(plain) + 2 + len(tail) <= _PALETTE_WIDTH:
        return f"{head}  [{DIM}]{tail}[/{DIM}]"
    return f"{head}\n    [{DIM}]{tail}[/{DIM}]"


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


class UpdatePrompt(ModalScreen[bool]):
    """A newer Ephe on the remote: update now, or keep working.

    Updating replaces the code the running process was started from, so the
    app closes itself afterwards and the next start carries the new build.
    """

    BINDINGS = [
        Binding("escape", "later", "Later", priority=True),
        Binding("n", "later", "Later", show=False, priority=True),
        Binding("enter", "update", "Update", priority=True),
        Binding("y", "update", "Update", show=False, priority=True),
    ]

    def __init__(self, version: str, url: str = "") -> None:
        super().__init__()
        self._version = version
        self._url = url

    def compose(self) -> ComposeResult:
        with Vertical(classes="overlay-card"):
            yield Static(
                f"[bold {TEXT}]Ephe update[/bold {TEXT}]", classes="overlay-title"
            )
            yield Static(
                f"[{TEXT}]Ephe {self._version} is available.[/{TEXT}]\n"
                f"[{DIM}]Updating closes Ephe. Start it again with: ephe[/{DIM}]",
                id="update-body",
            )
            yield Static(f"[{DIM}]Enter update · Esc later[/{DIM}]", id="update-hint")

    def action_update(self) -> None:
        self.dismiss(True)

    def action_later(self) -> None:
        self.dismiss(False)


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
