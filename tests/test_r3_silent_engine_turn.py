"""W1-R3 / W8 — a silent turn must not look like an answer.

Measured against the running backend (OpenRouter free model): a request that
needed a tool came back repeatedly as an empty bubble — `assistant` with
"", no `chunk`, no `tool_*`. The provider answered with an HTTP 200 in all 188
cases, and the surface showed silence as though Ephe had replied.

With the cause still open on that (no 429, no provider error), the
message names no reason we have evidenced — only what helps next.

Contract (W8 reversed point 2):
1. Empty and no tool run is silent — "no text, no tool run, no answer".
2. Empty **after** a tool run is likewise silent, but a different
   story: the files are there, the answer is not. Two states, two sentences.
3. Content means: no message — not even when it is a single bullet point.
4. Both messages stay actionable, without inventing a cause.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.routes.chat import (  # noqa: E402
    SILENT_AFTER_TOOLS_TURN,
    SILENT_ENGINE_TURN,
    silent_turn_message,
)


def test_empty_answer_without_tools_is_silent():
    assert silent_turn_message("", []) == SILENT_ENGINE_TURN
    assert silent_turn_message("   \n ", []) == SILENT_ENGINE_TURN


def test_text_is_not_reported_as_a_silent_run():
    assert silent_turn_message("Die ersten Dateien sind…", []) is None


def test_tool_run_without_answer_uses_the_other_sentence():
    """W8, path 1: the tool exception let the error fizzle away unnamed."""
    tools = [{"tool": "create_pdf", "ok": True}]
    assert silent_turn_message("", tools) == SILENT_AFTER_TOOLS_TURN
    assert silent_turn_message("", tools) != SILENT_ENGINE_TURN


def _server_error_leaves() -> list[str]:
    """The two German sentences the chat panel shows, read from the bundle that carries them.

    They stood in `server/routes/chat.py` until 2026-11-24; the reader's text is the bundle's
    now, so the checks below run over both halves of what a reader can actually be shown.
    """
    root = Path(__file__).resolve().parents[1] / "app" / "src" / "locales"
    bundle = json.loads((root / "de.json").read_text(encoding="utf-8"))["serverError"]
    return [bundle["silent_engine_turn"], bundle["silent_after_tools_turn"]]


def test_every_silent_turn_text_offers_a_next_step_without_a_cause():
    """Both fallbacks and both German sentences, checked as one set.

    A reader reaches one of the four depending on their language and how far the client got,
    so the promise — a next step, no invented cause — has to hold on all of them.
    """
    texts = [SILENT_ENGINE_TURN, SILENT_AFTER_TOOLS_TURN, *_server_error_leaves()]
    for text in texts:
        assert "noch einmal" in text or "Try again" in text, text
        for erfundene_ursache in ("429", "Drossel", "Rate limit", "geh\u00e4ngt", "Timeout"):
            assert erfundene_ursache not in text, erfundene_ursache
    assert "Werkbank" in _server_error_leaves()[1]
    assert "workbench" in SILENT_AFTER_TOOLS_TURN
    assert "Einstellungen" in _server_error_leaves()[0]
    assert "Settings" in SILENT_ENGINE_TURN
