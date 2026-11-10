"""Ephe — `components.tools`: what one manifest declares and what a name means.

core/plugin_tools_contract.py

A plugin that contributes a tool has to say four things about it: which name it answers
to, which file and callable carries it, which permission family it works in, and what the
model is told it does. Until #13 the manifest carried one of those four — a bare string
naming a *kernel* tool the plugin switched on, judged by `core/capability_policy`. That
list stays exactly as it was for a version 1 bundle, because every first-party bundle that
declares tools at all is written in it; a version 2 bundle declares one object per tool and
gets no lenient path back, so the two shapes are a function of the version rather than a
choice per entry.

Why the entry is text and stays text. Ruling A1 of the platform order: nothing in this
process imports a plugin. The entry is validated here the way the confined worker (#9)
will read it — `core.sandbox.runner.resolve_entry_file` re-resolves the same dotted module
inside the plugin directory with the same `_under` containment — so a bundle that passes
validation is a bundle whose worker can find its entry, and a bundle that fails never
reaches a process. Validation deliberately does not require the file to exist: the check is
about the shape of what is declared, and a missing entry answers at the call with a coded
refusal rather than a half-read manifest.

Why the name is declared, and what guards it. A bundle serves the name it writes —
`web_search`, not `plugin_web-research_web_search` — because the model was taught that name,
prompts and saved sessions carry it, and migrating a tool's implementation must not rename
the contract. `core.tools.dynamic_registry.served_tool_name` is still the one function both
the manifest scan and the mount call, so the rule has one home.

The prefix was never what stopped one plugin answering in another's namespace; the
reservation map does. `reserved_tool_names()` is its one source — the kernel map, the live
MCP rail and the names the shipped first-party bundles serve — and `verify`, install and the
mount read it through `reserved_tool`, refusing with the namespace code, the held name and
the prefixed name to choose instead. `core.plugin_registry` still marks a name two bundles
both declare as contested, so `refuse_contested_names` denies the mount with a reason naming
both. Dropping the prefix also drops the collision it created — `timer` + `lite_x` and
`timer-lite` + `x` used to spell one string, which a single manifest could never see coming.

What replaces the prefix's guarantee is a rule with a sharper edge: a v2 bundle cannot
declare a kernel or first-party name at all, at verify, at install and at the mount. One
name, one provider, at every moment — the refusal is the mechanism working; routing around
it is not an option the design offers.

What is refused, in one list: an unknown field, a suffix outside `[a-z][a-z0-9_]*`, a served
name past the 64-character ceiling the namespace carries, an entry that is absolute, leaves
the plugin directory, names something other than a Python file, holds more or less than one
`:`, or names a callable that is not an identifier, a module path with a segment that cannot
be imported, a family outside `KNOWN_TOOL_FAMILIES`, a family the manifest's own
`permissions.tool_families` does not ask for, a description that is empty, a parameter object
that is not an object, and a name declared twice in one manifest.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.tools.dynamic_registry import ToolDescriptor

__all__ = [
    "FIRST_PARTY_RESERVED",
    "MAX_SERVED_NAME_CHARS",
    "REQUIRED_TOOL_FIELDS",
    "RESERVED_TOOL_CODE",
    "ReservedName",
    "TOOL_ENTRY_FIELDS",
    "ToolClaim",
    "declared_families",
    "descriptors_for",
    "module_entry",
    "reserved_namespace",
    "reserved_tool",
    "reserved_tool_names",
    "reserved_tool_refusals",
    "suggested_tool_name",
    "tool_claims",
    "validate_tools",
]

#: The ceiling #6 puts on a served name; a name past it cannot be registered, so a
#: manifest that produces one is refused here rather than at the mount.
MAX_SERVED_NAME_CHARS = 64
#: The namespace code of a name a first-party bundle already serves. Kernel and MCP names
#: keep the codes `core.tools.dynamic_registry` speaks (`reserved_kernel`, `reserved_mcp`).
FIRST_PARTY_RESERVED = "reserved_first_party"
#: The refusal code for one declared tool that claims a reserved name.
RESERVED_TOOL_CODE = "reserved_tool_name"
TOOL_ENTRY_FIELDS = frozenset(
    {"name", "entry", "family", "description", "parameters", "transport"}
)
REQUIRED_TOOL_FIELDS = ("name", "entry", "family", "description")

_SUFFIX_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_SEGMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_MODULE_SUFFIX = ".py"
_EMPTY_PARAMETERS: dict = {"type": "object", "properties": {}}


@dataclass(frozen=True)
class ToolClaim:
    """One declared tool, normalized the way the scan, the mount and the gate all read it.

    ``name`` is the served name a caller addresses; ``suffix`` is what the manifest
    spelled. Keeping both is what lets a contested name say which two declarations met.
    ``entry`` is the dotted module the confined worker resolves, and ``declared`` the same
    entry as the bundle wrote it — the one form that says which file has to ship, which is
    the question the gate asks and validation deliberately does not.
    """

    plugin_id: str
    suffix: str
    name: str
    entry: str
    declared: str
    family: str
    description: str
    parameters: dict
    contributed: bool
    #: The rail the call rides: "plugin" (confined worker) or "mcp" (the bundle's
    #: own tool server). An MCP tool carries no entry — the server owns the callable.
    transport: str = "plugin"


def module_entry(entry: str) -> str:
    """`tools/tick.py:run` as the dotted module the confined worker names."""
    path, sep, callable_name = str(entry).rpartition(":")
    if not sep:
        return ""
    return f"{path[: -len(_MODULE_SUFFIX)].replace('/', '.')}:{callable_name}"


def _namespace_reserved() -> dict[str, str]:
    """The kernel and live-MCP names the dynamic registry itself refuses.

    Read lazily: the manifest layer does not import the tool layer at module scope, and an
    unreadable name space grants nothing rather than crashing.
    """
    try:
        from core.tools.dynamic_registry import default_reserved_names

        return dict(default_reserved_names())
    except Exception:  # noqa: BLE001 - an unreadable name space grants nothing
        return {}


def reserved_namespace(name: str) -> str:
    """The collision code of a kernel or live-MCP name, or "" for none.

    This is the dynamic registry's intake question, answered at the manifest layer so the
    scan and the mount read the same map. A first-party bundle's name is refused through
    `reserved_tool`, which knows which bundle ships it; this function deliberately answers
    only the two live rails the registry registers against.
    """
    return str(_namespace_reserved().get(name) or "")


@dataclass(frozen=True)
class ReservedName:
    """One name the platform already serves, and who holds it.

    ``code`` is the namespace code a refusal speaks (`reserved_kernel`, `reserved_mcp`,
    `reserved_first_party`), ``owner`` is the kernel, the MCP rail or the first-party
    bundle, and ``builtin_dir`` is the directory of that bundle — the only directory that
    may serve the name. A user bundle, and a staged copy waiting to become one, has no
    claim on it.
    """

    name: str
    code: str
    owner: str
    builtin_dir: Path | None = None

    def action(self, plugin_id: str) -> str:
        """What the author can do instead: pick the prefixed, free name."""
        return f"choose {suggested_tool_name(self.name, plugin_id)!r}"


def suggested_tool_name(name: str, plugin_id: str) -> str:
    """A free served name for one bundle: `<name>_<plugin>`, inside the name ceiling."""
    slug = re.sub(r"[^a-z0-9]+", "_", str(plugin_id).lower()).strip("_") or "plugin"
    candidate = f"{name}_{slug}"
    if len(candidate) > MAX_SERVED_NAME_CHARS:
        candidate = candidate[: MAX_SERVED_NAME_CHARS - 2].rstrip("_") + "_x"
    return candidate


def reserved_tool_names() -> dict[str, ReservedName]:
    """Every name a bundle may not serve, in one map — the single source of reservation.

    Three answers in one place: the kernel map and the live MCP rail (through
    `default_reserved_names`, the object the descriptor registry refuses against), and the
    names the shipped first-party bundles serve. `verify`, install, the mount and the
    registry scan all read this function, so the set of reserved names never forks into a
    second catalog.
    """
    from core import plugin_manifest

    reserved: dict[str, ReservedName] = {}
    for name, code in _namespace_reserved().items():
        owner = "kernel" if code == "reserved_kernel" else "mcp"
        reserved[str(name)] = ReservedName(str(name), str(code), owner)
    root = plugin_manifest.builtin_plugins_root()
    for entry in plugin_manifest.scan_plugins(root):
        manifest = entry["manifest"]
        if entry["error"] or not isinstance(manifest, dict):
            continue
        for claim in tool_claims(manifest):
            reserved.setdefault(
                claim.name,
                ReservedName(
                    claim.name,
                    FIRST_PARTY_RESERVED,
                    claim.plugin_id,
                    Path(entry["dir"]),
                ),
            )
    return reserved


def reserved_tool(
    name: str,
    *,
    plugin_id: str = "",
    plugin_dir: Path | str | None = None,
    reserved: dict[str, ReservedName] | None = None,
) -> ReservedName | None:
    """The reservation a claim on ``name`` meets, or None when the name is free.

    The bundle that ships a first-party name may serve it again — its own directory is the
    one witness that it is that bundle, so a user copy that happens to carry the same id is
    still refused. Every other claimant is refused, and a caller that cannot name the
    directory fails closed.
    """
    table = reserved_tool_names() if reserved is None else reserved
    entry = table.get(str(name))
    if entry is None:
        return None
    if (
        entry.builtin_dir is not None
        and plugin_dir is not None
        and str(plugin_id) == entry.owner
    ):
        try:
            if Path(plugin_dir).resolve() == entry.builtin_dir.resolve():
                return None
        except OSError:
            pass
    return entry


def reserved_tool_refusals(
    manifest: dict, plugin_dir: Path | str | None = None
) -> tuple[dict, ...]:
    """Each declared tool that claims a reserved name, with code, name and way out.

    A version-2 claim on any reserved name is refused. A version-1 manifest does not
    contribute a tool, but it may not switch on a name a first-party bundle already serves
    either — that is the same takeover one version older. The shape is the one `verify`
    and the install path report: `code` is `reserved_tool_name`, `name` the claimed tool,
    `namespace` the code of the space that holds it, and `action` the free name the author
    can choose.
    """
    plugin_id = str(manifest.get("name") or "")
    reserved = reserved_tool_names()
    out: list[dict] = []
    for claim in tool_claims(manifest):
        held = reserved_tool(
            claim.name,
            plugin_id=plugin_id,
            plugin_dir=plugin_dir,
            reserved=reserved,
        )
        if held is None:
            continue
        if not claim.contributed and held.code != FIRST_PARTY_RESERVED:
            continue
        out.append(
            {
                "code": RESERVED_TOOL_CODE,
                "name": claim.name,
                "namespace": held.code,
                "owner": held.owner,
                "action": held.action(plugin_id),
            }
        )
    return tuple(out)


def validate_tools(manifest: dict, plugin_dir: Path) -> str | None:
    """The `components.tools` contract for both supported versions: an error, or None.

    Called once from `core.plugin_manifest._validate`, the way `validate_ui` and
    `validate_libraries` are called, so the version-1 branch keeps `capability_policy`'s
    kernel-permission answer exactly where it was.
    """
    from core import plugin_manifest

    components = manifest.get("components", {})
    tools = components.get("tools", [])
    if not isinstance(tools, list):
        return "components.tools: list expected"
    if manifest.get("manifest_version") == plugin_manifest.MANIFEST_VERSION_V2:
        return _validate_v2(manifest, plugin_dir, tools)
    return _validate_v1(manifest, tools)


def _validate_v1(manifest: dict, tools: list) -> str | None:
    from core.capability_policy import validate_tool_permissions

    for tool in tools:
        if not isinstance(tool, str):
            return (
                "components.tools: a version 1 manifest names the kernel tools it "
                f"activates; a declared entry is version 2 ({tool!r})"
            )
        if not _SUFFIX_RE.match(tool):
            return f"components.tools: bad tool name {tool!r}"
    return validate_tool_permissions(manifest)


def _validate_v2(manifest: dict, plugin_dir: Path, tools: list) -> str | None:
    from core.tools.dynamic_registry import served_tool_name

    declared = declared_families(manifest)
    plugin_id = str(manifest.get("name") or "")
    seen: set[str] = set()
    # The bundle's MCP server: a tool riding that rail needs one declared, and the
    # server entry obeys the same lexical rule a plugin callable does. The host
    # never imports it — the confined server runs it (ruling A1).
    components = manifest.get("components", {})
    mcp = components.get("mcp") if isinstance(components, dict) else None
    has_mcp_tool = any(
        isinstance(t, dict) and (t.get("transport") or "plugin") == "mcp" for t in tools
    )
    if mcp is not None or has_mcp_tool:
        if not isinstance(mcp, dict):
            return "components.mcp: an object with a server entry is expected"
        error = _entry_field_error("components.mcp", mcp.get("entry"), plugin_dir)
        if error:
            return error
    for index, tool in enumerate(tools):
        if not isinstance(tool, dict):
            return (
                f"components.tools: a version 2 bundle declares one object per tool, "
                f"not {tool!r}"
            )
        suffix = tool.get("name")
        label = suffix if isinstance(suffix, str) and suffix.strip() else f"entry {index}"
        prefix = f"components.tools.{label}"
        error = _entry_error(prefix, tool, plugin_dir, declared)
        if error:
            return error
        if suffix in seen:
            return f"components.tools: duplicate name {suffix!r} in one manifest"
        seen.add(suffix)
        served = served_tool_name(plugin_id, str(suffix))
        if len(served) > MAX_SERVED_NAME_CHARS:
            return (
                f"components.tools.{suffix}: served name {served!r} is "
                f"{len(served)} characters, past the {MAX_SERVED_NAME_CHARS} the "
                "tool namespace carries"
            )
    return None


def declared_families(manifest: dict) -> frozenset[str]:
    """The families `permissions.tool_families` asks for, as one set.

    The gate reads it through this function: a second answer to "which families does this
    bundle claim" is a second authority, and #11 refuses an undeclared family at the call.
    """
    permissions = manifest.get("permissions", {})
    families = permissions.get("tool_families", []) if isinstance(permissions, dict) else []
    return frozenset(str(family) for family in families) if isinstance(families, list) else frozenset()


def _entry_error(prefix: str, tool: dict, plugin_dir: Path, declared: frozenset[str]) -> str | None:
    unknown = sorted(set(tool) - TOOL_ENTRY_FIELDS)
    if unknown:
        return f"{prefix}: unknown field(s): {', '.join(unknown)}"
    suffix = tool.get("name")
    if not isinstance(suffix, str) or not _SUFFIX_RE.match(suffix or ""):
        return (
            f"{prefix}: {suffix!r} is not a tool name "
            "([a-z][a-z0-9_]* expected)"
        )
    transport = tool.get("transport") or "plugin"
    if transport not in ("plugin", "mcp"):
        return (
            f"{prefix}.transport: {transport!r} is not a rail the registry "
            "carries (plugin or mcp)"
        )
    if transport == "mcp":
        if "entry" in tool:
            return (
                f"{prefix}.entry: an MCP tool rides the bundle's server; the "
                "server owns the callable, not a second entry here"
            )
    else:
        error = _entry_field_error(prefix, tool.get("entry"), plugin_dir)
        if error:
            return error
    error = _permission_error(prefix, tool.get("family"), declared)
    if error:
        return error
    return _surface_error(prefix, tool)


def _surface_error(prefix: str, tool: dict) -> str | None:
    """What the model is offered: a description the schema must carry, and its shape.

    The fingerprint (#6) is taken over these bytes and #15 diffs them against the
    lockfile, so the description and the parameter object are the contract a later turn
    checks for a rug pull. A parameter object that is not an object has no answer to
    check at all.
    """
    description = tool.get("description")
    if not isinstance(description, str) or not description.strip():
        return f"{prefix}.description: non-empty string expected"
    parameters = tool.get("parameters")
    if parameters is None:
        return None
    if not isinstance(parameters, dict):
        return f"{prefix}.parameters: object expected"
    if parameters.get("type", "object") != "object":
        return f"{prefix}.parameters: type must be 'object'"
    return None


def _entry_field_error(prefix: str, entry: object, plugin_dir: Path) -> str | None:
    from core.plugin_manifest import _under

    if not isinstance(entry, str) or not entry.strip():
        return f"{prefix}.entry: a plugin-relative path.py:callable is expected"
    path_part, colon, callable_name = entry.rpartition(":")
    if not colon:
        return f"{prefix}.entry: {entry!r} carries no ':callable'"
    if entry.count(":") != 1:
        return f"{prefix}.entry: {entry!r} holds more than one ':'"
    if not _SEGMENT_RE.match(callable_name):
        return f"{prefix}.entry: {callable_name!r} is not a callable name"
    if not path_part:
        return f"{prefix}.entry: {entry!r} names no module path"
    candidate = PurePosixPath(path_part)
    if candidate.is_absolute():
        return (
            f"{prefix}.entry: {entry!r} is an absolute path; declare it relative "
            "to the plugin directory"
        )
    parts = path_part.split("/")
    if _under(plugin_dir, *parts) is None:
        return f"{prefix}.entry: {entry!r} resolves outside the plugin directory"
    if candidate.suffix.lower() != _MODULE_SUFFIX:
        return f"{prefix}.entry: {entry!r} is not a .py file"
    module_parts = parts[:-1] + [parts[-1][: -len(_MODULE_SUFFIX)]]
    if not all(_SEGMENT_RE.match(part) for part in module_parts):
        return (
            f"{prefix}.entry: {entry!r} has a module path segment that cannot be "
            "imported"
        )
    return None


def _permission_error(prefix: str, family: object, declared: frozenset[str]) -> str | None:
    from core.plugin_manifest import KNOWN_TOOL_FAMILIES

    label = f"{prefix}.family"
    if not isinstance(family, str) or family not in KNOWN_TOOL_FAMILIES:
        return f"{label}: {family!r} is outside the known tool families"
    if family not in declared:
        return f"{label}: {family!r} is not in permissions.tool_families"
    return None


def tool_claims(manifest: dict) -> tuple[ToolClaim, ...]:
    """Every declared tool of one validated manifest, in declaration order.

    A malformed entry yields no claim rather than a wrong one: the manifest that carries
    it was quarantined by `validate_tools` before anything read this.
    """
    from core import plugin_manifest
    from core.tools.dynamic_registry import served_tool_name

    plugin_id = str(manifest.get("name") or "")
    components = manifest.get("components", {})
    if not isinstance(components, dict):
        return ()
    tools = components.get("tools", [])
    if not isinstance(tools, list):
        return ()
    contributed = manifest.get("manifest_version") == plugin_manifest.MANIFEST_VERSION_V2
    claims: list[ToolClaim] = []
    for tool in tools:
        if not contributed:
            if isinstance(tool, str):
                claims.append(
                    ToolClaim(
                        plugin_id=plugin_id,
                        suffix=tool,
                        name=tool,
                        entry="",
                        declared="",
                        family="",
                        description="",
                        parameters={},
                        contributed=False,
                    )
                )
            continue
        if not isinstance(tool, dict):
            continue
        suffix = tool.get("name")
        if not isinstance(suffix, str):
            continue
        transport = str(tool.get("transport") or "plugin")
        entry = tool.get("entry")
        # A plugin tool names its callable; an MCP tool rides the bundle's server
        # and carries none. Either way the claim is the declared name.
        if transport == "plugin" and not isinstance(entry, str):
            continue
        entry_text = entry if isinstance(entry, str) else ""
        parameters = tool.get("parameters")
        claims.append(
            ToolClaim(
                plugin_id=plugin_id,
                suffix=suffix,
                name=served_tool_name(plugin_id, suffix),
                entry=module_entry(entry_text),
                declared=entry_text,
                family=str(tool.get("family") or ""),
                description=str(tool.get("description") or ""),
                parameters=dict(parameters) if isinstance(parameters, dict) else {},
                contributed=True,
                transport=transport,
            )
        )
    return tuple(claims)


def descriptors_for(manifest: dict) -> tuple[ToolDescriptor, ...]:
    """The mount-ready descriptors behind one validated manifest.

    #15 hands the result to `replace_for_plugin` and gets one atomic swap with it. No
    plugin module is imported to build them: an entry that leaves this text-shaped is
    the defect ruling A1 exists to keep out.
    """
    from core.tools.dynamic_registry import (
        TRANSPORT_MCP,
        TRANSPORT_PLUGIN,
        ToolDescriptor,
        fingerprint_for,
    )

    # One authority answers "which families does this bundle claim", and the descriptor
    # carries its answer so the bridge (#23) grants a call against the same set the gate
    # (#11) judges the tool's own family by.
    bundle_families = declared_families(manifest)

    out: list[ToolDescriptor] = []
    for claim in tool_claims(manifest):
        if not claim.contributed:
            continue
        schema = {
            "type": "function",
            "function": {
                "name": claim.name,
                "description": claim.description,
                "parameters": claim.parameters or dict(_EMPTY_PARAMETERS),
            },
        }
        out.append(
            ToolDescriptor(
                name=claim.name,
                plugin_id=claim.plugin_id,
                schema=schema,
                families=bundle_families,
                transport=TRANSPORT_MCP if claim.transport == "mcp" else TRANSPORT_PLUGIN,
                entry=claim.entry if claim.transport != "mcp" else None,
                tool_family=claim.family,
                fingerprint=fingerprint_for(schema),
            )
        )
    return tuple(out)
