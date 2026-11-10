"""◑ Ephe · TDD — an iterative team: the leader reads reports and gives the next order.

The four shipped orchestrations run one cycle. `leader` plans, members run once,
the leader summarizes. The owner's team keeps going: a member reports back, the
leader reads it and issues the next instruction to a named member, until the
leader says done. This adds an `iterative` orchestration that loops on a structured
leader decision, bounded by a real iteration cap, and terminates fail-safe when the
decision cannot be read.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import agent_store, agent_teams  # noqa: E402


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    root = tmp_path / "cfg"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(root))
    return root


def _agent(name: str):
    return agent_store.create_agent(
        {
            "name": name,
            "description": f"{name} description",
            "tools": ["read_file", "file_search"],
            "instructions": f"You are {name}.",
        }
    )


def _iterative_team(name="Loop crew", **budget):
    leader = _agent(f"{name} lead")
    member_a = _agent(f"{name} a")
    member_b = _agent(f"{name} b")
    return agent_teams.create_team(
        {
            "name": name,
            "description": "test team",
            "instructions": "Work together.",
            "leader_id": leader["id"],
            "member_ids": [member_a["id"], member_b["id"]],
            "orchestration": "iterative",
            "model_policy": "inherit",
            "budget": {"max_rounds": 4, "wall_timeout": 60, **budget},
        }
    )


class SeqSubagent:
    """A helper double whose report advances per call for each role."""

    calls: list[dict] = []
    reports: dict[str, list[str]] = {}
    cursors: dict[str, int] = {}

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.agent_id = kwargs["agent_id"]
        self.model = kwargs.get("model")
        SeqSubagent.calls.append(kwargs)

    async def run(self):
        role = self.kwargs["role"]
        seq = SeqSubagent.reports.get(role, [f"{role} report"])
        i = SeqSubagent.cursors.get(role, 0)
        SeqSubagent.cursors[role] = i + 1
        report = seq[min(i, len(seq) - 1)]

        class R:
            status = "ok"
            tool_calls: list = []

        R.report = report
        return R()


@pytest.fixture
def seq_subagent(monkeypatch):
    import core.subagent as subagent_mod

    SeqSubagent.calls = []
    SeqSubagent.reports = {}
    SeqSubagent.cursors = {}
    monkeypatch.setattr(subagent_mod, "Subagent", SeqSubagent)
    return SeqSubagent


def _member_calls(fake, role):
    return [c for c in fake.calls if c["role"] == role]


def test_schema_accepts_iterative_and_bounds_the_iteration_cap(cfg):
    """GIVEN an iterative team WHEN it is created THEN the orchestration is accepted
    and the iteration cap is bounded."""
    team = _iterative_team(max_iterations=3)
    assert team["orchestration"] == "iterative"
    assert team["budget"]["max_iterations"] == 3

    over = _iterative_team("Over crew", max_iterations=999)
    assert over["budget"]["max_iterations"] <= 8


def test_the_leader_continues_a_named_member_then_finishes(cfg, seq_subagent):
    """GIVEN members that report once and a leader that orders one more round
    WHEN the team runs
    THEN the named member runs again with the leader's instruction and the loop ends."""
    team = _iterative_team()
    lead = f"{team['name']} lead"
    target = f"{team['name']} a"
    seq_subagent.reports[lead] = [
        json.dumps({"action": "continue", "member": target, "instruction": "Dig deeper into the second source."}),
        json.dumps({"action": "done", "summary": "Both sources agree; the answer is 42."}),
    ]

    result = asyncio.run(agent_teams.run_team(team, "Find the answer"))

    assert result["status"] == "ok"
    assert len(_member_calls(seq_subagent, target)) == 2
    second = _member_calls(seq_subagent, target)[1]
    assert "Dig deeper into the second source." in second["task"]
    assert "42" in result["report"]


def test_a_leader_that_says_done_runs_no_extra_round(cfg, seq_subagent):
    """GIVEN a leader that finishes on its first decision
    WHEN the team runs
    THEN each member ran only in the initial round."""
    team = _iterative_team()
    lead = f"{team['name']} lead"
    seq_subagent.reports[lead] = [
        json.dumps({"action": "done", "summary": "Already complete."}),
    ]

    result = asyncio.run(agent_teams.run_team(team, "Find the answer"))

    assert result["status"] == "ok"
    assert len(_member_calls(seq_subagent, f"{team['name']} a")) == 1
    assert len(_member_calls(seq_subagent, f"{team['name']} b")) == 1


def test_an_unreadable_decision_terminates_fail_safe(cfg, seq_subagent):
    """GIVEN a leader whose report carries no readable decision
    WHEN the team runs
    THEN the loop ends instead of spinning, and the run still reports."""
    team = _iterative_team()
    seq_subagent.reports[f"{team['name']} lead"] = ["Just some prose with no decision."]

    result = asyncio.run(agent_teams.run_team(team, "Find the answer"))

    assert result["status"] == "ok"
    assert len(_member_calls(seq_subagent, f"{team['name']} a")) == 1


def test_the_iteration_cap_bounds_the_loop(cfg, seq_subagent):
    """GIVEN a leader that always continues and a cap of two iterations
    WHEN the team runs
    THEN the loop stops at the cap and reports the budget hit."""
    team = _iterative_team(max_iterations=2)
    lead = f"{team['name']} lead"
    target = f"{team['name']} a"
    seq_subagent.reports[lead] = [
        json.dumps({"action": "continue", "member": target, "instruction": "Again."}),
    ]

    result = asyncio.run(agent_teams.run_team(team, "Find the answer"))

    assert result["budget_hit"] is True
    # initial round + at most two continue rounds
    assert len(_member_calls(seq_subagent, target)) <= 3


def test_a_continue_at_an_unknown_member_terminates(cfg, seq_subagent):
    """GIVEN a leader that names a member the team does not have
    WHEN the team runs
    THEN the loop ends safely rather than calling nobody."""
    team = _iterative_team()
    seq_subagent.reports[f"{team['name']} lead"] = [
        json.dumps({"action": "continue", "member": "nobody", "instruction": "Go."}),
    ]

    result = asyncio.run(agent_teams.run_team(team, "Find the answer"))

    assert result["status"] == "ok"
    assert len(_member_calls(seq_subagent, f"{team['name']} a")) == 1