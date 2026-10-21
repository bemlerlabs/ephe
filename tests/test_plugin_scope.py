"""GAP-01 / SCOPE-01 — workspace scoping for plugin file capabilities.

A tool owned by a plugin may read and write inside the active workspace only.
The same call made outside a plugin (the kernel path) keeps its allowed roots.
User and workspace switch state resolve workspace-first.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.plugin_lifecycle import PluginLifecycle


@pytest.fixture()
def scoped(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    config = tmp_path / "config"
    for directory in (workspace, outside, config):
        directory.mkdir()
    monkeypatch.setenv("EPHE_WORKSPACE", str(workspace))
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(config))
    from core import audit_log, plugin_runtime

    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", tmp_path / "audit.log")
    plugin_runtime.invalidate_ownership_cache()
    yield workspace, outside
    plugin_runtime.invalidate_ownership_cache()


@pytest.mark.asyncio
async def test_plugin_file_tools_are_workspace_scoped(scoped) -> None:
    from core.tools import file_ops
    from core.tools.registry import execute_tool

    workspace, outside = scoped
    inside_file = workspace / "note.txt"
    outside_file = outside / "secret.txt"
    inside_file.write_text("inside", encoding="utf-8")
    outside_file.write_text("SECRET-CONTENT", encoding="utf-8")

    inside = await execute_tool("read_file", {"path": str(inside_file)})
    assert "inside" in inside

    refused = await execute_tool("read_file", {"path": str(outside_file)})
    assert "access denied" in refused.lower()
    assert "SECRET-CONTENT" not in refused

    # The kernel path is unchanged: the same file is readable when no plugin
    # owns the call.
    assert "SECRET-CONTENT" in await file_ops.read_file(str(outside_file))


@pytest.mark.asyncio
async def test_a_plugin_write_outside_the_workspace_is_refused(scoped) -> None:
    from core.tools.registry import execute_tool

    workspace, outside = scoped
    target = outside / "written.txt"
    result = await execute_tool(
        "write_file", {"path": str(target), "content": "should not land"}
    )
    assert "access denied" in result.lower()
    assert not target.exists()

    inside = workspace / "written.txt"
    result = await execute_tool(
        "write_file", {"path": str(inside), "content": "lands"}
    )
    assert inside.read_text(encoding="utf-8") == "lands"
    assert "lands" in result


@pytest.mark.asyncio
async def test_a_plugin_file_tool_fails_closed_without_a_valid_workspace(
    scoped, monkeypatch
) -> None:
    from core.tools.registry import execute_tool

    workspace, _outside = scoped
    target = workspace / "note.txt"
    target.write_text("inside", encoding="utf-8")
    monkeypatch.setenv("EPHE_WORKSPACE", "/")
    result = await execute_tool("read_file", {"path": str(target)})
    assert "access denied" in result.lower()


def test_precedence(tmp_path) -> None:
    lifecycle = PluginLifecycle(
        tmp_path / "plugin-state.json",
        versions={"web-research": "1.0.0"},
        audit_sink=lambda entry: None,
    )
    lifecycle.set_enabled("web-research", False, scope="user")
    lifecycle.set_enabled("web-research", True, scope="workspace")
    assert lifecycle.snapshot("web-research", "user").enabled is False
    effective = lifecycle.effective("web-research")
    assert effective.enabled is True
    assert effective.scope == "workspace"
