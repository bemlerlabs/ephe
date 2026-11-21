"""Dynamic tool registry: descriptor records for tools a plugin contributes at runtime.

Ruling A1 of the Creator Mode platform order rests on this module: a descriptor
carries a transport name and a textual ``module:callable`` entry, and the server
process imports no plugin code, executes none and stores no callable. Transport
resolution and execution belong to the tasks that read this registry (#7 schema and
execute hooks, #9 confined runner, #15 hot-mount and pinning). Visibility stays
gated by ``core.plugin_runtime``, which owns conflicts; this module only refuses
reservations at intake.

One naming rule belongs here because #98 moved it: a contributed tool is served under the
name the manifest declares, and the namespace lives on the plugin package, not inside the
tool name. What protects that is the reserved map below and the contested-name scan in
``core.plugin_registry`` — see ``served_tool_name``.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

TRANSPORT_MCP = "mcp"
TRANSPORT_PLUGIN = "plugin"
TRANSPORTS = (TRANSPORT_MCP, TRANSPORT_PLUGIN)

MCP_PREFIX = "mcp_"

# Outcome codes for a refused registration. Descriptor-shape problems raise ValueError
# while the record is built (a programming error); these codes cover refusals against
# the live name space, which a caller reports to the user and the audit reads.
COLLISION_KERNEL = "reserved_kernel"
COLLISION_MCP = "reserved_mcp"
NAME_TAKEN = "name_taken"
PLUGIN_MISMATCH = "plugin_mismatch"

# Lowercase names. Dashes are allowed because a manifest slug can carry them and an
# MCP-discovered name is whatever the server spelled; a plugin's own declared tool name is
# checked against the stricter `_TOOL_NAME_RE` in the manifest contract, so what reaches
# the model is provider-safe either way.
_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
# A dotted module path plus one callable name, text only. The confined worker (#9)
# re-resolves it inside the plugin directory before anything runs.
_ENTRY_RE = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*:[A-Za-z_][A-Za-z0-9_]*$"
)
_FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")


def served_tool_name(plugin_id: str, name: str) -> str:
    """The served name of one declared tool: the name the manifest spells, unchanged.

    This used to build `plugin_<id>_<name>`, and the reason for the prefix — one plugin
    cannot answer in another's namespace — is answered twice over without it.
    `default_reserved_names()` maps every kernel and live MCP name to its collision code
    and `register` refuses those, and a name two plugins both declare is contested: the
    scan marks it, `refuse_contested_names` refuses the mount, and the reason names both
    plugins. A prefix was a third authority over a question those two already settle, and
    it cost the one thing nobody wanted — migrating a tool that the model already knows as
    `web_search` would have renamed it.

    The plugin id stays a parameter because this remains the single place a served name is
    spelled: the manifest scan (#13), the mount (#15) and the namespace rule all call it, so
    if the rule ever changes again there is one function to change.
    """
    return str(name)


def canonical_schema_bytes(schema: Mapping) -> bytes:
    """The pinned bytes behind a fingerprint: the schema as one sorted JSON document.

    Key order and whitespace are normalized, so two equal contracts hash equal, and a
    change to the parameters or the description moves the digest.
    """
    if not isinstance(schema, dict):
        raise ValueError("schema: an object (dict) is expected")
    return json.dumps(
        schema, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def fingerprint_for(schema: Mapping) -> str:
    """sha256 of the canonical schema bytes; the description lives inside those bytes."""
    return hashlib.sha256(canonical_schema_bytes(schema)).hexdigest()


def _function_body(schema: dict) -> dict | None:
    """The function object inside the registry envelope, or the bare object form."""
    inner = schema.get("function")
    if isinstance(inner, dict):
        return inner
    if "name" in schema or "description" in schema:
        return schema
    return None


def _known_families() -> frozenset[str]:
    from core import plugin_manifest

    return frozenset(plugin_manifest.KNOWN_TOOL_FAMILIES)


def _kernel_tool_names() -> frozenset[str]:
    from core.tools.registry import TOOL_MAP

    return frozenset(TOOL_MAP)


def _live_mcp_names() -> frozenset[str]:
    from core.tools import mcp_client

    return frozenset(mcp_client.get_mcp_tools())


def default_reserved_names() -> dict[str, str]:
    """Names a dynamic descriptor cannot take, each mapped to its collision code.

    The kernel map is consulted whole (task #8 owns that number), and the MCP catalog
    is read live because remote tools join it without a server restart.
    """
    reserved = {name: COLLISION_KERNEL for name in _kernel_tool_names()}
    reserved.update({name: COLLISION_MCP for name in _live_mcp_names()})
    return reserved


@dataclass(frozen=True)
class ToolDescriptor:
    """One contributed tool: what the model sees, how the call is reached, who owns it.

    The field purposes the later tasks read:
    - ``name`` — the full offered name; construction checks it against the plugin's
      namespace, so the name itself encodes ownership.
    - ``plugin_id`` — the manifest slug that owns the tool; unregistration, audit and
      the gate all key on it.
    - ``schema`` — the function schema handed to the model, registry envelope or bare
      object; its inner name has to equal ``name``.
    - ``transport`` — the string "mcp" or "plugin" that routes the call. A callable
      fails the type check: holding one would defeat ruling A1.
    - ``entry`` — the relative ``module:callable`` text the confined worker resolves
      inside the plugin directory; None on the MCP rail, which needs none.
    - ``tool_family`` — one of the manifest permission families, the unit the approval
      hook (#11) consults.
    - ``fingerprint`` — sha256 over the canonical schema bytes, recomputed at build so
      a stale or forged pin is refused; #15 diffs it against the lockfile.
    - ``families`` — every family the declaring manifest asks for, which is what the
      bridge (#23) grants a call against. Empty means nothing is granted.
    """

    name: str
    plugin_id: str
    schema: dict
    transport: str
    entry: str | None
    tool_family: str
    fingerprint: str
    #: A frozenset, checked at construction: the bridge reads it as the bundle's grant,
    #: so a callable or a name outside the manifest vocabulary must not survive the build.
    families: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not _NAME_RE.match(self.name):
            raise ValueError(f"name: {self.name!r} is not a lowercase tool name")
        if not isinstance(self.plugin_id, str) or not _SLUG_RE.match(self.plugin_id):
            raise ValueError(f"plugin_id: {self.plugin_id!r} is not a manifest slug")
        if not isinstance(self.transport, str) or self.transport not in TRANSPORTS:
            raise ValueError(
                f"transport: {self.transport!r} must be one of {TRANSPORTS}; "
                "a callable is refused here by type, and none is ever stored"
            )
        if (
            not isinstance(self.tool_family, str)
            or self.tool_family not in _known_families()
        ):
            raise ValueError(
                f"tool_family: {self.tool_family!r} is outside the manifest vocabulary"
            )
        if not isinstance(self.families, frozenset) or any(
            not isinstance(family, str) or family not in _known_families()
            for family in self.families
        ):
            raise ValueError(
                f"families: {self.families!r} must be a frozenset of the manifest vocabulary"
            )
        if not isinstance(self.schema, dict) or not self.schema:
            raise ValueError("schema: a non-empty object is expected")
        body = _function_body(self.schema)
        if body is None:
            raise ValueError("schema: a function object (name/description) is expected")
        body_name = body.get("name")
        if body_name is not None and body_name != self.name:
            raise ValueError(
                f"name: schema carries {body_name!r}, the descriptor carries {self.name!r}"
            )
        if self.transport == TRANSPORT_PLUGIN:
            if not isinstance(self.entry, str) or not _ENTRY_RE.match(self.entry):
                raise ValueError(
                    f"entry: {self.entry!r} is not a relative module:callable"
                )
        elif self.entry is not None:
            raise ValueError(
                "entry: the mcp transport is resolved by the existing MCP client"
            )
        self._check_namespace()
        if not isinstance(self.fingerprint, str) or not _FINGERPRINT_RE.match(
            self.fingerprint
        ):
            raise ValueError("fingerprint: 64 lowercase hex characters expected")
        if self.fingerprint != fingerprint_for(self.schema):
            raise ValueError("fingerprint: does not match the canonical schema bytes")

    def _check_namespace(self) -> None:
        if self.transport == TRANSPORT_MCP:
            if not self.name.startswith(MCP_PREFIX):
                raise ValueError(
                    f"name: an mcp transport name must start with {MCP_PREFIX!r}"
                )
            return
        # The namespace rule, restated for names that are declared rather than derived:
        # a plugin tool may not wear the MCP rail's prefix, and it must be a name a
        # provider can call. Whether the kernel already holds it is not answerable here —
        # that question belongs to `register`, which can read the live map at the moment it answers.
        if self.name.startswith(MCP_PREFIX):
            raise ValueError(
                f"name: {self.name!r} sits in the {MCP_PREFIX!r} namespace, which the "
                "plugin transport does not own"
            )
        if not _NAME_RE.match(self.name):
            raise ValueError(f"name: {self.name!r} is not a callable tool name")


@dataclass(frozen=True)
class Outcome:
    """A registration verdict: ok, plus a stable code and a readable detail when refused."""

    ok: bool
    code: str = ""
    detail: str = ""


def _refusal(code: str, detail: str) -> Outcome:
    return Outcome(False, code, detail)


def _invalidate_schema_cache() -> None:
    """Drops the model-facing schema cache after a committed change, best effort.

    The registry state is already committed when this runs, so an import problem is
    never a reason to roll back; the cache entry expires on its own TTL.
    """
    try:
        from core.tools.creator_guard import invalidate_family_map
        from core.tools.registry import (
            invalidate_addressable_tool_names,
            invalidate_tool_schema_cache,
        )

        invalidate_tool_schema_cache()
        invalidate_addressable_tool_names()
        # The Creator gate answers "which family does this name come from" out of the
        # same scanned portfolio, so a mount or an unmount retargets that answer too.
        invalidate_family_map()
    except Exception:  # noqa: BLE001 - the lazy seam is deliberate, as in mcp_client
        pass


class DynamicToolRegistry:
    """A name-keyed set of ToolDescriptors, safe to read and write from several threads.

    One lock guards both indexes. Every read hands out a snapshot tuple, so a turn in
    flight never iterates a live dict; freezing per turn is task #36 on top of this.
    The registry imports no plugin and gates no visibility: ``core.plugin_runtime``
    keeps that authority, and a contested name stays hidden there.
    """

    def __init__(
        self,
        reserved_names: Callable[[], Mapping[str, str]] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._by_name: dict[str, ToolDescriptor] = {}
        self._by_plugin: dict[str, dict[str, ToolDescriptor]] = {}
        self._reserved_names = (
            default_reserved_names if reserved_names is None else reserved_names
        )

    def register(self, descriptor: ToolDescriptor) -> Outcome:
        """Add one descriptor; a taken or reserved name is refused with a reason."""
        with self._lock:
            refusal = self._refuse(descriptor, replace_owner=None)
            if refusal is not None:
                return refusal
            self._install(descriptor)
            _invalidate_schema_cache()
            return Outcome(True)

    def replace_for_plugin(
        self, plugin_id: str, descriptors: Iterable[ToolDescriptor]
    ) -> Outcome:
        """Swap one plugin's whole set atomically: every check runs before the first write.

        An empty batch clears the plugin. A foreign plugin id, a name repeated in the
        batch, a reserved name or a name owned by another plugin refuses the call, and
        the previous set survives byte for byte — the hot-mount rollback (#15) depends
        on that.
        """
        batch = tuple(descriptors)
        with self._lock:
            seen: set[str] = set()
            for descriptor in batch:
                if descriptor.plugin_id != plugin_id:
                    return _refusal(
                        PLUGIN_MISMATCH,
                        f"{descriptor.name!r} belongs to plugin {descriptor.plugin_id!r}",
                    )
                if descriptor.name in seen:
                    return _refusal(NAME_TAKEN, f"{descriptor.name!r} appears twice in the batch")
                seen.add(descriptor.name)
            for descriptor in batch:
                refusal = self._refuse(descriptor, replace_owner=plugin_id)
                if refusal is not None:
                    return refusal
            for name in self._by_plugin.pop(plugin_id, {}):
                self._by_name.pop(name, None)
            for descriptor in batch:
                self._install(descriptor)
            _invalidate_schema_cache()
            return Outcome(True)

    def unregister_all_plugins(self) -> int:
        """Drop every plugin-owned descriptor; the kernel map is untouched.

        A process that mounts bundles shares one registry, so a test file that installs
        bundles leaves descriptors behind for the next one. This is the seam that makes
        that state explicit instead of leaking it through `_by_plugin`.
        """
        with self._lock:
            owners = list(self._by_plugin)
        total = 0
        for plugin_id in owners:
            total += self.unregister_plugin(plugin_id)
        return total

    def unregister_plugin(self, plugin_id: str) -> int:
        """Drop every descriptor of one plugin and return how many were live; 0 for an unknown id."""
        with self._lock:
            owned = self._by_plugin.pop(plugin_id, None)
            if not owned:
                return 0
            for name in owned:
                self._by_name.pop(name, None)
            _invalidate_schema_cache()
            return len(owned)

    def get(self, name: str) -> ToolDescriptor | None:
        with self._lock:
            return self._by_name.get(name)

    def names(self) -> tuple[str, ...]:
        """The live names, sorted, as one snapshot."""
        with self._lock:
            return tuple(sorted(self._by_name))

    def descriptor_snapshot(self) -> tuple[ToolDescriptor, ...]:
        """An immutable, name-sorted view; later writes never touch a handed-out tuple."""
        with self._lock:
            return tuple(self._by_name[name] for name in sorted(self._by_name))

    def _refuse(
        self, descriptor: ToolDescriptor, *, replace_owner: str | None
    ) -> Outcome | None:
        collision = self._reserved_names().get(descriptor.name)
        if collision:
            return _refusal(
                str(collision), f"{descriptor.name!r} is reserved by the {collision} name space"
            )
        current = self._by_name.get(descriptor.name)
        if current is not None and current.plugin_id != replace_owner:
            return _refusal(
                NAME_TAKEN,
                f"{descriptor.name!r} is already registered by plugin {current.plugin_id!r}",
            )
        return None

    def _install(self, descriptor: ToolDescriptor) -> None:
        self._by_name[descriptor.name] = descriptor
        self._by_plugin.setdefault(descriptor.plugin_id, {})[descriptor.name] = descriptor


_DEFAULT_REGISTRY = DynamicToolRegistry()


def default_registry() -> DynamicToolRegistry:
    """The process-wide instance: #7 reads it while building schemas and executing."""
    return _DEFAULT_REGISTRY
