"""
tests/test_finding_08_swarm_tool_calling.py

Finding 8: Swarm specialists had no tool-calling capability.
Fix: _call_model() now accepts use_tools=True and executes tool calls.

Given-When-Then Tests:
  1. GIVEN use_tools=False WHEN _call_model() THEN no tools kwarg passed
  2. GIVEN use_tools=True WHEN _call_model() THEN tools schema is passed
  3. GIVEN LLM returns tool call WHEN use_tools=True THEN tool is executed and result fed back
  4. GIVEN _run_specialist() WHEN called THEN uses tools (use_tools=True)
  5. GIVEN _plan() WHEN called THEN does NOT use tools (pure reasoning)
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest


# Test 1: GIVEN no tools WHEN call_model THEN tools not in kwargs

@pytest.mark.asyncio
async def test_given_no_tools_when_call_model_then_no_tools_kwarg():
    """GIVEN use_tools=False WHEN _call_model() THEN tools not passed to chat()."""
    from core.swarm import _call_model

    mock_response = MagicMock()
    mock_response.message.content = "Test answer"
    mock_response.message.tool_calls = None

    mock_client = MagicMock()
    mock_client.chat = AsyncMock(return_value=mock_response)

    with patch("core.swarm._make_client", return_value=mock_client):
        result = await _call_model("sys", "user", "model", use_tools=False)

    chat_kwargs = mock_client.chat.call_args
    assert "tools" not in chat_kwargs.kwargs, "tools should NOT be in kwargs when use_tools=False"
    assert result == "Test answer"


# Test 2: GIVEN tools WHEN call_model THEN tools schema passed

@pytest.mark.asyncio
async def test_given_tools_when_call_model_then_tools_schema_passed():
    """GIVEN use_tools=True WHEN _call_model() THEN tools schema is passed to chat()."""
    from core.swarm import _call_model

    mock_response = MagicMock()
    mock_response.message.content = "Test answer"
    mock_response.message.tool_calls = None

    mock_client = MagicMock()
    mock_client.chat = AsyncMock(return_value=mock_response)

    fake_schemas = [{"type": "function", "function": {"name": "web_search"}}]

    with patch("core.swarm._make_client", return_value=mock_client), \
         patch("core.tools.get_tool_schemas", return_value=fake_schemas):
        result = await _call_model("sys", "user", "model", use_tools=True)

    chat_kwargs = mock_client.chat.call_args.kwargs
    assert "tools" in chat_kwargs, "tools should be in kwargs when use_tools=True"
    assert chat_kwargs["tools"] == fake_schemas


# Test 3: GIVEN tool call returned WHEN use_tools THEN tool executed

@pytest.mark.asyncio
async def test_given_tool_call_when_use_tools_then_tool_executed():
    """GIVEN LLM returns a tool call WHEN use_tools=True THEN execute_tool is called."""
    from core.swarm import _call_model

    # First response: LLM asks for tool
    mock_tool_call = MagicMock()
    mock_tool_call.function.name = "web_search"
    mock_tool_call.function.arguments = {"query": "test"}

    first_response = MagicMock()
    first_response.message.content = ""
    first_response.message.tool_calls = [mock_tool_call]

    # Second response: after tool result
    second_response = MagicMock()
    second_response.message.content = "Final answer with search results"

    mock_client = MagicMock()
    mock_client.chat = AsyncMock(side_effect=[first_response, second_response])

    with patch("core.swarm._make_client", return_value=mock_client), \
         patch("core.tools.get_tool_schemas", return_value=[]), \
         patch("core.tools.execute_tool", new_callable=AsyncMock, return_value="search results"):
        result = await _call_model("sys", "user", "model", use_tools=True)

    assert result == "Final answer with search results"
    assert mock_client.chat.call_count == 2  # Initial + followup


# Test 4: GIVEN _run_specialist WHEN called THEN use_tools=True

@pytest.mark.asyncio
async def test_given_run_specialist_when_called_then_uses_tools():
    """GIVEN _run_specialist() WHEN called THEN passes use_tools=True to _call_model."""
    from core.swarm import _run_specialist

    with patch("core.swarm._call_model", new_callable=AsyncMock, return_value="done") as mock_call:
        await _run_specialist("subtask", "main task", "model", 0, None)

    mock_call.assert_called_once()
    _, kwargs = mock_call.call_args
    assert kwargs.get("use_tools") is True or mock_call.call_args[0][-1] is True


# Test 5: GIVEN _plan WHEN called THEN no tools (pure reasoning)

@pytest.mark.asyncio
async def test_given_plan_when_called_then_no_tools():
    """GIVEN _plan() WHEN called THEN _call_model use_tools defaults to False."""
    from core.swarm import _plan

    with patch("core.swarm._call_model", new_callable=AsyncMock, return_value='["task1"]') as mock_call:
        await _plan("main task", "model")

    mock_call.assert_called_once()
    # _plan does not pass use_tools, so it defaults to False
    call_args = mock_call.call_args
    if len(call_args.args) > 3:
        assert call_args.args[3] is False or call_args.args[3] is not True
    else:
        assert call_args.kwargs.get("use_tools", False) is False


@pytest.mark.asyncio
async def test_given_specialist_with_tools_when_called_then_only_the_core_landscape():
    """Wave 3 covered only the main path: a specialist got the full registry.

    The specialist should see the same core as the main agent — the rare tools
    reach it through tool_search, not through 4 400 tokens of preview load.
    """
    from core.swarm import _call_model
    from core.tools import get_tool_schemas
    from core.tools.discovery import CORE_TOOLS

    mock_response = MagicMock()
    mock_response.message.content = "fertig"
    mock_response.message.tool_calls = None
    mock_client = MagicMock()
    mock_client.chat = AsyncMock(return_value=mock_response)

    with patch("core.swarm._make_client", return_value=mock_client):
        await _call_model("sys", "user", "model", use_tools=True)

    passed = mock_client.chat.call_args.kwargs["tools"]
    names = {t["function"]["name"] for t in passed}
    assert names == set(CORE_TOOLS) & {t["function"]["name"] for t in get_tool_schemas()}
    assert len(passed) < len(get_tool_schemas()), "der Specialist sieht die volle Landschaft"
    assert {"tool_search", "tool_describe", "tool_call"} <= names
