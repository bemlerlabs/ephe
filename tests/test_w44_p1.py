"""tests/test_w44_p1.py — wave 44 P1 regression (Deep-Audit 2026-09-16).

P1a: run_shell in the agent tool loop passes the model cwd through to
     execute_confirmed_shell (before: only 'command', the cwd was lost).
RULE: tests BEFORE the implementation (TDD).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_ollama_response(content: str = "", tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    response = MagicMock()
    response.message = msg
    return response


def _make_tool_call(name: str, arguments: dict):
    func = MagicMock()
    func.name = name
    func.arguments = arguments
    tc = MagicMock()
    tc.function = func
    return tc


@pytest.mark.asyncio
async def test_p1a_run_shell_threads_model_cwd_in_agent_loop():
    """GIVEN the model calls run_shell with command AND cwd
    WHEN chat_with_tools walks the shell branch (on_shell_confirm approved)
    THEN execute_confirmed_shell receives the cwd passed through from args.
    """
    from core.chat import chat_with_tools

    tool_call = _make_tool_call(
        "run_shell", {"command": "ls", "cwd": "/tmp/probe"}
    )
    first = _make_ollama_response(tool_calls=[tool_call])
    final = _make_ollama_response(content="fertig")

    async def approve(command: str) -> bool:
        return True

    with patch("core.chat.ollama.AsyncClient") as MockClient, patch(
        "core.chat.execute_confirmed_shell",
        new=AsyncMock(return_value="ok"),
    ) as mock_exec:
        client = AsyncMock()
        client.chat = AsyncMock(side_effect=[first, final])
        MockClient.return_value = client

        await chat_with_tools(
            model="gemma4:12b",
            history=[{"role": "user", "content": "list mal"}],
            on_chunk=lambda c: None,
            allowed_tool_names=["run_shell"],
            on_shell_confirm=approve,
        )

    # cwd must be passed through as a keyword (not only command positionally).
    mock_exec.assert_awaited_once()
    _, kwargs = mock_exec.call_args
    assert kwargs.get("cwd") == "/tmp/probe", (
        f"run_shell-cwd ging verloren: kwargs={kwargs}"
    )


@pytest.mark.asyncio
async def test_p1a_run_shell_without_cwd_still_works():
    """GIVEN run_shell without a cwd field
    WHEN the agent loop runs
    THEN cwd is passed through as None (workspace-root fallback, no crash)."""
    from core.chat import chat_with_tools

    tool_call = _make_tool_call("run_shell", {"command": "pwd"})
    first = _make_ollama_response(tool_calls=[tool_call])
    final = _make_ollama_response(content="fertig")

    async def approve(command: str) -> bool:
        return True

    with patch("core.chat.ollama.AsyncClient") as MockClient, patch(
        "core.chat.execute_confirmed_shell",
        new=AsyncMock(return_value="ok"),
    ) as mock_exec:
        client = AsyncMock()
        client.chat = AsyncMock(side_effect=[first, final])
        MockClient.return_value = client

        await chat_with_tools(
            model="gemma4:12b",
            history=[{"role": "user", "content": "pwd"}],
            on_chunk=lambda c: None,
            allowed_tool_names=["run_shell"],
            on_shell_confirm=approve,
        )

    mock_exec.assert_awaited_once()
    _, kwargs = mock_exec.call_args
    assert kwargs.get("cwd") is None
