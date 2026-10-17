"""R65 — User agents + user hooks + deep plugins wiring (Extensions wave E5).

1. Agent profiles (~/.ephe/agents/*.json + plugin manifest components.agents):
   {name, description?, tools, model?, timeout?}. Validation is fail-closed:
   unknown tools quarantine the profile, timeout clamps to [30, 900], a
   profile with no valid tools never loads.
2. spawn_agent integration: subagent_type resolves a profile → the helper
   runs with the PROFILE's tools/model/timeout; an unknown label behaves
   exactly like today (read-only default whitelist) — never break userspace.
3. User hooks (~/.ephe/hooks.json): pre_tool (transform or block via
   {"block": reason}), post_tool (transform via {"result": …}) — commands
   read JSON on stdin, fail-tolerant (crash = ignored + audit), match filter
   per tool name, priority ordering.
4. Deep plugins wiring is real:
   - plugins.plugin_autorun=false (default) → freshly installed marketplace
     plugins land DISABLED in the registry; true → enabled.
   - the MCP count is no longer a deep settings field (I3-6); the live
     config shows in GET /api/settings/mcp.
5. tts plugin gate: /api/audio/synthesize denies with an honest error when
   the tts plugin is explicitly disabled (explicit registry entries only).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import agent_profiles  # noqa: E402

PROFILE = {
    "name": "scout",
    "description": "Fast read-only explorer",
    "tools": ["read_file", "list_directory", "file_search"],
    "timeout": 60,
}


class TestAgentProfiles:

    def test_user_profile_loads(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        agents = tmp_path / "cfg" / "agents"
        agents.mkdir(parents=True)
        (agents / "scout.json").write_text(json.dumps(PROFILE))
        profiles, _ = agent_profiles.load_profiles()
        assert profiles["scout"]["tools"] == ["read_file", "list_directory", "file_search"]
        assert profiles["scout"]["timeout"] == 60

    def test_unknown_tools_quarantine_profile(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        agents = tmp_path / "cfg" / "agents"
        agents.mkdir(parents=True)
        bad = {**PROFILE, "name": "rooty", "tools": ["read_file", "format_everything"]}
        (agents / "rooty.json").write_text(json.dumps(bad))
        profiles = agent_profiles.load_profiles()
        assert "rooty" not in profiles

    def test_timeout_clamped(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        agents = tmp_path / "cfg" / "agents"
        agents.mkdir(parents=True)
        (agents / "slow.json").write_text(json.dumps({**PROFILE, "name": "slow", "timeout": 9999}))
        profiles, _ = agent_profiles.load_profiles()
        assert profiles["slow"]["timeout"] == 900

    def test_plugin_agents_require_active_plugin(self, tmp_path, monkeypatch):
        """G: manifest plugin with components.agents, registry-disabled W: resolve T: absent."""
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        manifest_agents = [{"name": "scout", "tools": ["read_file"], "description": "d", "plugin": "my-pack"}]
        cfg = tmp_path / "cfg"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "plugins.json").write_text(json.dumps({"plugins": [{"name": "my-pack", "enabled": False}]}))
        profiles, _ = agent_profiles.load_profiles(manifest_agents=manifest_agents)
        assert "scout" not in profiles
        profiles2, _ = agent_profiles.load_profiles(
            manifest_agents=manifest_agents,
            registry_override={"plugins": [{"name": "my-pack", "enabled": True}]},
        )
        assert "scout" in profiles2

    def test_resolve_for_spawn(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        agents = tmp_path / "cfg" / "agents"
        agents.mkdir(parents=True)
        (agents / "scout.json").write_text(json.dumps(PROFILE))
        resolved = agent_profiles.resolve_for_spawn("scout")
        assert resolved is not None
        assert resolved["tools"] == PROFILE["tools"]
        assert agent_profiles.resolve_for_spawn("does-not-exist") is None


class TestSpawnIntegration:

    def test_subagent_accepts_profile_overrides(self):
        """G: profile values W: Subagent T: allowed_tools/timeout override defaults."""
        from core.subagent import Subagent

        s = Subagent(
            agent_id="t1", role="scout", task="t",
            allowed_tools=["read_file"], timeout=45.0, model="m",
        )
        assert s.allowed_tools == ["read_file"]
        assert s.timeout == 45.0

    def test_default_behaviour_unchanged(self):
        from core.subagent import SUBAGENT_TIMEOUT, Subagent

        s = Subagent(agent_id="t2", role="x", task="t", model="m")
        assert s.allowed_tools is None  # run() falls back to the default whitelist
        assert s.timeout is None

    def test_spawn_schema_documents_agent_profiles(self):
        from core.tools.subagent_tool import SPAWN_AGENT_SCHEMA

        props = SPAWN_AGENT_SCHEMA["function"]["parameters"]["properties"]
        assert "profile" in props["subagent_type"]["description"].lower() or "profile" in SPAWN_AGENT_SCHEMA["function"]["description"].lower()


class TestUserHooks:

    def test_pre_tool_block(self, tmp_path, monkeypatch):
        """G: hooks.json pre_tool returns {"block": reason} W: execute T: blocked honestly."""
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        cfg = tmp_path / "cfg"
        cfg.mkdir(parents=True, exist_ok=True)
        hooks = cfg / "hooks.json"
        hooks.write_text(json.dumps({
            "pre_tool": [{
                "command": f"{sys.executable} -c \"import json,sys; d=json.load(sys.stdin); print(json.dumps({{'block': 'policy says no'}}))\"",
                "match": "read_file",
            }],
        }))
        from core import user_hooks

        user_hooks.reset_cache()
        import asyncio

        from core.tools.registry import execute_tool

        result = asyncio.run(execute_tool("read_file", {"path": "/tmp/x"}))
        assert "blocked" in result.lower() and "policy says no" in result

    def test_post_tool_transform(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        cfg = tmp_path / "cfg"
        cfg.mkdir(parents=True, exist_ok=True)
        hooks = cfg / "hooks.json"
        hooks.write_text(json.dumps({
            "post_tool": [{
                "command": f"{sys.executable} -c \"import json,sys; d=json.load(sys.stdin); print(json.dumps({{'result': d['result'] + ' [hooked]'}}))\"",
            }],
        }))
        from core import user_hooks

        user_hooks.reset_cache()
        import asyncio

        from core.tools.registry import execute_tool

        result = asyncio.run(execute_tool("no_such_tool", {}))
        assert "[hooked]" in result

    def test_crashing_hook_is_fail_tolerant(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        cfg = tmp_path / "cfg"
        cfg.mkdir(parents=True, exist_ok=True)
        hooks = cfg / "hooks.json"
        hooks.write_text(json.dumps({
            "pre_tool": [{"command": f"{sys.executable} -c \"import sys; sys.exit(3)\""}],
        }))
        from core import user_hooks

        user_hooks.reset_cache()
        import asyncio

        from core.tools.registry import execute_tool

        result = asyncio.run(execute_tool("no_such_tool", {}))
        assert "not found" in result.lower()  # flow unaffected


class TestDeepWiring:

    def test_autorun_controls_install_state(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        (tmp_path / "cfg").mkdir(parents=True, exist_ok=True)
        from core.plugin_market import _register_installed
        from core.plugin_store import load_registry

        _register_installed("whatever")
        registry = {p["name"]: p["enabled"] for p in load_registry()}
        assert registry["whatever"] is False  # default: autorun OFF

        from core import settings_schema as ss

        monkeypatch.setattr(
            ss, "load_deep_settings",
            lambda: {"plugins": {"plugins.plugin_autorun": True}},
        )
        _register_installed("second")
        registry = {p["name"]: p["enabled"] for p in load_registry()}
        assert registry["second"] is True

    def test_mcp_gaete_ist_kein_settings_feld_mehr(self, tmp_path, monkeypatch):
        """I3-6: plugins.mcp_servers_count was a gauge, not a control — every GET
        overwrote the user value with the live count. MCP servers are shown and
        configured in the MCP section (GET/PUT /api/settings/mcp)."""
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        monkeypatch.setenv("EPHE_MCP_SERVERS", "http://127.0.0.1:9/mcp")
        from server.main import create_app
        from fastapi.testclient import TestClient

        with TestClient(create_app()) as client:
            deep = client.get("/api/settings").json()["deep"]
            keys = {f["key"] for s in deep for f in s["fields"]}
            assert "plugins.mcp_servers_count" not in keys
            mcp = client.get("/api/settings/mcp").json()
            assert len(mcp["servers"]) == 1, "die Live-Anzahl lebt im MCP-Bereich"

    def test_tts_gate_denies_when_disabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        cfg = tmp_path / "cfg"
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "plugins.json").write_text(json.dumps({"plugins": [{"name": "voice", "enabled": False}]}))
        from server.main import create_app
        from fastapi.testclient import TestClient

        with TestClient(create_app()) as client:
            r = client.post("/api/audio/synthesize", json={"text": "hi", "voice": "x"})
            assert r.status_code == 403
            assert "voice" in r.text.lower()
