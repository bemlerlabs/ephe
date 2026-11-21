"""B7 — one contributed tool, followed the whole way down the rail.

The slice tests each own a section: `test_dynamic_registry.py` the descriptor store,
`test_plugin_hot_mount.py` the transition, `test_dynamic_gate_audit.py` the gates and the
trail, `test_dynamic_runner.py` the confined child. This file asks the question none of
them can answer alone — does a bundle that declares one tool end up running that tool in a
child process, with the user asked and the trail able to say so? A rail that passes every
section test and fails at the seam between two of them is the failure mode this wave has
already hit twice, so the seam gets its own file.

Three more things live here because they are properties of the whole rail rather than of a
part: two bundles mounting at the same moment must leave one consistent served set; a
mount–unmount–mount cycle must re-offer the same name without a fresh acknowledgment; and
no contributed tool is auto-approved whatever family its descriptor claims.
"""
from __future__ import annotations

import asyncio
import json
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_manifest, plugin_runtime
from core.plugin_lifecycle import STATE_FILENAME, PluginLifecycle
from core.tools.approval import ApprovalPolicy
from core.tools.dynamic_registry import default_registry, served_tool_name
from core.tools.registry import execute_tool, get_tool_schemas, invalidate_tool_schema_cache

_REGISTRY = default_registry()
_MOUNTED: set[str] = set()


def _tool(name: str, family: str = "read") -> dict:
    return {
        "name": name,
        "entry": "handlers.py:run",
        "family": family,
        "description": "Report how many of the named thing are in view.",
        "parameters": {
            "type": "object",
            "properties": {"unit": {"type": "string"}},
            "required": ["unit"],
        },
    }


def _write_bundle(lane: dict, plugin_id: str, tools: list[dict]) -> Path:
    """A v2 bundle in the lane's own root, with the entry file the child will open."""
    directory = lane["root"] / plugin_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ephe-plugin.json").write_text(
        json.dumps({
            "manifest_version": 2,
            "name": plugin_id,
            "version": "0.1.0",
            "description": "A bundle that declares tools for the rail test.",
            "publisher": {"name": "Ephe"},
            "license": "MIT",
            "permissions": {"tool_families": ["read", "write"], "data_roots": []},
            "components": {"skills": [], "commands": [], "tools": tools},
        }),
        encoding="utf-8",
    )
    (directory / "handlers.py").write_text(
        "def run(arguments, state_dir):\n"
        "    import os\n"
        "    return {'pid': os.getpid(), 'unit': arguments.get('unit')}\n",
        encoding="utf-8",
    )
    _MOUNTED.add(plugin_id)
    plugin_runtime.invalidate_ownership_cache()
    invalidate_tool_schema_cache()
    return directory


def _lifecycle(lane: dict) -> PluginLifecycle:
    return PluginLifecycle(
        lane["config"] / STATE_FILENAME,
        versions=plugin_runtime._installed_versions(),
    )


@pytest.fixture()
def lane(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    config.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_PERSONA_DIR", str(config / "persona"))
    monkeypatch.setenv("EPHE_WORKSPACE", str(tmp_path / "workspace"))
    from core import audit_log

    log = tmp_path / "audit.log"
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", log)
    root = tmp_path / "plugins"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", root)
    plugin_runtime.invalidate_ownership_cache()
    invalidate_tool_schema_cache()
    yield {"root": root, "config": config, "log": log, "tmp": tmp_path}
    for plugin_id in list(_MOUNTED):
        _REGISTRY.unregister_plugin(plugin_id)
    _MOUNTED.clear()
    plugin_runtime.invalidate_ownership_cache()
    invalidate_tool_schema_cache()


def _rows(log: Path, kind: str) -> list[dict]:
    if not log.exists():
        return []
    return [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("kind") == kind
    ]


def _schema_names() -> list[str]:
    return [entry.get("function", {}).get("name", "") for entry in get_tool_schemas()]


def test_a_declared_tool_runs_in_a_child_after_the_user_says_yes(lane):
    """GIVEN a bundle declaring one read tool WHEN it mounts and the dialog approves
    THEN the answer came from another process and the trail shows ask and exec."""
    _write_bundle(lane, "counter", [_tool("count")])
    name = served_tool_name("counter", "count")
    assert _lifecycle(lane).mount("counter").names == (name,)
    assert name in _schema_names()

    asked: list[str] = []

    async def _approve(tool: str, args: dict) -> bool:
        asked.append(tool)
        return True

    answer = asyncio.run(
        execute_tool(name, {"unit": "widgets"}, policy=ApprovalPolicy(on_confirm=_approve))
    )

    assert asked == [name], "the user was never asked about the contributed tool"
    payload = json.loads(str(answer))
    assert payload["unit"] == "widgets"
    assert payload["pid"] > 0 and payload["pid"] != __import__("os").getpid(), (
        "the tool ran in this process"
    )
    exec_rows = [row for row in _rows(lane["log"], "tool_exec") if row.get("tool") == name]
    assert exec_rows, _rows(lane["log"], "tool_exec")
    assert "plugin=counter" in str(exec_rows[0])


def test_a_mounted_tool_is_asked_about_and_a_decline_runs_nothing(lane):
    """The chat rail's confirm rule, proven on a name that arrived from a manifest.

    #11 pinned `chat_tool_requires_confirm` against a descriptor registered directly; a
    mounted bundle is the case the product actually serves, and the rule must not depend
    on how the name got there.
    """
    from core.tools.approval_rules import chat_tool_requires_confirm
    from core.tools.chat_gate import confirm_for_chat

    _write_bundle(lane, "clockwork", [_tool("chime")])
    name = served_tool_name("clockwork", "chime")
    assert _lifecycle(lane).mount("clockwork").names == (name,)

    assert chat_tool_requires_confirm(name) is True

    async def _decline(tool: str, args: dict) -> bool:
        return False

    approved, denial = asyncio.run(
        confirm_for_chat(name, {"unit": "hours"}, on_confirm=_decline)
    )

    assert approved is False
    assert getattr(denial, "code", "") == "not_approved_by_user"
    assert not [row for row in _rows(lane["log"], "tool_exec") if row.get("tool") == name]


def test_two_bundles_mounting_at_once_leave_one_consistent_served_set(lane):
    """The seam #6's atomic swap protects: a concurrent mount is not a torn array.

    Every name the two bundles declare is served exactly once, and each belongs to the
    bundle that declared it — the property a mid-turn rebuild would break in the way the
    supply-chain literature names tool shadowing.
    """
    _write_bundle(lane, "left", [_tool("alpha"), _tool("beta")])
    _write_bundle(lane, "right", [_tool("gamma"), _tool("delta")])
    barrier = threading.Barrier(2)
    outcomes: list[tuple] = []
    lock = threading.Lock()

    def mount_one(plugin_id: str) -> None:
        machine = _lifecycle(lane)
        barrier.wait()
        try:
            result = machine.mount(plugin_id)
            row = (result.names, ())
        except Exception as exc:  # noqa: BLE001 — the thread reports, the test decides
            row = ((), (str(exc),))
        with lock:
            outcomes.append(row)

    threads = [
        threading.Thread(target=mount_one, args=(plugin,)) for plugin in ("left", "right")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not outcomes[0][1] and not outcomes[1][1], outcomes
    served = sorted(name for row in outcomes for name in row[0])
    assert served == sorted(
        [
            served_tool_name("left", "alpha"),
            served_tool_name("left", "beta"),
            served_tool_name("right", "gamma"),
            served_tool_name("right", "delta"),
        ]
    )
    assert len(served) == len(set(served)), "one name served twice"
    owners = {item.name: item.plugin_id for item in _REGISTRY.descriptor_snapshot()}
    assert owners[served_tool_name("left", "alpha")] == "left"
    assert owners[served_tool_name("right", "gamma")] == "right"

    from core.plugin_lockfile import LOCK_FILENAME, pinned_tools, read_lockfile

    lock = read_lockfile(lane["config"] / LOCK_FILENAME)
    assert pinned_tools(lock, "left"), "the concurrent mount lost the first bundle's pins"
    assert pinned_tools(lock, "right"), "the concurrent mount lost the second bundle's pins"


def test_a_mount_unmount_mount_cycle_re_offers_the_same_name_without_a_new_alarm(lane):
    """The pin is a memory of the contract, so re-mounting unchanged bytes stays silent."""
    _write_bundle(lane, "metronome", [_tool("swing")])
    name = served_tool_name("metronome", "swing")
    machine = _lifecycle(lane)

    first = machine.mount("metronome")
    machine.unmount("metronome")
    assert name not in _schema_names()
    again = machine.mount("metronome")

    assert first.first_mount is True
    assert again.names == (name,)
    assert again.changed == (), "an unchanged bundle was refused as a changed contract"
    assert again.first_mount is False
    assert name in _schema_names()
