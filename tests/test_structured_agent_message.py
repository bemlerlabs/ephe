"""Structured Agent Message (2026-08-22): thinking throughput + agent messages.

Core mandate: the TUI has to show what the AI is thinking and doing:
  1. react_loop() forwards on_thinking + on_phase to chat_with_tools
     (before that both broke off inside the pipeline — "thinking died in the loop").
  2. The TUI renders agent turns as an AgentMessageCard:
     🧠 thinking collapsible + tool-call blocks (verb phrasings, AI-client style) + markdown answer.
  3. Onboarding: the DGX default comes LIVE from /v1/models instead of hardcoded
     (deployment-drift defence, mandate 2026-08-21).

Test rule of this project: deployment readiness = real tests. The
/v1/models fetch runs against a REAL local HTTP server.
"""
from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest


# 1. react_loop: on_thinking + on_phase Throughput

def test_react_loop_passes_on_thinking_and_on_phase(monkeypatch):
    """GIVEN react_loop() with on_thinking + on_phase callbacks
    THEN both are forwarded to chat_with_tools() in EVERY iteration."""
    import core.react as react_mod
    from core.react import react_loop

    captured: list[dict] = []

    async def fake_chat_with_tools(**kwargs) -> str:
        captured.append({k: kwargs.get(k) for k in ("on_thinking", "on_phase", "on_chunk")})
        return "Antwort"

    async def fake_reflect(*args, **kwargs):
        from core.react import ReflexionResult

        return ReflexionResult(needs_revision=False, reason="ok")

    monkeypatch.setattr(react_mod, "chat_with_tools", fake_chat_with_tools)
    monkeypatch.setattr(react_mod, "reflect", fake_reflect)

    thinking_calls: list[str] = []
    phase_calls: list[str] = []

    async def run():
        await react_loop(
            question="hallo",
            model="m",
            on_chunk=lambda c: None,
            on_thinking=lambda c: thinking_calls.append(c),
            on_phase=lambda p: phase_calls.append(p),
        )

    asyncio.run(run())

    assert captured, "chat_with_tools wurde nicht aufgerufen"
    for entry in captured:
        assert entry["on_thinking"] is not None, "on_thinking wird NICHT durchgereicht"
        assert entry["on_phase"] is not None, "on_phase wird NICHT durchgereicht"


def test_react_loop_emits_thinking_and_phase_to_callbacks(monkeypatch):
    """GIVEN chat_with_tools invokes on_thinking/on_phase
    THEN the UI (the callbacks) receives the calls."""
    import core.react as react_mod
    from core.react import react_loop, ReflexionResult

    async def fake_chat_with_tools(
        *, on_thinking=None, on_phase=None, on_chunk=None, **kwargs
    ) -> str:
        if on_thinking:
            on_thinking("Gedanken ")
            on_thinking("token")
        if on_phase:
            on_phase("Tool round 1…")
        if on_chunk:
            on_chunk("Finale ")
        return "Finale "

    async def fake_reflect(*args, **kwargs):
        return ReflexionResult(needs_revision=False, reason="")

    monkeypatch.setattr(react_mod, "chat_with_tools", fake_chat_with_tools)
    monkeypatch.setattr(react_mod, "reflect", fake_reflect)

    thinking: list[str] = []
    phase: list[str] = []

    async def run():
        await react_loop(
            question="hallo",
            model="m",
            on_chunk=lambda c: None,
            on_thinking=thinking.append,
            on_phase=phase.append,
        )

    asyncio.run(run())
    assert thinking == ["Gedanken ", "token"]
    assert phase == ["Tool round 1…"]


# 2. TUI: AgentMessageCard renders Thinking + Tool-Calls + Markdown

def test_tui_agent_message_card_structure(tmp_path, monkeypatch):
    """GIVEN an agent turn with thinking + tool call + markdown answer
    THEN the TUI shows: thinking collapsible + tool block + markdown answer."""
    from core.session import SESSION_DIR  # noqa: F401
    import core.session as session_module
    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True)
    monkeypatch.setattr(session_module, "SESSION_DIR", session_dir)
    monkeypatch.setattr(session_module, "SESSION_FILE", session_dir / "default.json")

    from ui.app import EpheApp
    from ui.widgets import ChatView
    from textual.widgets import Collapsible as _Collapsible

    app = EpheApp(model="gemma4:12b", reset=True)

    async def run():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            chat = app.query_one(ChatView)
            # Simulate a full agent turn through the Message API
            # (the same chain as in the real _stream_response worker)
            chat.post_message(ChatView.BeginAssistantMessage())
            await pilot.pause()
            chat.post_message(ChatView.AppendThinking("Plan: Datei lesen."))
            chat.post_message(ChatView.ToolCallStart("read_file", {"path": "/tmp/x.txt"}))
            chat.post_message(ChatView.ToolCallDone("read_file", "content-x"))
            chat.post_message(ChatView.AppendChunk("**Ephe** ist bereit."))
            await pilot.pause()
            chat.post_message(ChatView.FinalizeAssistantMessage())
            await pilot.pause()

            # Structure checks (inside the running app!)
            cards = list(app.query(".agent-message-card"))
            assert len(cards) == 1, "genau eine AgentMessageCard erwartet"
            card = cards[0]

            # The thinking collapsible exists and is collapsed after finalize.
            # AI-client labels: live "Thinking", done "Thought for Ns"/"Thought briefly".
            thinking = card.query_one(".thinking-block", _Collapsible)
            assert thinking.collapsed is True, "Thinking-Block soll nach Finalize collapsed sein"
            assert thinking.title.startswith("Thought"), "Thinking-Block soll KI-Client-Style 'Thought…' zeigen"
            assert thinking.visible is True, "Thinking-Block soll sichtbar sein (Tokens geflossen)"

            # Tool block: verb phrasing (AI client) — read_file → category 'explore'
            # → live 'Exploring…', done 'Explored x.txt'. No ▶/✅.
            from ui.widgets import _ToolCallBlock

            tool_blocks = list(card.query(_ToolCallBlock))
            assert len(tool_blocks) == 1, "genau ein Tool-Call-Block erwartet"
            assert not tool_blocks[0].has_class("tool-pending"), "Tool-Block soll fertig sein (pending-Klasse weg)"
            assert "Explored" in tool_blocks[0].title, f"Tool-Block soll 'Explored' zeigen, nicht {tool_blocks[0].title!r}"

            # The markdown answer is visible (not the live block)
            assert card.query_one("#answer-md").visible is True
            assert card.query_one("#answer-live").visible is False

    asyncio.run(run())


def test_tui_markdown_rendered_not_literal(tmp_path, monkeypatch):
    """GIVEN a markdown answer with **bold**
    THEN it is rendered — the literal '**' do NOT sit in the
    live block (F1 from the screenshot)."""
    from core.session import SESSION_DIR  # noqa: F401
    import core.session as session_module
    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True)
    monkeypatch.setattr(session_module, "SESSION_DIR", session_dir)
    monkeypatch.setattr(session_module, "SESSION_FILE", session_dir / "default.json")

    from ui.app import EpheApp
    from ui.widgets import ChatView

    app = EpheApp(model="gemma4:12b", reset=True)

    async def run():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            chat = app.query_one(ChatView)
            chat.post_message(ChatView.BeginAssistantMessage())
            await pilot.pause()
            chat.post_message(ChatView.AppendChunk("**fett** und normal"))
            await pilot.pause()
            chat.post_message(ChatView.FinalizeAssistantMessage())
            await pilot.pause()

            card = app.query_one(".agent-message-card")
            live = card.query_one("#answer-live")
            assert live.visible is False, "Live-Block muss nach Finalize unsichtbar sein"
            answer_md = card.query_one("#answer-md")
            assert answer_md.visible is True, "Markdown-Antwort muss sichtbar sein"
            # Markdown renderable present (no literal '**' string in the live block)
            content = getattr(live, "_content", None) or ""
            assert "**fett**" not in content, "Roh-Markup im Live-Block"

    asyncio.run(run())


def test_tui_reset_answer_clears_acc_and_streams_new(tmp_path, monkeypatch):
    """GIVEN a streamed answer (revision scenario: the 1st answer was insufficient)
    WHEN   ChatView.ResetAnswer on the active AgentMessageCard
    THEN   the answer accumulator is emptied + the live block reset
    AND    new chunks build the 2nd answer ANEW (no duplication of the 1st)"""
    from core.session import SESSION_DIR  # noqa: F401
    import core.session as session_module
    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True)
    monkeypatch.setattr(session_module, "SESSION_DIR", session_dir)
    monkeypatch.setattr(session_module, "SESSION_FILE", session_dir / "default.json")

    from ui.app import EpheApp
    from ui.widgets import ChatView

    app = EpheApp(model="gemma4:12b", reset=True)

    async def run():
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.pause()
            chat = app.query_one(ChatView)
            # Iteration 1: answer 1 streams live
            chat.post_message(ChatView.BeginAssistantMessage())
            await pilot.pause()
            chat.post_message(ChatView.AppendChunk("Erste Antwort "))
            await pilot.pause()
            card = app.query_one(".agent-message-card")
            assert card._answer_acc == "Erste Antwort ", "1. Antwort ist im Acc"

            # Revision: reset + iteration 2 streams the new answer
            chat.post_message(ChatView.ResetAnswer())
            await pilot.pause()
            assert card._answer_acc == "", "Accumulator muss nach Reset leer sein"
            assert card._streaming_answer is False, "Streaming-Flag muss zurückgesetzt sein"

            chat.post_message(ChatView.AppendChunk("Zweite Antwort"))
            await pilot.pause()
            assert card._answer_acc == "Zweite Antwort", (
                f"2. Antwort muss NEU aufbauen, statt zu duplizieren: {card._answer_acc!r}"
            )

            chat.post_message(ChatView.FinalizeAssistantMessage())
            await pilot.pause()
            assert card.query_one("#answer-md").visible is True

    asyncio.run(run())


# 3. Onboarding: live model default via /v1/models

class _ModelsHandler(BaseHTTPRequestHandler):
    model_ids = ["qwen3.8-27b"]

    def do_GET(self):  # noqa: N802
        if self.path.endswith("/models"):
            payload = {"data": [{"id": m} for m in self.model_ids]}
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A003
        pass


def _start_models_server(model_ids: list[str]) -> tuple[HTTPServer, int]:
    _ModelsHandler.model_ids = model_ids
    server = HTTPServer(("127.0.0.1", 0), _ModelsHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def test_fetch_served_models_live_server():
    """GIVEN a real local /v1/models server
    THEN _fetch_served_models returns the served ids."""
    server, port = _start_models_server(["qwen3.8-27b"])
    try:
        import ephe_cli

        ids = ephe_cli._fetch_served_models(f"http://127.0.0.1:{port}/v1")
        assert ids == ["qwen3.8-27b"], f"Live-IDs erwartet, bekam {ids}"
    finally:
        server.shutdown()


def test_fetch_served_models_unreachable_returns_none():
    """GIVEN an unreachable engine
    THEN _fetch_served_models returns None (no crash, the default stays)."""
    import ephe_cli

    assert ephe_cli._fetch_served_models("http://127.0.0.1:1/v1", timeout=1.0) is None


def test_onboarding_openai_compat_preset_uses_live_model(tmp_path, monkeypatch, capsys):
    """GIVEN onboarding with the preset "Your own OpenAI-compatible endpoint
          (DGX Spark / vLLM)" against a live engine serving qwen3.8-27b
    THEN the LIVE model is proposed as the default (not a
    hardcoded model name — deployment-drift defence) AND the preset
    is visible in the menu."""
    server, port = _start_models_server(["qwen3.8-27b"])
    try:
        import ephe_cli

        answers = iter(
            [
                "3",                                          # Preset: the OpenAI-compatible one (DGX Spark / vLLM)
                f"http://127.0.0.1:{port}/v1",                # URL
                "",                                           # Model: the default (from the live list)
                "",                                           # API key: none
            ]
        )

        choice = ephe_cli._run_engine_onboarding(input_fn=lambda _p: next(answers), config_path=str(tmp_path / "engine.json"))

        assert choice.model == "qwen3.8-27b", (
            f"Live-Modell erwartet, bekam {choice.model!r} (Deployment-Drift!)"
        )
        assert choice.api_url == f"http://127.0.0.1:{port}/v1"
        # The live model list was shown
        out = capsys.readouterr().out
        assert "qwen3.8-27b" in out, "Live-Modell-Liste fehlt im Output"
        # W18/A3: the onboarding preset exists and is named
        assert "DGX Spark / vLLM" in out, "Onboarding-Preset fehlt im Menü"
        # No hardcoded drift default left in the code
        assert "deepseek-v4-flash" not in out
    finally:
        server.shutdown()


def test_onboarding_offline_engine_keeps_placeholder_model(tmp_path, monkeypatch, capsys):
    """GIVEN onboarding against an OFFLINE engine (no /v1/models)
    THEN the neutral placeholder of the preset stays — no crash and
    no hardcoded model name (the user corrects it in the next step)."""
    import ephe_cli

    answers = iter(
        [
            "3",
            "http://127.0.0.1:1/v1",  # offline (port 1 → Connection refused right away)
            "",
            "",                       # API key: none
        ]
    )

    choice = ephe_cli._run_engine_onboarding(input_fn=lambda _p: next(answers), config_path=str(tmp_path / "engine.json"))

    assert choice.model == "custom-model", "neutraler Platzhalter erwartet"
    assert choice.provider == "openai_compatible"
    assert choice.api_url == "http://127.0.0.1:1/v1"
