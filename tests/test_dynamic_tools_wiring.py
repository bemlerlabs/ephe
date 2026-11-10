"""Task #7 — the dynamic registry wired into the schema view and the execution path.

These tests pin what later wave-2 tasks rely on: a registered descriptor appears in
``get_tool_schemas()`` through the existing gate and filter, its block is name-sorted
(the base the per-turn freeze #36 builds on), a call on a dynamic name is refused with
a reason code and runs nothing (the confined runner #9 does not exist yet), the live
MCP dispatch keeps priority over a same-named descriptor, and argument validation on a
dynamic schema refuses exactly like it does on a kernel schema.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from core.tools.dynamic_registry import (
    ToolDescriptor,
    default_registry,
    fingerprint_for,
    served_tool_name,
)
from core.tools.registry import (
    TOOL_MAP,
    execute_tool,
    get_tool_schemas,
    invalidate_tool_schema_cache,
)

_REGISTRY = default_registry()
_TOUCHED: set[str] = set()


def _schema(name: str, *, required: tuple[str, ...] = ("unit",)) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": "Counts the widgets currently in view.",
            "parameters": {
                "type": "object",
                "properties": {"unit": {"type": "string"}},
                "required": list(required),
            },
        },
    }


def _descriptor(
    plugin_id: str = "timer",
    tool: str = "tick",
    *,
    transport: str = "plugin",
    entry: str | None = "handlers:run",
    schema: dict | None = None,
) -> ToolDescriptor:
    name = (
        served_tool_name(plugin_id, tool) if transport == "plugin" else f"mcp_{tool}"
    )
    if schema is None:
        schema = _schema(name)
    _TOUCHED.add(plugin_id)
    return ToolDescriptor(
        name=name,
        plugin_id=plugin_id,
        schema=schema,
        transport=transport,
        entry=entry if transport == "plugin" else None,
        tool_family="read",
        fingerprint=fingerprint_for(schema),
    )


def _names(schemas: list[dict]) -> list[str]:
    return [
        entry["function"]["name"]
        for entry in schemas
        if isinstance(entry.get("function"), dict)
        and entry["function"].get("name")
    ]


@pytest.fixture(autouse=True)
def cfg(tmp_path, monkeypatch):
    invalidate_tool_schema_cache()
    root = tmp_path / "cfg"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(root))
    yield root
    for plugin_id in _TOUCHED:
        _REGISTRY.unregister_plugin(plugin_id)
    _TOUCHED.clear()
    invalidate_tool_schema_cache()


def _disable_plugin(cfg: Path, plugin_id: str) -> None:
    # The committed switch state is the real deactivation path: lifecycle writes
    # plugin-state.json and the runtime's cached lifecycle reloads it on the next read.
    from core import plugin_runtime
    from core.plugin_lifecycle import STATE_FILENAME, PluginLifecycle

    state = PluginLifecycle(
        cfg / STATE_FILENAME, versions=plugin_runtime._installed_versions()
    )
    state.set_enabled(plugin_id, False)


class TestSchemaView:
    def test_registered_descriptor_appears_with_the_envelope_shape(self):
        assert _REGISTRY.register(_descriptor()).ok
        schemas = get_tool_schemas()
        entry = next(
            e for e in schemas
            if e.get("function", {}).get("name") == "tick"
        )
        assert entry["type"] == "function"
        function = entry["function"]
        assert function["description"] == "Counts the widgets currently in view."
        assert function["parameters"]["required"] == ["unit"]
        # The kernel map is not touched: visibility here comes from the descriptor.
        assert "tick" not in TOOL_MAP

    def test_deactivating_the_plugin_hides_the_descriptor(self, cfg):
        # "web-research" is a builtin plugin, so its committed switch state gates it.
        descriptor = _descriptor(plugin_id="web-research", tool="pulse")
        assert _REGISTRY.register(descriptor).ok
        served = served_tool_name("web-research", "pulse")
        assert served == "pulse"
        assert served in _names(get_tool_schemas())
        _disable_plugin(cfg, "web-research")
        assert served not in _names(get_tool_schemas())

    def test_dynamic_block_is_name_sorted_and_stable_across_two_registrations(self):
        assert _REGISTRY.register(_descriptor(tool="brake")).ok
        assert _REGISTRY.register(_descriptor(tool="accelerate")).ok
        assert _REGISTRY.register(_descriptor(plugin_id="alarmit", tool="ring")).ok

        def dynamic_names() -> list[str]:
            return [n for n in _names(get_tool_schemas()) if _REGISTRY.get(n)]

        first = dynamic_names()
        assert first == sorted(first)
        # The names this test registered stay in the sorted block. A shipped
        # contributed tool may sit in the same block.
        assert {"accelerate", "brake", "ring"} <= set(first)
        assert dynamic_names() == first

    def test_registration_and_deregistration_invalidate_the_schema_cache(
        self, monkeypatch
    ):
        # A long TTL proves it is the invalidation, not an expiry, that moves the view.
        monkeypatch.setattr("core.tools.registry.TOOL_SCHEMA_CACHE_TTL_SECONDS", 3600)
        assert "tick" not in _names(get_tool_schemas())  # warms the cache
        assert _REGISTRY.register(_descriptor()).ok
        assert "tick" in _names(get_tool_schemas())
        assert _REGISTRY.unregister_plugin("timer") == 1
        assert "tick" not in _names(get_tool_schemas())


class TestExecution:
    @pytest.mark.asyncio
    async def test_plugin_transport_call_refuses_without_executing(self):
        descriptor = _descriptor(tool="tick", entry="never_imported_handler:run")
        assert _REGISTRY.register(descriptor).ok
        result = await execute_tool(descriptor.name, {"unit": "seconds"})
        assert "is not available" in result
        assert getattr(result, "code", "") == "tool_not_available"
        assert getattr(result, "happened", True) is False
        # Nothing ran: the entry text was never imported in this process (ruling A1).
        assert "never_imported_handler" not in sys.modules
        # And nothing could run: the record holds no callable anywhere.
        assert not any(callable(value) for value in vars(descriptor).values())

    @pytest.mark.asyncio
    async def test_live_mcp_tool_keeps_priority_over_the_descriptor(self, monkeypatch):
        descriptor = _descriptor(plugin_id="demo", tool="github_search", transport="mcp")
        assert _REGISTRY.register(descriptor).ok
        served = {"mcp_github_search": {"schema": {"name": descriptor.name, "description": "Served live"}}}
        monkeypatch.setattr("core.tools.registry.get_mcp_tools", lambda: served)

        async def _fake_call(name: str, arguments: dict) -> tuple[str, bool]:
            return "answered by the mcp client", False

        monkeypatch.setattr("core.tools.registry.call_registered_mcp_tool", _fake_call)
        result = await execute_tool(descriptor.name, {})
        assert "answered by the mcp client" in result
        assert "is not available" not in result

    @pytest.mark.asyncio
    async def test_mcp_transport_descriptor_also_refuses_when_not_served(self):
        descriptor = _descriptor(plugin_id="demo", tool="absent_remote", transport="mcp")
        assert _REGISTRY.register(descriptor).ok
        result = await execute_tool(descriptor.name, {"unit": "seconds"})
        assert "is not available" in result
        assert getattr(result, "code", "") == "tool_not_available"


class TestArgumentValidation:
    @pytest.mark.asyncio
    async def test_bad_shape_refused_identically_on_dynamic_and_kernel_schema(self):
        from core.tool_repair import repair_class_of

        # An argument set with an undeclared key and a missing required parameter
        # has no deterministic repair on either rail — both must refuse identically.
        kernel = await execute_tool("extract_pdf_text", {"bogus": 1})
        schema = {
            "type": "function",
            "function": {
                "name": "paths",
                "description": "Opens a recorded path.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }
        descriptor = _descriptor(tool="paths", schema=schema)
        assert _REGISTRY.register(descriptor).ok
        dynamic = await execute_tool(descriptor.name, {})  # same missing-param call

        assert kernel.startswith("[TOOL-ERROR]")
        assert dynamic.startswith("[TOOL-ERROR]")
        assert repair_class_of(kernel) == repair_class_of(dynamic) == "missing-param"
        assert str(dynamic).replace(descriptor.name, "X") == str(kernel).replace(
            "extract_pdf_text", "X"
        )
