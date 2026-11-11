"""SHADOW — a first-party tool name is not a bundle's to take.

PE2E proved three failures in one place: a self-made bundle that declares `web_search`
passed `verify_plugin_bundle` and the install, the mount answered 409, and the installed
bundle (enabled or disabled) still took `web_search` out of the tool offer, because the
registry scan let a foreign claim own a kernel or first-party name. The same preflight
accepted a `handlers.py` with a syntax error.

Each test asks the function the product asks: `reserved_tool_names` is the one
reservation map, `verify_plugin_bundle` is the author's preflight, `install_plugin_bundle`
runs the install path, `PluginLifecycle.mount` runs the mount, and `filter_schemas` is
what the model is offered. A disabled bundle may remove its own names, never another's.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_manifest, plugin_runtime
from core.plugin_lifecycle import STATE_FILENAME, LifecycleError, PluginLifecycle
from core.plugin_manifest import MANIFEST_FILENAME
from core.plugin_registry import scan_tool_activations
from core.plugin_tools_contract import (
    FIRST_PARTY_RESERVED,
    reserved_tool,
    reserved_tool_names,
)
from core.tools import creator_tools

_VALID_HANDLER = (
    "def run(arguments, state_dir):\n"
    "    return {'ok': True, 'arguments': arguments}\n"
)

#: The two shapes one test run needs: a first-party name served by a shipped bundle and
#: a name the kernel map still holds.
_FIRST_PARTY = "web_search"
_KERNEL = "delete_file"

def _call(tool: str, **arguments) -> dict:
    payload = getattr(creator_tools, tool)(**arguments)
    assert isinstance(payload, str), f"{tool} must answer a JSON string"
    return json.loads(payload)

def _tool(name: str = "tick", entry: str = "handlers.py:run") -> dict:
    return {
        "name": name,
        "entry": entry,
        "family": "read",
        "description": f"The {name} tool this bundle declares.",
    }

def _bundle(root: Path, plugin_id: str, tool: dict, files: dict[str, str]) -> Path:
    """A v2 bundle in the user root, with the files its entries name."""
    directory = root / plugin_id
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "manifest_version": 2,
        "name": plugin_id,
        "version": "0.1.0",
        "description": "A bundle that claims a name.",
        "publisher": {"name": "Ephe"},
        "license": "MIT",
        "permissions": {"tool_families": ["read"], "data_roots": []},
        "components": {"skills": [], "commands": [], "tools": [tool]},
    }
    (directory / MANIFEST_FILENAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    for relative, text in files.items():
        target = directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return directory

def _staged(lane: dict, tool_name: str, handler: str = _VALID_HANDLER) -> Path:
    """A scaffolded bundle whose manifest declares one tool and ships its handler."""
    answer = _call(
        "create_plugin_scaffold",
        name="weather-card",
        description="Reads one sky.",
    )
    bundle = Path(answer["bundle"])
    manifest = json.loads((bundle / MANIFEST_FILENAME).read_text())
    manifest["permissions"]["tool_families"] = ["read"]
    manifest["components"]["tools"] = [
        _tool(name=tool_name, entry="tools/sky.py:run")
    ]
    (bundle / MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
    (bundle / "tools").mkdir(parents=True, exist_ok=True)
    (bundle / "tools" / "sky.py").write_text(handler, encoding="utf-8")
    return bundle

def _staged_mcp(lane: dict, handler: str) -> Path:
    """A bundle whose one tool rides its own MCP server entry."""
    answer = _call(
        "create_plugin_scaffold",
        name="weather-card",
        description="Reads one sky.",
    )
    bundle = Path(answer["bundle"])
    manifest = json.loads((bundle / MANIFEST_FILENAME).read_text())
    manifest["permissions"]["tool_families"] = ["read"]
    manifest["components"]["mcp"] = {"entry": "server.py:serve"}
    manifest["components"]["tools"] = [
        {
            "name": "sky_read",
            "transport": "mcp",
            "family": "read",
            "description": "Reads the one sky this bundle knows.",
        }
    ]
    (bundle / MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
    (bundle / "server.py").write_text(handler, encoding="utf-8")
    return bundle

def _schemas(*names: str) -> list[dict]:
    return [{"type": "function", "function": {"name": name}} for name in names]

@pytest.fixture()
def lane(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    root = config / "plugins"
    root.mkdir(parents=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", root)
    plugin_runtime.invalidate_ownership_cache()
    yield {"config": config, "root": root, "tmp": tmp_path}
    plugin_runtime.invalidate_ownership_cache()

def _disable(config: Path, plugin_id: str) -> None:
    PluginLifecycle(
        config / STATE_FILENAME,
        versions=plugin_runtime._installed_versions(),
    ).set_enabled(plugin_id, False)
    plugin_runtime.invalidate_ownership_cache()

# 1. One reservation map

def test_one_map_reserves_kernel_and_first_party_names(lane):
    """The map answers kernel, MCP and shipped-bundle names from one place."""
    reserved = reserved_tool_names()
    assert reserved[_KERNEL].code == "reserved_kernel"
    first = reserved[_FIRST_PARTY]
    assert first.code == FIRST_PARTY_RESERVED
    assert first.owner == "web-research"
    assert "web_search_weather_card" in first.action("weather-card")
    assert reserved_tool(
        _FIRST_PARTY, plugin_id="weather-card", plugin_dir=lane["root"] / "weather-card"
    ) is not None
    assert reserved_tool(
        _FIRST_PARTY,
        plugin_id="web-research",
        plugin_dir=ROOT / "plugins" / "web-research",
    ) is None, "the bundle that ships the name may still serve it"

# 2. An installed or disabled bundle takes nothing out of the offer

@pytest.mark.parametrize("claimed", [_FIRST_PARTY, _KERNEL])
def test_a_disabled_bundle_leaves_the_offer_alone(lane, claimed):
    _bundle(lane["root"], "weather-card", _tool(name=claimed), {"handlers.py": _VALID_HANDLER})
    plugin_runtime.invalidate_ownership_cache()
    _disable(lane["config"], "weather-card")

    scanned = scan_tool_activations(lane["root"])
    assert claimed not in [name for name, _owner in scanned.owners]
    assert scanned.conflicts == ()
    assert plugin_runtime.is_tool_visible(claimed) is True
    offered = _schemas(claimed)
    assert plugin_runtime.filter_schemas(offered) == offered

@pytest.mark.parametrize("claimed", [_FIRST_PARTY, _KERNEL])
def test_an_enabled_but_unmounted_bundle_takes_nothing_out_of_the_offer(lane, claimed):
    """`scan` is not the mount: a claim on a reserved name never owns the name."""
    _bundle(lane["root"], "weather-card", _tool(name=claimed), {"handlers.py": _VALID_HANDLER})
    plugin_runtime.invalidate_ownership_cache()

    assert plugin_runtime.is_tool_visible(claimed) is True
    gate = plugin_runtime.tool_gate(claimed)
    assert gate.plugin != "weather-card"
    offered = _schemas(claimed)
    assert plugin_runtime.filter_schemas(offered) == offered

def test_a_version_1_activation_cannot_own_a_first_party_name(lane):
    """The version-1 switch cannot take a name the shipped bundle serves either."""
    directory = lane["root"] / "legacy-research"
    directory.mkdir(parents=True)
    (directory / MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "name": "legacy-research",
                "version": "1.0.0",
                "description": "Activates a name somebody else serves.",
                "permissions": {"tool_families": ["network"], "data_roots": []},
                "components": {"skills": [], "commands": [], "tools": [_FIRST_PARTY]},
            }
        ),
        encoding="utf-8",
    )
    plugin_runtime.invalidate_ownership_cache()

    scanned = scan_tool_activations(lane["root"])
    assert _FIRST_PARTY not in [name for name, _owner in scanned.owners]
    assert plugin_runtime.is_tool_visible(_FIRST_PARTY) is True

# 3. verify refuses the name with code, name and action

@pytest.mark.parametrize("claimed", [_FIRST_PARTY, _KERNEL])
def test_verify_refuses_a_reserved_name_with_a_way_out(lane, claimed):
    _staged(lane, claimed)
    answer = _call("verify_plugin_bundle", bundle="weather-card")

    assert answer["ok"] is False
    assert answer["error"] == "name_reserved"
    refusal = answer["refusals"][0]
    assert refusal["code"] == "reserved_tool_name"
    assert refusal["name"] == claimed
    assert f"{claimed}_weather_card" in refusal["action"]
    assert claimed in " ".join(answer["problems"])

def test_install_refuses_a_reserved_name_without_a_prior_verify(lane):
    """The install path is defensive on its own: no verify call is a bypass."""
    _staged(lane, _FIRST_PARTY)
    answer = _call("install_plugin_bundle", bundle="weather-card")

    assert answer["error"] == "install_refused", answer
    detail = answer["detail"]
    assert detail["status"] == "refused"
    assert "reserved_tool_name" in detail["error"]
    assert _FIRST_PARTY in detail["error"]
    assert f"{_FIRST_PARTY}_weather_card" in detail["error"]
    assert list(lane["root"].iterdir()) == [], "nothing lands in the plugins root"

def test_verify_refuses_a_version_1_activation_of_a_first_party_name(lane):
    """The version-1 switch is not a shortcut around the reservation."""
    _staged(lane, "sky_read")
    bundle = Path(creator_tools.bundle_dir("weather-card"))
    manifest = json.loads((bundle / MANIFEST_FILENAME).read_text())
    manifest["manifest_version"] = 1
    manifest["permissions"]["tool_families"] = ["network"]
    manifest["components"]["tools"] = [_FIRST_PARTY]
    (bundle / MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")

    answer = _call("verify_plugin_bundle", bundle="weather-card")

    assert answer["ok"] is False
    assert answer["error"] == "name_reserved"
    assert answer["refusals"][0]["namespace"] == FIRST_PARTY_RESERVED
    assert f"{_FIRST_PARTY}_weather_card" in answer["refusals"][0]["action"]

def test_a_mount_refuses_a_first_party_name(lane):
    _bundle(lane["root"], "weather-card", _tool(name=_FIRST_PARTY), {"handlers.py": _VALID_HANDLER})
    plugin_runtime.invalidate_ownership_cache()
    lifecycle = PluginLifecycle(
        lane["config"] / STATE_FILENAME,
        versions=plugin_runtime._installed_versions(),
    )

    with pytest.raises(LifecycleError) as caught:
        lifecycle.mount("weather-card")

    assert caught.value.code == FIRST_PARTY_RESERVED
    assert caught.value.status == 409
    assert caught.value.data.get("name") == _FIRST_PARTY
    assert f"{_FIRST_PARTY}_weather_card" in caught.value.data.get("action", "")

# 4. verify is a preflight for the Python it hands the worker

def test_verify_refuses_a_syntax_error_with_file_and_line(lane):
    _staged(lane, "sky_read", handler="def run(:\n    return 1\n")
    answer = _call("verify_plugin_bundle", bundle="weather-card")

    assert answer["ok"] is False
    assert answer["error"] == "source_invalid"
    problems = " ".join(answer["problems"])
    assert "tools/sky.py" in problems
    assert ":1:" in problems or "line 1" in problems

def test_verify_accepts_the_handler_it_parsed(lane):
    """The control: a valid entry file passes the same preflight."""
    _staged(lane, "sky_read")
    answer = _call("verify_plugin_bundle", bundle="weather-card")

    assert answer["ok"] is True, answer
    assert answer["tools"] == ["sky_read"]

def test_verify_parses_the_mcp_server_entry_too(lane):
    """An MCP tool carries no entry of its own; the server file still has to compile."""
    _staged_mcp(lane, "def serve(:\n    return 1\n")
    answer = _call("verify_plugin_bundle", bundle="weather-card")

    assert answer["ok"] is False, answer
    assert answer["error"] == "source_invalid"
    assert any("server.py:1:" in problem for problem in answer["problems"])

def test_verify_accepts_a_compiling_mcp_server(lane):
    _staged_mcp(lane, "def serve(arguments, state_dir):\n    return {}\n")
    answer = _call("verify_plugin_bundle", bundle="weather-card")

    assert answer["ok"] is True, answer
