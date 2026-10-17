"""
Tests for core/swarm_state.py – shared state store
GWT notation (Given-When-Then)
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from core.swarm_state import (
    AgentStatus,
    SwarmPhase,
    SwarmStateStore,
    AgentState,
    SwarmSession,
)


# Fixtures

@pytest.fixture
def store() -> SwarmStateStore:
    """Fresh store for each test."""
    return SwarmStateStore()


# Session Management

def test_create_session(store: SwarmStateStore):
    """Given empty store When create_session Then session exists with PLANNING phase."""
    swarm_id = store.create_session("Test Task")

    assert swarm_id.startswith("swarm-")
    session = store.get_session(swarm_id)
    assert session is not None
    assert session.task == "Test Task"
    assert session.phase == SwarmPhase.PLANNING


async def test_update_session_phase(store: SwarmStateStore):
    """Given session When update_phase Then phase changes and subscriber notified."""
    events: list[dict] = []
    store.subscribe(events.append)

    swarm_id = store.create_session("Phase Test")
    await store.update_session_phase(swarm_id, SwarmPhase.EXECUTING)

    session = store.get_session(swarm_id)
    assert session.phase == SwarmPhase.EXECUTING

    # Subscriber should have received events
    phase_events = [e for e in events if e.get("type") == "swarm_status"]
    assert len(phase_events) >= 2  # create + update


async def test_session_done_sets_finished_at(store: SwarmStateStore):
    """Given session When phase=DONE Then finished_at is set."""
    swarm_id = store.create_session("Done Test")
    await store.update_session_phase(swarm_id, SwarmPhase.DONE)

    session = store.get_session(swarm_id)
    assert session.finished_at is not None


# Agent Management

def test_register_agent(store: SwarmStateStore):
    """Given session When register_agent Then agent exists with SPAWNED status."""
    swarm_id = store.create_session("Agent Test")
    agent_id = store.register_agent(swarm_id, "researcher", "Find AI trends")

    assert agent_id.startswith("sw-")
    agent = store.get_agent(agent_id)
    assert agent is not None
    assert agent.role == "researcher"
    assert agent.subtask == "Find AI trends"
    assert agent.status == AgentStatus.SPAWNED


async def test_update_agent_status(store: SwarmStateStore):
    """Given spawned agent When update_status(RUNNING) Then status changes + subscriber notified."""
    events: list[dict] = []
    store.subscribe(events.append)

    swarm_id = store.create_session("Status Test")
    agent_id = store.register_agent(swarm_id, "analyzer", "Analyze data")
    await store.update_agent_status(agent_id, AgentStatus.RUNNING, "Processing...")

    agent = store.get_agent(agent_id)
    assert agent.status == AgentStatus.RUNNING
    assert agent.progress_detail == "Processing..."

    progress_events = [e for e in events if e.get("type") == "agent_progress"]
    assert len(progress_events) >= 1
    assert progress_events[0]["status"] == "running"


async def test_set_agent_result(store: SwarmStateStore):
    """Given agent When set_result Then result is stored."""
    swarm_id = store.create_session("Result Test")
    agent_id = store.register_agent(swarm_id, "writer", "Write summary")
    await store.set_agent_result(agent_id, "Here is the summary...")

    agent = store.get_agent(agent_id)
    assert agent.result == "Here is the summary..."


async def test_set_agent_error(store: SwarmStateStore):
    """Given agent When set_error Then status=ERROR + error stored."""
    events: list[dict] = []
    store.subscribe(events.append)

    swarm_id = store.create_session("Error Test")
    agent_id = store.register_agent(swarm_id, "coder", "Fix bug")
    await store.set_agent_error(agent_id, "Connection timeout")

    agent = store.get_agent(agent_id)
    assert agent.status == AgentStatus.ERROR
    assert agent.error == "Connection timeout"
    assert agent.finished_at is not None


async def test_terminate_agent(store: SwarmStateStore):
    """Given running agent When terminate_agent Then status=TERMINATED + event emitted."""
    events: list[dict] = []
    store.subscribe(events.append)

    swarm_id = store.create_session("Terminate Test")
    agent_id = store.register_agent(swarm_id, "researcher", "Research topic")
    await store.set_agent_result(agent_id, "Research complete")
    await store.terminate_agent(agent_id)

    agent = store.get_agent(agent_id)
    assert agent.status == AgentStatus.TERMINATED
    assert agent.finished_at is not None

    term_events = [e for e in events if e.get("type") == "agent_terminated"]
    assert len(term_events) == 1


# Multi-Agent Queries

def test_get_all_agents(store: SwarmStateStore):
    """Given session with 3 agents When get_all_agents Then returns all 3."""
    swarm_id = store.create_session("Multi Test")
    store.register_agent(swarm_id, "a", "Task A")
    store.register_agent(swarm_id, "b", "Task B")
    store.register_agent(swarm_id, "c", "Task C")

    agents = store.get_all_agents(swarm_id)
    assert len(agents) == 3


async def test_all_agents_finished(store: SwarmStateStore):
    """Given 3 agents When all DONE/TERMINATED Then all_agents_finished=True."""
    swarm_id = store.create_session("Finished Test")
    a1 = store.register_agent(swarm_id, "a", "T1")
    a2 = store.register_agent(swarm_id, "b", "T2")
    a3 = store.register_agent(swarm_id, "c", "T3")

    assert store.all_agents_finished(swarm_id) is False

    await store.update_agent_status(a1, AgentStatus.DONE)
    await store.update_agent_status(a2, AgentStatus.TERMINATED)
    await store.update_agent_status(a3, AgentStatus.ERROR)

    assert store.all_agents_finished(swarm_id) is True


# Pub/Sub

def test_subscribe_unsubscribe(store: SwarmStateStore):
    """Given subscriber When unsubscribe Then no more events."""
    events: list[dict] = []
    cb = lambda e: events.append(e)
    store.subscribe(cb)

    store.create_session("Sub Test 1")
    assert len(events) > 0

    count_before = len(events)
    store.unsubscribe(cb)
    store.create_session("Sub Test 2")
    assert len(events) == count_before  # No new events


def test_subscriber_exception_doesnt_crash(store: SwarmStateStore):
    """Given faulty subscriber When event emitted Then no crash."""
    def bad_callback(event: dict) -> None:
        raise RuntimeError("Subscriber crashed")

    store.subscribe(bad_callback)
    # Should not raise
    swarm_id = store.create_session("Crash Test")
    assert swarm_id is not None


# Cleanup

async def test_cleanup_session(store: SwarmStateStore):
    """Given session with agents When cleanup_session Then all data removed."""
    swarm_id = store.create_session("Cleanup Test")
    a1 = store.register_agent(swarm_id, "a", "T1")
    a2 = store.register_agent(swarm_id, "b", "T2")

    await store.cleanup_session(swarm_id)

    assert store.get_session(swarm_id) is None
    assert store.get_agent(a1) is None
    assert store.get_agent(a2) is None


# Tool Tracking

async def test_add_tool_used(store: SwarmStateStore):
    """Given agent When add_tool_used Then tool is tracked (no duplicates)."""
    swarm_id = store.create_session("Tool Test")
    agent_id = store.register_agent(swarm_id, "researcher", "Search")

    await store.add_tool_used(agent_id, "web_search")
    await store.add_tool_used(agent_id, "browser_go")
    await store.add_tool_used(agent_id, "web_search")  # duplicate

    agent = store.get_agent(agent_id)
    assert agent.tools_used == ["web_search", "browser_go"]


# Stats

def test_get_stats(store: SwarmStateStore):
    """Given store with data When get_stats Then returns counts."""
    swarm_id = store.create_session("Stats Test")
    store.register_agent(swarm_id, "a", "T1")
    store.register_agent(swarm_id, "b", "T2")

    stats = store.get_stats()
    assert stats["sessions"] == 1
    assert stats["agents"] == 2


# T-09: SQLite backend (phase 3 persistence)

def test_sqlite_backend_survives_reinstantiation(tmp_path):
    """
    GIVEN a SwarmStateStore with a SQLite db_path
    WHEN a session is created and the store is instantiated again
    THEN the session is still retrievable (persistence across a restart)
    """
    db_path = str(tmp_path / "swarm.db")

    store1 = SwarmStateStore(db_path=db_path)
    swarm_id = store1.create_session("Persistent Task")
    del store1  # simulate a crash / a restart

    store2 = SwarmStateStore(db_path=db_path)
    session = store2.get_session(swarm_id)
    assert session is not None
    assert session.task == "Persistent Task"


def test_sqlite_agent_survives_reinstantiation(tmp_path):
    """
    GIVEN an agent registered in the SQLite store
    WHEN the store is instantiated again
    THEN the agent is still retrievable
    """
    db_path = str(tmp_path / "swarm.db")

    store1 = SwarmStateStore(db_path=db_path)
    swarm_id = store1.create_session("Agent Persist Test")
    agent_id = store1.register_agent(swarm_id, "researcher", "Datei analysieren")
    del store1

    store2 = SwarmStateStore(db_path=db_path)
    agent = store2.get_agent(agent_id)
    assert agent is not None
    assert agent.role == "researcher"
    assert agent.subtask == "Datei analysieren"


def test_in_memory_default_backwards_compatible():
    """
    GIVEN no db_path
    WHEN SwarmStateStore() is instantiated
    THEN it behaves as before (full backwards compatibility)
    """
    store = SwarmStateStore()  # no argument
    swarm_id = store.create_session("In-Memory Task")
    assert store.get_session(swarm_id) is not None
    agent_id = store.register_agent(swarm_id, "worker", "Task")
    assert store.get_agent(agent_id) is not None


# T-10: budget tracker (phase 3 governance)

from core.swarm_state import BudgetExceededError  # noqa: E402 — added once it turns green


def test_budget_tracker_blocks_spawn_when_exceeded():
    """
    GIVEN token_budget=1000
    WHEN 1001 tokens are consumed
    THEN register_agent raises BudgetExceededError
    """
    store = SwarmStateStore(token_budget=1000)
    swarm_id = store.create_session("Budget Test")

    store.record_tokens(swarm_id, 1001)  # budget exceeded

    with pytest.raises(BudgetExceededError):
        store.register_agent(swarm_id, "researcher", "Task")


def test_budget_tracker_allows_spawn_within_budget():
    """
    GIVEN token_budget=1000
    WHEN 999 tokens are consumed
    THEN register_agent works without an error
    """
    store = SwarmStateStore(token_budget=1000)
    swarm_id = store.create_session("Budget OK")

    store.record_tokens(swarm_id, 999)
    agent_id = store.register_agent(swarm_id, "researcher", "Task")
    assert agent_id is not None


def test_budget_report_contains_per_agent_stats():
    """
    GIVEN 2 agents each using 100 tokens
    WHEN get_budget_report() is called
    THEN: total=200, per-agent breakdown correct
    """
    store = SwarmStateStore()
    swarm_id = store.create_session("Report Test")
    a1 = store.register_agent(swarm_id, "a", "T1")
    a2 = store.register_agent(swarm_id, "b", "T2")

    store.record_tokens(swarm_id, 100, agent_id=a1)
    store.record_tokens(swarm_id, 100, agent_id=a2)

    report = store.get_budget_report(swarm_id)
    assert report["total_tokens"] == 200
    assert report["per_agent"][a1] == 100
    assert report["per_agent"][a2] == 100


def test_budget_report_no_budget_set():
    """
    GIVEN no token_budget set
    WHEN get_budget_report() is called
    THEN budget_limit is None, total_tokens correct
    """
    store = SwarmStateStore()
    swarm_id = store.create_session("Unbounded")
    a1 = store.register_agent(swarm_id, "worker", "T")
    store.record_tokens(swarm_id, 50, agent_id=a1)

    report = store.get_budget_report(swarm_id)
    assert report["total_tokens"] == 50
    assert report["budget_limit"] is None


# T-12: add_tool_used deduplication under concurrency

async def test_concurrent_add_tool_used_no_duplicates(store: SwarmStateStore):
    """
    GIVEN two asyncio tasks call add_tool_used(web_search) at the same time
    WHEN the lock engages correctly
    THEN 'web_search' appears only once in tools_used
    """
    swarm_id = store.create_session("Concurrent")
    agent_id = store.register_agent(swarm_id, "a", "T")

    await asyncio.gather(
        store.add_tool_used(agent_id, "web_search"),
        store.add_tool_used(agent_id, "web_search"),
    )

    agent = store.get_agent(agent_id)
    assert agent.tools_used.count("web_search") == 1


# T-14: budget SSE event — budget_exceeded pub/sub

def test_budget_exceeded_emits_event():
    """
    GIVEN token_budget=500
    WHEN 501 tokens are recorded
    THEN a budget_exceeded event is emitted to every subscriber
    """
    events = []
    store = SwarmStateStore(token_budget=500)
    store.subscribe(events.append)
    swarm_id = store.create_session("Budget event test")

    store.record_tokens(swarm_id, 501)

    budget_events = [e for e in events if e.get("type") == "budget_exceeded"]
    assert len(budget_events) == 1
    assert budget_events[0]["swarm_id"] == swarm_id
    assert budget_events[0]["tokens_used"] == 501
    assert budget_events[0]["budget"] == 500


def test_budget_event_not_emitted_within_budget():
    """
    GIVEN token_budget=500
    WHEN 499 tokens are recorded
    THEN no budget_exceeded event
    """
    events = []
    store = SwarmStateStore(token_budget=500)
    store.subscribe(events.append)
    swarm_id = store.create_session("Within budget")

    store.record_tokens(swarm_id, 499)

    budget_events = [e for e in events if e.get("type") == "budget_exceeded"]
    assert len(budget_events) == 0


def test_budget_event_emitted_only_once():
    """
    GIVEN token_budget=500
    WHEN record_tokens is called twice (300 tokens each)
    THEN budget_exceeded is emitted exactly once (no spam on follow-up calls)
    """
    events = []
    store = SwarmStateStore(token_budget=500)
    store.subscribe(events.append)
    swarm_id = store.create_session("Once only")

    store.record_tokens(swarm_id, 300)  # 300 — still OK
    store.record_tokens(swarm_id, 300)  # 600 — exceeded → event

    budget_events = [e for e in events if e.get("type") == "budget_exceeded"]
    assert len(budget_events) == 1  # no duplicate event
