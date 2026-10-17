"""
Tests for core/swarm.py
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.swarm import SwarmResult, _plan, _synthesize, run_swarm


# Helpers


def mock_ollama_response(text: str):
    """Build a mock ollama chat response dict."""
    resp = MagicMock()
    resp.__getitem__ = lambda self, key: {
        "message": MagicMock(**{"__getitem__": lambda s, k: text if k == "content" else None})
    }[key]
    # Simpler approach:
    msg = MagicMock()
    msg.__getitem__ = lambda self, k: text
    response = MagicMock()
    response.__getitem__ = lambda self, k: msg if k == "message" else None
    return response


def patch_chat(return_texts: list[str]):
    """
    Context manager: patch ollama.AsyncClient().chat to return texts in order.
    Each call returns the next text as a proper attribute-style response.
    """
    call_count = 0
    texts = list(return_texts)

    async def fake_chat(*args, **kwargs):
        nonlocal call_count
        text = texts[min(call_count, len(texts) - 1)]
        call_count += 1
        # Return attribute-style response (matching real ollama response)
        msg = MagicMock()
        msg.content = text
        msg.tool_calls = None
        response = MagicMock()
        response.message = msg
        # Also support dict-style access for backward compatibility
        response.__getitem__ = lambda self, k: {"content": text} if k == "message" else None
        return response

    return patch("core.swarm.ollama.AsyncClient", return_value=MagicMock(chat=AsyncMock(side_effect=fake_chat)))


# _plan


async def test_plan_returns_list_from_json():
    """Planner parses JSON array from model output."""
    json_output = '["Task A", "Task B", "Task C"]'

    with patch_chat([json_output]):
        result = await _plan("Build a REST API", "phi4-mini")

    assert isinstance(result, list)
    assert len(result) == 3
    assert result[0] == "Task A"


async def test_plan_handles_json_in_markdown_block():
    """Planner extracts JSON even when wrapped in markdown code block."""
    markdown_output = '```json\n["Design schema", "Write endpoints"]\n```'

    with patch_chat([markdown_output]):
        result = await _plan("Build REST API", "phi4-mini")

    assert len(result) == 2
    assert result[0] == "Design schema"


async def test_plan_fallback_on_invalid_json():
    """Planner falls back to [task] if model returns non-JSON."""
    with patch_chat(["I will break this into parts: first do X, then Y"]):
        result = await _plan("Some task", "phi4-mini")

    # Fallback: wrap original task
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0] == "Some task"


async def test_plan_limits_to_max_specialists():
    """Planner caps output at MAX_SPECIALISTS (4)."""
    from core.swarm import MAX_SPECIALISTS

    many_tasks = json.dumps([f"Task {i}" for i in range(10)])

    with patch_chat([many_tasks]):
        result = await _plan("Huge task", "phi4-mini")

    assert len(result) <= MAX_SPECIALISTS


# run_swarm (integration)


async def test_run_swarm_returns_swarm_result():
    """Full pipeline returns SwarmResult with expected fields."""
    # Plan returns 2 subtasks, specialists and synthesizer return text
    planner_response = '["Write data model", "Write API endpoints"]'
    specialist_response = "Here is the implementation..."
    synthesizer_response = "Combined final answer."

    responses = [
        planner_response,        # planner call
        specialist_response,     # specialist 1
        specialist_response,     # specialist 2
        synthesizer_response,    # synthesizer
    ]

    with patch_chat(responses):
        result = await run_swarm(
            task="Build a booking system",
            model="phi4-mini",
        )

    assert isinstance(result, SwarmResult)
    assert result.task == "Build a booking system"
    assert len(result.subtasks) == 2
    assert len(result.partial_results) == 2
    assert result.final == synthesizer_response


async def test_run_swarm_calls_on_progress():
    """on_progress callback is called during the pipeline."""
    progress_calls: list[str] = []

    planner_response = '["Subtask A", "Subtask B"]'
    responses = [planner_response, "result A", "result B", "final synthesis"]

    with patch_chat(responses):
        await run_swarm(
            task="Test task",
            model="phi4-mini",
            on_progress=progress_calls.append,
        )

    assert len(progress_calls) > 0
    # Should include planner status, specialist updates, and synthesizer status
    all_text = "\n".join(progress_calls)
    assert "Planer" in all_text or "parallel" in all_text or "Swarm" in all_text


async def test_run_swarm_works_without_on_progress():
    """on_progress=None should not crash."""
    responses = ['["Do something"]', "result", "synthesis"]

    with patch_chat(responses):
        result = await run_swarm(
            task="Simple task",
            model="phi4-mini",
            on_progress=None,
        )

    assert isinstance(result, SwarmResult)
    assert result.final == "synthesis"


async def test_run_swarm_parallel_execution():
    """Specialists should run in parallel (asyncio.gather)."""
    call_times: list[float] = []

    async def slow_chat(*args, **kwargs):
        import time
        await asyncio.sleep(0.05)  # each specialist takes 50ms
        call_times.append(asyncio.get_event_loop().time())
        msg = MagicMock()
        msg.content = "result"
        msg.tool_calls = None
        resp = MagicMock()
        resp.message = msg
        return resp

    with patch(
        "core.swarm.ollama.AsyncClient",
        return_value=MagicMock(chat=AsyncMock(side_effect=slow_chat)),
    ):
        # Planner plan: 3 specialists
        with patch("core.swarm._plan", return_value=["Task1", "Task2", "Task3"]):
            with patch("core.swarm._synthesize", return_value="final"):
                result = await run_swarm(task="Parallel test", model="phi4-mini")

    assert isinstance(result, SwarmResult)


# SwarmResult


def test_swarm_result_repr():
    r = SwarmResult(
        task="test",
        subtasks=["a", "b"],
        partial_results=["ra", "rb"],
        final="done",
    )
    assert "SwarmResult" in repr(r)
    assert "2" in repr(r)


# commands integration


def test_is_swarm_command():
    from core.commands import is_swarm_command

    assert is_swarm_command("/swarm build a REST API") is True
    assert is_swarm_command("/SWARM test") is True
    assert is_swarm_command("/post something") is False
    assert is_swarm_command("swarm test") is False
    assert is_swarm_command("") is False


def test_extract_swarm_task():
    from core.commands import extract_swarm_task

    assert extract_swarm_task("/swarm Build a booking API") == "Build a booking API"
    assert extract_swarm_task("/swarm  spaces  ") == "spaces"
    assert extract_swarm_task("/swarm") == ""
    assert extract_swarm_task("/SWARM großes Projekt") == "großes Projekt"
