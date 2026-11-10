"""Ephe — `capabilities.memory`: the memory provider one manifest declares.

core/plugin_memory_contract.py

A bundle may point the agent's memory at a backend of its own. It says so once, in a
version 2 manifest, and the kernel decides every consequence: the provider is registered
by the same scan the tool gate reads, it answers only while its plugin is active, and the
declared URL is the only endpoint it can reach. Nothing here imports plugin code — ruling
A1 of the platform order holds for memory exactly as it holds for tools.

Why the transport vocabulary is one name. A provider has to answer in this process's
memory call path (turn-time reads), so it cannot be a confined worker spawn. The shape
that already speaks to a foreign brain is the Kepta bridge's HTTP protocol, and it is the
only one; a second transport is a new wire contract, not a config value, so it is not
accepted until it is written down. Declaring `kepta-bridge` means "this URL speaks the
protocol `core/memory_kepta_bridge.py` implements".

What the kernel keeps. `kepta` and `kepta-bridge` are its own providers and their ids are
refused in a manifest, so a bundle can never shadow the local brain or the operator's
env-selected instance. `core/memory_provider.VALID_PROVIDERS` is the list, and
`tests/test_plugin_memory_provider.py` pins the two files to one another rather than
importing across the seam.

Fail-closed rules, in one list: `capabilities` in a version 1 manifest, an unknown
section, a section that is not an object, an unknown field, a missing or malformed
provider id, an id the kernel owns, an id past the ceiling, a transport outside the
vocabulary, a URL that is not http(s), carries credentials or a fragment, a scope that is
not a slug, a blank description, and a provider declared without the `network` family in
`permissions.tool_families`. Each of them quarantines the whole bundle.

Two bundles that declare one id: neither wins. The scan marks the id contested and names
both claimants; `get` answers None for it, so a caller falls back exactly the way it does
for an id nobody declared. That is the same answer the tool gate gives a contested name.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import urlsplit

__all__ = [
    "BUILTIN_PROVIDER_IDS",
    "CAPABILITY_SECTIONS",
    "DEFAULT_TRANSPORT",
    "MAX_PROVIDER_ID_CHARS",
    "MEMORY_FIELDS",
    "MEMORY_TRANSPORTS",
    "MemoryProviderClaim",
    "MemoryProviderTable",
    "memory_claim",
    "scan_memory_providers",
    "validate_memory",
]

#: Provider ids the kernel owns; a manifest may not take one.
BUILTIN_PROVIDER_IDS: frozenset[str] = frozenset({"kepta", "kepta-bridge"})
#: The capability sections this contract knows. One name, so an unknown one is a typo.
CAPABILITY_SECTIONS: frozenset[str] = frozenset({"memory"})
#: The wire protocols a declared provider may speak. `kepta-bridge` is the only one.
MEMORY_TRANSPORTS: tuple[str, ...] = ("kepta-bridge",)
DEFAULT_TRANSPORT = "kepta-bridge"
MEMORY_FIELDS: frozenset[str] = frozenset(
    {"id", "transport", "url", "scope", "description"}
)
#: Ceiling on a provider id: it rides in env, records and refusal sentences.
MAX_PROVIDER_ID_CHARS = 40

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
#: A scope lands in a request body and in one folder name, so it stays in this alphabet.
_SCOPE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


@dataclass(frozen=True)
class MemoryProviderClaim:
    """One declared provider, normalized the way the scan and the resolution read it.

    ``plugin_id`` owns the declaration and is what the lifecycle gate asks about;
    ``provider_id`` is the name a user writes in `EPHE_MEMORY_PROVIDER` or in a record.
    The URL is the whole reach of the provider: nothing else from the bundle crosses.
    """

    plugin_id: str
    provider_id: str
    transport: str
    url: str
    scope: str
    description: str = ""


@dataclass(frozen=True)
class MemoryProviderTable:
    """Every declared provider over one scan, with the ids two bundles claim."""

    claims: tuple[MemoryProviderClaim, ...] = ()
    contested: tuple[str, ...] = ()
    _reasons: tuple[tuple[str, str], ...] = ()

    def get(self, provider_id: str) -> MemoryProviderClaim | None:
        """The claim behind one id, or None — contested and unknown answer the same."""
        if provider_id in self.contested:
            return None
        for claim in self.claims:
            if claim.provider_id == provider_id:
                return claim
        return None

    def conflict_reason(self, provider_id: str) -> str:
        return dict(self._reasons).get(
            provider_id, f"provider {provider_id!r} is claimed by more than one plugin"
        )

    def provider_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                claim.provider_id
                for claim in self.claims
                if claim.provider_id not in self.contested
            )
        )


def _memory_section(manifest: dict) -> dict | None:
    capabilities = manifest.get("capabilities")
    if not isinstance(capabilities, dict):
        return None
    section = capabilities.get("memory")
    return section if isinstance(section, dict) else None


def validate_memory(manifest: dict) -> str | None:
    """The `capabilities.memory` contract; called once from the manifest contract."""
    capabilities = manifest.get("capabilities")
    if capabilities is None:
        return None
    if manifest.get("manifest_version") != 2:
        return "capabilities: manifest_version 2 required"
    if not isinstance(capabilities, dict):
        return "capabilities: object expected"
    unknown = sorted(set(capabilities) - CAPABILITY_SECTIONS)
    if unknown:
        return f"capabilities: unknown section(s): {', '.join(unknown)}"
    memory = capabilities.get("memory")
    if memory is None:
        return None
    if not isinstance(memory, dict):
        return "capabilities.memory: object expected"
    unknown_fields = sorted(set(memory) - MEMORY_FIELDS)
    if unknown_fields:
        return f"capabilities.memory: unknown field(s): {', '.join(unknown_fields)}"

    provider_id = memory.get("id")
    if not isinstance(provider_id, str) or not _SLUG_RE.match(provider_id):
        return "capabilities.memory.id: lowercase slug expected (a-z0-9-)"
    if len(provider_id) > MAX_PROVIDER_ID_CHARS:
        return (
            "capabilities.memory.id: at most "
            f"{MAX_PROVIDER_ID_CHARS} characters expected"
        )
    if provider_id in BUILTIN_PROVIDER_IDS:
        return f"capabilities.memory.id: {provider_id!r} is a kernel provider id"

    transport = memory.get("transport", DEFAULT_TRANSPORT)
    if transport not in MEMORY_TRANSPORTS:
        allowed = ", ".join(MEMORY_TRANSPORTS)
        return (
            "capabilities.memory.transport: "
            f"{transport!r} is not a transport this kernel speaks ({allowed})"
        )

    url = memory.get("url")
    parsed = urlsplit(url) if isinstance(url, str) else None
    if parsed is None or parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "capabilities.memory.url: an http(s) URL expected"
    if "@" in parsed.netloc:
        return "capabilities.memory.url: credentials in the URL are refused"
    if parsed.fragment:
        return "capabilities.memory.url: a fragment is refused"

    scope = memory.get("scope")
    if scope is not None and (not isinstance(scope, str) or not _SCOPE_RE.match(scope)):
        return (
            "capabilities.memory.scope: a slug of lowercase letters, digits, dash, "
            "dot, underscore expected"
        )
    description = memory.get("description", "")
    if not isinstance(description, str) or (
        description and not description.strip()
    ):
        return "capabilities.memory.description: non-empty string expected"

    families = (manifest.get("permissions") or {}).get("tool_families") or []
    if "network" not in families:
        return "capabilities.memory: permissions.tool_families must include 'network'"
    return None


def memory_claim(manifest: Any) -> MemoryProviderClaim | None:
    """The claim one validated manifest carries, or None when it declares none."""
    if not isinstance(manifest, dict) or validate_memory(manifest) is not None:
        return None
    memory = _memory_section(manifest)
    if memory is None:
        return None
    return MemoryProviderClaim(
        plugin_id=str(manifest.get("name") or ""),
        provider_id=str(memory["id"]),
        transport=str(memory.get("transport", DEFAULT_TRANSPORT)),
        url=str(memory["url"]),
        scope=str(memory.get("scope") or ""),
        description=str(memory.get("description") or ""),
    )


def scan_memory_providers(entries: Iterable[dict]) -> MemoryProviderTable:
    """Claims from one manifest scan (`core.plugin_manifest.scan_plugins`), plus conflicts.

    Takes the entries rather than scanning them, so this module stays below the loader it
    is called from and a caller owns the root it reads.
    """
    claims: list[MemoryProviderClaim] = []
    claimants: dict[str, list[str]] = {}
    for entry in entries:
        manifest = entry.get("manifest")
        if entry.get("error") or not manifest:
            continue
        claim = memory_claim(manifest)
        if claim is None:
            continue
        claims.append(claim)
        claimants.setdefault(claim.provider_id, []).append(claim.plugin_id)
    contested = tuple(sorted(pid for pid, owners in claimants.items() if len(owners) > 1))
    reasons = tuple(
        (
            pid,
            f"provider {pid!r} is claimed by "
            + ", ".join(f"{owner!r}" for owner in sorted(claimants[pid])),
        )
        for pid in contested
    )
    return MemoryProviderTable(
        claims=tuple(sorted(claims, key=lambda item: item.provider_id)),
        contested=contested,
        _reasons=reasons,
    )
