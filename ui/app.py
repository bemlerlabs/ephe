"""
◑ Ephe – App

Main Textual application for Ephe.
Branding: ◑ Ephe · runs locally, everything else a decision.
Ephe – Bad Liebenzell, Black Forest
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Footer, Static

if TYPE_CHECKING:
    from core.model_provider import ModelProviderConfig

from core import __edition__, __tagline__, __version__
from core.chat import (
    EngineNotReachableError,
    OllamaModelBusyError,
    OllamaModelNotFoundError,
    OllamaNotReachableError,
    check_engine_connection,
    check_ollama_connection,
    chat_with_tools,
)
from core.react import react_loop, ReActStep
from core.tools import ShellConfirmationRequired
from core.tools.approval import ApprovalPolicy
from core.engine_config import (
    EngineChoice,
    OPENAI_COMPAT,
    load_engine_config,
    save_engine_config,
)
from core.swarm import run_swarm
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
from core.session import (
    delete_session,
    load_last_session,
    save_session,
    session_info,
    was_session_corrupt,
)
from core.types import Message
from core.memory import Memory
from core.profile import UserProfile, load_profile
from core.corrections import CorrectionJournal
from core.skills import SkillLoader
from ui.widgets import ChatView, ConfirmPrompt, HistoryInput, StatusBar
from ui.context_meter import estimate_context_usage, resolve_window
from ui.palette import ACCENT


def _chosen_engine():
    """The engine the user chose (persisted config, else engine env) — None if neither."""
    try:
        from core.engine_config import resolve_engine_choice

        return resolve_engine_choice(allow_prompt=False)
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
        return key
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

        The input row comes from ``HistoryInput.KEYS`` and the app row from
        ``BINDINGS``, so a new binding reaches the greeting without a second edit.
        """
        app_row = "  ·  ".join(
            f"{_key_label(binding.key)} = {binding.description}"
            for binding in self.BINDINGS
            if binding.show
        )
        return "\n   ".join(row for row in (HistoryInput.key_hints(), app_row) if row)

    BINDINGS = [
        Binding("ctrl+r", "reset_session", "Reset session", show=True),
        Binding("ctrl+l", "clear_chat", "Clear display", show=True),
        Binding("q", "quit", "Quit", show=True, priority=False),
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
        # Ink-ground brand header (unique instead of the generic Textual header):
        # [◑] Ephe  v<version>  ........  Runs locally. Everything else is a decision.
        with Horizontal(id="brand-header"):
            yield Static(f"[{ACCENT}]◑[/{ACCENT}]", id="brand-mark")
            yield Static("Ephe", id="brand-title")
            yield Static(f"v{__version__}", id="brand-version")
            yield Static(__tagline__, id="brand-tagline")
        yield ChatView(id="chat-view")
        yield HistoryInput(id="input-area")
        yield StatusBar(id="status-bar")
        yield Footer()

    # ── Startup ──────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        """Called when the app is ready. Load session, init memory, connect to Ollama."""
        if self._reset_on_start:
            delete_session()

        # Lazy init Phase 2 modules (silently – no crash if unavailable)
        try:
            self._memory = Memory()
            self._profile = load_profile()
            self._corrections = CorrectionJournal()
            self._skill_loader = SkillLoader()
        except Exception:
            pass  # Memory unavailable – app still works

        self._load_session_and_greet()
        self.query_one(HistoryInput).focus_input()

        # Check Ollama connection asynchronously (non-blocking)
        self.run_worker(self._async_check_connection(), exclusive=False)
        # Attach the MCP servers from mcp.json / EPHE_MCP_SERVERS (non-blocking)
        self.run_worker(self._async_init_mcp(), exclusive=False)

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

    def _load_session_and_greet(self) -> None:
        chat = self.query_one(ChatView)

        if was_session_corrupt():
            chat.post_message(
                ChatView.AddSystemMessage(
                    "[Session was corrupt – starting fresh]",
                    style="error-msg",
                )
            )

        session = load_last_session()
        self._session = session
        count, when = session_info()

        # Multi-session hint (Phase 2 item 7): shows when further sessions
        # exist in parallel. Fail-safe (no exception inside the greeting).
        multi_hint = ""
        try:
            from core.multi_session import list_sessions as _ms_list
            n_sessions = len(_ms_list())
            if n_sessions > 1:
                multi_hint = (
                    f"\n   {n_sessions} sessions stored — "
                    f"`ephe session list` to switch."
                )
        except Exception:
            multi_hint = ""

        if count > 0:
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"◑ Ephe – Welcome back.\n"
                    f"   Last session: {count} messages, {when}\n"
                    f"   {self._key_hints()}{multi_hint}",
                    style="welcome",
                )
            )
        else:
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"◑ Ephe – Ready. Runs locally. Everything else is a decision.\n"
                    f"   /help  /post  /debug  /idea  /explain  /commit  /swarm\n"
                    f"   {self._key_hints()}{multi_hint}",
                    style="welcome",
                )
            )

        self._post_context_meter()

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
        chat.post_message(
            ChatView.AddSystemMessage(
                f"◑ Model switched → {self.model}  ({self._provider_label()})\n"
                "   History and session kept.",
                style="system-msg",
            )
        )

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
                    import os
                    os.environ["EPHE_MODEL"] = os.environ["EPHE_MODEL"] = healed
                    if os.environ.get("EPHE_MODEL_PROVIDER") == OPENAI_COMPAT:
                        os.environ["EPHE_OPENAI_COMPAT_MODEL"] = healed
                    try:
                        cfg = load_engine_config()
                        if cfg is not None:
                            save_engine_config(
                                EngineChoice(
                                    provider=cfg.provider,
                                    model=healed,
                                    api_url=cfg.api_url,
                                )
                            )
                    except Exception:
                        pass  # a persistence error must not block the healing run
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

    def on_history_input_submitted(self, event: HistoryInput.Submitted) -> None:
        """User pressed Enter in the HistoryInput widget."""
        user_input = event.value.strip()
        if not user_input:
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

        # Append the user message
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
        hist_input = self.query_one(HistoryInput)

        hist_input.disable()
        status.post_message(StatusBar.SetStreaming(True))
        chat.post_message(ChatView.BeginAssistantMessage())

        full_response = ""

        def on_chunk(chunk: str) -> None:
            nonlocal full_response
            full_response += chunk
            chat.post_message(ChatView.AppendChunk(chunk))

        def on_loading_hint() -> None:
            """Called when the model needs more than 15s (loading from disk)."""
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"⏳ Model '{self.model}' is loading…\n"
                    f"   Large models (>4GB) need 30-90s on the first call.\n"
                    f"   Please wait.",
                    style="fallback-hint",
                )
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
            if self._session and self._session[-1]["role"] == "user":
                self._session.pop()
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
            # Remove the user message we added optimistically
            if self._session and self._session[-1]["role"] == "user":
                self._session.pop()
            chat.post_message(
                ChatView.AddSystemMessage(body_text, style="error-msg")
            )
        except OllamaModelBusyError as exc:
            # The engine is alive but the model does not answer within the budget →
            # an honest "please try again" message instead of silence.
            status.post_message(StatusBar.SetError("Model busy"))
            if self._session and self._session[-1]["role"] == "user":
                self._session.pop()
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
            status.post_message(StatusBar.SetError(f"Fehler: {exc}"))
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"⚠  Unerwarteter Fehler: {exc}",
                    style="error-msg",
                )
            )
        else:
            # Success – persist assistant + store in memory
            if full_response:
                self._session.append(
                    Message(role="assistant", content=full_response)
                )
                save_session(self._session)
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
            self._post_context_meter()
            hist_input.enable()

    @staticmethod
    async def _loading_hint_after_delay(
        callback: Callable[[], None], delay: float
    ) -> None:
        """Helper: call callback after delay seconds (cancelled if model responds first)."""
        await asyncio.sleep(delay)
        callback()

    # ── Swarm Worker ──────────────────────────────────────────────────────────

    @work(exclusive=True, thread=False)
    async def _run_swarm(self, task: str) -> None:
        """
        Multi-agent swarm pipeline:
          planner → N specialists (parallel) → synthesizer → ChatView

        The exclusive=True means only one AI job (chat OR swarm) runs at a time.
        """
        chat = self.query_one(ChatView)
        status = self.query_one(StatusBar)
        hist_input = self.query_one(HistoryInput)

        hist_input.disable()
        status.post_message(StatusBar.SetStreaming(True))
        chat.post_message(ChatView.BeginAssistantMessage())

        accumulated = ""

        def on_progress(text: str) -> None:
            nonlocal accumulated
            accumulated += text + "\n"
            # Stream progress into the live assistant area
            chat.post_message(ChatView.AppendChunk(text + "\n"))

        try:
            result = await run_swarm(
                task=task,
                model=self.model,
                on_progress=on_progress,
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
            save_session(self._session)

        except OllamaNotReachableError:
            status_text, body_text = self._engine_down_text(swarm=True)
            status.post_message(StatusBar.SetError(status_text))
            chat.post_message(
                ChatView.AddSystemMessage(body_text, style="error-msg")
            )
        except OllamaModelNotFoundError as exc:
            status.post_message(StatusBar.SetError(f"Model missing: {exc.model}"))
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
            status.post_message(StatusBar.SetError(f"Swarm-Fehler: {exc}"))
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"⚠  Swarm-Fehler: {exc}",
                    style="error-msg",
                )
            )
        finally:
            chat.post_message(ChatView.FinalizeAssistantMessage())
            status.post_message(StatusBar.SetStreaming(False))
            self._post_context_meter()
            hist_input.enable()

    # ── Learn / Goal Workers ──────────────────────────────────────────────────

    @work(exclusive=True, thread=False)
    async def _run_learn(self, topic: str) -> None:
        """The /learn pipeline: scan this workspace, build the skill, install it."""
        chat = self.query_one(ChatView)
        status = self.query_one(StatusBar)
        hist_input = self.query_one(HistoryInput)

        hist_input.disable()
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
            save_session(self._session)

        except OllamaNotReachableError:
            status_text, body_text = self._engine_down_text()
            status.post_message(StatusBar.SetError(status_text))
            chat.post_message(ChatView.AddSystemMessage(body_text, style="error-msg"))
        except OllamaModelNotFoundError as exc:
            status.post_message(StatusBar.SetError(f"Model missing: {exc.model}"))
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
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"Skill builder failed: {exc}",
                    style="error-msg",
                )
            )
        finally:
            chat.post_message(ChatView.FinalizeAssistantMessage())
            status.post_message(StatusBar.SetStreaming(False))
            self._post_context_meter()
            hist_input.enable()

    @work(exclusive=True, thread=False)
    async def _run_goal(self, spec) -> None:
        """The /goal loop: the check command decides, a failure buys another turn."""
        chat = self.query_one(ChatView)
        status = self.query_one(StatusBar)
        hist_input = self.query_one(HistoryInput)

        hist_input.disable()
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
            save_session(self._session)

        except OllamaNotReachableError:
            status_text, body_text = self._engine_down_text()
            status.post_message(StatusBar.SetError(status_text))
            chat.post_message(ChatView.AddSystemMessage(body_text, style="error-msg"))
        except OllamaModelNotFoundError as exc:
            status.post_message(StatusBar.SetError(f"Model missing: {exc.model}"))
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
            chat.post_message(
                ChatView.AddSystemMessage(
                    f"Goal loop failed: {exc}",
                    style="error-msg",
                )
            )
        finally:
            chat.post_message(ChatView.FinalizeAssistantMessage())
            status.post_message(StatusBar.SetStreaming(False))
            self._post_context_meter()
            hist_input.enable()

    # ── Actions ───────────────────────────────────────────────────────────────


    def action_reset_session(self) -> None:
        """Ctrl+R – delete session and clear display."""
        delete_session()
        self._session = []
        self._post_context_meter()
        chat = self.query_one(ChatView)
        chat.clear_display()
        chat.post_message(
            ChatView.AddSystemMessage(
                "◑ Session reset. Fresh start.",
                style="system-msg",
            )
        )

    def action_clear_chat(self) -> None:
        """Ctrl+L – clear the visual display only. Session data kept."""
        self.query_one(ChatView).clear_display()

    def action_quit(self) -> None:
        """q – quit Ephe."""
        self.exit()
