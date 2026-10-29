"""One switch per capability: the offer list, the call, the sub-agent whitelist.

The file the user edits is the state; the two readers are the places that already
own the decision. A tool that is off must not be offered to the model, must not
run when a model or a bridge names it anyway, and must leave the sub-agent
whitelist it sat in.
"""
from __future__ import annotations

import asyncio

import pytest

from core import capabilities


@pytest.fixture(autouse=True)
def config_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    return tmp_path


class TestStore:
    def test_a_switch_is_written_and_read_back(self):
        assert capabilities.set_enabled("web_search", False) is True
        assert capabilities.disabled() == {"web_search"}
        assert capabilities.is_enabled("web_search") is False
        assert "web_search" in capabilities.store_path().read_text()

    def test_switching_it_back_on_leaves_no_entry(self):
        capabilities.set_enabled("web_search", False)
        capabilities.set_enabled("web_search", True)
        assert capabilities.state()["disabled"] == []

    def test_the_bridge_tools_cannot_be_switched_off(self):
        for name in sorted(capabilities.ALWAYS_ON):
            assert capabilities.set_enabled(name, False) is False
        assert capabilities.disabled() == set()

    def test_a_broken_file_reads_as_nothing_switched_off(self, config_dir):
        capabilities.store_path().write_text("{not json")
        assert capabilities.disabled() == set()


class TestOfferList:
    def test_a_switched_off_tool_leaves_the_offer_list(self):
        from core.tools.registry import get_tool_schemas

        def offered() -> set[str]:
            return {str((s.get("function") or {}).get("name") or "") for s in get_tool_schemas()}

        assert "web_search" in offered()
        capabilities.set_enabled("web_search", False)
        assert "web_search" not in offered()
        # It stays in the known set: the settings view has to be able to switch it back.
        assert "web_search" in capabilities.tool_names()

    def test_the_catalog_names_the_state_and_the_kind(self):
        capabilities.set_enabled("web_search", False)
        rows = {row["name"]: row for row in capabilities.catalog()}
        assert rows["web_search"]["enabled"] is False
        assert rows["web_search"]["kind"] == "builtin"
        assert rows["read_file"]["safe"] is True
        assert rows["ask_user"]["locked"] is True


class TestExecution:
    def test_a_switched_off_tool_refuses_even_when_it_is_named(self):
        from core.tools import execute_tool

        capabilities.set_enabled("web_search", False)
        out = asyncio.run(execute_tool("web_search", {"query": "x"}))
        assert "switched off in Settings" in out
        assert "web_search" in out


class TestSubagentWhitelist:
    def test_the_stock_list_is_the_base(self):
        assert capabilities.subagent_allowlist() == list(capabilities.SUBAGENT_BASE_WHITELIST)

    def test_an_addition_joins_the_whitelist(self):
        capabilities.set_subagent_extra(["query_codebase"])
        assert "query_codebase" in capabilities.subagent_allowlist()

    def test_a_switched_off_tool_leaves_the_whitelist(self):
        capabilities.set_enabled("read_file", False)
        assert "read_file" not in capabilities.subagent_allowlist()


class TestRoutes:
    @pytest.fixture
    def client(self, config_dir, monkeypatch):
        import core.engine_config as engine_config

        monkeypatch.setattr(engine_config, "CONFIG_DIR", config_dir / "config")
        from fastapi.testclient import TestClient
        from server.main import create_app

        return TestClient(create_app())

    def test_the_view_lists_every_capability_with_its_state(self, client):
        body = client.get("/api/capabilities").json()
        names = [row["name"] for row in body["tools"]["tools"]]
        assert "read_file" in names and "web_search" in names
        assert body["tools"]["enabled_count"] == body["tools"]["count"]

    def test_a_switch_reaches_the_store(self, client):
        resp = client.patch("/api/capabilities/web_search", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json() == {"name": "web_search", "enabled": False}
        view = client.get("/api/capabilities").json()["tools"]
        assert view["enabled_count"] == view["count"] - 1
        row = next(item for item in view["tools"] if item["name"] == "web_search")
        assert row["enabled"] is False

    def test_an_unknown_capability_is_404(self, client):
        assert client.patch("/api/capabilities/no_such_tool", json={"enabled": False}).status_code == 404

    def test_a_bridge_tool_refuses_the_switch_with_409(self, client):
        assert client.patch("/api/capabilities/ask_user", json={"enabled": False}).status_code == 409

    def test_the_allowlist_edit_replaces_the_additions(self, client):
        resp = client.put("/api/capabilities/subagent-allowlist", json={"names": ["query_codebase"]})
        assert resp.status_code == 200
        assert "query_codebase" in resp.json()["tools"]
        assert capabilities.state()["subagent_extra"] == ["query_codebase"]

    def test_an_unknown_allowlist_name_is_refused(self, client):
        resp = client.put("/api/capabilities/subagent-allowlist", json={"names": ["no_such_tool"]})
        assert resp.status_code == 422
        assert capabilities.state()["subagent_extra"] == []
