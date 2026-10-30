"""
◑ Ephe – App

Main Textual application for Ephe.
Branding: ◑ Ephe · runs locally, everything else a decision.
Ephe – Bad Liebenzell, Black Forest
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
import textwrap
from urllib.parse import urlparse

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Static

if TYPE_CHECKING:
    from core.model_provider import ModelProviderConfig


from core import __tagline__, __version__
from core import multi_session as ms
from core.chat import (
    EngineNotReachableError,
    OllamaModelBusyError,
    OllamaModelNotFoundError,
    OllamaNotReachableError,
    check_engine_connection,
    check_ollama_connection,
)
from core.react import react_loop, ReActStep
from core.tools import ShellConfirmationRequired
from core.tools.approval import ApprovalPolicy
from core.engine_config import OPENAI_COMPAT
from core.swarm_v2 import run_swarm_v2
from core.commands import (
    extract_learn_topic,
    extract_swarm_task,
    is_goal_command,
    is_info_command,
    is_learn_command,
    is_swarm_command,
    parse_goal_command,
    render_info_command,
    resolve_command,
)
from core.types import Message
from core.memory import Memory
from core.profile import UserProfile, load_profile
from core.corrections import CorrectionJournal
from core.skills import SkillLoader
from ui.composer import Composer
from ui.widgets import ChatView, ConfirmPrompt, StatusBar
from ui.context_meter import estimate_context_usage, resolve_window
from ui.overlays import (
    CommandPalette,
    HelpOverlay,
    ModelPicker,
    PaletteEntry,
)
from ui.session_switcher import SessionChoice, SessionSwitcher
from ui import editor as editor_mod
from ui import file_context
from ui.palette import ACCENT, DIM, ERROR, OK, WARN
from ui.terminal_mark import MARK_HEAD, MARK_ROWS


def _relative_when(iso: object) -> str:
    """A short age for the session greeting; the store writes ISO-8601."""
    try:
        stamp = datetime.fromisoformat(str(iso))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        delta = datetime.now(tz=timezone.utc) - stamp
        if delta.days == 0:
            hours = delta.seconds // 3600
            if hours == 0:
                return "just now"
            return "1 hour ago" if hours == 1 else f"{hours} hours ago"
        if delta.days == 1:
            return "yesterday"
        return f"{delta.days} days ago"
    except (TypeError, ValueError):
        return ""


def _chosen_engine():
    """The engine the user chose (persisted config, else engine env) — None if neither.

    A half-written config counts as none: a remote provider without its endpoint
    starts nothing, so the app opens the setup instead of a chat that cannot send.
    """
    try:
        from core.engine_config import resolve_engine_choice

        choice = resolve_engine_choice(allow_prompt=False)
        return choice if choice is not None and choice.is_complete() else None
    except Exception:
        return None


def _active_provider() -> "ModelProviderConfig | None":
    """The provider resolver's config, or None when nothing is configured."""
    try:
        from core.model_provider import get_active_provider

        return get_active_provider()
    except Exception:
        return None


def _key_label(key: str) -> str:
    """A key as the greeting spells it: 'ctrl+r' reads as 'Ctrl+R', a bare 'q' as 'q'."""
    parts = key.split("+")
    if len(parts) == 1:
        return key.upper() if key.startswith("f") and key[1:].isdigit() else key
    return "+".join(part.upper() if len(part) == 1 else part.capitalize() for part in parts)


class EpheApp(App):
    """
    ◑ Ephe – Main Application

    Keyboard-first TUI for the engine this session was configured with.
    Ephe – Bad Liebenzell, Black Forest.
    """

    CSS_PATH = Path(__file__).parent / "ephe.tcss"

    TITLE = f"◑ Ephe  v{__version__}"
    SUB_TITLE = __tagline__

    def _provider_label(self) -> str:
        """The engine this session talks to, as 'provider · host'.

        The label comes from the provider resolver (core/model_provider) and the
        host from the API URL the chat call reads, so the bar names the endpoint
        in play instead of a vendor this file assumes.
        """
        if self.api_url:
            label, url = "OpenAI-compatible API", self.api_url
        else:
            provider = _active_provider()
            label = provider.label if provider is not None else "Local engine"
            url = provider.base_url if provider is not None else ""
        host = urlparse(url).netloc
        return f"{label} · {host}" if host else label

    def _engine_down_text(self, *, swarm: bool = False) -> tuple[str, str]:
        """The engine-down pair (status bar, chat body) for this session's engine.

        ``OllamaNotReachableError`` is the transport-down bucket of *every*
        provider — a remote OpenAI-compatible engine raises it too — so naming
        Ollama would send the reader to a program this turn never used. The
        provider resolver names the local engine, and the TUI's own ``api_url``
        names the remote one.
        """
        if self.api_url:
            lead = "Swarm aborted.  " if swarm else ""
            return (
                f"Engine not reachable: {self.api_url}",
                f"⚠  {lead}Engine not reachable: {self.api_url}\n"
                "   Check the endpoint (engine.json → api_url).",
            )
        provider = _active_provider()
        label = provider.label if provider is not None else "The local engine"
        endpoint = (provider.base_url if provider is not None else "") or "the local endpoint"
        lead = "Swarm aborted — " if swarm else ""
        return (
            f"{label} not reachable: {endpoint}",
            f"⚠  {lead}{label} not reachable at {endpoint}\n"
            "   Start it with:  ollama serve\n"
            "   Download:       https://ollama.com",
        )

    def _key_hints(self) -> str:
        """The key lines of the greeting, built from the widgets that own the keys.

        The input row comes from ``Composer.KEYS`` and the app row from
        ``BINDINGS``, so a new binding reaches the greeting without a second edit.
        """
        app_row = "  ·  ".join(
            f"{_key_label(binding.key)} = {binding.description}"
            for binding in self.BINDINGS
            if binding.show
        )
        return "\n   ".join(row for row in (Composer.key_hints(), app_row) if row)

    BINDINGS = [
        Binding("ctrl+p", "palette", "Actions", show=True, priority=True),
        Binding("ctrl+o", "sessions", "Sessions", show=True),
        Binding("f2", "model_picker", "Model", show=True),
        Binding("f10", "engine_setup", "Engine", show=False),
        Binding("f1", "help", "Help", show=True),
        Binding("f8", "undo_turn", "Undo", show=False),
        Binding("f9", "redo_turn", "Redo", show=False),
        Binding("f4", "editor", "Editor", show=False),
        Binding("ctrl+r", "new_session", "New", show=True),
        Binding("ctrl+l", "clear_chat", "Clear", show=True),
        Binding("q", "quit", "Quit", show=False, priority=False),
    ]

    # ── Init ─────────────────────────────────────────────────────────────────

    def __init__(
        self,
        model: str | None = None,
        reset: bool = False,
        api_url: str | None = None,
        auto_approve: bool = False,
        declined: bool = False,
        dry_run: bool = False,
    ) -> None:
        super().__init__()
        # The TUI names no model of its own. Without an explicit one the tag comes
        # from the chosen engine (engine.json, else the engine env), and an empty
        # string is honest: nothing was chosen yet (`ephe configure` is the way out).
        if model:
            self.model, self.api_url = model, api_url
        else:
            chosen = _chosen_engine()
            self.model = chosen.model if chosen is not None else ""
            self.api_url = api_url or (chosen.api_url if chosen is not None else None)
        self._reset_on_start = reset
        # P0-1 E1: tool-approval flags. ApprovalPolicy is set ONLY when the user
        # passes an explicit flag (--yes/--no/--dry-run). Without a flag the
        # existing TUI behaviour path stays as is (on_shell_confirm=None →
        # ShellConfirmationRequired → inline confirmation) — we do not replace it
        # with a blocking input()-TTY prompt.
        self._auto_approve = auto_approve
        self._declined = declined
        self._dry_run = dry_run
        self._session: list[Message] = []
        self._session_id = ""
        # Phase 2: Memory + Skills + Profile (lazy init)
        self._memory: Memory | None = None
        self._profile: UserProfile | None = None
        self._corrections: CorrectionJournal | None = None
        self._skill_loader: SkillLoader | None = None
        # Full history for the next _stream_response call
        # (incl. skill system prompt + profile + corrections)
        self._pending_history: list[Message] = []
        # In-TUI tool approval: session allowlist ('a' = always)
        self._confirm_allowed: set[str] = set()
        # One running turn: a steer channel while the model works, and the
        # queued submissions that could not be steered into it.
        self._streaming = False
        self._steer_channel = None
        self._queued: list[str] = []
        self._redo: list[list[Message]] = []
        self._turn_user_index: int | None = None
        self._engine_missing = not self.model.strip()
        self._run_state = "rest"

    # ── P0-1 E1: Tool-Approval ───────────────────────────────────────────────

    def _approval_policy(self) -> ApprovalPolicy:
        """ApprovalPolicy for the worker call.

        State-of-the-art standard: safe/read-only tools run without a prompt.
        Mutating tools are confirmed INTERACTIVELY in the TUI (y/n/a) — the user
        does not have to remember CLI flags. Explicit flags
        (--yes/--no/--dry-run) still win over the prompt.
        ``interactive=False`` prevents the blocking input()-PTY path.
        """
        return ApprovalPolicy(
            auto_approve=self._auto_approve,
            declined=self._declined,
            dry_run=self._dry_run,
            on_confirm=self._on_tui_tool_confirm,
            interactive=False,
        )

    async def _on_tui_tool_confirm(self, tool_name: str, args: dict) -> bool:
        """In-TUI confirm: shows the prompt in the chat, waits for y/n/a.

        - 'a' (always) → put the tool on the session allowlist
        - already allowed → return True immediately (no second prompt)
        """
        if tool_name in self._confirm_allowed:
            return True
        chat = self.query_one(ChatView)
        self._set_run_state("waiting")
        try:
            if tool_name == "run_shell":
                command = str(args.get("command", ""))
                question = f"Run shell command?  {command}"
            else:
                preview = ", ".join(f"{k}={str(v)[:40]}" for k, v in list((args or {}).items())[:3])
                question = f"Run tool '{tool_name}'?  ({preview})"
            prompt = await chat.show_confirm_prompt(question, tool_name)
            try:
                await asyncio.wait_for(prompt.answered.wait(), timeout=300.0)
            except asyncio.TimeoutError:
                # No input within 300s → decline conservatively (no silent approval)
                return False
            # Read the result straight from the widget (set synchronously in on_key) —
            # no race through the app handler (which runs asynchronously AFTER event.set()).
            approved, _always = prompt.result
            return bool(approved)
        finally:
            if self._streaming:
                self._set_run_state("working")

    def on_confirm_prompt_answered(self, event: "ConfirmPrompt.Answered") -> None:
        """App handler: maintain the session allowlist + show the result in the chat.

        (The worker reads the approval result directly from the prompt widget;
        this is about the after-effect: 'always' allowlist + feedback.)
        """
        if event.always and event.answer:
            self._confirm_allowed.add(event.tool_name)
        chat = self.query_one(ChatView)
        if event.answer and event.always:
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"✔  {event.tool_name} allowed for this session.",
                    style="system-msg",
                )
            )
        elif not event.answer:
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"✖  {event.tool_name} declined — execution stopped.",
                    style="system-msg",
                )
            )

    # ── Layout ───────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        # Ink-ground brand header: mark, name, the session in front of you, and
        # one state word — the terminal's answer to "what is running here".
        with Horizontal(id="brand-header"):
            yield Static(Text("\n".join(MARK_HEAD), style=ACCENT), id="brand-mark")
            yield Static("Ephe", id="brand-title")
            yield Static(f"v{__version__}", id="brand-version")
            yield Static("", id="brand-session")
            yield Static(f"[{DIM}]rest[/{DIM}]", id="brand-state")
        yield ChatView(id="chat-view")
        yield Composer(id="input-area")
        yield StatusBar(id="status-bar")
        yield Footer()

    # ── Startup ──────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Called when the app is ready. Load session, init memory, connect to Ollama."""
        if self._reset_on_start:
            entry = ms.create_session("New Session")
            ms.switch_to(str(entry["id"]))

        # Lazy init Phase 2 modules (silently – no crash if unavailable)
        try:
            self._memory = Memory()
            self._profile = load_profile()
            self._corrections = CorrectionJournal()
            self._skill_loader = SkillLoader()
        except Exception:
            pass  # Memory unavailable – app still works

        self._load_session_and_greet()
        self.query_one(Composer).focus_input()

        if self._engine_missing:
            # Nothing is sent until an engine is chosen. The app stays usable and
            # opens the setup itself, so a first start does not dead-end in a
            # command line the user did not ask for.
            self._set_run_state("offline")
            self.query_one(StatusBar).post_message(
                StatusBar.SetError("No engine configured — F10 opens the setup")
            )
            self.query_one(ChatView).post_message(
                ChatView.AddSystemMessage(
                    "⚠  No engine configured yet.\n"
                    "   Pick one in the setup that opens now (F10 reopens it).\n"
                    "   Nothing is sent until an engine is chosen.",
                    style="error-msg",
                )
            )
            self.call_after_refresh(self.action_engine_setup)
        else:
            self._set_run_state("rest")
            # Check the chosen engine asynchronously (non-blocking)
            self.run_worker(self._async_check_connection(), exclusive=False)
        # Attach the MCP servers from mcp.json / EPHE_MCP_SERVERS (non-blocking)
        self.run_worker(self._async_init_mcp(), exclusive=False)
        # One line when this build is behind — a release or untagged merges.
        self.run_worker(self._async_check_update(), exclusive=False)

    async def _async_check_update(self) -> None:
        """Say, once at boot, whether a newer build exists.

        The check reaches GitHub, so it runs off the event loop and stays
        silent when the answer is "current" or unknown: the transcript is a run
        log, not a status board."""
        try:
            from core.update_check import check_for_update

            info = await asyncio.to_thread(check_for_update)
        except Exception:
            return
        if not info.get("available"):
            return
        if info.get("channel") == "main":
            behind = int(info.get("commitsBehind") or 0)
            plural = "" if behind == 1 else "s"
            line = (
                f"↑ {behind} new commit{plural} on main since this build "
                f"({info.get('commit', '?')} → {info.get('latest', 'main')})."
            )
        else:
            line = (
                f"↑ Ephe {info.get('latest', '?')} is out — this build runs "
                f"{info.get('current', '?')}."
            )
        self.query_one(ChatView).post_message(
            ChatView.AddSystemMessage(f"{line}\n   Run:  ephe update", style="system-msg")
        )

    async def _async_init_mcp(self) -> None:
        """Wire the configured MCP servers into this terminal at startup.

        The PWA server does this in its lifespan; the TUI never did, so a server
        the user configured stayed invisible here (the registry held no remote
        tool). Fail-tolerant: a server error must not cost the start.
        """
        try:
            from core.mcp_config import init_mcp_from_config

            registered = await init_mcp_from_config()
        except Exception:
            return
        if not registered:
            return
        self.query_one(ChatView).post_message(
            ChatView.AddSystemMessage(
                f"◑ MCP: {len(registered)} tool(s) registered "
                f"({', '.join(registered)})",
                style="system-msg",
            )
        )

    async def on_unmount(self) -> None:
        """Close the MCP child processes on exit — a leftover is a leak."""
        try:
            from core.tools.mcp_client import close_all_mcp_clients

            await close_all_mcp_clients()
        except Exception:
            pass

    def _save_session(self) -> None:
        """Persist the transcript into its one server-authoritative file."""
        if self._session_id:
            ms.save_messages(self._session_id, self._session)

    def _load_session_and_greet(self) -> None:
        chat = self.query_one(ChatView)

        if ms.legacy_was_corrupt():
            chat.post_message(
                ChatView.AddSystemMessage(
                    "[Legacy session was corrupt – left in place, starting fresh]",
                    style="error-msg",
                )
            )

        sid = ms.active_session_id()
        self._session_id = sid
        self._session = ms.load_messages(sid)
        meta = ms.get_session(sid) or {}
        title = str(meta.get("title") or "default")
        count = len(self._session)
        when = _relative_when(meta.get("last_active"))

        # Multi-session hint (Phase 2 item 7): shows when further sessions
        # exist in parallel. Fail-safe (no exception inside the greeting).
        self._set_session_labels(title, count)
        self.query_one(StatusBar).post_message(StatusBar.SetSession(title, count))

        if count > 0:
            chat.post_message(ChatView.AddSystemVisual(self._welcome_card(
                head=("Ephe", "Welcome back."),
                body=(f"Session “{title}”: {count} messages, {when}.",
                      *self._key_hint_rows(), *self._session_hints()),
            )))
        else:
            chat.post_message(ChatView.AddSystemVisual(self._welcome_card(
                head=("Ephe", "Runs locally. Everything else is a decision."),
                body=(f"Session “{title}”. /sessions switches, /new starts one.",
                      *self._key_hint_rows(), *self._session_hints()),
            )))
        self._post_context_meter()

    def _key_hint_rows(self) -> tuple[str, ...]:
        """The key legend as one row per line, ready for the card's right margin."""
        return tuple(
            line.strip() for line in self._key_hints().splitlines() if line.strip()
        )

    def _session_hints(self) -> tuple[str, ...]:
        """The lines under the greeting: one per thing the user can do next."""
        hints = []
        try:
            stored = len(ms.list_sessions())
        except Exception:
            stored = 0
        if stored > 1:
            hints.append(
                f"{stored} sessions stored — /sessions opens the list, "
                "`ephe session list` names them."
            )
        return tuple(hints)

    def _welcome_card(self, head: tuple[str, ...], body: tuple[str, ...]) -> Text:
        """The moth beside the first words of a session.

        The mark is the alpha cut of `docs/media/paper-moth-master.png` folded into
        braille by `scripts/generate_terminal_mark.py`, so the terminal shows the
        same silhouette as the app icon. The words sit in its right margin.

        A Text carries styles as spans: a session title is the user's own text and
        must not reach a markup parser.
        """
        gutter = 3
        width = max(len(row) for row in MARK_ROWS) + gutter
        # 72 keeps a wrapped row inside a 100-column terminal next to the mark; a
        # narrower terminal wraps the whole block the same way any long line does.
        wrapped: list[str] = []
        for line in body:
            wrapped.extend(textwrap.wrap(line, width=72) or [""])
        rows = max(len(MARK_ROWS) + 1 + len(wrapped), 2 + len(head))
        visual = Text()
        for index in range(rows):
            if index:
                visual.append("\n")
            mark = MARK_ROWS[index] if index < len(MARK_ROWS) else ""
            visual.append(mark.ljust(width), style=DIM)
            head_row = index - 1
            if 0 <= head_row < len(head):
                visual.append(head[head_row], style=f"bold {ACCENT}")
            else:
                body_row = index - (len(MARK_ROWS) + 1)
                if 0 <= body_row < len(wrapped):
                    visual.append(wrapped[body_row])
        return visual

    def _switch_session(self, sid: str) -> bool:
        """Load another stored session; the active cursor moves with it."""
        if ms.get_session(sid) is None:
            self.query_one(ChatView).post_message(
                ChatView.AddSystemMessage(f"Unknown session: {sid}", style="error-msg")
            )
            return False
        self._save_session()
        ms.switch_to(sid)
        self._session_id = sid
        self._redo.clear()
        self.query_one(ChatView).clear_display()
        self._load_session_and_greet()
        self._post_context_meter()
        return True

    def _set_session_labels(self, title: str, count: int) -> None:
        try:
            self.query_one("#brand-session", Static).update(
                f"[{DIM}]{title}[/{DIM}]"
            )
        except Exception:
            return

    def _set_run_state(self, state: str) -> None:
        self._run_state = state
        colours = {
            "rest": DIM,
            "working": ACCENT,
            "waiting": WARN,
            "done": OK,
            "error": ERROR,
            "offline": ERROR,
        }
        try:
            self.query_one("#brand-state", Static).update(
                f"[{colours.get(state, DIM)}]{state}[/{colours.get(state, DIM)}]"
            )
        except Exception:
            return

    def _set_queue(self) -> None:
        try:
            self.query_one(Composer).set_queue(len(self._queued))
            self.query_one(StatusBar).post_message(StatusBar.SetQueue(len(self._queued)))
        except Exception:
            return

    def _settle(self) -> None:
        """One short flourish after a finished turn, never under reduced motion."""
        if not self._animations_enabled():
            return
        try:
            status = self.query_one(StatusBar)
        except Exception:
            return
        status.add_class("settle")
        self.set_timer(0.6, lambda: status.remove_class("settle"))

    @staticmethod
    def _animations_enabled() -> bool:
        try:
            from core.settings_schema import deep_bool

            return bool(deep_bool("appearance.animations_enabled"))
        except Exception:
            return True

    def _post_context_meter(self) -> None:
        """Hand the session's context fill to the status bar (P2-9).

        The window follows the active engine, so a model switch re-sizes the chip.
        A composition without the widget (a headless test) is left alone instead
        of raising.
        """
        try:
            status = self.query_one(StatusBar)
        except Exception:
            return
        window, _source = resolve_window(self.model)
        status.post_message(
            StatusBar.SetMeter(estimate_context_usage(self._session, window))
        )

    def _handle_model_switch(self, new_model: str) -> None:
        """Runtime engine switch: sets the active model without a restart.

        The provider (api_url) stays unchanged — only the model name inside the
        same engine is switched. That makes "/model qwen3.8-flash-next" on the
        DGX and "/model <tag>" on local Ollama possible without losing the
        running session (history, skills, memory).
        """
        if not new_model:
            return
        written = self._persist_model(new_model)
        self.model = new_model
        chat = self.query_one(ChatView)
        chat.post_message(ChatView.AddUserMessage(f"/model {new_model}"))
        # Update the status label right away (the provider stays the same).
        self.query_one(StatusBar).post_message(
            StatusBar.SetStatus(
                connected=True, model=self.model, provider=self._provider_label()
            )
        )
        self._post_context_meter()
        persisted = "engine.json updated" if written else "engine.json not written"
        chat.post_message(
            ChatView.AddSystemMessage(
                f"◑ Model switched → {self.model}  ({self._provider_label()})\n"
                f"   {persisted}; history and session kept.",
                style="system-msg",
            )
        )

    def _persist_model(self, model: str) -> bool:
        """Write the model into the same engine config the PWA writes."""
        try:
            from core.engine_config import load_engine_config, persist_engine_choice

            existing = load_engine_config()
            provider = existing.provider if existing is not None else (
                OPENAI_COMPAT if self.api_url else "local_ollama"
            )
            written = persist_engine_choice(provider, model, self.api_url)
            updated = load_engine_config()
            if updated is not None:
                updated.apply_env()
            return bool(written)
        except Exception:
            return False

    def _heal_model_drift(self, available: list[str]) -> str | None:
        """Pick the auto-healable model when the configured one is missing.

        Conservative rules (never guess):
        - exactly 1 model loaded                       → take that one
        - several: 1 contains "qwen" (active DGX family) → take that one
        - otherwise → None (the user must pick explicitly via /model)
        """
        if not available:
            return None
        if len(available) == 1:
            return available[0]
        # Several loaded: look for the active model family (DGX = Qwen).
        qwen = [m for m in available if "qwen" in m.lower()]
        if len(qwen) == 1:
            return qwen[0]
        return None

    async def _async_check_connection(self) -> None:
        """Ping the active engine on startup, show model list if not found."""
        if self.api_url:
            connected, status_text, available = await check_engine_connection(
                self.api_url, self.model
            )
        else:
            connected, status_text, available = await check_ollama_connection(self.model)

        self.query_one(StatusBar).post_message(
            StatusBar.SetStatus(connected=connected, model=self.model, provider=self._provider_label())
        )
        self._set_run_state("rest" if connected else "offline")

        chat = self.query_one(ChatView)

        if not connected:
            if self.api_url:
                chat.post_message(
                    ChatView.AddSystemMessage(
                        f"⚠  Engine not reachable: {self.api_url}\n"
                        f"   Check the service behind that URL.\n"
                        f"   Model: {self.model}",
                        style="error-msg",
                    )
                )
            else:
                provider = _active_provider()
                label = provider.label if provider is not None else "The local engine"
                endpoint = (provider.base_url if provider is not None else "") or "the local endpoint"
                chat.post_message(
                    ChatView.AddSystemMessage(
                        f"⚠  {label} not reachable at {endpoint}.\n"
                        "   Start it with:  ollama serve\n"
                        "   Download:       https://ollama.com",
                        style="error-msg",
                    )
                )
            return

        # Model not listed by the active engine → show what IS available
        model_present = any(self.model in name for name in available)
        if not model_present:
            if self.api_url:
                # ── Auto-heal: model drift (DGX/vLLM) ──────────────────────────
                # The configured model is missing on the engine but another one is
                # (unambiguously) loaded → switch to it automatically and update
                # engine.json (no dead end).
                healed = self._heal_model_drift(available)
                if healed:
                    old_model = self.model
                    self.model = healed
                    self._persist_model(healed)
                    self.query_one(StatusBar).post_message(
                        StatusBar.SetStatus(
                            connected=True, model=self.model,
                            provider=self._provider_label(),
                        )
                    )
                    chat.post_message(
                        ChatView.AddSystemMessage(
                            f"◑  Model auto-corrected: {old_model} → {healed}\n"
                            f"   (engine.json updated — the start command is unchanged.)",
                            style="system-msg",
                        )
                    )
                    return

                # No unambiguous candidate → show the existing model list
                model_list = "\n".join(
                    f"   • {name}" for name in available[:10]
                ) or "   (the engine lists no models)"
                chat.post_message(
                    ChatView.AddSystemMessage(
                        f"⚠  Model '{self.model}' is not loaded on the engine.\n\n"
                        f"   Available on {self.api_url}:\n"
                        f"{model_list}\n\n"
                        f"   Load it there or switch with:\n"
                        f"   /model <name>",
                        style="error-msg",
                    )
                )
            else:
                model_list = "\n".join(
                    f"   • {name}" for name in available[:10]
                ) or "   (nothing installed)"
                chat.post_message(
                    ChatView.AddSystemMessage(
                        f"⚠  Model '{self.model}' is not installed locally.\n\n"
                        f"   Install it with:\n"
                        f"   ollama pull {self.model}\n\n"
                        f"   Or start with one that is there:\n"
                        f"{model_list}\n\n",
                        style="error-msg",
                    )
                )

    # ── Message Handling ──────────────────────────────────────────────────────

    def on_composer_submitted(self, event: Composer.Submitted) -> None:
        self._accept_input(event.value)

    def _accept_input(self, value: str) -> None:
        """Route a line to the running turn or to a new one."""
        text = value.strip()
        if not text:
            return
        if self._streaming:
            self._during_turn(text)
            return
        self._submit_turn(text)

    def _during_turn(self, text: str) -> None:
        """Steer the running turn where the setting allows, else queue in order."""
        chat = self.query_one(ChatView)
        channel = self._steer_channel
        steer_allowed = True
        try:
            from core.settings_schema import deep_bool

            steer_allowed = bool(deep_bool("chat.allow_input_while_streaming"))
        except Exception:
            steer_allowed = True
        steer = None
        if steer_allowed and channel is not None and not channel.closed:
            try:
                steer = channel.request(text)
            except Exception:
                steer = None
        if steer is not None:
            chat.post_message(ChatView.AddUserMessage(f"↪ steer: {text}"))
            self._session.append(Message(role="user", content=f"[steer] {text}"))
            self._save_session()
            chat.post_message(
                ChatView.AddSystemMessage(
                    "↪ Direction queued for the running turn — it lands at the next round boundary.",
                    style="system-msg",
                )
            )
            return
        self._queued.append(text)
        self._set_queue()
        chat.post_message(
            ChatView.AddSystemMessage(
                f"⏳ Queued #{len(self._queued)} — it runs when this turn ends.",
                style="system-msg",
            )
        )

    def _run_next_queued(self) -> None:
        if self._streaming or not self._queued:
            return
        text = self._queued.pop(0)
        self._set_queue()
        self._submit_turn(text)

    def _finish_simple_turn(self, chat: ChatView, status: StatusBar) -> None:
        self._refresh_seal(status)
        chat.post_message(ChatView.FinalizeAssistantMessage())
        status.post_message(StatusBar.SetStreaming(False))
        self._streaming = False
        self._post_context_meter()
        if self._run_state not in ("error", "offline"):
            self._set_run_state("done")
        self._settle()
        self.call_after_refresh(self._run_next_queued)

    def _rollback_turn(self) -> None:
        """Drop the optimistic messages of a failed turn (question and steers)."""
        if self._turn_user_index is None:
            if self._session and self._session[-1]["role"] == "user":
                self._session.pop()
            return
        del self._session[self._turn_user_index :]
        self._turn_user_index = None
        self._save_session()

    def _submit_turn(self, user_input: str) -> None:
        # ! → shell through the existing approval path (never bypassed)
        if user_input.startswith("!"):
            command = user_input[1:].strip()
            if not command:
                self.query_one(ChatView).post_message(
                    ChatView.AddSystemMessage(
                        "Usage: !<command>  — runs through the approval prompt.",
                        style="system-msg",
                    )
                )
                return
            self._shell_mode(command)
            return

        # App commands run in the terminal itself.
        verb = user_input.split(maxsplit=1)[0].lower()
        app_actions = {
            "/new": self.action_new_session,
            "/sessions": self.action_sessions,
            "/undo": self.action_undo_turn,
            "/redo": self.action_redo_turn,
            "/editor": self.action_editor,
            "/help": self.action_help,
            "/setup": self.action_engine_setup,
            "/configure": self.action_engine_setup,
        }
        if verb in app_actions:
            app_actions[verb]()
            return
        if verb == "/model" and len(user_input.split()) == 1:
            self.action_model_picker()
            return

        # /swarm → multi-agent pipeline (bypass normal chat)
        if is_swarm_command(user_input):
            task = extract_swarm_task(user_input)
            if not task:
                self.query_one(ChatView).post_message(
                    ChatView.AddSystemMessage(
                        "Usage: /swarm <task>\n"
                        "Example: /swarm Build a REST API for a booking system",
                        style="system-msg",
                    )
                )
                return
            self.query_one(ChatView).post_message(ChatView.AddUserMessage(user_input))
            self._run_swarm(task)
            return

        # /learn → skill-builder (writes a new SKILL.md for the topic)
        if is_learn_command(user_input):
            topic = extract_learn_topic(user_input)
            if not topic:
                self.query_one(ChatView).post_message(
                    ChatView.AddSystemMessage(
                        "Usage: /learn <topic>\n"
                        "Example: /learn How we structure FastAPI routes",
                        style="system-msg",
                    )
                )
                return
            self.query_one(ChatView).post_message(ChatView.AddUserMessage(user_input))
            self._run_learn(topic)
            return

        # /goal → the goal loop the PWA and `ephe goal` drive (core/goal_loop.py)
        if is_goal_command(user_input):
            spec = parse_goal_command(user_input)
            if not spec.task:
                self.query_one(ChatView).post_message(
                    ChatView.AddSystemMessage(
                        'Usage: /goal <target> [--check "<cmd>"] [--max-turns N]\n'
                        "Example: /goal Fix the login bug --max-turns 2",
                        style="system-msg",
                    )
                )
                return
            self.query_one(ChatView).post_message(ChatView.AddUserMessage(user_input))
            self._run_goal(spec)
            return

        # /switch <id> → another stored session; the active cursor moves too.
        if user_input.lower().startswith("/switch "):
            self._switch_session(user_input.split(maxsplit=1)[1].strip())
            return

        # /model <name> → runtime engine switch (no restart).
        # A bare "/model" (no argument) stays the info command
        # (raised further down) — the switch explicitly requires "<name>".
        if user_input.lower().startswith("/model ") and len(user_input.split()) > 1:
            self._handle_model_switch(user_input.split()[1].strip())
            return

        # /help /model /engine /configure → render locally (no LLM roundtrip).
        # Caught before skill resolution: deterministic and instant.
        if is_info_command(user_input):
            self.query_one(ChatView).post_message(ChatView.AddUserMessage(user_input))
            self.query_one(ChatView).post_message(
                ChatView.AddSystemMessage(
                    render_info_command(user_input),
                    style="tool-call",
                )
            )
            return

        # ── Evaluate skill triggers (/research, /files, /review, /write, /shell)
        resolved = resolve_command(user_input)

        # @file tokens become a provenance block in the prompt. A missing
        # workspace is named; the message still goes out without the attachment.
        context = file_context.build_context(resolved)
        if context.attached:
            labels = ", ".join(item.label() for item in context.attached)
            self.query_one(ChatView).post_message(
                ChatView.AddSystemMessage(f"◑ Context attached: {labels}", style="system-msg")
            )
        for note in context.notes:
            self.query_one(ChatView).post_message(
                ChatView.AddSystemMessage(note, style="error-msg")
            )
        if context.error:
            self.query_one(ChatView).post_message(
                ChatView.AddSystemMessage(context.error, style="error-msg")
            )
        resolved = context.prompt

        skill_system_prompt: str | None = None
        if user_input.startswith("/") and self._skill_loader is not None:
            skill = self._skill_loader.resolve_trigger(user_input.split()[0])
            if skill is not None:
                skill_system_prompt = skill.system_prompt
                # Skill context as the first message when the session is empty
                self.query_one(ChatView).post_message(
                    ChatView.AddSystemMessage(
                        f"⚡ Skill active: {skill.name}",
                        style="tool-call",
                    )
                )

        # ── Detect corrections ("Das ist falsch:" or "Das stimmt nicht:")  # language-gate: ignore (quotes the keyword tuple on the next line, ui/app.py:496)
        correction_keywords = ("das ist falsch", "das stimmt nicht", "falsch:", "nicht korrekt")
        if any(kw in user_input.lower() for kw in correction_keywords):
            if self._corrections is not None:
                self._corrections.add(
                    wrong="(last answer)",
                    correct=user_input,
                )

        # ── Build the full history (including the context layers)
        pending: list[Message] = []

        # Layer 1: profile context (when the profile has content)
        if self._profile is not None:
            ctx = self._profile.to_context_string()
            if ctx:
                pending.append(Message(role="system", content=ctx))

        # Layer 2: correction context (avoids repeating mistakes)
        if self._corrections is not None:
            corr_ctx = self._corrections.to_context_string(max_items=3)
            if corr_ctx:
                pending.append(Message(role="system", content=corr_ctx))

        # Layer 3: skill system prompt (overrides default behaviour)
        if skill_system_prompt:
            pending.append(Message(role="system", content=skill_system_prompt))

        # Layer 4: conversation history
        pending.extend(self._session)

        # Append the user message. The index is where an error rolls the turn
        # back to — steers append after it and belong to the same turn.
        self._redo.clear()
        self._turn_user_index = len(self._session)
        self._session.append(Message(role="user", content=resolved))
        pending.append(Message(role="user", content=resolved))

        # Keep it for the worker
        self._pending_history = pending

        # Show in UI
        chat = self.query_one(ChatView)
        chat.post_message(ChatView.AddUserMessage(user_input))

        # Kick off the streaming worker
        self._stream_response()

    # ── Streaming Worker ──────────────────────────────────────────────────────

    @work(exclusive=True, thread=False)
    async def _stream_response(self) -> None:
        """
        Async Textual worker. Streams Ollama response token by token.

        CRITICAL design rules:
        - Never modify widgets directly. Use post_message() only.
        - asyncio.CancelledError must propagate (don't swallow it).
        - Input is disabled for the duration of streaming.
        """
        chat = self.query_one(ChatView)
        status = self.query_one(StatusBar)

        status.post_message(StatusBar.SetStreaming(True))
        chat.post_message(ChatView.BeginAssistantMessage())

        from core.steering import SteeringChannel, bind_channel, reset_channel

        channel = SteeringChannel(
            turn_id=f"tui-{self._session_id}", session_id=self._session_id
        )
        token = bind_channel(channel)
        self._steer_channel = channel
        self._streaming = True
        self._set_run_state("working")

        full_response = ""

        def on_chunk(chunk: str) -> None:
            nonlocal full_response
            full_response += chunk
            chat.post_message(ChatView.AppendChunk(chunk))

        def on_loading_hint() -> None:
            """Called when the turn needs more than 15s."""
            chat.post_message(
                ChatView.AddSystemMessage(self._slow_turn_hint(), style="fallback-hint")
            )

        try:
            # Hint task: shows "loading…" when the model needs >15s
            hint_task = asyncio.create_task(
                self._loading_hint_after_delay(on_loading_hint, delay=15.0)
            )

            # ── Tool-call callbacks ───────────────────────────────────────────
            def on_tool_start(tool_name: str, args: dict, call_id: str = "") -> None:
                """Create the tool-call block inside the agent turn (▶ pending)."""
                chat.post_message(ChatView.ToolCallStart(tool_name, args))

            def on_tool_done(tool_name: str, result: str, call_id: str = "") -> None:
                """Close the last tool block (✅ + full output)."""
                chat.post_message(ChatView.ToolCallDone(tool_name, result))

            def on_thinking(chunk: str) -> None:
                """Stream thinking tokens live into the 🧠 block (visible reasoning)."""
                chat.post_message(ChatView.AppendThinking(chunk))

            def on_phase(phase_text: str) -> None:
                """Make the agent phase visible (loading / tool round n / retrying)."""
                chat.post_message(ChatView.SetPhase(phase_text))

            # ── on_step: shows the revision hint BEFORE the new answer arrives
            def on_react_step(step: ReActStep) -> None:
                """Called BEFORE the next LLM call (on_step after reflect)."""
                if step.reflexion.needs_revision:
                    # Hint: the new answer is coming right away
                    chat.post_message(
                        ChatView.AddSystemMessage(
                            f"🔄 Reflection: the answer falls short – improving it…\n"
                            f"   Reason: {step.reflexion.reason[:120]}",
                            style="tool-call",
                        )
                    )

            # ── on_revision: clears the answer accumulator BEFORE iteration 2 streams
            # (the PWA 'revision' event inside the TUI) — without the reset the
            # improved answer would append to iteration 1 and show up twice.
            def on_revision(reason: str) -> None:
                chat.post_message(ChatView.ResetAnswer())

            # Extract the question safely from pending_history
            if self._pending_history:
                last_msg = self._pending_history[-1]
                question = last_msg.get("content", "") if isinstance(last_msg, dict) else ""
                context = self._pending_history[:-1]
            else:
                question = ""
                context = []

            try:
                full_response = await react_loop(
                    question=question,
                    model=self.model,
                    api_url=self.api_url,
                    context=context,
                    on_chunk=on_chunk,
                    on_thinking=on_thinking,
                    on_phase=on_phase,
                    on_tool_start=on_tool_start,
                    on_tool_done=on_tool_done,
                    on_step=on_react_step,
                    on_revision=on_revision,
                    approval_policy=self._approval_policy(),
                )
            finally:
                hint_task.cancel()
                try:
                    await hint_task
                except asyncio.CancelledError:
                    pass

        except ShellConfirmationRequired as exc:
            # ── Shell confirmation (TUI inline confirm) ───────────────────────
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"🖥  Shell command proposed:\n"
                    f"   {exc.command}\n\n"
                    f"   Run it yourself or copy it.",
                    style="tool-call",
                )
            )

        except EngineNotReachableError as exc:
            # The OpenAI-compatible engine (DGX-Spark) does not answer —
            # a CLEAR diagnosis instead of the old, wrong "Ollama" message.
            status.post_message(StatusBar.SetError("Engine not reachable"))
            self._set_run_state("offline")
            self._rollback_turn()
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"⚠  Engine not reachable: {exc.base_url}\n"
                    "   Check the service behind that URL, then the configured\n"
                    "   endpoint (engine.json → api_url).",
                    style="error-msg",
                )
            )
        except OllamaNotReachableError:
            status_text, body_text = self._engine_down_text()
            status.post_message(StatusBar.SetError(status_text))
            # Remove the turn's optimistic messages (the question and any steer)
            self._set_run_state("offline")
            self._rollback_turn()
            chat.post_message(
                ChatView.AddSystemMessage(body_text, style="error-msg")
            )
        except OllamaModelBusyError as exc:
            # The engine is alive but the model does not answer within the budget →
            # an honest "please try again" message instead of silence.
            status.post_message(StatusBar.SetError("Model busy"))
            self._set_run_state("error")
            self._rollback_turn()
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"⚠  Model '{exc.model}' is busy or loading "
                    f"(timeout after {exc.timeout:.0f}s).\n"
                    "   Please try again — on a reasoning model the first\n"
                    "   answer under load can take longer.",
                    style="error-msg",
                )
            )
        except OllamaModelNotFoundError as exc:
            status.post_message(StatusBar.SetError(f"Model not found: {exc.model}"))
            self._set_run_state("error")
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"⚠  Model '{exc.model}' is not there.\n"
                    f"   Install it with:  ollama pull {exc.model}",
                    style="error-msg",
                )
            )
        except asyncio.CancelledError:
            # Worker was cancelled (e.g., app is closing) – clean exit
            pass
        except Exception as exc:
            # Unknown error – show in UI, never crash
            status.post_message(StatusBar.SetError(f"Error: {exc}"))
            self._set_run_state("error")
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"⚠  Unexpected error: {exc}",
                    style="error-msg",
                )
            )
        else:
            # Success – persist assistant + store in memory
            if full_response:
                self._session.append(
                    Message(role="assistant", content=full_response)
                )
                self._save_session()
                # Phase 2: store important answers persistently in memory
                if self._memory is not None:
                    try:
                        # Store the last user question + the answer together
                        last_user = next(
                            (m["content"] for m in reversed(self._session)
                             if m["role"] == "user"), ""
                        )
                        self._memory.store(
                            f"Q: {last_user}\nA: {full_response[:500]}",
                            metadata={"model": self.model},
                        )
                    except Exception:
                        pass  # a memory error never crashes the app
        finally:
            chat.post_message(ChatView.FinalizeAssistantMessage())
            status.post_message(StatusBar.SetStreaming(False))
            channel.close()
            reset_channel(token)
            self._steer_channel = None
            self._streaming = False
            self._turn_user_index = None
            self._post_context_meter()
            if self._run_state != "error" and self._run_state != "offline":
                self._set_run_state("done")
            self._settle()
            self.call_after_refresh(self._run_next_queued)

    def _slow_turn_hint(self) -> str:
        """What a long wait means on the engine the user actually chose.

        The disk-load figure is an Ollama fact; a hosted endpoint has no weights to
        load, so it gets the reason that applies there instead.
        """
        if self.api_url:
            return (
                f"⏳ Waiting on {self.model} — a hosted engine queues requests.\n"
                f"   Nothing is wrong; the answer is on its way."
            )
        return (
            f"⏳ Model '{self.model}' is loading…\n"
            f"   Large models (>4GB) need 30-90s on the first call.\n"
            f"   Please wait."
        )

    @staticmethod
    async def _loading_hint_after_delay(
        callback: Callable[[], None], delay: float
    ) -> None:
        """Helper: call callback after delay seconds (cancelled if model responds first)."""
        await asyncio.sleep(delay)
        callback()

    # ── Swarm Worker ──────────────────────────────────────────────────────────

    def _refresh_seal(self, status: StatusBar) -> None:
        """K3: the audit chain's verdict, read from the log it guards."""
        try:
            from core.audit_log import verify_chain

            status.post_message(StatusBar.SetSeal(verify_chain()))
        except Exception:
            status.post_message(StatusBar.SetSeal(None))

    @work(exclusive=True, thread=False)
    async def _run_swarm(self, task: str) -> None:
        """
        Multi-agent swarm pipeline:
          planner → N specialists (parallel) → synthesizer → ChatView

        The exclusive=True means only one AI job (chat OR swarm) runs at a time.
        """
        chat = self.query_one(ChatView)
        status = self.query_one(StatusBar)
        self._streaming = True
        self._set_run_state("working")
        status.post_message(StatusBar.SetStreaming(True))
        chat.post_message(ChatView.BeginAssistantMessage())

        accumulated = ""
        wave = {"total": 0, "active": 0}

        def on_progress(text: str) -> None:
            nonlocal accumulated
            accumulated += text + "\n"
            # Stream progress into the live assistant area
            chat.post_message(ChatView.AppendChunk(text + "\n"))

        def on_swarm_event(event: dict) -> None:
            """K3: the same structured frames the PWA deck reads, at the footer."""
            kind = str(event.get("type", ""))
            if kind == "swarm_created":
                wave["total"] = len(event.get("agents") or [])
                status.post_message(StatusBar.SetAgents(0, wave["total"]))
                on_progress(f"🐝 {wave['total']} helpers spawned")
            elif kind == "swarm_agent_started":
                wave["active"] += 1
                status.post_message(StatusBar.SetAgents(wave["active"], wave["total"]))
                on_progress(
                    f"▶ {event.get('agent_id')} ({event.get('role', '')}) "
                    f"{event.get('model', '')}".rstrip()
                )
            elif kind == "swarm_agent_done":
                wave["active"] = max(0, wave["active"] - 1)
                status.post_message(StatusBar.SetAgents(wave["active"], wave["total"]))
                on_progress(f"✓ {event.get('agent_id')}: {str(event.get('summary') or '')[:80]}")
            elif kind == "swarm_done":
                status.post_message(StatusBar.SetAgents(0, wave["total"]))

        try:
            result = await run_swarm_v2(
                task=task,
                model=self.model,
                on_event=on_swarm_event,
            )

            # Show final synthesis as the main response
            final_text = (
                "\n━━━━━━━━━━━━━━━━━━━━━━━━\n"
                "◑ Swarm result\n"
                "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
                + result.final
            )
            chat.post_message(ChatView.AppendChunk(final_text))

            # Persist to session
            self._session.append(Message(role="user", content=f"/swarm {task}"))
            self._session.append(
                Message(role="assistant", content=accumulated + final_text)
            )
            self._save_session()
            self._refresh_seal(status)

        except OllamaNotReachableError:
            status_text, body_text = self._engine_down_text(swarm=True)
            status.post_message(StatusBar.SetError(status_text))
            self._set_run_state("offline")
            chat.post_message(
                ChatView.AddSystemMessage(body_text, style="error-msg")
            )
        except OllamaModelNotFoundError as exc:
            status.post_message(StatusBar.SetError(f"Model missing: {exc.model}"))
            self._set_run_state("error")
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"⚠  Model '{exc.model}' is not there.\n"
                    f"   ollama pull {exc.model}",
                    style="error-msg",
                )
            )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            status.post_message(StatusBar.SetError(f"Swarm error: {exc}"))
            self._set_run_state("error")
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"⚠  Swarm error: {exc}",
                    style="error-msg",
                )
            )
        finally:
            self._finish_simple_turn(chat, status)

    # ── Learn / Goal Workers ──────────────────────────────────────────────────

    @work(exclusive=True, thread=False)
    async def _run_learn(self, topic: str) -> None:
        """The /learn pipeline: scan this workspace, build the skill, install it."""
        chat = self.query_one(ChatView)
        status = self.query_one(StatusBar)
        self._streaming = True
        self._set_run_state("working")
        status.post_message(StatusBar.SetStreaming(True))
        chat.post_message(ChatView.BeginAssistantMessage())

        def on_chunk(text: str) -> None:
            chat.post_message(ChatView.AppendChunk(text))

        def on_phase(phase: str) -> None:
            chat.post_message(ChatView.AppendChunk(f"\n{phase}\n"))

        def on_tool_start(name: str, args: dict, call_id: str = "") -> None:
            chat.post_message(ChatView.AppendChunk(f"  {name}({str(args)[:60]})\n"))

        def on_tool_done(name: str, result: str, call_id: str = "") -> None:
            chat.post_message(ChatView.AppendChunk(f"  {name}: {str(result)[:60]}\n"))

        try:
            from core.skill_builder import build_skill

            skill = await build_skill(
                topic=topic,
                model=self.model,
                on_phase=on_phase,
                on_chunk=on_chunk,
                on_tool_start=on_tool_start,
                on_tool_done=on_tool_done,
            )
            # The new skill lands DISABLED: the user enables it in Settings → Skills.
            done = (
                f"\n\nNew skill: {skill.name} ({skill.trigger})\n"
                f"{skill.description}\nEnable it in Settings → Skills."
            )
            chat.post_message(ChatView.AppendChunk(done))
            self._session.append(Message(role="user", content=f"/learn {topic}"))
            self._session.append(Message(role="assistant", content=done))
            self._save_session()

        except OllamaNotReachableError:
            status_text, body_text = self._engine_down_text()
            status.post_message(StatusBar.SetError(status_text))
            self._set_run_state("offline")
            chat.post_message(ChatView.AddSystemMessage(body_text, style="error-msg"))
        except OllamaModelNotFoundError as exc:
            status.post_message(StatusBar.SetError(f"Model missing: {exc.model}"))
            self._set_run_state("error")
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"Model '{exc.model}' is not present.\n   ollama pull {exc.model}",
                    style="error-msg",
                )
            )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            status.post_message(StatusBar.SetError(f"Skill builder failed: {exc}"))
            self._set_run_state("error")
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"Skill builder failed: {exc}",
                    style="error-msg",
                )
            )
        finally:
            self._finish_simple_turn(chat, status)

    @work(exclusive=True, thread=False)
    async def _run_goal(self, spec) -> None:
        """The /goal loop: the check command decides, a failure buys another turn."""
        chat = self.query_one(ChatView)
        status = self.query_one(StatusBar)
        self._streaming = True
        self._set_run_state("working")
        status.post_message(StatusBar.SetStreaming(True))
        chat.post_message(ChatView.BeginAssistantMessage())

        def on_phase(text: str) -> None:
            chat.post_message(ChatView.AppendChunk(f"\n{text}\n"))

        try:
            from core.goal_loop import GoalRunner

            runner = GoalRunner(
                model=self.model,
                check_command=spec.check,
                max_turns=spec.max_turns,
                on_phase=on_phase,
            )
            result = await runner.run(spec.task)

            verdict = "GOAL OK" if result.success else "GOAL FAILED"
            body = f"\n{verdict} after {result.turns} turn(s) — check: {spec.check}\n"
            if result.check_output:
                body += f"\n{result.check_output.strip()[:2000]}\n"
            chat.post_message(ChatView.AppendChunk(body))
            self._session.append(Message(role="user", content=f"/goal {spec.task}"))
            self._session.append(
                Message(role="assistant", content=f"{result.answer}\n{body}")
            )
            self._save_session()

        except OllamaNotReachableError:
            status_text, body_text = self._engine_down_text()
            status.post_message(StatusBar.SetError(status_text))
            self._set_run_state("offline")
            chat.post_message(ChatView.AddSystemMessage(body_text, style="error-msg"))
        except OllamaModelNotFoundError as exc:
            status.post_message(StatusBar.SetError(f"Model missing: {exc.model}"))
            self._set_run_state("error")
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"Model '{exc.model}' is not present.\n   ollama pull {exc.model}",
                    style="error-msg",
                )
            )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            status.post_message(StatusBar.SetError(f"Goal loop failed: {exc}"))
            self._set_run_state("error")
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"Goal loop failed: {exc}",
                    style="error-msg",
                )
            )
        finally:
            self._finish_simple_turn(chat, status)

    # ── Actions ──────────────────────────────────────────────────────────────

    def _refuse_while_running(self) -> bool:
        if not self._streaming:
            return False
        self.query_one(ChatView).post_message(
            ChatView.AddSystemMessage(
                "A turn is running. Queue the command or wait for it to end.",
                style="system-msg",
            )
        )
        return True

    def action_new_session(self) -> None:
        """Ctrl+R / /new – start a session; the old transcript stays on disk."""
        if self._refuse_while_running():
            return
        self._save_session()
        entry = ms.create_session("New Session")
        ms.switch_to(str(entry["id"]))
        self._session_id = str(entry["id"])
        self._session = []
        self._queued.clear()
        self._redo.clear()
        self._set_queue()
        self._post_context_meter()
        self.query_one(ChatView).clear_display()
        self._load_session_and_greet()
        self._set_run_state("rest")

    def action_reset_session(self) -> None:
        self.action_new_session()

    def action_sessions(self) -> None:
        if self._refuse_while_running():
            return
        self.push_screen(
            SessionSwitcher(self._session_id), self._on_session_choice
        )

    def _on_session_choice(self, choice: SessionChoice | None) -> None:
        self.query_one(Composer).focus_input()
        if choice is None or choice.action != "open" or not choice.sid:
            self._set_session_labels(*self._session_label_values())
            return
        if choice.sid == self._session_id:
            meta = ms.get_session(choice.sid) or {}
            self._set_session_labels(
                str(meta.get("title") or "default"), len(self._session)
            )
            return
        self._switch_session(choice.sid)
        self._set_run_state("rest")

    def action_palette(self) -> None:
        self.push_screen(
            CommandPalette(self._palette_entries()), self._run_palette_action
        )

    def _palette_entries(self) -> list[PaletteEntry]:
        from core.commands import get_command_help

        entries = [
            PaletteEntry("new_session", "New session", "Ctrl+R"),
            PaletteEntry("sessions", "Sessions", "Ctrl+O"),
            PaletteEntry("model_picker", "Model picker", "F2"),
            PaletteEntry("engine_setup", "Engine setup", "F10"),
            PaletteEntry("undo_turn", "Undo the last turn", "F8"),
            PaletteEntry("redo_turn", "Redo the last turn", "F9"),
            PaletteEntry("editor", "Edit the draft", "F4"),
            PaletteEntry("help", "Keys and commands", "F1"),
            PaletteEntry("clear_chat", "Clear the display", "Ctrl+L"),
            PaletteEntry("quit", "Quit", "q"),
        ]
        entries.extend(
            PaletteEntry(
                action=f"insert:{command} ",
                label=f"Insert {command}",
                detail=description,
            )
            for command, description in get_command_help()
        )
        return entries

    def _run_palette_action(self, action: str | None) -> None:
        if not action:
            self.query_one(Composer).focus_input()
            return
        if action.startswith("insert:"):
            self.query_one(Composer).set_text(action[len("insert:") :])
            self.query_one(Composer).focus_input()
            return
        self.run_action(action)

    def action_help(self) -> None:
        self.push_screen(
            HelpOverlay(self._help_text()),
            lambda _result: self.query_one(Composer).focus_input(),
        )

    def _help_text(self) -> str:
        from core.commands import get_command_help

        rows = [
            "◑ Ephe — keys",
            "",
            "  Enter              send the draft",
            "  Ctrl+J             new line (Shift+Enter where reported)",
            "  Tab                complete a command or an @file",
            "  ↑ / ↓              history on one line, cursor movement in a draft",
            "  Ctrl+↑ / Ctrl+↓    history at any draft length",
            "  Ctrl+P             every action",
            "  Ctrl+O, /sessions  session switcher (Ctrl+N new, F2 rename, F3 delete)",
            "  Ctrl+R, /new       new session",
            "  F2, /model         model picker (writes engine.json)",
            "  F10, /setup        engine setup: provider, endpoint, key, model",
            "  F8, /undo          undo the last turn",
            "  F9, /redo          restore the last undone turn",
            "  F4, /editor        edit the draft in $VISUAL/$EDITOR",
            "  F1, /help          this page",
            "  Ctrl+L             clear the display",
            "  q                  quit",
            "",
            "Draft tokens",
            "  @path              attach a workspace file to the prompt",
            "  @path#L10-L20      attach a line range",
            "  !command           run a shell command through the approval prompt",
            "",
            "Undo rewrites the transcript only. File edits a tool made are not",
            "reverted: the tool cards name the change set, and `git status` /",
            "`git restore <path>` are the file-level revert.",
            "",
            "Commands",
        ]
        rows.extend(f"  {command:<12} {description}" for command, description in get_command_help())
        return "\n".join(rows)

    def action_engine_setup(self) -> None:
        """Open the engine setup: provider list, then its endpoint, key and model."""
        from ui.setup import ProviderPicker

        self.push_screen(ProviderPicker(), self._after_provider_choice)

    def _after_provider_choice(self, provider: object) -> None:
        from ui.setup import EngineForm

        if provider is None:
            return
        self.push_screen(EngineForm(provider), self._apply_engine_choice)

    def _apply_engine_choice(self, choice: object) -> None:
        """Adopt the engine the setup stored, without restarting the app."""
        if choice is None:
            return
        self.model = getattr(choice, "model", "") or ""
        self.api_url = getattr(choice, "api_url", None)
        self._engine_missing = not self.model
        if self._engine_missing:
            return
        self._set_run_state("rest")
        self.query_one(StatusBar).post_message(
            StatusBar.SetStatus(
                connected=True, model=self.model, provider=self._provider_label()
            )
        )
        where = f" @ {self.api_url}" if self.api_url else ""
        self.query_one(ChatView).post_message(
            ChatView.AddSystemMessage(
                f"◑ Engine set → {getattr(choice, 'provider', '')} / {self.model}{where}\n"
                "   Type a message to start.",
                style="system-msg",
            )
        )
        self.run_worker(self._async_check_connection(), exclusive=False)

    def action_model_picker(self) -> None:
        self._open_model_picker()

    @work(exclusive=False, thread=False)
    async def _open_model_picker(self) -> None:
        if self._engine_missing:
            self.query_one(ChatView).post_message(
                ChatView.AddSystemMessage(
                    "No engine configured — F10 opens the setup",
                    style="error-msg",
                )
            )
            return
        if self.api_url:
            connected, _status, available = await check_engine_connection(
                self.api_url, self.model
            )
        else:
            connected, _status, available = await check_ollama_connection(self.model)
        if not connected:
            self.query_one(ChatView).post_message(
                ChatView.AddSystemMessage(
                    "Engine not reachable — start it, check the endpoint, then retry /model.",
                    style="error-msg",
                )
            )
            return
        if not available:
            self.query_one(ChatView).post_message(
                ChatView.AddSystemMessage(
                    "The engine lists no models — load one there, then retry /model.",
                    style="error-msg",
                )
            )
            return
        self.push_screen(ModelPicker(available, self.model), self._apply_model_choice)

    def _apply_model_choice(self, model: str | None) -> None:
        if model and model != self.model:
            self._handle_model_switch(model)

    def action_undo_turn(self) -> None:
        if self._refuse_while_running():
            return
        chat = self.query_one(ChatView)
        index = None
        for position in range(len(self._session) - 1, -1, -1):
            if self._session[position].get("role") == "user":
                index = position
                break
        if index is None:
            chat.post_message(ChatView.AddSystemMessage("Nothing to undo.", style="system-msg"))
            return
        removed = self._session[index:]
        self._redo.append(removed)
        del self._session[index:]
        self._save_session()
        self._render_transcript()
        self._post_context_meter()
        self._set_session_labels(*self._session_label_values())
        chat.post_message(
            ChatView.AddSystemMessage(
                f"↶ Undid the last turn ({len(removed)} messages). "
                "File changes stay; the tool cards and `git status` name them.",
                style="system-msg",
            )
        )

    def action_redo_turn(self) -> None:
        if self._refuse_while_running():
            return
        chat = self.query_one(ChatView)
        if not self._redo:
            chat.post_message(ChatView.AddSystemMessage("Nothing to redo.", style="system-msg"))
            return
        restored = self._redo.pop()
        self._session.extend(restored)
        self._save_session()
        self._render_transcript()
        self._post_context_meter()
        self._set_session_labels(*self._session_label_values())
        chat.post_message(
            ChatView.AddSystemMessage(
                f"↷ Restored the last undone turn ({len(restored)} messages).",
                style="system-msg",
            )
        )

    def _session_label_values(self) -> tuple[str, int]:
        meta = ms.get_session(self._session_id) or {}
        return str(meta.get("title") or "default"), len(self._session)

    def _render_transcript(self) -> None:
        chat = self.query_one(ChatView)
        chat.clear_display()
        for message in self._session:
            role = message.get("role")
            content = str(message.get("content") or "")
            if role == "user":
                chat.post_message(ChatView.AddUserMessage(content))
            elif role == "assistant":
                chat.post_message(ChatView.BeginAssistantMessage())
                chat.post_message(ChatView.AppendChunk(content))
                chat.post_message(ChatView.FinalizeAssistantMessage())

    def action_editor(self) -> None:
        if self._refuse_while_running():
            return
        composer = self.query_one(Composer)
        draft = composer.value
        if not draft.strip():
            self.query_one(ChatView).post_message(
                ChatView.AddSystemMessage("Nothing to edit — the draft is empty.", style="system-msg")
            )
            return
        command = editor_mod.editor_command()
        if command is None:
            self.query_one(ChatView).post_message(
                ChatView.AddSystemMessage(
                    "No editor configured — set $VISUAL or $EDITOR.",
                    style="error-msg",
                )
            )
            return
        with self.suspend():
            edited, error = editor_mod.run_editor(draft, command)
        if error:
            self.query_one(ChatView).post_message(
                ChatView.AddSystemMessage(error, style="error-msg")
            )
            return
        composer.set_text(edited or "")
        composer.focus_input()

    # ── Shell mode ──────────────────────────────────────────────────────────

    def _shell_mode(self, command: str) -> None:
        if self._streaming:
            self._during_turn(f"!{command}")
            return
        self._run_shell_command(command)

    @work(exclusive=True, thread=False)
    async def _run_shell_command(self, command: str) -> None:
        chat = self.query_one(ChatView)
        status = self.query_one(StatusBar)
        self._streaming = True
        self._set_run_state("working")
        status.post_message(StatusBar.SetStreaming(True))
        chat.post_message(ChatView.AddUserMessage(f"!{command}"))
        chat.post_message(ChatView.BeginAssistantMessage())
        chat.post_message(ChatView.ToolCallStart("run_shell", {"command": command}))
        refused = self._declined or self._dry_run
        if self._auto_approve:
            approved = True
        elif refused:
            approved = False
        else:
            approved = await self._on_tui_tool_confirm("run_shell", {"command": command})
        try:
            if refused:
                from core.tools.chat_gate import denial_message

                result = denial_message("run_shell", "not_approved_by_user")
            else:
                from core.tools._shell_exec import execute_confirmed_shell

                result = await execute_confirmed_shell(command, confirmed=approved)
                self._set_run_state("working")
        except Exception as exc:
            result = f"[TOOL-ERROR] run_shell: {exc}"
            self._set_run_state("error")
        chat.post_message(ChatView.ToolCallDone("run_shell", result))
        chat.post_message(ChatView.FinalizeAssistantMessage())
        self._session.append(Message(role="user", content=f"!{command}"))
        self._session.append(
            Message(role="assistant", content=f"$ {command}\n{result}")
        )
        self._save_session()
        status.post_message(StatusBar.SetStreaming(False))
        self._streaming = False
        self._post_context_meter()
        if self._run_state not in ("error", "offline"):
            self._set_run_state("done")
        self._settle()
        self.call_after_refresh(self._run_next_queued)

    def action_clear_chat(self) -> None:
        """Ctrl+L – clear the visual display only. Session data kept."""
        self.query_one(ChatView).clear_display()

    def action_quit(self) -> None:
        """q – quit Ephe."""
        self.exit()
