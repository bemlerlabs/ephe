"""Gate and audit parity for the dynamic rail: a contributed tool is governed like a kernel one.

Two failures this file exists to keep apart. The first is a bypass: a `plugin_` name
that reaches a confined worker without the approval gate having judged it, which is
what wave G1 found on the meta-router path and what #11 must not reopen. The second is
the opposite — a dynamic tool refused for a reason a kernel tool would never get, so
the surface advertises a plugin tool nothing can call.

The unit of judgment is the descriptor's declared `tool_family` (#6) read against the
permission the plugin's own manifest asked for (`permissions.tool_families`,
validated by `core.plugin_manifest`). A family the manifest never declared is refused
before a worker exists; a family no manifest speaks of yet — every plugin whose tools
#13 has not moved into the manifest — is judged by the conservative answer only, which
asks before it runs and refuses in a read-only mode. Nothing here widens an approval:
no dynamic tool auto-runs on the chat path, because `chat_tool_requires_confirm` keeps
its rule that a name outside the read-only set is asked about.

The audit half writes the identity of what ran, in the shape `core.dynamic_refusals
.rail_fields` defines: plugin id, family, transport and the short fingerprint — and
never a host path, a schema body or a line of plugin source.
"""
from __future__ import annotations

from typing import Optional

from core.dynamic_refusals import rail_fields
from core.tools.chat_gate import denial_message
from core.tools.dynamic_registry import default_registry

#: Families a read-only mode may still run. Only `read`: a plugin tool that reaches the
#: network, a shell or a file writes in every way that matters to the mode's promise.
#: `web_search` sits in the kernel's own read-only set and stays there by name — this
#: table says nothing about kernel tools, which `READ_ONLY_MODE_TOOLS` already lists.
READ_ONLY_FAMILIES = frozenset({"read"})

#: The audit kinds this rail writes. All three exist already (`tool_start` and
#: `tool_exec` around a run, `tool_refused` for a call that did not happen, `security`
#: for a permission the plugin never asked for); inventing a fourth name would split
#: the trail a reader has to walk.
KIND_START = "tool_start"
KIND_RESULT = "tool_exec"
KIND_REFUSED = "tool_refused"
KIND_SECURITY = "security"


def descriptor_for(name: str):
    """The registered descriptor behind a tool name, or None for a kernel name."""
    if not name:
        return None
    try:
        return default_registry().get(name)
    except Exception:  # noqa: BLE001 — an unreadable registry is no descriptor
        return None


def declared_families(plugin_id: str) -> frozenset[str]:
    """The tool families one plugin's manifest declares, from the scan the gate reads.

    Empty is a real answer with two meanings the caller has to tell apart: a plugin no
    manifest carries (#13 has not moved its tools in yet) and a plugin that declared
    nothing. Both stop this file from granting anything, so they are folded into one
    "cannot judge" answer rather than a permission.
    """
    from core import plugin_manifest

    try:
        scanned = plugin_manifest.scan_plugins(None)
    except Exception:  # noqa: BLE001 — a broken portfolio declares nothing
        return frozenset()
    for record in scanned:
        manifest = record.get("manifest")
        if not isinstance(manifest, dict) or str(manifest.get("name")) != plugin_id:
            continue
        permissions = manifest.get("permissions")
        if not isinstance(permissions, dict):
            return frozenset()
        families = permissions.get("tool_families") or ()
        if not isinstance(families, (list, tuple, set)):
            return frozenset()
        return frozenset(str(family) for family in families)
    return frozenset()


def declares_family(plugin_id: str, family: str) -> Optional[bool]:
    """True if the manifest declares it, False if it declares others, None if it cannot say."""
    from core.plugin_manifest import KNOWN_TOOL_FAMILIES

    if family not in KNOWN_TOOL_FAMILIES:
        return False
    families = declared_families(plugin_id)
    if not families:
        return None
    return family in families


def permission_denial(name: str, arguments: dict):
    """The refusal for a dynamic tool whose family its plugin never asked for.

    Runs at the call that would execute, beside the plugin gate and the mode gate, so
    the deferred bridge (`tool_search` then `tool_call`) is answered the same way the
    model's own dispatch is. None when the name is not dynamic, when the declaration
    covers the family, and when no manifest can be read to judge it — the last of these
    keeps the run on the asking path instead of granting it.
    """
    descriptor = descriptor_for(name)
    if descriptor is None:
        return None
    verdict = declares_family(descriptor.plugin_id, descriptor.tool_family)
    if verdict is not False:
        return None
    denial = denial_message(
        name, "plugin_family_undeclared", family=descriptor.tool_family
    )
    audit(name, arguments, KIND_SECURITY, decision="denied", status="undeclared-family")
    audit(
        name,
        arguments,
        KIND_REFUSED,
        decision="plugin_family_undeclared",
        status="error",
    )
    return denial


def runs_read_only(name: str) -> bool:
    """True when a read-only mode may execute this dynamic tool: declared and read.

    All three halves have to hold — the descriptor's family is `read`, the plugin's
    manifest declares `read`, and the registry actually holds the name. Anything else
    answers False, which is the mode's own refusal.
    """
    descriptor = descriptor_for(name)
    if descriptor is None or descriptor.tool_family not in READ_ONLY_FAMILIES:
        return False
    return declares_family(descriptor.plugin_id, descriptor.tool_family) is True


def audit(name: str, arguments: dict, kind: str, *, decision: str, status: str) -> None:
    """One rail line, with the descriptor's identity beside it. Best effort by contract."""
    from core.audit_log import audit_event

    try:
        audit_event(
            kind,
            tool=name,
            args=arguments,
            decision=decision,
            status=status,
            detail=rail_fields(descriptor_for(name)),
        )
    except Exception:  # noqa: BLE001 — the trail never blocks the call it records
        pass


def audit_refused(name: str, arguments: dict, *, decision: str, status: str) -> None:
    """A call that did not happen, in the trail: the existing `tool_refused` kind."""
    audit(name, arguments, KIND_REFUSED, decision=decision, status=status)


def audit_result(name: str, arguments: dict, *, ok: bool) -> None:
    """The one result line of a permitted call — `tool_exec`, status `ok` or `error`."""
    audit(
        name,
        arguments,
        KIND_RESULT,
        decision="ok" if ok else "blocked",
        status="ok" if ok else "error",
    )


__all__ = [
    "KIND_REFUSED",
    "KIND_RESULT",
    "KIND_SECURITY",
    "KIND_START",
    "READ_ONLY_FAMILIES",
    "audit",
    "audit_refused",
    "audit_result",
    "declared_families",
    "declares_family",
    "descriptor_for",
    "permission_denial",
    "runs_read_only",
]
