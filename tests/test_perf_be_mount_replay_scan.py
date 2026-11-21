"""PERF-BE-FIX 1 — one mount replay reads the portfolio once, not once per bundle.

The first tool-schema read after a backend start replays every recorded mount. Each
mount asked the same two portfolio questions again — which names are reserved, and
which names the scanned bundles claim — so a 12-bundle replay walked the whole
portfolio 48 times (51 scans, 1,063 manifest parses, ~720 ms measured in
`/tmp/rel/PERF-BE-REPORT.md` §3.1). The replay now hands one namespace to every mount
of the pass; it reads the portfolio the first time a mount asks and drops it with the
pass.

The cases pin the count and the invalidation; the mount outcomes stay in
`test_plugin_mount_replay.py`.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_manifest, plugin_mount_replay, plugin_runtime
from core.plugin_lifecycle import STATE_FILENAME, PluginLifecycle
from core.tools.dynamic_registry import default_registry
from core.tools.registry import invalidate_tool_schema_cache

_REGISTRY = default_registry()
_BUNDLES = {"scan-a": "tick_a", "scan-b": "tick_b", "scan-c": "tick_c"}


def _bundle(root: Path, plugin: str, tool: str) -> Path:
    directory = root / plugin
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ephe-plugin.json").write_text(
        json.dumps({
            "manifest_version": 2,
            "name": plugin,
            "version": "0.1.0",
            "description": f"{plugin} replay probe",
            "publisher": {"name": "Ephe"},
            "license": "MIT",
            "permissions": {"tool_families": ["read"], "data_roots": []},
            "components": {"skills": [], "commands": [], "tools": [{
                "name": tool,
                "entry": "handlers.py:run",
                "family": "read",
                "description": "Report the seconds left.",
                "parameters": {"type": "object", "properties": {}},
            }]},
        }),
        encoding="utf-8",
    )
    (directory / "handlers.py").write_text(
        "def run(arguments, state_dir):\n    return 'ok'\n", encoding="utf-8"
    )
    return directory


@pytest.fixture()
def lane(tmp_path, monkeypatch):
    config = tmp_path / "cfg"
    config.mkdir()
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    monkeypatch.setenv("EPHE_PERSONA_DIR", str(config / "persona"))
    monkeypatch.setenv("EPHE_WORKSPACE", str(tmp_path / "workspace"))
    builtin = tmp_path / "builtin"
    builtin.mkdir()
    monkeypatch.setenv("EPHE_BUILTIN_PLUGINS_ROOT", str(builtin))
    monkeypatch.setattr(plugin_manifest, "BUILTIN_PLUGINS_ROOT", builtin)
    root = tmp_path / "plugins"
    root.mkdir()
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", root)
    from core import audit_log

    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", tmp_path / "audit.log")
    plugin_mount_replay.reset()
    plugin_runtime.invalidate_ownership_cache()
    invalidate_tool_schema_cache()
    yield {"root": root, "config": config, "tmp": tmp_path}
    for plugin in _BUNDLES:
        _REGISTRY.unregister_plugin(plugin)
    plugin_mount_replay.reset()
    plugin_runtime.invalidate_ownership_cache()
    invalidate_tool_schema_cache()


def _mount_all(lane) -> None:
    for plugin, tool in _BUNDLES.items():
        _bundle(lane["root"], plugin, tool)
    plugin_runtime.invalidate_ownership_cache()
    for plugin in _BUNDLES:
        PluginLifecycle(
            lane["config"] / STATE_FILENAME, versions=plugin_runtime._installed_versions()
        ).mount(plugin)
    invalidate_tool_schema_cache()


def _restart(lane) -> None:
    for plugin in _BUNDLES:
        _REGISTRY.unregister_plugin(plugin)
    plugin_mount_replay.reset()
    plugin_runtime.invalidate_ownership_cache()
    invalidate_tool_schema_cache()


def _counted_scans(monkeypatch) -> Counter:
    calls: Counter = Counter()
    real = plugin_manifest.scan_plugins

    def counted(*args, **kwargs):
        calls["scan_plugins"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(plugin_manifest, "scan_plugins", counted)
    return calls


def test_a_replay_of_three_bundles_reads_the_portfolio_once(lane, monkeypatch):
    """GIVEN three mounted bundles and one fresh-process replay
    WHEN the replay pass runs
    THEN every tool is published again and the portfolio was read once for the pass."""
    _mount_all(lane)
    _restart(lane)
    assert not any(_REGISTRY.get(tool) for tool in _BUNDLES.values())

    plugin_runtime.lifecycle()  # the manifest-signature caches the pass itself reads
    calls = _counted_scans(monkeypatch)
    outcome = plugin_mount_replay.republish_all()

    assert {row["status"] for row in outcome.values()} == {"published"}
    assert set(_BUNDLES.values()) <= set(_REGISTRY.names()), "the replay served nothing"
    # One reserved-name scan plus one activation scan answer every mount of the pass.
    # Before the namespace the same replay ran 4 scans per bundle (12 here).
    assert calls["scan_plugins"] <= 2, (
        f"the pass read the portfolio {calls['scan_plugins']} times"
    )


def test_the_replay_answers_are_dropped_by_the_ownership_invalidation(lane):
    """GIVEN a pass-level namespace that already answered WHEN the ownership cache is
    invalidated THEN the next question is answered from the folders again."""
    from core.plugin_mount_trust import MountNamespace

    _bundle(lane["root"], "scan-a", "tick_a")
    plugin_runtime.invalidate_ownership_cache()
    namespace = MountNamespace()
    assert namespace.directory("scan-a") == lane["root"] / "scan-a"

    _bundle(lane["root"], "scan-d", "tick_d")
    plugin_runtime.invalidate_ownership_cache()

    assert namespace.directory("scan-a") == lane["root"] / "scan-a"
    assert namespace.directory("scan-d") == lane["root"] / "scan-d", (
        "an invalidated namespace kept the portfolio it read before the write"
    )
