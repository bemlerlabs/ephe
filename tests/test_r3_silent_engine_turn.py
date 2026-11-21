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


def test_both_messages_offer_a_next_step_without_a_cause():
    for text in (SILENT_ENGINE_TURN, SILENT_AFTER_TOOLS_TURN):
        assert "noch einmal" in text or "Versuch es" in text
        for erfundene_ursache in ("429", "Drossel", "Rate limit", "gehängt", "Timeout"):
            assert erfundene_ursache not in text, erfundene_ursache
    assert "Werkbank" in SILENT_AFTER_TOOLS_TURN
    assert "Einstellungen" in SILENT_ENGINE_TURN
