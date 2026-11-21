"""Agent Center — local agent profiles, model precedence, API and run records.

The profile contract stays compatible with ``~/.ephe/agents/*.json``: a file
written by the old Extensions wave still loads, a file written by the Agent
Center carries the richer record and the same fail-closed tool validation.

Model precedence is task override > agent > global engine. The spawn path has
no task-level model, so an agent's pinned model must reach ``Subagent`` and an
agent without a pin must leave the global engine in charge.
"""
from __future__ import annotations

import asyncio
import json
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import agent_profiles, agent_store  # noqa: E402


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    root = tmp_path / "cfg"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(root))
    return root


def _payload(**overrides):
    data = {
        "name": "scout",
        "description": "Fast read-only explorer",
        "tools": ["read_file", "list_directory", "file_search"],
        "instructions": "Stay factual.",
        "timeout": 60,
    }
    data.update(overrides)
    return data


class TestStore:

    def test_create_writes_owner_only_file(self, cfg):
        record = agent_store.create_agent(_payload())
        path = cfg / "agents" / f"{record['id']}.json"
        assert path.is_file()
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
        assert record["origin"] == "local"
        assert record["archived"] is False
        assert record["etag"]

    def test_create_rejects_unknown_tool(self, cfg):
        with pytest.raises(agent_store.AgentError) as exc:
            agent_store.create_agent(_payload(tools=["read_file", "format_everything"]))
        assert exc.value.code == "invalid_tools"

    def test_create_rejects_empty_tools(self, cfg):
        with pytest.raises(agent_store.AgentError) as exc:
            agent_store.create_agent(_payload(tools=[]))
        assert exc.value.code == "invalid_tools"

    def test_create_rejects_duplicate_name(self, cfg):
        agent_store.create_agent(_payload())
        with pytest.raises(agent_store.AgentError) as exc:
            agent_store.create_agent(_payload(description="second"))
        assert exc.value.code == "duplicate_name"
        assert exc.value.status == 409

    def test_create_reserves_the_default_agent_name(self, cfg):
        with pytest.raises(agent_store.AgentError) as exc:
            agent_store.create_agent(_payload(name="Ephe"))
        assert exc.value.code == "reserved_name"

    def test_update_requires_matching_etag(self, cfg):
        record = agent_store.create_agent(_payload())
        with pytest.raises(agent_store.AgentError) as exc:
            agent_store.update_agent(record["id"], {"description": "x"}, etag="stale")
        assert exc.value.code == "etag_conflict"
        assert exc.value.status == 412
        updated = agent_store.update_agent(
            record["id"], {"description": "new"}, etag=record["etag"]
        )
        assert updated["description"] == "new"
        assert updated["etag"] != record["etag"]

    def test_etag_from_the_list_is_accepted_on_save(self, cfg):
        agent_store.create_agent(_payload())
        listed = next(a for a in agent_store.list_agents()["agents"] if a["id"] == "scout")
        updated = agent_store.update_agent(
            "scout", {"description": "from the list"}, etag=listed["etag"]
        )
        assert updated["description"] == "from the list"

    def test_duplicate_archives_and_restores(self, cfg):
        record = agent_store.create_agent(_payload())
        copy = agent_store.duplicate_agent(record["id"])
        assert copy["id"] != record["id"]
        assert copy["name"] != record["name"]
        archived = agent_store.set_archived(record["id"], True)
        assert archived["archived"] is True
        assert any(a["id"] == record["id"] for a in agent_store.list_agents()["agents"])
        restored = agent_store.set_archived(record["id"], False)
        assert restored["archived"] is False

    def test_archive_is_local_only(self, cfg):
        with pytest.raises(agent_store.AgentError) as exc:
            agent_store.set_archived("ephe", True)
        assert exc.value.code == "read_only"
        assert exc.value.status == 409

    def test_archived_and_disabled_agents_do_not_spawn(self, cfg):
        record = agent_store.create_agent(_payload())
        assert agent_profiles.resolve_for_spawn("scout") is not None
        agent_store.set_archived(record["id"], True)
        assert agent_profiles.resolve_for_spawn("scout") is None
        agent_store.set_archived(record["id"], False)
        agent_store.update_agent(
            record["id"], {"enabled": False}, etag=agent_store.get_agent(record["id"])["etag"]
        )
        assert agent_profiles.resolve_for_spawn("scout") is None

    def test_legacy_profile_still_loads(self, cfg):
        agents = cfg / "agents"
        agents.mkdir(parents=True)
        (agents / "old.json").write_text(
            json.dumps({"name": "old", "tools": ["read_file"], "timeout": 45})
        )
        profile = agent_profiles.resolve_for_spawn("old")
        assert profile["tools"] == ["read_file"]
        assert profile["timeout"] == 45
        assert profile["model"] is None

    def test_model_object_reaches_the_spawn_profile(self, cfg):
        record = agent_store.create_agent(
            _payload(model={"provider": "openai_compatible", "model": "gpt-x"})
        )
        profile = agent_profiles.resolve_for_spawn(record["name"])
        assert profile["model"] == "gpt-x"
        assert profile["instructions"] == "Stay factual."

    def test_runs_are_content_free(self, cfg):
        record = agent_store.create_agent(_payload())
        agent_store.record_run(
            run_id="subagent-1",
            agent_id=record["id"],
            agent_name=record["name"],
            model="gpt-x",
            model_source="agent",
            source="test",
            status="ok",
            duration_ms=1200,
            tool_calls=2,
            prompt_chars=400,
            report_chars=900,
        )
        runs = agent_store.list_runs(record["id"])
        assert runs[0]["agent_id"] == record["id"]
        assert runs[0]["model_source"] == "agent"
        raw = (cfg / "agents" / "runs.jsonl").read_text(encoding="utf-8")
        assert "prompt text" not in raw
        assert "Stay factual" not in raw


class TestSpawnModelPrecedence:

    def test_spawn_passes_the_agent_model(self, cfg, monkeypatch):
        import core.subagent as subagent_mod
        from core.tools import subagent_tool

        agent_store.create_agent(_payload(model={"provider": "openai_compatible", "model": "gpt-x"}))
        seen: dict = {}

        class FakeSubagent:
            def __init__(self, **kwargs):
                seen.update(kwargs)

            async def run(self):
                class R:
                    status = "ok"
                    report = "done"
                    tool_calls: list = []
                return R()

        monkeypatch.setattr(subagent_mod, "Subagent", FakeSubagent)
        out = asyncio.run(subagent_tool.spawn_agent("d", "p", subagent_type="scout"))
        assert "done" in out
        assert seen["model"] == "gpt-x"
        assert seen["allowed_tools"] == ["read_file", "list_directory", "file_search"]
        assert seen["instructions"] == "Stay factual."
        runs = agent_store.list_runs(agent_store.list_agents()["agents"][1]["id"])
        assert runs[0]["model_source"] == "agent"

    def test_spawn_without_a_profile_leaves_model_to_the_engine(self, cfg, monkeypatch):
        import core.subagent as subagent_mod
        from core.tools import subagent_tool

        seen: dict = {}

        class FakeSubagent:
            def __init__(self, **kwargs):
                seen.update(kwargs)

            async def run(self):
                class R:
                    status = "ok"
                    report = "done"
                    tool_calls: list = []
                return R()

        monkeypatch.setattr(subagent_mod, "Subagent", FakeSubagent)
        asyncio.run(subagent_tool.spawn_agent("d", "p", subagent_type="nobody"))
        assert seen["model"] is None
        assert seen["instructions"] == ""


class TestRoutes:

    @pytest.fixture
    def client(self, cfg):
        from fastapi.testclient import TestClient

        from server.main import create_app

        with TestClient(create_app()) as c:
            yield c

    def test_list_has_the_default_agent_and_local_rows(self, client):
        agent_store.create_agent(_payload())
        body = client.get("/api/agents").json()
        names = {a["name"]: a for a in body["agents"]}
        assert "Ephe" in names and names["Ephe"]["read_only"] is True
        assert names["scout"]["origin"] == "local"
        tools = client.get("/api/agents/tools").json()["tools"]
        assert {"read_file", "web_search"} <= {row["name"] for row in tools}

    def test_create_update_and_etag(self, client, cfg):
        created = client.post(
            "/api/agents", json=_payload(),
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert created.status_code == 201
        row = created.json()
        stale = client.put(
            f"/api/agents/{row['id']}",
            json={"description": "x"},
            headers={"If-Match": "stale", "X-Requested-With": "XMLHttpRequest"},
        )
        assert stale.status_code == 412
        ok = client.put(
            f"/api/agents/{row['id']}",
            json={"description": "x"},
            headers={"If-Match": row["etag"], "X-Requested-With": "XMLHttpRequest"},
        )
        assert ok.status_code == 200
        assert ok.json()["description"] == "x"

    def test_mutations_require_the_xhr_marker(self, client):
        r = client.post("/api/agents", json=_payload())
        assert r.status_code == 403

    def test_archive_and_runs_routes(self, client):
        row = client.post(
            "/api/agents", json=_payload(), headers={"X-Requested-With": "XMLHttpRequest"}
        ).json()
        archived = client.post(
            f"/api/agents/{row['id']}/archive",
            json={"archived": True},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert archived.status_code == 200
        assert archived.json()["archived"] is True
        runs = client.get(f"/api/agents/{row['id']}/runs").json()
        assert runs["runs"] == []

    def test_test_run_uses_the_agent_model(self, client, cfg, monkeypatch):
        row = client.post(
            "/api/agents",
            json=_payload(model={"provider": "openai_compatible", "model": "gpt-x"}),
            headers={"X-Requested-With": "XMLHttpRequest"},
        ).json()
        seen: dict = {}

        class FakeSubagent:
            def __init__(self, **kwargs):
                seen.update(kwargs)

            async def run(self):
                class R:
                    status = "ok"
                    report = "answer"
                    tool_calls: list = []
                return R()

        import core.subagent as subagent_mod

        monkeypatch.setattr(subagent_mod, "Subagent", FakeSubagent)
        result = client.post(
            f"/api/agents/{row['id']}/test",
            json={"prompt": "ping"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert result.status_code == 200
        assert result.json()["report"] == "answer"
        assert seen["model"] == "gpt-x"

    def test_archived_agent_cannot_be_tested(self, client):
        row = client.post(
            "/api/agents", json=_payload(), headers={"X-Requested-With": "XMLHttpRequest"}
        ).json()
        client.post(
            f"/api/agents/{row['id']}/archive",
            json={"archived": True},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        result = client.post(
            f"/api/agents/{row['id']}/test",
            json={"prompt": "ping"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert result.status_code == 409
        assert result.json()["error"]["detail"]["code"] == "agent_archived"

    def test_duplicate_plugin_agent_becomes_local(self, client, cfg, monkeypatch):
        plugin_rows = [{
            "id": "plugin-agent", "name": "reviewer", "description": "plugin one",
            "tools": ["read_file"], "timeout": 120, "model": None,
            "instructions": "", "origin": "plugin:quality-pack", "read_only": True,
            "archived": False, "enabled": True,
        }]
        monkeypatch.setattr(agent_store, "plugin_agents", lambda: plugin_rows)
        listed = client.get("/api/agents").json()["agents"]
        assert any(a["id"] == "plugin-agent" and a["read_only"] for a in listed)
        copy = client.post(
            "/api/agents/plugin-agent/duplicate",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert copy.status_code == 201
        assert copy.json()["origin"] == "local"
        assert copy.json()["read_only"] is False
