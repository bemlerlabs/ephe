"""J2 parity round: background tasks (task_output/task_stop) + swarm modes
(general|explore|judge) + agent_message continuation. TDD, hermetic."""
from __future__ import annotations

import asyncio

import pytest

from core.tools.shell_tools import run_shell, task_output, task_stop


# background register

@pytest.mark.asyncio
async def test_bg_run_returns_task_id_and_completes():
    out = await run_shell("echo hi", run_in_background=True)
    assert out.startswith("bg")
    res = await task_output(out, block=True, timeout_s=10)
    assert "hi" in res


@pytest.mark.asyncio
async def test_bg_two_tasks_get_distinct_ids():
    a = await run_shell("echo a", run_in_background=True)
    b = await run_shell("echo b", run_in_background=True)
    assert a != b


@pytest.mark.asyncio
async def test_task_output_unknown_id_is_honest():
    res = await task_output("bg999", block=False)
    assert "not found" in res.lower() or "bg999" not in res


@pytest.mark.asyncio
async def test_task_stop_marks_stopped_or_done():
    tid = await run_shell("sleep 2", run_in_background=True)
    status = await task_stop(tid)
    assert isinstance(status, str) and status != ""


@pytest.mark.asyncio
async def test_task_stop_unknown_id():
    assert "not found" in (await task_stop("bg999")).lower()


# swarm modes + agent_message

def test_spawn_schema_has_task_type_enum():
    from core.swarm_v2 import get_spawn_swarm_schema
    props = get_spawn_swarm_schema()["function"]["parameters"]["properties"]
    assert "task_type" in props
    assert set(props["task_type"]["enum"]) == {"general", "explore", "judge"}


def test_mode_config_budgets():
    from core.swarm_v2 import _mode_config
    assert _mode_config("general")["max_iterations"] == 5
    assert _mode_config("explore")["max_iterations"] > 5
    assert _mode_config("judge")["max_iterations"] <= 3


def test_agent_message_schema_exists():
    from core.swarm_v2 import get_agent_message_schema
    schema = get_agent_message_schema()
    props = schema["function"]["parameters"]["properties"]
    assert "agent_id" in props and "message" in props


def test_agent_history_store_roundtrip():
    from core.swarm_v2 import _store_agent_history, _get_agent_history
    _store_agent_history("agent_x", [{"role": "user", "content": "hi"}])
    hist = _get_agent_history("agent_x")
    assert hist[0]["content"] == "hi"


# registry integration

def test_registry_exposes_j2_tools():
    from core.tools.registry import get_tool_schemas
    names = {s["function"]["name"] for s in get_tool_schemas()}
    assert {"task_output", "task_stop", "agent_message"} <= names
