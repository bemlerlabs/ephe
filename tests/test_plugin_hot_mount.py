"""Task #15 — a hot mount is one atomic transition on the lifecycle machine.

The question this file asks is not "can a tool be registered" (#6 answered that) but
"what happens to the rest of the machine when a mount breaks". A mount moves three
artifacts at once: the descriptor set in the dynamic registry, the activation record in
the lifecycle state file, and the pinned fingerprints in the lockfile. Every one of them
either ends up at the new bundle or is put back exactly where it was — a half-applied
mount is the corrupt state this task exists to prevent, and a plugin left serving two
contracts at once is worse than a plugin that never mounted.

Four directions are pinned. A mounted tool is served *and* runs in the confined worker,
so the mount is proven through the same rail a model uses. A failure at any step after
the first mutation restores all three artifacts and says in the audit which step broke.
A name the portfolio contests, or one the kernel or the MCP rail already holds, is
refused before anything is written, with the reason that names both claimants. Unmount
removes precisely that plugin's names, refuses a late call with a code rather than a
500, and is safe to repeat.

Everything here runs against a fixture bundle in a temporary plugin root; the shipped
portfolio is not edited by a mount test.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from core import plugin_manifest, plugin_runtime
from core.plugin_lifecycle import STATE_FILENAME, LifecycleError, PluginLifecycle
from core.plugin_lifecycle_types import (
    STEP_ACTIVATION,
    STEP_LOCKFILE,
    STEP_NOTIFY,
    STEP_REGISTRY,
)
from core.plugin_registry import scan_tool_activations
from core.tools.dynamic_registry import default_registry, served_tool_name
from core.tools.registry import execute_tool, get_tool_schemas, invalidate_tool_schema_cache

_REGISTRY = default_registry()
_PLUGINS: set[str] = set()

#: one declared tool, in the shape #13's contract validates and #9's worker resolves
_TICK = {
    "name": "tick",
    "entry": "handlers.py:run",
    "family": "read",
    "description": "Report how many seconds are left.",
    "parameters": {
        "type": "object",
        "properties": {"unit": {"type": "string"}},
        "required": ["unit"],
    },
}


def _manifest(plugin_id: str, tools: list[dict], *, version: str = "0.1.0") -> dict:
    return {
        "manifest_version": 2,
        "name": plugin_id,
        "version": version,
        "description": "A fixture bundle that contributes tools.",
        "publisher": {"name": "Ephe"},
        "license": "MIT",
        "permissions": {"tool_families": ["read"], "data_roots": []},
        "components": {"skills": [], "commands": [], "tools": tools},
    }


def _write_bundle(lane: dict, plugin_id: str, tools: list[dict]) -> Path:
    """A plugin directory whose manifest validates and whose entry file ships.

    Writing a bundle also rebuilds the machine under test: `lifecycle()` refreshes its
    installed set when the portfolio changes, and a mount asked for a bundle that
    appeared after construction is the ordinary case, not a special one.
    """
    directory = lane["root"] / plugin_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ephe-plugin.json").write_text(
        json.dumps(_manifest(plugin_id, tools), indent=2), encoding="utf-8"
    )
    (directory / "handlers.py").write_text(
        "def run(arguments, state_dir):\n"
        "    import os\n"
        "    return {'pid': os.getpid(), 'unit': arguments.get('unit')}\n",
        encoding="utf-8",
    )
    _PLUGINS.add(plugin_id)
    lane["lifecycle"] = _new_lifecycle(lane["config"])
    return directory


def _schema_names() -> list[str]:
    return [
        entry.get("function", {}).get("name", "") for entry in get_tool_schemas()
    ]


def _new_lifecycle(config: Path) -> PluginLifecycle:
    plugin_runtime.invalidate_ownership_cache()
    return PluginLifecycle(
        config / STATE_FILENAME, versions=plugin_runtime._installed_versions()
    )


@pytest.fixture
def lane(tmp_path, monkeypatch):
    """A hermetic config, one temporary plugin root and a cold audit trail."""
    from core import audit_log

    config = tmp_path / "cfg"
    config.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_PERSONA_DIR", str(config / "persona"))
    monkeypatch.setenv("EPHE_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", tmp_path / "audit.log")
    root = tmp_path / "plugins"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", root)
    plugin_runtime.invalidate_ownership_cache()
    invalidate_tool_schema_cache()
    state_path = config / STATE_FILENAME
    yield {
        "config": config,
        "root": root,
        "state": state_path,
        "lock": config / "plugin-lock.json",
        "log": tmp_path / "audit.log",
        "lifecycle": _new_lifecycle(config),
    }
    for plugin_id in list(_PLUGINS):
        _REGISTRY.unregister_plugin(plugin_id)
    _PLUGINS.clear()
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


def _snapshot_bytes(lane) -> tuple[bytes, tuple, bytes]:
    """The three artifacts a mount moves, as they are on disk right now."""
    state = lane["state"].read_bytes() if lane["state"].exists() else b""
    lock = lane["lock"].read_bytes() if lane["lock"].exists() else b""
    return state, _REGISTRY.descriptor_snapshot(), lock


def test_a_mount_serves_the_tool_and_the_confined_worker_runs_it(lane):
    """GIVEN a fixture bundle that declares one tool
    WHEN the lifecycle mounts it
    THEN the served name is in the registry and the schema view, and a call on it
    runs in a child process and answers."""
    _write_bundle(lane, "acme", [_TICK])
    name = served_tool_name("acme", "tick")

    result = lane["lifecycle"].mount("acme")

    assert result.names == (name,)
    assert result.first_mount is True
    assert _REGISTRY.get(name) is not None
    assert name in _schema_names()

    payload = json.loads(str(asyncio.run(execute_tool(name, {"unit": "seconds"}))))
    assert payload["unit"] == "seconds"
    assert payload["pid"] > 0


def test_a_mount_refuses_a_bundle_that_does_not_validate(lane):
    """A broken manifest is a coded refusal and no artifact moves at all."""
    directory = _write_bundle(lane, "broken", [_TICK])
    (directory / "ephe-plugin.json").write_text("{ not json", encoding="utf-8")
    before = _snapshot_bytes(lane)

    with pytest.raises(LifecycleError) as caught:
        lane["lifecycle"].mount("broken")

    assert caught.value.code == "mount_manifest_invalid"
    assert caught.value.status == 422
    assert _snapshot_bytes(lane) == before


@pytest.mark.parametrize(
    "step, method",
    [
        (STEP_LOCKFILE, "_mount_record_lockfile"),
        (STEP_ACTIVATION, "_mount_record_activation"),
        (STEP_REGISTRY, "_mount_publish_descriptors"),
        (STEP_NOTIFY, "_mount_notify"),
    ],
)
def test_a_mount_that_breaks_after_the_first_mutation_restores_everything(
    lane, monkeypatch, step, method
):
    """GIVEN a mount that dies at one named step after the first write
    WHEN the failure unwinds
    THEN the state file, the descriptor set and the lockfile are byte-for-byte what
    they were, and the audit says which step broke."""
    _write_bundle(lane, "acme", [_TICK])
    lane["lifecycle"].set_enabled("acme", True)
    mount_ok = lane["lifecycle"].mount("acme")
    assert mount_ok.names
    before = _snapshot_bytes(lane)

    def _boom(*_args, **_kwargs):
        raise RuntimeError(f"injected at {step}")

    monkeypatch.setattr(PluginLifecycle, method, _boom)

    with pytest.raises(RuntimeError, match=f"injected at {step}"):
        lane["lifecycle"].mount("acme", acknowledge=("plugin_acme_tick",))

    assert _snapshot_bytes(lane) == before
    assert _REGISTRY.get(served_tool_name("acme", "tick")).fingerprint
    rolled = [
        row
        for row in _rows(lane["log"], "plugin_lifecycle")
        if row["decision"] == "mount" and row["status"] == "rolled_back"
    ]
    assert rolled and f"step={step}" in rolled[0]["detail"]
    assert not [
        row
        for row in _rows(lane["log"], "plugin_lifecycle")
        if row["decision"] == "mount" and row["status"] == "committed"
        and f"step={step}" in row["detail"]
    ]


def test_a_mount_refuses_a_name_two_bundles_contest(lane):
    """Two bundles declaring one name: both lose it, and the refusal says so in the words
    the scan already owns.

    Since #98 the conflict is the ordinary case rather than a spelling accident — the
    derived prefix used to manufacture collisions out of dashes, and it also hid the real
    one. Two manifests that both promise `tick` is the collision the guard exists for.
    """
    _write_bundle(lane, "timer", [dict(_TICK)])
    _write_bundle(lane, "timer-lite", [dict(_TICK)])
    contested = served_tool_name("timer", "tick")
    before = _snapshot_bytes(lane)

    with pytest.raises(LifecycleError) as caught:
        lane["lifecycle"].mount("timer")

    assert caught.value.code == "mount_tool_conflict"
    assert caught.value.status == 409
    assert caught.value.detail == scan_tool_activations(None).reason_for(contested)
    assert "timer-lite" in caught.value.detail
    assert _snapshot_bytes(lane) == before


@pytest.mark.parametrize(
    "collision",
    ["reserved_kernel", "reserved_mcp"],
)
def test_a_name_the_kernel_or_the_mcp_rail_holds_is_refused_at_the_mount(
    lane, monkeypatch, collision
):
    """#7 left this concern open: a contributed name that steps into a live namespace
    never reaches the registry, and the refusal carries that namespace's own code."""
    from core.tools import dynamic_registry

    _write_bundle(lane, "acme", [_TICK])
    reserved = {served_tool_name("acme", "tick"): collision}
    monkeypatch.setattr(
        dynamic_registry, "default_reserved_names", lambda: dict(reserved)
    )
    before = _snapshot_bytes(lane)

    with pytest.raises(LifecycleError) as caught:
        lane["lifecycle"].mount("acme")

    assert caught.value.code == collision
    assert _snapshot_bytes(lane) == before
    assert _REGISTRY.get(served_tool_name("acme", "tick")) is None


def test_an_unmount_removes_exactly_that_plugins_names(lane):
    """Two bundles mounted; unmounting one leaves the other served and callable."""
    _write_bundle(lane, "acme", [_TICK])
    _write_bundle(lane, "other", [dict(_TICK, name="tock")])
    lane["lifecycle"].mount("acme")
    lane["lifecycle"].mount("other")

    result = lane["lifecycle"].unmount("acme")

    assert result.removed == (served_tool_name("acme", "tick"),)
    assert served_tool_name("acme", "tick") not in _REGISTRY.names()
    assert served_tool_name("acme", "tick") not in _schema_names()
    assert served_tool_name("other", "tock") in _REGISTRY.names()
    assert served_tool_name("other", "tock") in _schema_names()


def test_unmount_drops_that_name_from_the_addressable_set(lane, monkeypatch):
    """A hot-mounted name is addressable while the mount holds it, and only then.

    The read while the tool is served fills the manifest-scan cache. Unmount has
    to take that name out on the next read, and the neighbour that is still
    mounted stays. Mount and unmount also drop the scan, so a later read cannot
    keep a name the rail has taken down. The per-turn tool freeze would carry
    a stale name into a later read.
    """
    from core.tools import registry as tool_registry

    drops = {"n": 0}
    original = tool_registry.invalidate_addressable_tool_names

    def _spy() -> None:
        drops["n"] += 1
        original()

    monkeypatch.setattr(tool_registry, "invalidate_addressable_tool_names", _spy)
    _write_bundle(lane, "acme", [_TICK])
    _write_bundle(lane, "other", [dict(_TICK, name="tock")])
    tick = served_tool_name("acme", "tick")
    tock = served_tool_name("other", "tock")
    assert tick not in tool_registry.addressable_tool_names()
    assert tock not in tool_registry.addressable_tool_names()

    lane["lifecycle"].mount("acme")
    lane["lifecycle"].mount("other")
    assert tick in tool_registry.addressable_tool_names()
    assert tock in tool_registry.addressable_tool_names()

    lane["lifecycle"].unmount("acme")

    assert tick not in tool_registry.addressable_tool_names()
    assert tock in tool_registry.addressable_tool_names()
    assert drops["n"] >= 3


def test_a_call_for_a_just_unmounted_name_is_a_coded_refusal(lane):
    """The name is gone, so the answer is a reason a surface can translate — never a
    500 and never a silent pass."""
    _write_bundle(lane, "acme", [_TICK])
    name = served_tool_name("acme", "tick")
    lane["lifecycle"].mount("acme")
    lane["lifecycle"].unmount("acme")

    answer = asyncio.run(execute_tool(name, {"unit": "seconds"}))

    assert getattr(answer, "code", "") == "tool_not_available"
    assert "unmounted" in str(answer)
    refused = [
        row for row in _rows(lane["log"], "tool_refused") if row["tool"] == name
    ]
    assert refused and refused[-1]["decision"] == "tool_not_available"


def test_a_second_unmount_is_idempotent(lane):
    """Repeating the removal changes nothing and refuses nothing."""
    _write_bundle(lane, "acme", [_TICK])
    lane["lifecycle"].mount("acme")
    first = lane["lifecycle"].unmount("acme")
    before = _snapshot_bytes(lane)

    second = lane["lifecycle"].unmount("acme")

    assert second.removed == ()
    assert second.names == ()
    assert before == _snapshot_bytes(lane)
    assert first.removed == (served_tool_name("acme", "tick"),)


def test_the_trail_carries_a_row_for_the_mount_its_refusal_and_its_rollback(
    lane, monkeypatch
):
    """Three outcomes of one transition, each readable in the audit by itself: a mount
    that committed, a mount that refused, and a mount that rolled back."""
    # `acme` serves a name of its own; the pair below both promise `tick`, so the second
    # mount is the refused one and the first still commits.
    _write_bundle(lane, "acme", [dict(_TICK, name="acme_only")])
    _write_bundle(lane, "timer", [dict(_TICK)])
    _write_bundle(lane, "timer-lite", [dict(_TICK)])
    lane["lifecycle"].mount("acme")
    with pytest.raises(LifecycleError):
        lane["lifecycle"].mount("timer")

    def _boom(*_args, **_kwargs):
        raise RuntimeError("injected")

    monkeypatch.setattr(PluginLifecycle, "_mount_notify", _boom)
    with pytest.raises(RuntimeError):
        lane["lifecycle"].mount("acme")

    decisions = {
        (row["decision"], row["status"], row["tool"])
        for row in _rows(lane["log"], "plugin_lifecycle")
    }
    assert ("mount", "committed", "acme") in decisions
    assert ("mount", "refused", "timer") in decisions
    assert ("mount", "rolled_back", "acme") in decisions
