"""Agent Teams — store, templates, local runner, model policy and routes."""
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


def _agent(name: str, **overrides):
    data = {
        "name": name,
        "description": f"{name} description",
        "tools": ["read_file", "file_search"],
        "instructions": f"You are {name}.",
    }
    data.update(overrides)
    return agent_store.create_agent(data)


def _team(name="Research crew", *, template=None, **overrides):
    leader = _agent(f"{name} lead")
    member_a = _agent(f"{name} a")
    member_b = _agent(f"{name} b")
    payload = {
        "name": name,
        "description": "test team",
        "instructions": "Work together.",
        "leader_id": leader["id"],
        "member_ids": [member_a["id"], member_b["id"]],
        "orchestration": "sequential",
        "model_policy": "inherit",
    }
    if template:
        payload["template"] = template
    payload.update(overrides)
    return agent_teams.create_team(payload)


class FakeSubagent:
    calls: list[dict] = []
    report_by_role: dict[str, str] = {}

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.agent_id = kwargs["agent_id"]
        self.model = kwargs.get("model")
        FakeSubagent.calls.append(kwargs)

    async def run(self):
        role = self.kwargs["role"]
        report = FakeSubagent.report_by_role.get(role, f"{role} report")

        class R:
            status = "ok"
            tool_calls: list = []

        R.report = report
        return R()


@pytest.fixture
def fake_subagent(monkeypatch):
    import core.subagent as subagent_mod

    FakeSubagent.calls = []
    FakeSubagent.report_by_role = {}
    monkeypatch.setattr(subagent_mod, "Subagent", FakeSubagent)
    return FakeSubagent


class TestTeamStore:

    def test_create_and_list(self, cfg):
        team = _team()
        listed = agent_teams.list_teams()["teams"]
        assert [row["id"] for row in listed] == [team["id"]]
        assert team["orchestration"] == "sequential"
        assert team["budget"]["max_rounds"] == 4

    def test_etag_from_the_list_is_accepted_on_save(self, cfg):
        team = _team()
        listed = agent_teams.list_teams()["teams"][0]
        updated = agent_teams.update_team(
            team["id"], {"description": "from the list"}, etag=listed["etag"]
        )
        assert updated["description"] == "from the list"

    def test_leader_cannot_be_a_member(self, cfg):
        leader = _agent("solo lead")
        member = _agent("solo member")
        with pytest.raises(agent_teams.TeamError) as exc:
            agent_teams.create_team(
                {
                    "name": "bad",
                    "leader_id": leader["id"],
                    "member_ids": [leader["id"], member["id"]],
                }
            )
        assert exc.value.code == "invalid_members"

    def test_unknown_agent_is_refused(self, cfg):
        leader = _agent("known lead")
        with pytest.raises(agent_teams.TeamError) as exc:
            agent_teams.create_team(
                {"name": "bad", "leader_id": leader["id"], "member_ids": ["nobody"]}
            )
        assert exc.value.code == "unknown_agent"

    def test_member_cap(self, cfg):
        leader = _agent("cap lead")
        members = [_agent(f"cap {n}")["id"] for n in range(5)]
        with pytest.raises(agent_teams.TeamError) as exc:
            agent_teams.create_team(
                {"name": "big", "leader_id": leader["id"], "member_ids": members}
            )
        assert exc.value.code == "invalid_members"

    def test_team_policy_needs_a_model(self, cfg):
        leader = _agent("policy lead")
        member = _agent("policy member")
        with pytest.raises(agent_teams.TeamError) as exc:
            agent_teams.create_team(
                {
                    "name": "policy",
                    "leader_id": leader["id"],
                    "member_ids": [member["id"]],
                    "model_policy": "team",
                }
            )
        assert exc.value.code == "invalid_model"

    def test_update_uses_etag_and_archive_restores(self, cfg):
        team = _team()
        with pytest.raises(agent_teams.TeamError) as exc:
            agent_teams.update_team(team["id"], {"description": "x"}, etag="old")
        assert exc.value.code == "etag_conflict"
        updated = agent_teams.update_team(
            team["id"], {"description": "x"}, etag=team["etag"]
        )
        assert updated["description"] == "x"
        archived = agent_teams.set_archived(team["id"], True)
        assert archived["archived"] is True
        assert agent_teams.set_archived(team["id"], False)["archived"] is False

    def test_archived_member_does_not_hide_the_team(self, cfg):
        team = _team()
        agent_store.set_archived(team["member_ids"][0], True)
        listed = agent_teams.list_teams()["teams"]
        assert [row["id"] for row in listed] == [team["id"]]

    def test_template_creates_agents_and_a_team(self, cfg):
        team = agent_teams.create_team({"template": "research"})
        names = {a["name"] for a in agent_store.list_agents()["agents"]}
        assert "Research Lead" in names
        assert "Source Analyst" in names
        assert "Claim Verifier" in names
        assert len(team["member_ids"]) == 2
        assert team["orchestration"] == "parallel"


class TestTeamRunner:

    def test_sequential_runs_every_member_then_the_leader(self, cfg, fake_subagent):
        team = _team()
        result = asyncio.run(agent_teams.run_team(team, "Do the task", run_id="team-run0042"))
        assert result["run_id"] == "team-run0042"
        assert result["status"] == "ok"
        roles = [call["role"] for call in fake_subagent.calls]
        assert roles[0] == "Research crew a"
        assert roles[1] == "Research crew b"
        assert roles[2] == "Research crew lead"
        assert result["members"][-1]["role"] == "leader"
        assert result["members"][0]["role"] == "member"
        assert result["report"].startswith("Research crew lead")

    def test_parallel_starts_all_members(self, cfg, fake_subagent):
        team = _team(orchestration="parallel")
        result = asyncio.run(agent_teams.run_team(team, "Do the task"))
        assert result["status"] == "ok"
        member_roles = [call["role"] for call in fake_subagent.calls[:-1]]
        assert set(member_roles) == {"Research crew a", "Research crew b"}

    def test_leader_mode_plans_then_runs_every_member(self, cfg, fake_subagent):
        team = _team(orchestration="leader")
        result = asyncio.run(agent_teams.run_team(team, "Do the task"))
        assert result["status"] == "ok"
        roles = [call["role"] for call in fake_subagent.calls]
        assert roles.count("Research crew lead") == 2  # plan + summary
        assert {"Research crew a", "Research crew b"} <= set(roles)
        assert result["plan"]

    def test_max_rounds_truncates_members_and_reports_budget(self, cfg, fake_subagent):
        team = _team(budget={"max_rounds": 1, "wall_timeout": 60})
        result = asyncio.run(agent_teams.run_team(team, "Do the task"))
        assert result["status"] == "budget"
        assert result["budget_hit"] is True
        member_calls = [call for call in fake_subagent.calls if call["role"] != "Research crew lead"]
        assert len(member_calls) == 1

    def test_per_member_policy_uses_the_pinned_models(self, cfg, fake_subagent):
        leader = _agent("pinned lead", model={"provider": None, "model": "lead-model"})
        alpha = _agent("pinned a", model={"provider": None, "model": "alpha-model"})
        beta = _agent("pinned b")
        team = agent_teams.create_team(
            {
                "name": "pinned",
                "leader_id": leader["id"],
                "member_ids": [alpha["id"], beta["id"]],
                "orchestration": "sequential",
                "model_policy": "per_member",
            }
        )
        asyncio.run(agent_teams.run_team(team, "task"))
        models = {call["role"]: call["model"] for call in fake_subagent.calls}
        assert models["pinned a"] == "alpha-model"
        assert models["pinned b"] is None
        assert models["pinned lead"] == "lead-model"

    def test_team_policy_and_task_override_win(self, cfg, fake_subagent):
        leader = _agent("policy lead model", model={"provider": None, "model": "lead-model"})
        member = _agent("policy member model", model={"provider": None, "model": "member-model"})
        team = agent_teams.create_team(
            {
                "name": "team-model",
                "leader_id": leader["id"],
                "member_ids": [member["id"]],
                "model_policy": "team",
                "model": {"provider": None, "model": "team-model"},
            }
        )
        asyncio.run(agent_teams.run_team(team, "task"))
        assert {call["model"] for call in fake_subagent.calls} == {"team-model"}
        fake_subagent.calls = []
        asyncio.run(agent_teams.run_team(team, "task", model="override-model"))
        assert {call["model"] for call in fake_subagent.calls} == {"override-model"}

    def test_archived_member_stops_the_run(self, cfg, fake_subagent):
        team = _team()
        agent_store.set_archived(team["member_ids"][0], True)
        result = asyncio.run(agent_teams.run_team(team, "task"))
        assert result["status"] == "error"
        assert "not available" in result["report"]
        assert fake_subagent.calls == []

    def test_runs_are_recorded_content_free(self, cfg, fake_subagent):
        team = _team()
        asyncio.run(agent_teams.run_team(team, "SECRET-TASK-TEXT"))
        runs = agent_teams.list_runs(team["id"])
        assert runs[0]["status"] == "ok"
        raw = (agent_teams.teams_root() / "runs.jsonl").read_text(encoding="utf-8")
        assert "SECRET-TASK-TEXT" not in raw
        agent_runs = agent_store.list_runs(team["member_ids"][0])
        assert agent_runs and agent_runs[0]["source"] == "team"


class TestTeamRoutes:

    @pytest.fixture
    def client(self, cfg):
        from fastapi.testclient import TestClient

        from server.main import create_app

        with TestClient(create_app()) as c:
            yield c

    def test_create_from_template_and_list(self, client):
        created = client.post(
            "/api/agent-teams",
            json={"template": "research"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert created.status_code == 201
        team = created.json()
        assert team["name"] == "Research team"
        listed = client.get("/api/agent-teams").json()["teams"]
        assert listed[0]["id"] == team["id"]
        templates = client.get("/api/agent-teams/templates").json()["templates"]
        assert {t["key"] for t in templates} >= {"research", "code-review", "release"}

    def test_run_and_read_the_result(self, client, fake_subagent):
        created = client.post(
            "/api/agent-teams",
            json={"template": "research"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        ).json()
        result = client.post(
            f"/api/agent-teams/{created['id']}/run",
            json={"task": "What changed?"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert result.status_code == 200
        body = result.json()
        assert body["status"] == "ok"
        assert body["members"]
        state = client.get(f"/api/agent-teams/runs/{body['run_id']}").json()
        assert state["status"] == "ok"
        runs = client.get(f"/api/agent-teams/{created['id']}/runs").json()["runs"]
        assert runs[0]["run_id"] == body["run_id"]

    def test_archived_team_does_not_run(self, client):
        created = client.post(
            "/api/agent-teams",
            json={"template": "research"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        ).json()
        client.post(
            f"/api/agent-teams/{created['id']}/archive",
            json={"archived": True},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        refused = client.post(
            f"/api/agent-teams/{created['id']}/run",
            json={"task": "x"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert refused.status_code == 409
        assert refused.json()["error"]["detail"]["code"] == "team_archived"

    def test_unknown_run_cannot_be_cancelled(self, client):
        refused = client.post(
            "/api/agent-teams/runs/team-nope/cancel",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert refused.status_code == 404
