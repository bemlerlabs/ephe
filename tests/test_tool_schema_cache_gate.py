"""Tool-schema cache gate.

The plugin gate is a post filter OUTSIDE the schema cache: the cache stores the
unfiltered list and get_tool_schemas() runs filter_schemas() on every return.
A disabled plugin's tools must therefore be absent on every call of a TTL
window, not only on the first (cache-miss) one.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.plugin_store import REGISTRY_FILENAME  # noqa: E402


def _write_registry(cfg_root: Path, plugins: list[dict], master: bool | None = None) -> None:
    cfg_root.mkdir(parents=True, exist_ok=True)
    body: dict = {"plugins": plugins}
    if master is not None:
        body["master_enabled"] = master
    (cfg_root / REGISTRY_FILENAME).write_text(json.dumps(body), encoding="utf-8")


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    root = tmp_path / "cfg"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(root))
    import core.tools.registry as registry

    monkeypatch.setattr(registry, "_TOOL_SCHEMA_CACHE", None)
    return root


def _names(schemas: list[dict]) -> set:
    return {e.get("function", {}).get("name") for e in schemas}


def test_disabled_plugin_stays_hidden_across_cached_calls(cfg):
    """G: web-research disabled W: two get_tool_schemas() calls inside one TTL
    T: both exclude the family and the two payloads serialise identically."""
    _write_registry(cfg, [{"name": "web-research", "enabled": False}])
    from core.tools import registry

    first = registry.get_tool_schemas()
    assert registry._TOOL_SCHEMA_CACHE is not None  # second call hits the cache
    second = registry.get_tool_schemas()

    assert "web_search" not in _names(first)
    assert "web_search" not in _names(second), "disabled tool leaked from the cache"
    assert "fetch_url" not in _names(second)
    assert "read_file" in _names(second)
    assert json.dumps(first) == json.dumps(second)


def test_filtered_schemas_gate_holds_across_cached_calls(cfg):
    """G: same registry W: two get_filtered_tool_schemas() calls T: both gated."""
    _write_registry(cfg, [{"name": "web-research", "enabled": False}])
    from core.tools import registry

    whitelist = ["web_search", "fetch_url", "read_file"]
    first = registry.get_filtered_tool_schemas(whitelist)
    second = registry.get_filtered_tool_schemas(whitelist)

    assert "web_search" not in _names(first)
    assert "web_search" not in _names(second)
    assert "read_file" in _names(second)


def test_registry_flip_applies_without_invalidation(cfg):
    """G: plugin toggled off then on between cached calls W: no cache reset
    T: the tool disappears, then returns on the next call."""
    _write_registry(cfg, [{"name": "web-research", "enabled": False}])
    from core.tools import registry

    hidden = registry.get_tool_schemas()
    assert "web_search" not in _names(hidden)

    from core.plugin_lifecycle import STATE_FILENAME, PluginLifecycle

    lifecycle = PluginLifecycle(
        cfg / STATE_FILENAME,
        versions={"web-research": "1.0.0"},
        audit_sink=lambda entry: None,
    )
    lifecycle.set_enabled("web-research", True)
    visible = registry.get_tool_schemas()
    assert "web_search" in _names(visible)
