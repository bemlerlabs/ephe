"""R60 — Plugin runtime wiring (Extensions wave E1).

The plugin store's toggles become real: the runtime consults plugin state
and hides/disables the mapped tool families. Keystone honesty properties:

1. Catalog → tool-family mapping: web-research→{web_search, fetch_url},
   memory→{memory}, vision→{analyze_image, vision_click, vision_type},
   image-studio→{generate_image}, code-shell→{run_shell},
   mcp-connector→prefix "mcp_".
2. Only EXPLICIT registry entries gate (plugins.json via the store UI);
   catalog defaults never hide tools silently (no behavior change until the
   user toggles — never break userspace).
3. Legacy master switch (plugins.json top-level `master_enabled`): the gating
   bypass retired with O-1. Explicit per-plugin states win; pause all is the
   separate global control.
4. TOOL_MAP stays complete (userspace); gating applies to the SCHEMA view
   (model-facing) and to EXECUTION (fail-closed, honest denial + audit).
5. Unknown plugin ids / unknown tool names never crash — fail-closed means
   execution denial for explicitly disabled plugins only.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_runtime  # noqa: E402
from core.plugin_store import REGISTRY_FILENAME, config_root  # noqa: E402


def _write_registry(tmp_path: Path, plugins: list[dict], master: bool | None = None) -> None:
    root = tmp_path / "cfg"
    root.mkdir(parents=True, exist_ok=True)
    body: dict = {"plugins": plugins}
    if master is not None:
        body["master_enabled"] = master
    (root / REGISTRY_FILENAME).write_text(json.dumps(body), encoding="utf-8")


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    return tmp_path / "cfg"


class TestGateSemantics:

    def test_default_all_visible_without_registry(self, cfg):
        """G: no plugins.json W: gate T: every mapped tool visible (stock)."""
        assert plugin_runtime.is_tool_visible("web_search") is True
        assert plugin_runtime.is_tool_visible("run_shell") is True

    def test_disabled_plugin_hides_family(self, cfg):
        """G: web-research disabled in registry W: gate T: both tools hidden."""
        _write_registry(cfg.parent, [{"name": "web-research", "enabled": False}])
        assert plugin_runtime.is_tool_visible("web_search") is False
        assert plugin_runtime.is_tool_visible("fetch_url") is False
        assert plugin_runtime.is_tool_visible("run_shell") is True

    def test_catalog_defaults_never_gate(self, cfg):
        """G: catalog says image-studio=false, registry silent W: gate T: visible."""
        assert plugin_runtime.is_tool_visible("generate_image") is True

    def test_mcp_prefix_rule(self, cfg):
        _write_registry(cfg.parent, [{"name": "mcp-connector", "enabled": False}])
        assert plugin_runtime.is_tool_visible("mcp_github_search") is False
        assert plugin_runtime.is_tool_visible("read_file") is True

    def test_master_off_no_longer_bypasses_explicit_off(self, cfg):
        """G: web-research disabled and legacy master off W: gate T: still hidden."""
        _write_registry(cfg.parent, [{"name": "web-research", "enabled": False}], master=False)
        assert plugin_runtime.is_tool_visible("web_search") is False
        assert plugin_runtime.is_tool_visible("read_file") is True

    def test_unknown_tool_visible_and_unknown_plugin_ignored(self, cfg):
        _write_registry(cfg.parent, [{"name": "totally-unknown-plugin", "enabled": False}])
        assert plugin_runtime.is_tool_visible("read_file") is True
        assert plugin_runtime.is_tool_visible("does_not_exist_tool") is True


class TestSchemaView:

    def test_filter_schemas_hides_disabled_family(self, cfg, monkeypatch):
        import core.tools.registry as registry

        _write_registry(cfg.parent, [{"name": "web-research", "enabled": False}])
        monkeypatch.setattr(registry, "_TOOL_SCHEMA_CACHE", None)
        names = {
            e["function"]["name"]
            for e in registry.get_tool_schemas()
            if "function" in e and "name" in e.get("function", {})
        }
        assert "web_search" not in names
        assert "read_file" in names

    def test_tool_map_stays_complete(self, cfg):
        """G: plugins disabled W: TOOL_MAP T: unchanged size (userspace)."""
        _write_registry(cfg.parent, [{"name": "web-research", "enabled": False}])
        from core.tools.registry import TOOL_MAP

        assert len(TOOL_MAP) == 77


class TestExecution:

    @pytest.mark.asyncio
    async def test_execute_denied_for_hidden_tool(self, cfg):
        """G: web-research off W: execute_tool(web_search) T: honest denial."""
        _write_registry(cfg.parent, [{"name": "web-research", "enabled": False}])
        from core.tools.registry import execute_tool

        result = await execute_tool("web_search", {"query": "x"})
        assert "disabled" in result.lower()
        assert "web-research" in result

    @pytest.mark.asyncio
    async def test_execute_denial_is_audited(self, cfg, monkeypatch, tmp_path):
        _write_registry(cfg.parent, [{"name": "code-shell", "enabled": False}])
        from core import audit_log

        log_file = tmp_path / "audit.log"
        monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", log_file)

        from core.tools.registry import execute_tool

        await execute_tool("run_shell", {"command": "ls"})
        log = log_file.read_text(encoding="utf-8")
        assert "plugin_gate" in log

    @pytest.mark.asyncio
    async def test_execute_still_works_when_enabled(self, cfg):
        """G: shell on (default) W: execute unknown tool T: normal not-found path."""
        from core.tools.registry import execute_tool

        result = await execute_tool("no_such_tool", {})
        assert "not found" in result.lower()


class TestMasterPersistence:

    def test_master_roundtrip(self, cfg):
        assert plugin_runtime.load_master_enabled() is True
        assert plugin_runtime.set_master_enabled(False) is True
        assert plugin_runtime.load_master_enabled() is False
        _write_registry(cfg.parent, [{"name": "web-research", "enabled": False}], master=True)
        assert plugin_runtime.load_master_enabled() is True

    def test_legacy_registry_shape_still_reads(self, cfg):
        """G: old plugins.json without master key W: load T: default true."""
        _write_registry(cfg.parent, [{"name": "web-research", "enabled": False}])
        assert plugin_runtime.load_master_enabled() is True
