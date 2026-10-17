"""Task 3 TDD: reasoning models get a large timeout budget.

Root cause: _tool_detection_timeout() classified qwen3.8-27b (a 27B
reasoning model, startswith("qwen3.")) as a "Small Model" with 25s —
exactly the old qwen3:4b tagging, only with the wrong result. 27B
reasoning needs 30-90s TTFB under load → tool-detect
timeout → the wrong Ollama-busy error.

The budget follows the model class, not the name — the retry practice the
fix rests on.
"""
from __future__ import annotations

from core.chat import (
    _tool_detection_timeout,
    TOOL_DETECT_TIMEOUT_DEFAULT,
    TOOL_DETECT_TIMEOUT_LARGE_REASONING,
)


def test_qwen3_8_27b_is_not_a_small_model():
    """qwen3.8-27b (dot notation, 27B reasoning) gets 120s, not 25s."""
    budget = _tool_detection_timeout("qwen3.8-27b")
    assert budget == TOOL_DETECT_TIMEOUT_LARGE_REASONING, (
        f"27B-Reasoning-Modell braucht {TOOL_DETECT_TIMEOUT_LARGE_REASONING}s, "
        f"bekam {budget}s"
    )


def test_qwen3_4b_small_model_keeps_small_budget():
    """qwen3:4b (colon notation, 4B) stays a Small Model (25s)."""
    assert _tool_detection_timeout("qwen3:4b") == 25.0


def test_model_budget_defaults_when_unknown():
    """Unknown models get the default budget (conservative)."""
    assert _tool_detection_timeout("gemma4:12b") == TOOL_DETECT_TIMEOUT_DEFAULT
    assert _tool_detection_timeout("custom-anything") == TOOL_DETECT_TIMEOUT_DEFAULT
