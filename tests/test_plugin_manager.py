"""P1 — the read-only plugin_manager model tool.

The agent may inspect the installed portfolio and its state, but it cannot
install, enable, disable, update or remove through this tool. Those actions keep
the approval gate and the lifecycle endpoint.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.plugin_lifecycle import LifecycleError, PluginLifecycle
from core.tools.plugin_manager import PLUGIN_MANAGER_SCHEMA, plugin_manager


def _call(**kwargs) -> dict:
    return json.loads(plugin_manager(**kwargs))


@pytest.fixture()
def device(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    return tmp_path


def test_list_reports_the_whole_portfolio(device) -> None:
    payload = _call(action="list")
    assert payload["read_only"] is True
    assert payload["counts"] == {"plugins": 17, "skills": 51, "mcp": 7, "commands": 32}
    assert len(payload["plugins"]) == 17
    assert [p["name"] for p in payload["plugins"]] == sorted(
        p["name"] for p in payload["plugins"]
    )
    assert all(
        p["enabled"] is True and p["scope"] == "user" for p in payload["plugins"]
    )
    web = next(p for p in payload["plugins"] if p["name"] == "web-research")
    assert web["activated_tools"] == ["fetch_url", "web_search"]


def test_omitting_the_action_lists_the_portfolio(device) -> None:
    payload = _call()
    assert payload["read_only"] is True
    assert payload == _call(action="list")


@pytest.mark.parametrize("blank", ["", "   "])
def test_a_blank_action_lists_the_portfolio_too(device, blank) -> None:
    assert _call(action=blank) == _call(action="list")


def test_the_schema_makes_action_optional_and_names_the_default(device) -> None:
    function = PLUGIN_MANAGER_SCHEMA["function"]
    parameters = function["parameters"]
    assert "action" in parameters["properties"]
    assert "action" not in (parameters.get("required") or [])
    assert parameters["properties"]["action"].get("default") == "list"
    description = function["description"].lower()
    assert "list" in description and "omit" in description


def test_the_engine_validator_accepts_a_call_without_action(device) -> None:
    from core.tools.registry import _validate_tool_arguments

    assert _validate_tool_arguments("plugin_manager", {}) is None


def test_list_reads_the_committed_switch_state(device) -> None:
    versions = {p["name"]: p["version"] for p in _call(action="list")["plugins"]}
    lifecycle = PluginLifecycle(device / "plugin-state.json", versions=versions)
    lifecycle.set_enabled("web-research", False)
    web = next(
        p for p in _call(action="list")["plugins"] if p["name"] == "web-research"
    )
    assert web["enabled"] is False
    assert web["state"] == "disabled"
    detail = _call(action="inspect", name="web-research")
    assert detail["plugin"]["enabled"] is False


def test_search_is_case_insensitive_and_explains_the_match(device) -> None:
    payload = _call(action="search", query="BROWSER")
    names = [p["name"] for p in payload["plugins"]]
    assert "browser-use" in names
    assert all(
        "browser" in (p["name"] + " " + p["description"]).lower()
        for p in payload["plugins"]
    )


def test_inspect_returns_declared_and_registered_capabilities(device) -> None:
    detail = _call(action="inspect", name="documents")
    assert detail["plugin"]["name"] == "documents"
    assert [c["name"] for c in detail["declared_commands"]] == ["pdf", "docx", "report"]
    # Inspect lists every capability this bundle owns, the command and the tools.
    assert detail["capabilities"] == [
        "documents.report",
        "tool:build_document",
        "tool:create_docx",
        "tool:create_pdf",
        "tool:create_qrcode",
        "tool:create_source_notebook",
        "tool:export_source_brief",
        "tool:extract_pdf_text",
        "tool:query_source_notebook",
        "tool:verify_artifact",
    ]
    assert "create_pdf" in detail["activated_tools"]


def test_inspect_an_unknown_plugin_is_an_error_not_an_invention(device) -> None:
    payload = _call(action="inspect", name="not-installed")
    assert payload["error"] == "unknown_plugin"
    assert payload["name"] == "not-installed"


def test_health_reports_quarantine_and_missing_dependencies(device) -> None:
    broken = device / "plugins" / "broken"
    broken.mkdir(parents=True)
    (broken / "ephe-plugin.json").write_text("{not json", encoding="utf-8")

    orphan = device / "plugins" / "orphan"
    orphan.mkdir(parents=True)
    (orphan / "ephe-plugin.json").write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "name": "orphan",
                "version": "1.0.0",
                "description": "needs a plugin that is not installed",
                "dependencies": ["absent-pack"],
                "permissions": {"tool_families": [], "data_roots": []},
                "components": {"skills": [], "commands": []},
            }
        ),
        encoding="utf-8",
    )

    payload = _call(action="health")
    assert payload["status"] == "degraded"
    assert {"name": "broken", "kind": "quarantined"} in payload["issues"]
    assert {
        "name": "orphan",
        "kind": "missing_dependency",
        "detail": "absent-pack",
    } in payload["issues"]


def test_health_reports_a_failed_switch(device) -> None:
    versions = {p["name"]: p["version"] for p in _call(action="list")["plugins"]}
    lifecycle = PluginLifecycle(
        device / "plugin-state.json",
        versions=versions,
        activator=lambda name: (_ for _ in ()).throw(RuntimeError("activation failed")),
    )
    lifecycle.set_enabled("web-research", False)
    with pytest.raises(LifecycleError):
        lifecycle.set_enabled("web-research", True)
    payload = _call(action="health")
    assert {"name": "web-research", "kind": "failed_state"} in payload["issues"]


def test_read_only(device) -> None:
    payload = _call(action="enable", name="web-research")
    assert payload["error"] == "read_only"
    assert set(payload["allowed"]) == {"list", "search", "inspect", "health"}
    assert not (device / "plugin-state.json").exists()


def test_the_tool_is_registered_and_safe(device) -> None:
    from core.tools.approval_rules import CHAT_AUTO_RUN_TOOLS, SAFE_TOOLS
    from core.tools.registry import TOOL_MAP, get_tool_schemas

    assert "plugin_manager" in TOOL_MAP
    assert "plugin_manager" in SAFE_TOOLS
    assert "plugin_manager" in CHAT_AUTO_RUN_TOOLS
    schemas = {s["function"]["name"]: s for s in get_tool_schemas()}
    assert schemas["plugin_manager"] == PLUGIN_MANAGER_SCHEMA
    required = PLUGIN_MANAGER_SCHEMA["function"]["parameters"].get("required") or []
    assert "action" not in required


def test_an_isolated_run_catalog_names_no_checkout_path_or_plugin(tmp_path, monkeypatch) -> None:
    """A proof run is graded on what the engine did, so its plugin catalog may not carry
    the developer's working tree: neither an absolute path from the checkout nor a
    first-party bundle that only exists there. The env comes from the run itself
    (`engine_environment`), so the test asks the harness to build the environment rather
    than assembling one by hand."""
    from evals.creation_transcript import engine_environment

    repo_root = Path(__file__).resolve().parents[1]
    key = tmp_path / "engine.key"
    key.write_text("sk-" + "0" * 32 + "\n", encoding="utf-8")
    env = engine_environment(
        key_file=key,
        config_dir=tmp_path / "config",
        base_url="https://api.deepseek.example/v1",
        model="deepseek-test",
        port=8801,
    )
    for name in ("EPHE_CONFIG_DIR", "EPHE_BUILTIN_PLUGINS_ROOT"):
        if name in env:
            monkeypatch.setenv(name, env[name])

    payload = _call(action="list")
    names = [plugin["name"] for plugin in payload["plugins"]]
    assert names == []
    assert "countdown" not in names
    assert str(repo_root) not in json.dumps(payload)
