"""#79 — a mounted bundle is still mounted after the process that mounted it is gone.

The state document keeps the `mounts` section and the descriptor registry keeps the tools,
and only one of those survives a restart. Before the replay, a fresh process served nothing
behind a name the Extensions surface still labelled mounted — a record the reader could not
act on and a label that asserted more than the machine held.

The replay is a re-mount, so these tests are about the seam and not about the transition:
that the read of the tool set is what triggers it, that it happens once and not on every
schema rebuild, and that a bundle the class rules refuse to bring back is *reported* rather
than silently skipped.
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

from core import plugin_manifest, plugin_mount_replay, plugin_runtime
from core.plugin_lifecycle import STATE_FILENAME, PluginLifecycle
from core.plugin_mount_records import MOUNTS_FIELD
from core.tools.dynamic_registry import default_registry, served_tool_name
from core.tools.registry import execute_tool, get_tool_schemas, invalidate_tool_schema_cache

_REGISTRY = default_registry()
_PLUGIN = "replay-probe"
_NAME = served_tool_name(_PLUGIN, "tick")


def _bundle(root: Path, body: str = "safe") -> Path:
    directory = root / _PLUGIN
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ephe-plugin.json").write_text(
        json.dumps({
            "manifest_version": 2,
            "name": _PLUGIN,
            "version": "0.1.0",
            "description": "A bundle the replay is expected to bring back.",
            "publisher": {"name": "Ephe"},
            "license": "MIT",
            "permissions": {"tool_families": ["read"], "data_roots": []},
            "components": {"skills": [], "commands": [], "tools": [{
                "name": "tick",
                "entry": "handlers.py:run",
                "family": "read",
                "description": "Report the seconds left.",
                "parameters": {
                    "type": "object",
                    "properties": {"unit": {"type": "string"}},
                    "required": ["unit"],
                },
            }]},
        }),
        encoding="utf-8",
    )
    (directory / "handlers.py").write_text(
        "def run(arguments, state_dir):\n"
        "    import os\n"
        "    return {'pid': os.getpid(), 'unit': arguments.get('unit'),"
        " 'body': '" + body + "'}\n",
        encoding="utf-8",
    )
    plugin_runtime.invalidate_ownership_cache()
    invalidate_tool_schema_cache()
    return directory


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
    plugin_mount_replay.reset()
    plugin_runtime.invalidate_ownership_cache()
    invalidate_tool_schema_cache()
    yield {"root": root, "config": config, "log": log, "tmp": tmp_path}
    _REGISTRY.unregister_plugin(_PLUGIN)
    plugin_mount_replay.reset()
    plugin_runtime.invalidate_ownership_cache()
    invalidate_tool_schema_cache()


def _mount(lane) -> None:
    PluginLifecycle(
        lane["config"] / STATE_FILENAME, versions=plugin_runtime._installed_versions()
    ).mount(_PLUGIN)


def _restart(lane) -> None:
    """What a new process looks like: the descriptors are gone, the record is not.

    The cached lifecycle is dropped with the ownership cache, so the next one reads the
    state document from disk the way a start does.
    """
    _REGISTRY.unregister_plugin(_PLUGIN)
    plugin_mount_replay.reset()
    plugin_runtime.invalidate_ownership_cache()
    invalidate_tool_schema_cache()


def _schema_names() -> list[str]:
    return [entry.get("function", {}).get("name", "") for entry in get_tool_schemas()]


def _rows(log: Path, decision: str) -> list[dict]:
    if not log.exists():
        return []
    return [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("decision") == decision
    ]


def test_a_recorded_mount_is_serving_again_after_the_process_restarts(lane):
    """GIVEN a mounted bundle WHEN its descriptors are gone and the tool set is read
    THEN the name is offered again and a call still runs in a child."""
    _bundle(lane["root"])
    _mount(lane)
    assert _NAME in _schema_names()
    _restart(lane)
    assert _NAME not in _REGISTRY.names(), "the restart simulation did not clear anything"

    assert _NAME in _schema_names(), "the replay never ran on the shared read"
    payload = json.loads(asyncio.run(execute_tool(_NAME, {"unit": "seconds"})))
    assert payload["unit"] == "seconds" and payload["pid"] > 0


def test_the_replay_runs_once_and_not_on_every_schema_rebuild(lane):
    _bundle(lane["root"])
    _mount(lane)
    _restart(lane)

    for _ in range(3):
        assert _NAME in _schema_names()

    rows = _rows(lane["log"], "mount_replay")
    assert len(rows) == 1, rows
    assert rows[0]["status"] == "done"
    assert "published=1" in rows[0]["detail"]


def test_a_local_bundle_whose_code_was_edited_offline_comes_back_with_the_new_bytes(lane):
    """The Creator saves between runs; the replay must serve what is on disk now."""
    directory = _bundle(lane["root"], body="before")
    _mount(lane)
    (directory / "handlers.py").write_text(
        "def run(arguments, state_dir):\n"
        "    import os\n"
        "    return {'pid': os.getpid(), 'unit': arguments.get('unit'),"
        " 'body': 'after'}\n",
        encoding="utf-8",
    )
    _restart(lane)

    assert _NAME in _schema_names()
    payload = json.loads(asyncio.run(execute_tool(_NAME, {"unit": "x"})))
    assert payload["unit"] == "x" and payload["body"] == "after"
    record = json.loads((lane["config"] / STATE_FILENAME).read_text(encoding="utf-8"))
    assert record[MOUNTS_FIELD][_PLUGIN]["trust"] == "local"


def test_a_signature_accepted_bundle_that_moved_offline_is_not_brought_back(lane):
    """The tamper case at boot: a refusal is reported, and the name stays unserved."""
    directory = _bundle(lane["root"])
    _mount(lane)
    state_path = lane["config"] / STATE_FILENAME
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state[MOUNTS_FIELD][_PLUGIN]["trust"] = "signed"
    state[MOUNTS_FIELD][_PLUGIN]["signed"] = True
    state_path.write_text(json.dumps(state), encoding="utf-8")
    (directory / "handlers.py").write_text(
        "def run(arguments, state_dir):\n    import os\n    return os.environ\n",
        encoding="utf-8",
    )
    _restart(lane)

    assert _NAME not in _schema_names(), "a moved signed bundle was served anyway"
    replayed = _rows(lane["log"], "mount_replay")
    assert replayed and replayed[0]["status"] == "partial"
    assert "refused" in replayed[0]["detail"]
    assert plugin_mount_replay.replay_of(_PLUGIN)["status"] == "refused"
    assert "mount_artifact_changed" in plugin_mount_replay.replay_of(_PLUGIN)["detail"]


def test_a_recorded_bundle_that_is_no_longer_on_disk_is_reported_not_raised(lane):
    """A deleted folder leaves its mount record behind; reading it must not break a turn."""
    _bundle(lane["root"])
    _mount(lane)
    import shutil

    shutil.rmtree(lane["root"] / _PLUGIN)
    _restart(lane)

    assert _NAME not in _schema_names()
    assert plugin_mount_replay.replay_of(_PLUGIN)["status"] == "refused"
    assert _rows(lane["log"], "mount_replay")[0]["status"] == "partial"


def test_an_unmounted_bundle_stays_unmounted_across_a_restart(lane):
    _bundle(lane["root"])
    _mount(lane)
    PluginLifecycle(
        lane["config"] / STATE_FILENAME, versions=plugin_runtime._installed_versions()
    ).unmount(_PLUGIN)
    _restart(lane)

    assert _NAME not in _schema_names()
    assert plugin_mount_replay.replay_of(_PLUGIN)["status"] == "not-replayed"
    assert _rows(lane["log"], "mount_replay") == []
