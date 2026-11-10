"""Task #11 — a contributed tool is gated and logged like a kernel tool.

The rail has to answer the same four questions for a `plugin_` name that it answers for
`read_file`: does the plugin's own manifest cover the family it declares, is the plugin
switched on, does the mode promise allow it, and did the user say yes. This file drives
those gates through `execute_tool` and reads the answer back from the **stored** audit
line rather than from a captured call argument — the pattern Wave 0 adopted in
`tests/test_composer_mode_rename.py`, because a mock proves the code called something and
only the file proves a reader can find out what happened.

Two directions are pinned. Nothing runs that the gates refuse, and nothing the gates
cover is refused with a weaker word than a kernel tool gets. The audit rows carry the
plugin id, the declared family, the transport and the short fingerprint (the leading 12
hex characters of #6's sha256) and no host path, no schema body, no plugin source.
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from core import plugin_manifest, plugin_runtime
from core.tools import dynamic_gate
from core.tools.chat_gate import DENIAL_PREFIX, denial_message, mode_denial
from core.tools.dynamic_registry import (
    ToolDescriptor,
    default_registry,
    fingerprint_for,
    served_tool_name,
)
from core.tools.registry import execute_tool, invalidate_tool_schema_cache

_REGISTRY = default_registry()
_TOUCHED: set[str] = set()

#: a plugin that exists in this tree and declares two families, so the declaration is
#: readable without a fixture: `plugins/web-research/ephe-plugin.json`
_INSTALLED = "web-research"
_UNDECLARED = "write"
#: the plugin id of the fixture bundle that declares its own tool, for the tests that
#: need the name to arrive from a manifest the way #15's mount delivers it
_GATED = "gate-probe"


def _schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "Counts the widgets currently in view.",
            "parameters": {
                "type": "object",
                "properties": {"unit": {"type": "string"}},
                "required": ["unit"],
            },
        },
    }


def _descriptor(plugin_id: str, tool: str, family: str) -> ToolDescriptor:
    name = served_tool_name(plugin_id, tool)
    schema = _schema(name)
    _TOUCHED.add(plugin_id)
    return ToolDescriptor(
        name=name,
        plugin_id=plugin_id,
        schema=schema,
        transport="plugin",
        entry="handlers:run",
        tool_family=family,
        fingerprint=fingerprint_for(schema),
    )


@pytest.fixture(autouse=True)
def lane(tmp_path, monkeypatch):
    from core import audit_log

    log = tmp_path / "audit.log"
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", log)
    config = tmp_path / "cfg"
    config.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    invalidate_tool_schema_cache()
    yield {"config": config, "log": log, "tmp": tmp_path}
    for plugin_id in _TOUCHED:
        _REGISTRY.unregister_plugin(plugin_id)
    _TOUCHED.clear()
    invalidate_tool_schema_cache()


def _stored(log: Path) -> list[dict]:
    """The lines the run left behind, read off the disk."""
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]


def _rows(log: Path, kind: str, tool: str) -> list[dict]:
    return [row for row in _stored(log) if row.get("kind") == kind and row.get("tool") == tool]


def _identity(descriptor: ToolDescriptor) -> dict:
    """What every rail row has to say about the call it records."""
    return {
        "plugin": f"plugin={descriptor.plugin_id}",
        "family": f"family={descriptor.tool_family}",
        "transport": f"transport={descriptor.transport}",
        "fingerprint": f"fingerprint={descriptor.fingerprint[:12]}",
    }


def _disable(config: Path, plugin_id: str) -> None:
    from core import plugin_runtime
    from core.plugin_lifecycle import STATE_FILENAME, PluginLifecycle

    PluginLifecycle(
        config / STATE_FILENAME, versions=plugin_runtime._installed_versions()
    ).set_enabled(plugin_id, False)


def _mount(tmp_path: Path, monkeypatch, plugin_id: str, families: list[str]) -> Path:
    """A resolvable plugin directory whose manifest declares exactly `families`."""
    root = tmp_path / "plugins" / plugin_id
    root.mkdir(parents=True, exist_ok=True)
    (root / "ephe-plugin.json").write_text(
        json.dumps({
            "manifest_version": 1, "name": plugin_id, "version": "0.1.0",
            "description": "A confined fixture plugin.",
            "permissions": {"tool_families": families, "data_roots": []},
            "components": {},
        }),
        encoding="utf-8",
    )
    (root / "handlers.py").write_text(
        "def run(arguments, state_dir):\n"
        "    import os\n"
        "    return {'pid': os.getpid(), 'unit': arguments.get('unit')}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", tmp_path / "plugins")
    return root


# The family gate


def test_a_family_the_manifest_never_declared_is_refused_by_the_gate(lane):
    descriptor = _descriptor(_INSTALLED, "scribble", _UNDECLARED)
    assert _REGISTRY.register(descriptor).ok
    assert dynamic_gate.declares_family(_INSTALLED, _UNDECLARED) is False

    denial = dynamic_gate.permission_denial(descriptor.name, {"unit": "seconds"})
    assert denial is not None and denial.code == "plugin_family_undeclared"
    assert DENIAL_PREFIX in str(denial) and "write" in str(denial)


@pytest.mark.parametrize("family", ["read", "network"])
def test_a_declared_family_passes_the_family_gate(lane, family):
    descriptor = _descriptor(_INSTALLED, f"tick_{family}", family)
    assert _REGISTRY.register(descriptor).ok
    assert dynamic_gate.declares_family(_INSTALLED, family) is True
    assert dynamic_gate.permission_denial(descriptor.name, {}) is None


def test_a_plugin_no_manifest_carries_is_never_granted_by_the_gate(lane):
    """#13 has not moved these names into a manifest yet, so nothing may be granted."""
    descriptor = _descriptor("timer", "tick", "read")
    assert _REGISTRY.register(descriptor).ok
    assert dynamic_gate.declares_family("timer", "read") is None
    assert dynamic_gate.permission_denial(descriptor.name, {}) is None
    assert dynamic_gate.runs_read_only(descriptor.name) is False


def test_an_undeclared_family_refuses_the_call_and_leaves_two_rows(lane):
    descriptor = _descriptor(_INSTALLED, "scribble", _UNDECLARED)
    assert _REGISTRY.register(descriptor).ok
    result = asyncio.run(execute_tool(descriptor.name, {"unit": "seconds"}))

    assert DENIAL_PREFIX in str(result)
    assert getattr(result, "code", "") == "plugin_family_undeclared"
    assert "is not available" not in str(result)
    assert not any(
        row.get("kind") == "tool_exec" and row.get("tool") == descriptor.name
        for row in _stored(lane["log"])
    ), "a refused call wrote a result row"
    assert "handlers" not in sys.modules

    identity = _identity(descriptor)
    refused = _rows(lane["log"], "tool_refused", descriptor.name)
    security = _rows(lane["log"], "security", descriptor.name)
    assert [row["decision"] for row in refused] == ["plugin_family_undeclared"]
    assert security and security[0]["decision"] == "denied"
    assert security[0]["status"] == "undeclared-family"
    for row in refused + security:
        for fragment in identity.values():
            assert fragment in row["detail"], (row, fragment)


# The switch: a disabled plugin answers disabled


def _declared_bundle(tmp_path: Path, monkeypatch, plugin_id: str, tool: str) -> Path:
    """A v2 bundle whose manifest declares one tool, mounted the way #15 mounts.

    The point of the fixture is *where the name comes from*: after #15 the mount
    transition is the only writer of a contributed descriptor, so the manifest scan —
    the same authority that answers for `read_file`'s owner plugin — is what the top gate
    reads. A test that registers a descriptor directly asks a question the product no
    longer has a shape for.
    """
    root = tmp_path / "declared"
    directory = root / plugin_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ephe-plugin.json").write_text(
        json.dumps({
            "manifest_version": 2,
            "name": plugin_id,
            "version": "0.1.0",
            "description": "A bundle that declares one network tool.",
            "publisher": {"name": "Ephe"},
            "license": "MIT",
            "permissions": {"tool_families": ["network"], "data_roots": []},
            "components": {
                "skills": [],
                "commands": [],
                "tools": [
                    {
                        "name": tool,
                        "entry": "handlers.py:run",
                        "family": "network",
                        "description": "Report how many seconds are left.",
                        "parameters": {
                            "type": "object",
                            "properties": {"unit": {"type": "string"}},
                            "required": ["unit"],
                        },
                    }
                ],
            },
        }),
        encoding="utf-8",
    )
    (directory / "handlers.py").write_text(
        "def run(arguments, state_dir):\n"
        "    import os\n"
        "    return {'pid': os.getpid(), 'unit': arguments.get('unit')}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", root)
    plugin_runtime.invalidate_ownership_cache()
    _TOUCHED.add(plugin_id)
    return directory


def test_a_disabled_plugin_answers_disabled_at_the_top_gate(lane, tmp_path, monkeypatch):
    """GIVEN a bundle whose manifest declares the tool and whose mount published it
    WHEN the plugin is switched off
    THEN the top gate refuses the call by name, from the scan alone."""
    from core.plugin_lifecycle import STATE_FILENAME, PluginLifecycle

    _declared_bundle(tmp_path, monkeypatch, _GATED, "pulse")
    name = served_tool_name(_GATED, "pulse")
    assert PluginLifecycle(
        lane["config"] / STATE_FILENAME, versions=plugin_runtime._installed_versions()
    ).mount(_GATED).names == (name,)
    descriptor = _REGISTRY.get(name)
    assert descriptor is not None
    _disable(lane["config"], _GATED)

    gate = plugin_runtime.tool_gate(name)
    assert gate.visible is False and gate.plugin == _GATED, (
        "the scan, not the descriptor registry, is what answers for this name"
    )
    assert descriptor.name in _REGISTRY.names()
    result = asyncio.run(execute_tool(descriptor.name, {"unit": "seconds"}))
    assert "is disabled" in str(result) and _GATED in str(result)
    assert "is not available" not in str(result)

    row = _rows(lane["log"], "tool_refused", descriptor.name)
    assert len(row) == 1, row
    assert row[0]["decision"] == "plugin_disabled"
    assert row[0]["status"] == "plugin-gate"
    for fragment in _identity(descriptor).values():
        assert fragment in row[0]["detail"]


def test_the_manifest_scan_is_the_gate_sole_owner_of_a_declared_name(
    lane, tmp_path, monkeypatch
) -> None:
    """The gate answers from the scan, so a descriptor cannot be its own authority.

    #13 derived the served name from the manifest and #15 made the mount the only writer,
    which is what let the registry-lookup branch go. This test is the reason that is safe
    rather than convenient: the verdict a reader gets has one source.
    """
    _declared_bundle(tmp_path, monkeypatch, _GATED, "pulse")
    name = served_tool_name(_GATED, "pulse")
    gate = plugin_runtime.tool_gate(name)

    assert gate.visible is True
    assert gate.plugin == _GATED, "the owner comes from the manifest, not from a lookup"
    assert plugin_runtime.tool_gate("plugin_manager").visible is True, (
        "a kernel name in the same prefix is untouched by the plugin branch"
    )


def test_the_disabled_plugin_loses_its_name_from_the_schema_view(lane):
    from core.tools.registry import get_tool_schemas

    descriptor = _descriptor(_INSTALLED, "pulse", "network")
    assert _REGISTRY.register(descriptor).ok
    names = [
        entry.get("function", {}).get("name") for entry in get_tool_schemas()
    ]
    assert descriptor.name in names
    _disable(lane["config"], _INSTALLED)
    assert descriptor.name not in [
        entry.get("function", {}).get("name") for entry in get_tool_schemas()
    ]


# The mode gate


@pytest.mark.parametrize("mode", ["plan", "architect", "ask", "analyst"])
def test_a_writing_family_is_refused_in_a_read_only_mode(lane, mode):
    from core.tools.session_ctx import reset_current_mode, set_current_mode

    descriptor = _descriptor(_INSTALLED, "scribble", _UNDECLARED)
    assert _REGISTRY.register(descriptor).ok
    token = set_current_mode(mode)
    try:
        denial = mode_denial(descriptor.name)
    finally:
        reset_current_mode(token)
    assert denial is not None
    assert denial.code == ("mode_no_tools" if mode in ("ask", "analyst") else "mode_read_only")


@pytest.mark.parametrize("mode", ["plan", "architect"])
def test_a_declared_read_tool_passes_the_mode_it_promises(lane, mode):
    from core.tools.session_ctx import reset_current_mode, set_current_mode

    descriptor = _descriptor(_INSTALLED, "peek", "read")
    assert _REGISTRY.register(descriptor).ok
    token = set_current_mode(mode)
    try:
        assert mode_denial(descriptor.name) is None
    finally:
        reset_current_mode(token)


def test_a_mode_refusal_writes_its_row(lane):
    from core.tools.session_ctx import reset_current_mode, set_current_mode

    descriptor = _descriptor("timer", "tick", "read")
    assert _REGISTRY.register(descriptor).ok
    token = set_current_mode("architect")
    try:
        result = asyncio.run(execute_tool(descriptor.name, {"unit": "seconds"}))
    finally:
        reset_current_mode(token)
    assert DENIAL_PREFIX in str(result)
    assert getattr(result, "code", "") == "mode_read_only"
    assert _rows(lane["log"], "mode_gate", descriptor.name)[0]["status"] == "mode_read_only"


# The approval profile


def test_no_dynamic_tool_is_auto_approved_whatever_family_it_declares(lane):
    """The gate never got weaker: every contributed name is asked about."""
    from core.tools.approval_rules import chat_tool_requires_confirm

    for family in ("read", "network", "write", "shell"):
        descriptor = _descriptor(_INSTALLED, f"tool_{family}", family)
        assert _REGISTRY.register(descriptor).ok
        assert chat_tool_requires_confirm(descriptor.name) is True


def test_a_strict_profile_denies_a_dynamic_call_it_cannot_ask_about(lane):
    """No approval channel is a denial, and the denial is a row."""
    from core.tools.approval import ApprovalPolicy

    descriptor = _descriptor(_INSTALLED, "scribble", "read")
    assert _REGISTRY.register(descriptor).ok
    strict = ApprovalPolicy(auto_approve=False, interactive=False)
    result = asyncio.run(execute_tool(descriptor.name, {"unit": "seconds"}, strict))

    # The same answer a kernel mutating tool gets from a profile that cannot ask: the
    # call is denied as mutating, and it says which name it denied.
    assert str(result).startswith("[Denied]") and "is mutating" in str(result)
    assert descriptor.name in str(result)
    row = _rows(lane["log"], "approval", descriptor.name)
    assert row and row[0]["decision"] == "denied"
    assert row[0]["status"] == "cli-policy"
    assert not _rows(lane["log"], "tool_exec", descriptor.name)
    assert not _rows(lane["log"], "tool_start", descriptor.name)


def test_an_unapproved_dialog_denies_at_the_chat_gate_and_auds_it(lane):
    from core.tools.chat_gate import confirm_for_chat

    descriptor = _descriptor(_INSTALLED, "scribble", "read")
    assert _REGISTRY.register(descriptor).ok

    async def _decline(name: str, args: dict) -> bool:
        return False

    approved, denial = asyncio.run(confirm_for_chat(descriptor.name, {"unit": "seconds"},
                                                    on_confirm=_decline))
    assert approved is False
    assert getattr(denial, "code", "") == "not_approved_by_user"
    row = _rows(lane["log"], "approval", descriptor.name)
    assert row[0]["decision"] == "denied" and row[0]["status"] == "chat-gate"


# The permitted call: one result row, no leak


def test_a_permitted_run_writes_exactly_one_result_row_with_its_identity(lane, monkeypatch):
    tmp_path = lane["tmp"]
    _mount(tmp_path, monkeypatch, "w11rail", ["read"])
    descriptor = _descriptor("w11rail", "tick", "read")
    assert _REGISTRY.register(descriptor).ok
    assert dynamic_gate.declares_family("w11rail", "read") is True

    result = asyncio.run(execute_tool(descriptor.name, {"unit": "seconds"}))
    payload = json.loads(str(result))
    assert payload["unit"] == "seconds"
    assert payload["pid"] != 0

    log = lane["log"]
    assert len(_rows(log, "tool_start", descriptor.name)) == 1
    results = _rows(log, "tool_exec", descriptor.name)
    assert len(results) == 1, results
    assert results[0]["status"] == "ok" and results[0]["decision"] == ""
    for row in _stored(log):
        if row.get("tool") != descriptor.name or row.get("kind") not in (
            "tool_start", "tool_exec", "tool_refused", "security"
        ):
            continue
        for fragment in _identity(descriptor).values():
            assert fragment in row["detail"], row
    assert not _rows(log, "tool_refused", descriptor.name)
    assert "plugin_entry" not in sys.modules, "the worker's import crossed into this process"


def test_the_stored_rows_carry_no_host_path_and_no_plugin_source(lane, monkeypatch):
    tmp_path = lane["tmp"]
    mounted = _mount(tmp_path, monkeypatch, "w11quiet", ["read"])
    descriptor = _descriptor("w11quiet", "tick", "read")
    assert _REGISTRY.register(descriptor).ok
    asyncio.run(execute_tool(descriptor.name, {"unit": "seconds"}))

    body = lane["log"].read_text(encoding="utf-8")
    assert str(mounted) not in body, "a plugin directory reached the audit trail"
    assert str(tmp_path) not in body, "a host path reached the audit trail"
    assert "def run(" not in body and "state_dir" not in body, "plugin source rode in the log"
    assert "handlers:run" not in body, "the descriptor entry is not an audit fact"


# The shape the trail is written in


def test_rail_fields_is_the_only_identity_writer(lane):
    """One shape for every row, so a reader parses one format and not three."""
    from core.dynamic_refusals import rail_fields

    descriptor = _descriptor(_INSTALLED, "tick", "read")
    assert rail_fields(descriptor).startswith(f"plugin={_INSTALLED} family=read ")
    assert rail_fields(None) == ""
    assert len(descriptor.fingerprint) == 64
    assert rail_fields(descriptor).endswith(descriptor.fingerprint[:12])


def test_the_denial_sentence_names_the_move_left(lane):
    denial = denial_message("plugin_acme_scribble", "plugin_family_undeclared", family="write")
    assert "write" in str(denial) and "reload" in str(denial)
    assert str(denial).endswith("Ask, or choose a read-only path.")
