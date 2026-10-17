"""
Tests for core/swarm_v2.py – Swarm Engine V2
GWT-Notation (Given-When-Then)
"""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.swarm_v2 import (
    SwarmAgent,
    SwarmOrchestrator,
    SwarmV2Result,
    run_swarm_v2,
    get_spawn_swarm_schema,
    get_terminate_self_schema,
    MAX_SWARM_AGENTS,
)
from core.swarm_state import (
    AgentStatus,
    SwarmPhase,
    SwarmStateStore,
)


# Helpers

def mock_chat_response(content: str = "", tool_calls: list | None = None):
    """Build a mock ollama chat response."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    resp = MagicMock()
    resp.message = msg
    # Also support dict-style access for synthesizer
    resp.__getitem__ = lambda self, key: {"message": {"content": content}}[key]
    return resp


def mock_spawn_tool_call(count: int, role: str, subtasks: list[str]):
    """A tool call named spawn_swarm, carrying count/role/subtasks in arguments."""
    tc = MagicMock()
    tc.function.name = "spawn_swarm"
    tc.function.arguments = {
        "count": count,
        "role": role,
        "subtasks": subtasks,
    }
    return tc


def mock_terminate_tool_call():
    """A tool call named terminate_self with empty arguments."""
    tc = MagicMock()
    tc.function.name = "terminate_self"
    tc.function.arguments = {}
    return tc


# Tool Schemas

def test_spawn_swarm_schema_is_valid():
    """Given spawn_swarm schema When accessed Then has correct structure."""
    schema = get_spawn_swarm_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "spawn_swarm"
    params = schema["function"]["parameters"]
    assert "count" in params["properties"]
    assert "role" in params["properties"]
    assert "subtasks" in params["properties"]
    assert params["required"] == ["count", "role", "subtasks"]


def test_terminate_self_schema_is_valid():
    """Given terminate_self schema When accessed Then has correct structure."""
    schema = get_terminate_self_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "terminate_self"


# SwarmV2Result

def test_swarm_v2_result_repr():
    """Given SwarmV2Result When repr Then shows key info."""
    r = SwarmV2Result(
        swarm_id="swarm-abc123",
        task="Test Task",
        subtasks=["A", "B", "C"],
        agent_results=["r1", "r2", "r3"],
        final="Combined result",
    )
    assert "swarm-abc123" in repr(r)
    assert "3" in repr(r)


# T-01: Synthesizer — Pydantic object (no dict access)

async def test_synthesizer_works_with_pydantic_object():
    """
    GIVEN Ollama ≥ 0.4 returns a Pydantic object (not a dict)
    WHEN _synthesize() is called
    THEN the content is extracted correctly, without a TypeError.

    This test FAILS as long as response["message"]["content"]
    stands on line 585 of swarm_v2.py — because a MagicMock without
    __getitem__ raises a TypeError.
    """
    store = SwarmStateStore()
    orch = SwarmOrchestrator(
        task="Analysiere KI-Trends",
        model="test-model",
        state_store=store,
    )
    orch.swarm_id = store.create_session("Analysiere KI-Trends")

    # real Pydantic style: attribute access, NO dict access
    pydantic_response = MagicMock(spec=[])  # spec=[] → no __getitem__!
    pydantic_response.message = MagicMock(spec=[])
    pydantic_response.message.content = "Synthese: KI-Trends 2026 zusammengefasst."

    with patch("core.swarm_v2.ollama.AsyncClient") as MockClient:
        MockClient.return_value.chat = AsyncMock(return_value=pydantic_response)
        result = await orch._synthesize(
            subtasks=["Trend 1", "Trend 2"],
            results=["Ergebnis 1", "Ergebnis 2"],
        )

    assert result == "Synthese: KI-Trends 2026 zusammengefasst."
    assert isinstance(result, str)


# SwarmOrchestrator – Manager Direct Answer

async def test_orchestrator_manager_answers_directly():
    """
    Given a simple task
    When Manager decides NOT to spawn
    Then SwarmV2Result has direct answer, no subtasks.
    """
    store = SwarmStateStore()
    events: list[dict] = []

    # Manager returns a direct answer (no tool calls)
    manager_response = mock_chat_response("This is a simple answer.")

    with patch("core.swarm_v2.ollama.AsyncClient") as MockClient:
        client = MockClient.return_value
        client.chat = AsyncMock(return_value=manager_response)

        result = await run_swarm_v2(
            task="What is 2+2?",
            model="test-model",
            on_event=events.append,
            state_store=store,
        )

    assert isinstance(result, SwarmV2Result)
    assert result.subtasks == []
    assert result.final == "This is a simple answer."


# SwarmOrchestrator – Full Pipeline

async def test_orchestrator_spawn_and_synthesize():
    """
    Given a complex task
    When Manager spawns 2 agents
    Then agents run parallel → synthesizer combines results.
    """
    store = SwarmStateStore()
    events: list[dict] = []

    # 1. Manager spawns 2 agents
    spawn_tc = mock_spawn_tool_call(2, "researcher", ["Sub A", "Sub B"])
    manager_response = mock_chat_response("", tool_calls=[spawn_tc])

    # 2. Specialist responses (no tool calls, direct answers)
    specialist_response = mock_chat_response("Specialist result here.")

    # 3. Synthesizer response
    synth_response = {"message": {"content": "Combined final answer."}}

    call_count = 0

    async def multi_chat(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # Manager
            return manager_response
        elif call_count <= 3:  # 2 specialists
            return specialist_response
        else:  # Synthesizer
            return synth_response

    with patch("core.swarm_v2.ollama.AsyncClient") as MockClient:
        client = MockClient.return_value
        client.chat = AsyncMock(side_effect=multi_chat)

        result = await run_swarm_v2(
            task="Research 2 topics",
            model="test-model",
            on_event=events.append,
            state_store=store,
        )

    assert isinstance(result, SwarmV2Result)
    assert len(result.subtasks) == 2
    assert len(result.agent_results) == 2
    assert result.final == "Combined final answer."

    # SSE events should include swarm lifecycle
    event_types = [e.get("type") for e in events]
    assert "swarm_status" in event_types
    assert "agent_spawned" in event_types
    assert "swarm_done" in event_types


# SwarmOrchestrator – Max Agents Cap

async def test_orchestrator_caps_agents_at_max():
    """
    Given Manager spawns 15 agents
    When Orchestrator processes
    Then capped at MAX_SWARM_AGENTS.
    """
    store = SwarmStateStore()

    subtasks = [f"Task {i}" for i in range(15)]
    spawn_tc = mock_spawn_tool_call(15, "analyzer", subtasks)
    manager_response = mock_chat_response("", tool_calls=[spawn_tc])
    specialist_response = mock_chat_response("Result")
    synth_response = {"message": {"content": "Synthesized."}}

    call_count = 0

    async def multi_chat(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return manager_response
        elif call_count <= 1 + MAX_SWARM_AGENTS:
            return specialist_response
        else:
            return synth_response

    with patch("core.swarm_v2.ollama.AsyncClient") as MockClient:
        client = MockClient.return_value
        client.chat = AsyncMock(side_effect=multi_chat)

        result = await run_swarm_v2(
            task="Huge task",
            model="test-model",
            state_store=store,
        )

    assert len(result.subtasks) <= MAX_SWARM_AGENTS


# SwarmAgent – Terminate Self

async def test_agent_terminate_self():
    """
    Given agent running
    When agent calls terminate_self
    Then agent terminates cleanly with result.
    """
    store = SwarmStateStore()
    swarm_id = store.create_session("Test")
    agent_id = store.register_agent(swarm_id, "tester", "Test task")

    # First response: assistant message with content
    first_response = mock_chat_response("Here is my answer.")
    # Override: agent calls terminate_self
    term_tc = mock_terminate_tool_call()
    term_response = mock_chat_response("", tool_calls=[term_tc])

    call_count = 0

    async def multi_chat(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return term_response
        return first_response

    with patch("core.swarm_v2.ollama.AsyncClient") as MockClient:
        client = MockClient.return_value
        client.chat = AsyncMock(side_effect=multi_chat)

        agent = SwarmAgent(
            agent_id=agent_id,
            role="tester",
            subtask="Test task",
            main_task="Main Task",
            model="test-model",
            state_store=store,
            swarm_id=swarm_id,
        )
        result = await agent.run()

    agent_state = store.get_agent(agent_id)
    assert agent_state.status == AgentStatus.TERMINATED


# SwarmAgent – Error Handling

async def test_agent_handles_timeout():
    """
    Given agent
    When Ollama times out
    Then agent returns error message, status=ERROR.
    """
    store = SwarmStateStore()
    swarm_id = store.create_session("Timeout Test")
    agent_id = store.register_agent(swarm_id, "slow", "Slow task")

    async def slow_chat(*args, **kwargs):
        await asyncio.sleep(999)

    with patch("core.swarm_v2.ollama.AsyncClient") as MockClient:
        client = MockClient.return_value
        client.chat = AsyncMock(side_effect=slow_chat)

        with patch("core.swarm_v2.AGENT_TIMEOUT", 0.1):
            agent = SwarmAgent(
                agent_id=agent_id,
                role="slow",
                subtask="Slow task",
                main_task="Main Task",
                model="test-model",
                state_store=store,
                swarm_id=swarm_id,
            )
            result = await agent.run()

    assert "Timeout" in result.summary
    agent_state = store.get_agent(agent_id)
    assert agent_state.status == AgentStatus.ERROR


async def test_agent_handles_exception():
    """
    Given agent
    When Ollama raises exception
    Then agent returns error, status=ERROR.
    """
    store = SwarmStateStore()
    swarm_id = store.create_session("Exception Test")
    agent_id = store.register_agent(swarm_id, "crasher", "Crash task")

    async def crashing_chat(*args, **kwargs):
        raise RuntimeError("Connection reset")

    with patch("core.swarm_v2.ollama.AsyncClient") as MockClient:
        client = MockClient.return_value
        client.chat = AsyncMock(side_effect=crashing_chat)

        agent = SwarmAgent(
            agent_id=agent_id,
            role="crasher",
            subtask="Crash task",
            main_task="Test",
            model="test-model",
            state_store=store,
            swarm_id=swarm_id,
        )
        result = await agent.run()

    assert "Fehler" in result.summary or "Connection" in result.summary
    agent_state = store.get_agent(agent_id)
    assert agent_state.status == AgentStatus.ERROR


# SwarmAgent – Tool Whitelist

async def test_agent_blocks_shell():
    """
    Given agent
    When LLM calls run_shell
    Then tool is blocked with message.
    """
    store = SwarmStateStore()
    swarm_id = store.create_session("Shell Test")
    agent_id = store.register_agent(swarm_id, "hacker", "Hack things")

    # First call: LLM wants run_shell
    shell_tc = MagicMock()
    shell_tc.function.name = "run_shell"
    shell_tc.function.arguments = {"command": "rm -rf /"}
    shell_response = mock_chat_response("", tool_calls=[shell_tc])

    # Second call: LLM gives up
    final_response = mock_chat_response("OK, I won't run shell.")

    call_count = 0

    async def multi_chat(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return shell_response
        return final_response

    with patch("core.swarm_v2.ollama.AsyncClient") as MockClient:
        client = MockClient.return_value
        client.chat = AsyncMock(side_effect=multi_chat)

        agent = SwarmAgent(
            agent_id=agent_id,
            role="hacker",
            subtask="Hack things",
            main_task="Test",
            model="test-model",
            state_store=store,
            swarm_id=swarm_id,
        )
        result = await agent.run()

    # Shell was blocked, Agent finished gracefully
    assert "rm -rf" not in result.as_text()


# S5: envelope parity (schema fields, cap, status)

def test_envelope_schema_fields():
    from core.swarm_v2 import SwarmEnvelope, _make_envelope, ENVELOPE_SUMMARY_CAP
    env = _make_envelope("a1", "Zeile1\nZeile2", trace_id="t", run_id="r",
                         task_spec_hash="h")
    assert isinstance(env, SwarmEnvelope)
    assert env.agent_id == "a1"
    assert env.status == "ok"
    assert env.trace_id == "t" and env.run_id == "r" and env.task_spec_hash == "h"
    assert env.facts == ["Zeile1", "Zeile2"]
    # Cap: long text → summary truncated, status=budget_exceeded
    big = "x" * (ENVELOPE_SUMMARY_CAP + 100)
    env2 = _make_envelope("a2", big)
    assert len(env2.summary) == ENVELOPE_SUMMARY_CAP
    assert env2.status == "budget_exceeded"


def test_task_spec_hash_stable():
    from core.swarm_v2 import _task_spec_hash
    assert _task_spec_hash("abc") == _task_spec_hash("abc")
    assert _task_spec_hash("abc") != _task_spec_hash("abd")
    assert len(_task_spec_hash("abc")) == 12


# Orchestrator – Agent Crash Resilience

async def test_orchestrator_survives_agent_crash():
    """
    Given 3 agents
    When one agent crashes
    Then other agents still complete, final result includes error.
    """
    store = SwarmStateStore()
    events: list[dict] = []

    spawn_tc = mock_spawn_tool_call(3, "worker", ["T1", "T2", "T3"])
    manager_response = mock_chat_response("", tool_calls=[spawn_tc])

    call_count = 0

    async def multi_chat(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # Manager
            return manager_response
        elif call_count == 2:  # Agent 1: OK
            return mock_chat_response("Agent 1 result")
        elif call_count == 3:  # Agent 2: CRASH
            raise RuntimeError("Agent 2 exploded")
        elif call_count == 4:  # Agent 3: OK
            return mock_chat_response("Agent 3 result")
        else:  # Synthesizer
            return {"message": {"content": "Final despite crash."}}

    with patch("core.swarm_v2.ollama.AsyncClient") as MockClient:
        client = MockClient.return_value
        client.chat = AsyncMock(side_effect=multi_chat)

        result = await run_swarm_v2(
            task="Resilience test",
            model="test-model",
            on_event=events.append,
            state_store=store,
        )

    assert isinstance(result, SwarmV2Result)
    assert len(result.agent_results) == 3
    # One result should contain error info
    error_results = [r for r in result.agent_results if "Fehler" in r or "Error" in r or "exploded" in r]
    assert len(error_results) >= 1
    # Final still exists
    assert result.final == "Final despite crash."


# SSE Events Completeness

async def test_full_pipeline_emits_all_events():
    """
    Given full swarm pipeline
    When completed
    Then all expected SSE event types emitted.
    """
    store = SwarmStateStore()
    events: list[dict] = []

    spawn_tc = mock_spawn_tool_call(2, "analyzer", ["Analyze X", "Analyze Y"])
    manager_response = mock_chat_response("", tool_calls=[spawn_tc])
    specialist_response = mock_chat_response("Analysis complete.")
    synth_response = {"message": {"content": "Summary of XY."}}

    call_count = 0

    async def multi_chat(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return manager_response
        elif call_count <= 3:
            return specialist_response
        else:
            return synth_response

    with patch("core.swarm_v2.ollama.AsyncClient") as MockClient:
        client = MockClient.return_value
        client.chat = AsyncMock(side_effect=multi_chat)

        await run_swarm_v2(
            task="Full pipeline",
            model="test-model",
            on_event=events.append,
            state_store=store,
        )

    event_types = set(e.get("type") for e in events)
    assert "swarm_status" in event_types
    assert "agent_spawned" in event_types
    assert "agent_progress" in event_types
    assert "swarm_done" in event_types


# Commands Integration

def test_swarm_command_recognized():
    """Given /swarm command When is_swarm_command Then True."""
    from core.commands import is_swarm_command, extract_swarm_task

    assert is_swarm_command("/swarm Analysiere 3 Trends")
    assert extract_swarm_task("/swarm Analysiere 3 Trends") == "Analysiere 3 Trends"
    assert not is_swarm_command("/post something")
