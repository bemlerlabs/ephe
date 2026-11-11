"""Wiring between the dynamic registry and the model-facing tool surface (wave 2, #7, #9).

`core/tools/registry.py` keeps only hook lines; the reading lives here. Three jobs:
hand the registered descriptors to the schema view in a stable order, keep the
descriptor of an inactive plugin out of that view (the check runs outside the schema
cache, where the plugin gate also runs, so a switch flip takes effect on the next
call), and answer a call on a dynamic name. Nothing here imports or invokes plugin
code — ruling A1: the descriptor's entry text is never resolved in this process. A
`plugin`-transport name runs in the confined runner (`core.sandbox.runner`), which
starts an OS-bounded child and reads its reply; a `mcp` name and any plugin whose
directory the registry cannot yet resolve (until #13 derives names from `plugin_id`)
keep the coded "not available" answer. A malformed argument shape is refused through
the same validation path the kernel tools use, before either rail is reached.
"""
from __future__ import annotations

import asyncio
import copy

from core import plugin_mount_replay
from core.dynamic_refusals import TOOL_NOT_AVAILABLE
from core.reason import reason
from core.tools.dynamic_registry import (
    TRANSPORT_MCP,
    TRANSPORT_PLUGIN,
    ToolDescriptor,
    default_registry,
)

#: The reason code a call on a visible-but-not-yet-runnable dynamic tool carries.
#: #10 registered the confined rail's codes once, in `core.dynamic_refusals`; this is
#: that one, named here for the two sites below that answer it.
REFUSAL_CODE = TOOL_NOT_AVAILABLE

_MCP_TEXT = (
    "the remote tool behind this name is not served right now — check the MCP "
    "server's connection, then call again"
)
_PLUGIN_TEXT = (
    "this plugin tool's own directory could not be resolved, so its confined "
    "worker was not started — do not retry this tool"
)
_UNMOUNTED_TEXT = (
    "this plugin tool was unmounted, so nothing runs behind the name — do not "
    "retry it; the plugin has to be mounted again"
)

#: Marker names from the kernel map. Each one is offered with the bundle tool's
#: schema and executed as that bundle tool. The kernel function stays on the
#: marker so the reachability contract can see one shared object.
MARKER_ALIASES = {
    "bash": "run_shell",
    "read": "read_file",
    "edit": "edit_file",
}


def _unmounted_refusal(name: str) -> str | None:
    """The coded answer for a name an unmount took away a moment ago.

    The registry no longer holds it, so without this the caller falls through to the
    unknown-tool line and a model that was offered the tool last turn reads a name it
    has never seen. One in-process ledger tells the two apart (#15).
    """
    from core.plugin_mount_records import unmounted_owner
    from core.tools.dynamic_gate import audit_refused

    plugin_id = unmounted_owner(name)
    if not plugin_id:
        return None
    audit_refused(name, {}, decision=REFUSAL_CODE, status="unmounted")
    return reason(
        REFUSAL_CODE,
        f"[Tool '{name}' is not available: {_UNMOUNTED_TEXT}]",
        plugin=plugin_id,
        transport=TRANSPORT_PLUGIN,
    )


def _envelope(descriptor: ToolDescriptor) -> dict:
    """The schema as the registry's envelope form, with the descriptor's own name.

    The descriptor's dict is never mutated: the envelope carries a copy, so the
    fingerprint stays pinned to the registered bytes.
    """
    body = descriptor.schema.get("function")
    if not isinstance(body, dict):
        body = descriptor.schema
    return {"type": "function", "function": {**body, "name": descriptor.name}}


def dynamic_tool_schemas() -> list[dict]:
    """The registered descriptors as schema envelopes, sorted by name.

    ``descriptor_snapshot()`` is one immutable tuple, name-sorted under the registry
    lock, so the appended block is byte-stable across calls while the set holds —
    the order the per-turn freeze (#36) builds on.

    The replay runs here rather than in one startup path because this is the read every
    surface shares: a bundle mounted before a restart is recorded as mounted and serves
    nothing until its descriptors come back, and the CLI, the TUI and an imported server
    all reach the tool set through this call.
    """
    plugin_mount_replay.publish_for_read()
    schemas = [_envelope(d) for d in default_registry().descriptor_snapshot()]
    by_name = {
        str((entry.get("function") or {}).get("name") or ""): entry for entry in schemas
    }
    for alias, canonical in MARKER_ALIASES.items():
        source = by_name.get(canonical)
        if source is None:
            continue
        copied = copy.deepcopy(source)
        function = copied.get("function")
        if isinstance(function, dict):
            function["name"] = alias
        schemas.append(copied)
    return schemas


def _plugin_active(plugin_id: str) -> bool:
    try:
        from core import plugin_runtime

        return plugin_runtime.is_plugin_active(plugin_id)
    except Exception:  # noqa: BLE001 - visibility fails open; execution refuses
        return True


def drop_inactive_plugin_schemas(schemas: list[dict]) -> list[dict]:
    """Hide the entries of a dynamic descriptor whose owning plugin is switched off.

    Only names the dynamic registry holds are examined, so the kernel and live MCP
    entries pass untouched — visibility authority for those stays in the plugin
    gate this function runs behind.
    """
    registry = default_registry()
    out: list[dict] = []
    for entry in schemas:
        raw = str((entry.get("function") or {}).get("name") or "")
        name = MARKER_ALIASES.get(raw, raw)
        descriptor = registry.get(name) if name else None
        if descriptor is not None and not _plugin_active(descriptor.plugin_id):
            continue
        out.append(entry)
    return out


async def dispatch_dynamic_call(name: str, arguments: dict) -> str | None:
    """The answer a call on a dynamic name gets.

    None when the name is not a registered descriptor — the caller then falls
    through to its unknown-tool line. A registered name validates its arguments
    through the same `_validate_tool_arguments` path as the kernel tools first, so a
    bad shape is refused identically and never reaches a worker. A `plugin` name that
    resolves to a real directory runs in the confined runner and returns its result;
    a `mcp` name routes through the plugin MCP manager to the confined server; a plugin
    whose directory the registry cannot yet resolve is refused with the coded "not
    available" line and starts nothing.
    """
    descriptor = default_registry().get(name)
    if descriptor is None:
        return _unmounted_refusal(name)
    from core.tools.registry import _audit_schema_rejection, _validate_tool_arguments

    validation_error = _validate_tool_arguments(name, arguments)
    if validation_error is not None:
        _audit_schema_rejection(name, arguments, validation_error)
        return validation_error
    if descriptor.transport == TRANSPORT_PLUGIN:
        executed = await asyncio.to_thread(_run_confined, descriptor, arguments)
        if executed is not None:
            return executed
    elif descriptor.transport == TRANSPORT_MCP:
        executed = await _run_plugin_mcp(descriptor, arguments)
        if executed is not None:
            return executed
    _audit_refusal(name, arguments)
    detail = _MCP_TEXT if descriptor.transport == TRANSPORT_MCP else _PLUGIN_TEXT
    text = f"[Tool '{name}' is not available: {detail}]"
    return reason(
        REFUSAL_CODE,
        text,
        plugin=descriptor.plugin_id,
        transport=str(descriptor.transport),
    )


def _run_confined(descriptor: ToolDescriptor, arguments: dict) -> str | None:
    """Delegate a plugin call to the confined runner; None when its directory is unknown."""
    try:
        from core.sandbox import runner

        return runner.execute(descriptor, arguments)
    except Exception as exc:  # noqa: BLE001 - a broken rail refuses, it never crashes the turn
        if exc.__class__.__name__ == "SandboxConfirmationRequired":
            raise
        return reason(
            REFUSAL_CODE,
            f"[Tool '{descriptor.name}' could not run: {type(exc).__name__}]",
            plugin=descriptor.plugin_id,
            transport=str(descriptor.transport),
        )


async def _run_plugin_mcp(descriptor: ToolDescriptor, arguments: dict) -> str | None:
    """Route a plugin MCP call through the confined server.

    The plugin MCP manager holds the running server for each plugin. If the server
    is not running (never started or crashed), returns None so the caller falls through
    to the "not available" refusal.
    """
    try:
        from core.plugin_mcp_server import plugin_mcp_manager

        manager = plugin_mcp_manager()
        if not manager.is_running(descriptor.plugin_id):
            return None
        text, is_error = await manager.call_tool(
            descriptor.plugin_id, descriptor.name, arguments
        )
        if is_error:
            return reason(
                REFUSAL_CODE,
                f"[Tool '{descriptor.name}' MCP error: {text}]",
                plugin=descriptor.plugin_id,
                transport=TRANSPORT_MCP,
            )
        return text
    except Exception as exc:  # noqa: BLE001 - a broken rail refuses, it never crashes the turn
        return reason(
            REFUSAL_CODE,
            f"[Tool '{descriptor.name}' could not run: {type(exc).__name__}]",
            plugin=descriptor.plugin_id,
            transport=TRANSPORT_MCP,
        )


def _audit_refusal(name: str, arguments: dict) -> None:
    """A refusal line in the audit: the existing tool_refused kind, no new names.

    The identity of the descriptor that was refused rides along — one shape, written by
    `core.tools.dynamic_gate`, so a reader can tell which pinned contract the call was
    made against without a host path or a schema body in the log.
    """
    from core.tools.dynamic_gate import audit_refused

    audit_refused(name, arguments, decision=REFUSAL_CODE, status="error")
