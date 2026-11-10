"""Task #6 — the descriptor-based dynamic tool registry: shape, atomicity, refusals.

The registry holds ToolDescriptor records for plugin-contributed tools. These tests
pin the contract later wave-2 tasks read: descriptors are frozen data with a
transport name and a textual entry, registrations that collide with the kernel or
live MCP name space are refused with a reason, replace_for_plugin commits all of a
batch or none of it, and reads hand out snapshots immune to later writes.
"""
from __future__ import annotations

import dataclasses
import threading

import pytest

from core.tools.dynamic_registry import (
    COLLISION_KERNEL,
    COLLISION_MCP,
    DynamicToolRegistry,
    NAME_TAKEN,
    PLUGIN_MISMATCH,
    ToolDescriptor,
    default_reserved_names,
    fingerprint_for,
    served_tool_name,
)


def _schema(name: str, description: str = "Counts the widgets in view.", **extra) -> dict:
    parameters = {
        "type": "object",
        "properties": {"unit": {"type": "string"}},
        "required": ["unit"],
    }
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
            **extra,
        },
    }


_UNSET = object()


def _descriptor(
    plugin_id: str = "timer",
    tool: str = "tick",
    *,
    transport: str = "plugin",
    name: str | None = None,
    entry: object = _UNSET,
    family: str = "read",
    families: frozenset | None = None,
    schema: dict | None = None,
    fingerprint: str | None = None,
) -> ToolDescriptor:
    if name is None:
        name = served_tool_name(plugin_id, tool) if transport == "plugin" else f"mcp_{tool}"
    if entry is _UNSET:
        entry = None if transport == "mcp" else f"tools.{plugin_id}:{tool}"
    schema = _schema(name) if schema is None else schema
    return ToolDescriptor(
        name=name,
        plugin_id=plugin_id,
        schema=schema,
        transport=transport,
        entry=entry,
        tool_family=family,
        families=frozenset({family}) if families is None else families,
        fingerprint=fingerprint if fingerprint is not None else fingerprint_for(schema),
    )


def _registry(**reserved: str) -> DynamicToolRegistry:
    mapping = reserved or {
        "plugin_manager": COLLISION_KERNEL,
        "mcp_live_reader": COLLISION_MCP,
    }
    return DynamicToolRegistry(reserved_names=lambda: mapping)


class TestDescriptorShape:

    def test_round_trip_get_names_and_snapshot(self):
        reg = _registry()
        d = _descriptor()
        assert reg.register(d).ok is True
        assert reg.get("tick") is d
        assert reg.names() == ("tick",)
        assert reg.descriptor_snapshot() == (d,)

    def test_descriptor_is_frozen(self):
        d = _descriptor()
        with pytest.raises(dataclasses.FrozenInstanceError):
            d.name = "renamed"

    def test_no_field_can_hold_a_callable(self):
        def _handler():
            return None

        field_names = {f.name for f in dataclasses.fields(ToolDescriptor)}
        assert field_names == {
            "name",
            "plugin_id",
            "schema",
            "transport",
            "entry",
            "tool_family",
            "families",
            "fingerprint",
        }
        with pytest.raises(ValueError, match="transport"):
            _descriptor(transport=_handler, entry=None)
        with pytest.raises(ValueError, match="entry"):
            _descriptor(entry=_handler)
        with pytest.raises(ValueError, match="schema"):
            _descriptor(schema=_handler)
        with pytest.raises(ValueError, match="families"):
            _descriptor(families=frozenset({_handler}))
        with pytest.raises(ValueError, match="families"):
            _descriptor(families=frozenset({"root"}))
        with pytest.raises(ValueError, match="families"):
            _descriptor(families={"read"})

    def test_plugin_transport_requires_entry_mcp_transport_forbids_it(self):
        with pytest.raises(ValueError, match="entry"):
            _descriptor(transport="plugin", entry=None)
        with pytest.raises(ValueError, match="entry"):
            _descriptor(transport="mcp", tool="peek", entry="tools.peek:peek")

    def test_entry_must_be_relative_module_colon_callable(self):
        for bad in (
            "../evil:tick",
            "/abs/evil:tick",
            "tools/timer:tick",
            "tools.timer:",
            ":tick",
            "tools.timer:tick:extra",
            "1bad.module:tick",
        ):
            with pytest.raises(ValueError, match="entry"):
                _descriptor(entry=bad)

    def test_namespace_and_family_are_validated_at_construction(self):
        with pytest.raises(ValueError, match="name"):
            _descriptor(name="Plugin_Timer_Tick")
        with pytest.raises(ValueError, match="name"):
            _descriptor(name="tick", schema=_schema("other_tick"))
        with pytest.raises(ValueError, match="plugin_id"):
            _descriptor(plugin_id="Bad Id", name="tick")
        with pytest.raises(ValueError, match="tool_family"):
            _descriptor(family="teleport")
        with pytest.raises(ValueError, match="transport"):
            _descriptor(transport="kernel", entry=None)

    def test_fingerprint_is_pinned_to_the_schema(self):
        # The schema's inner name is the descriptor's name: a pin over two different
        # contracts would let a mount claim one and serve the other.
        schema = _schema("tick")
        with pytest.raises(ValueError, match="fingerprint"):
            _descriptor(schema=schema, fingerprint="0" * 64)
        with pytest.raises(ValueError, match="fingerprint"):
            _descriptor(schema=schema, fingerprint="zzzz")


class TestFingerprint:

    def test_equal_schemas_fingerprint_equal_key_order_independent(self):
        left = _schema("tick", unit={"a": 1, "b": 2})
        right = _schema("tick", unit={"b": 2, "a": 1})
        assert fingerprint_for(left) == fingerprint_for(right)

    def test_parameter_change_moves_the_fingerprint(self):
        before = _schema("tick")
        after = _schema("tick")
        after["function"]["parameters"]["properties"]["unit"]["type"] = "integer"
        assert fingerprint_for(before) != fingerprint_for(after)

    def test_description_change_moves_the_fingerprint(self):
        before = _schema("tick", "Counts the widgets in view.")
        after = _schema("tick", "Counts only the red widgets now.")
        assert fingerprint_for(before) != fingerprint_for(after)


class TestCollisions:

    def test_kernel_name_refused_with_reason(self):
        reg = _registry()
        outcome = reg.register(_descriptor(plugin_id="manager", name="plugin_manager"))
        assert outcome.ok is False
        assert outcome.code == COLLISION_KERNEL
        assert "plugin_manager" in outcome.detail
        assert reg.names() == ()

    def test_live_mcp_name_refused_with_reason(self):
        reg = _registry()
        outcome = reg.register(_descriptor(transport="mcp", tool="live_reader"))
        assert outcome.ok is False
        assert outcome.code == COLLISION_MCP
        assert reg.names() == ()

    def test_default_provider_sees_the_real_tool_map(self, monkeypatch):
        import core.tools.dynamic_registry as dynamic_registry

        monkeypatch.setattr(dynamic_registry, "_live_mcp_names", lambda: frozenset())
        reserved = default_reserved_names()
        assert reserved["delete_file"] == COLLISION_KERNEL
        assert reserved["plugin_manager"] == COLLISION_KERNEL
        assert reserved["bash"] == COLLISION_KERNEL
        assert reserved["read"] == COLLISION_KERNEL
        assert reserved["edit"] == COLLISION_KERNEL
        assert "web_search" not in reserved
        assert "fetch_url" not in reserved
        assert "memory" not in reserved
        assert "browser_go" not in reserved
        assert "browser_exec" not in reserved
        assert "vision_click" not in reserved
        assert "vision_type" not in reserved
        assert "analyze_image" not in reserved
        for name in (
            "read_file", "run_shell", "write_file", "edit_file", "list_directory",
            "file_search", "load_workspace", "analyze_project", "run_tests",
            "run_linter", "format_code", "scaffold_project",
        ):
            assert name not in reserved
        for name in (
            "create_pdf", "create_docx", "create_qrcode", "extract_pdf_text",
            "build_document", "export_source_brief", "create_source_notebook",
            "query_source_notebook", "verify_artifact",
            "create_xlsx", "generate_chart",
            "create_pptx_deck", "create_pitch_deck", "inspect_pptx_template",
            "edit_pptx_template", "qa_pptx_deck", "create_diagram", "create_svg",
            "generate_image",
            "synthesize", "transcribe",
        ):
            assert name not in reserved
        assert len(reserved) >= 32

    def test_duplicate_registration_same_plugin_refused(self):
        reg = _registry()
        first = _descriptor(tool="shared")
        assert reg.register(first).ok is True
        outcome = reg.register(_descriptor(tool="shared"))
        assert outcome.ok is False
        assert outcome.code == NAME_TAKEN
        assert reg.get("shared") is first

    def test_a_name_another_plugin_holds_is_refused_at_registration(self):
        """Ownership is settled against the live registry, not against a name shape.

        #98 removed the derived prefix, so a name no longer spells who owns it and
        construction cannot answer the question. `register` does, against the live map:
        the descriptor builds, and the second plugin is refused with `name_taken`.
        """
        reg = _registry()
        assert reg.register(_descriptor(plugin_id="timer", tool="shared")).ok is True
        foreign = _descriptor(plugin_id="alarm", name="shared")
        outcome = reg.register(foreign)
        assert outcome.ok is False and outcome.code == NAME_TAKEN
        assert "timer" in outcome.detail


class TestAtomicReplace:

    def test_failed_replace_leaves_the_prior_set_intact(self):
        reg = _registry()
        first = _descriptor(plugin_id="manager", tool="tick")
        second = _descriptor(plugin_id="manager", tool="tock")
        reg.register(first)
        reg.register(second)

        bad_batch = (
            _descriptor(plugin_id="manager", tool="new"),
            _descriptor(plugin_id="manager", name="plugin_manager"),
        )
        outcome = reg.replace_for_plugin("manager", bad_batch)
        assert outcome.ok is False
        assert outcome.code == COLLISION_KERNEL
        # Prior set intact: both old descriptors are still served, nothing partial.
        assert reg.names() == ("tick", "tock")
        assert reg.get("tick") is first
        assert reg.get("tock") is second
        assert reg.get("new") is None

    def test_failed_replace_leaves_names_and_state_untouched(self):
        reg = _registry()
        reg.register(_descriptor(plugin_id="timer", tool="shared"))
        reg.register(_descriptor(plugin_id="alarm", tool="own"))
        # A batch that collides with a live MCP name commits nothing at all.
        outcome = reg.replace_for_plugin(
            "alarm",
            (
                _descriptor(plugin_id="alarm", tool="fresh"),
                _descriptor(plugin_id="alarm", transport="mcp", tool="live_reader"),
            ),
        )
        assert outcome.ok is False
        assert outcome.code == COLLISION_MCP
        assert reg.names() == ("own", "shared")
        assert reg.get("fresh") is None

    def test_successful_replace_swaps_only_that_plugin(self):
        reg = _registry()
        old = _descriptor(tool="tick")
        reg.register(old)
        reg.register(_descriptor(plugin_id="alarm", tool="ring"))
        fresh = _descriptor(tool="hum")
        assert reg.replace_for_plugin("timer", (fresh,)).ok is True
        assert reg.names() == ("hum", "ring")
        assert reg.get("hum") is fresh

    def test_replace_rejects_foreign_plugin_id_and_duplicate_in_batch(self):
        reg = _registry()
        outcome = reg.replace_for_plugin("timer", (_descriptor(plugin_id="alarm"),))
        assert outcome.ok is False
        assert outcome.code == PLUGIN_MISMATCH
        dup = _descriptor(tool="tick")
        outcome = reg.replace_for_plugin("timer", (dup, dup))
        assert outcome.ok is False
        assert reg.names() == ()


class TestUnregisterAndSnapshot:

    def test_unregister_removes_only_that_plugin(self):
        reg = _registry()
        reg.register(_descriptor(plugin_id="timer", tool="tick"))
        reg.register(_descriptor(plugin_id="alarm", tool="ring"))
        removed = reg.unregister_plugin("timer")
        assert removed == 1
        assert reg.names() == ("ring",)
        assert reg.get("tick") is None
        assert reg.unregister_plugin("timer") == 0
        assert reg.names() == ("ring",)

    def test_snapshot_is_immune_to_later_registration(self):
        reg = _registry()
        reg.register(_descriptor(tool="tick"))
        snapshot = reg.descriptor_snapshot()
        names_before = reg.names()
        reg.register(_descriptor(tool="tock"))
        reg.unregister_plugin("timer")
        assert snapshot == tuple([_descriptor(tool="tick")])
        assert names_before == ("tick",)
        assert reg.names() == ()


class TestConcurrency:

    def test_concurrent_register_and_unregister_ends_consistent(self):
        reg = DynamicToolRegistry(reserved_names=lambda: {})
        barrier = threading.Barrier(12)
        errors: list[BaseException] = []

        def writer(worker: int) -> None:
            try:
                barrier.wait()
                for tool in range(5):
                    reg.register(_descriptor(plugin_id=f"p{worker}", tool=f"t{tool}"))
            except BaseException as exc:  # surfaced through the main thread below
                errors.append(exc)

        def remover(worker: int) -> None:
            try:
                barrier.wait()
                for _ in range(5):
                    reg.unregister_plugin(f"p{worker % 6}")
            except BaseException as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(w,)) for w in range(6)]
        threads += [threading.Thread(target=remover, args=(w,)) for w in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert errors == []

        # The two indexes agree on every live name, and the sorted views are stable.
        for name, descriptor in reg._by_name.items():
            assert reg._by_plugin[descriptor.plugin_id][name] is descriptor
        for plugin_id, owned in reg._by_plugin.items():
            for name, descriptor in owned.items():
                assert reg._by_name[name] is descriptor
                assert descriptor.plugin_id == plugin_id
        snapshot = reg.descriptor_snapshot()
        assert reg.names() == tuple(sorted(d.name for d in snapshot))
