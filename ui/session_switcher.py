"""The session switcher: one store, one list, Enter opens.

Typing filters. Ctrl+N creates and opens a session; F2 renames the selected
one in place; F3 removes it, and a second F3 confirms because deleting a
transcript is the one action here that cannot be undone. Deleting the active
session opens the next one, or creates a new one when the store is empty.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import NamedTuple

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from core import multi_session as ms
from ui.palette import ACCENT, DIM, ERROR, OK, TEXT


class SessionChoice(NamedTuple):
    action: str
    sid: str = ""


def _age(iso: object) -> str:
    try:
        stamp = datetime.fromisoformat(str(iso))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        delta = datetime.now(tz=timezone.utc) - stamp
        if delta.days == 0:
            hours = delta.seconds // 3600
            return (
                "just now"
                if hours == 0
                else ("1 hour ago" if hours == 1 else f"{hours} hours ago")
            )
        if delta.days == 1:
            return "yesterday"
        return f"{delta.days} days ago"
    except (TypeError, ValueError):
        return ""


class SessionSwitcher(ModalScreen[SessionChoice]):
    """A filtered list of the sessions in the one server store."""

    BINDINGS = [
        Binding("escape", "close", "Close", priority=True),
        Binding("up", "previous", "Up", show=False, priority=True),
        Binding("down", "next", "Down", show=False, priority=True),
        Binding("ctrl+n", "new_session", "New", priority=True),
        Binding("f2", "rename", "Rename", priority=True),
        Binding("f3", "delete", "Delete", priority=True),
    ]

    def __init__(self, active_id: str) -> None:
        super().__init__()
        self._active_id = active_id
        self._sessions = ms.list_sessions()[:100]
        self._counts = {
            str(item.get("id") or ""): len(ms.load_messages(str(item.get("id") or "")))
            for item in self._sessions
        }
        self._matches = list(self._sessions)
        self._index = 0
        self._renaming: dict | None = None
        self._pending_delete = ""

    def compose(self) -> ComposeResult:
        with Vertical(classes="overlay-card"):
            yield Static(
                f"[bold {TEXT}]Sessions[/bold {TEXT}]", classes="overlay-title"
            )
            yield Input(placeholder="Filter sessions…", id="session-filter")
            yield Static("", id="session-list", markup=True)
            yield Static("", id="session-footer", markup=True)

    def on_mount(self) -> None:
        self.query_one("#session-filter", Input).focus()
        self._render_list()

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._renaming is not None:
            return
        needle = event.value.strip().lower()
        if needle:
            self._matches = [
                item
                for item in self._sessions
                if needle in str(item.get("title") or "").lower()
                or needle in str(item.get("id") or "").lower()
            ]
        else:
            self._matches = list(self._sessions)
        self._index = 0
        self._render_list()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self._renaming is not None:
            self._finish_rename(event.value)
            return
        self._open_selected()

    def action_close(self) -> None:
        if self._renaming is not None:
            self._cancel_rename()
            return
        self.dismiss(SessionChoice("none"))

    def action_next(self) -> None:
        if self._matches:
            self._index = (self._index + 1) % len(self._matches)
            self._render_list()

    def action_previous(self) -> None:
        if self._matches:
            self._index = (self._index - 1) % len(self._matches)
            self._render_list()

    def action_new_session(self) -> None:
        entry = ms.create_session("New Session")
        self.dismiss(SessionChoice("open", str(entry["id"])))

    def action_rename(self) -> None:
        if not self._matches:
            return
        selected = self._matches[self._index]
        self._renaming = selected
        box = self.query_one("#session-filter", Input)
        box.value = str(selected.get("title") or "")
        box.cursor_position = len(box.value)
        box.focus()
        self._render_list()

    def action_delete(self) -> None:
        if not self._matches or self._renaming is not None:
            return
        selected = self._matches[self._index]
        sid = str(selected.get("id") or "")
        if self._pending_delete != sid:
            self._pending_delete = sid
            self._render_list()
            return
        was_active = sid == self._active_id
        ms.delete_session(sid)
        self._pending_delete = ""
        self._sessions = ms.list_sessions()[:100]
        self._counts.pop(sid, None)
        self._matches = list(self._sessions)
        self._index = min(self._index, max(0, len(self._matches) - 1))
        if was_active:
            if self._matches:
                self.dismiss(
                    SessionChoice(
                        "open", str(self._matches[self._index].get("id") or "")
                    )
                )
            else:
                entry = ms.create_session("New Session")
                self.dismiss(SessionChoice("open", str(entry["id"])))
            return
        self._render_list()

    # ── Internals ────────────────────────────────────────────────────────────

    def _open_selected(self) -> None:
        if not self._matches:
            return
        self.dismiss(
            SessionChoice("open", str(self._matches[self._index].get("id") or ""))
        )

    def _finish_rename(self, title: str) -> None:
        title = title.strip()
        if self._renaming is not None and title:
            ms.rename_session(str(self._renaming.get("id")), title)
            self._sessions = ms.list_sessions()[:100]
            self._matches = list(self._sessions)
        self._cancel_rename()

    def _cancel_rename(self) -> None:
        self._renaming = None
        box = self.query_one("#session-filter", Input)
        box.value = ""
        box.placeholder = "Filter sessions…"
        box.focus()
        self._render_list()

    def _render_list(self) -> None:
        rows: list[str] = []
        if not self._matches:
            rows.append(f"[{DIM}]No session matches.[/{DIM}]")
        start = max(0, self._index - 6)
        visible = self._matches[start : start + 12]
        for offset, item in enumerate(visible):
            position = start + offset
            sid = str(item.get("id") or "")
            title = str(item.get("title") or "untitled")
            count = self._counts.get(sid, 0)
            marker = "●" if sid == self._active_id else " "
            colour = OK if sid == self._active_id else DIM
            cursor = (
                f"[bold {ACCENT}]›[/bold {ACCENT}]" if position == self._index else " "
            )
            label = (
                f"{cursor} [{colour}]{marker}[/{colour}] {title}  "
                f"[{DIM}]{sid} · {count} messages · {_age(item.get('last_active'))}[/{DIM}]"
            )
            if self._pending_delete == sid:
                label += f"  [bold {ERROR}]F3 again to delete[/bold {ERROR}]"
            rows.append(label)
        hidden = len(self._matches) - start - len(visible)
        if hidden > 0:
            rows.append(f"[{DIM}]… {hidden} more — type to filter[/{DIM}]")
        self.query_one("#session-list", Static).update("\n".join(rows))
        self.query_one("#session-footer", Static).update(
            f"[{DIM}]Enter open · Ctrl+N new · F2 rename · F3 delete · Esc close[/{DIM}]"
        )
        if self._renaming is not None:
            self.query_one("#session-filter", Input).placeholder = "Rename to…"
