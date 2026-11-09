"""One plugin and capability registry over the shipped portfolio.

P1 slice: the registry is read-only and does not wire the runtime. It reads the
14 manifests, the 51 built-in skills and the 7 curated MCP entries into typed
descriptors so later waves can replace the hardcoded runtime map from one source.
The five duplicate command/skill pairs are dropped on the command side; the
skill keeps the native name.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from core import mcp_catalog, plugin_manifest, plugin_tools_contract
from core.skills import Skill, SkillLoader

#: Command/skill pairs that keep the skill and remove the duplicate command.
DUPLICATE_COMMANDS: frozenset[tuple[str, str]] = frozenset(
    {
        ("documents", "pdf"),
        ("documents", "docx"),
        ("presentations", "deck"),
        ("spreadsheets", "xlsx"),
        ("web-research", "research"),
    }
)


class CapabilityKind(str, Enum):
    SKILL = "skill"
    COMMAND = "command"
    MCP_SERVER = "mcp_server"
    BUILTIN_TOOL = "builtin_tool"
    PLUGIN_TOOL = "plugin_tool"


class RegistryError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


def load_tool_activations(
    plugins_root: Path | None = None,
) -> tuple[tuple[str, str], ...]:
    """Tool name → activating plugin, derived from the manifests.

    A version 1 manifest activates a kernel tool and the capability stays kernel-owned; a
    version 2 manifest contributes a tool of its own, served under the name its plugin id
    derives. Two claimants of one served name fail closed instead of silently winning.
    """
    return _scan_or_raise(plugins_root).owners


def _scan_or_raise(plugins_root: Path | None) -> ToolActivations:
    scanned = scan_tool_activations(plugins_root)
    if scanned.conflicts:
        raise RegistryError(
            "duplicate_tool_activation", scanned.reason_for(scanned.conflicts[0])
        )
    return scanned


@dataclass(frozen=True)
class ToolActivations:
    """Who owns which served tool name, across the whole scanned portfolio.

    ``owners`` maps every name a manifest speaks of to one plugin; ``conflicts`` lists
    the names with more than one claim, or one claim and a kernel or MCP name already
    using it. The runtime gate hides every conflicted name from everyone, so the list has
    to say what met: ``reason_for`` names both plugins and both declarations.
    """

    owners: tuple[tuple[str, str], ...]
    conflicts: tuple[str, ...]
    contributed: tuple[str, ...] = ()
    _reasons: tuple[tuple[str, str], ...] = ()

    def reason_for(self, tool_name: str) -> str:
        return dict(self._reasons).get(tool_name, f"{tool_name}: claimed by more than one plugin")


def scan_tool_activations(plugins_root: Path | None = None) -> ToolActivations:
    """Like load_tool_activations, but reports conflicting tools instead of raising."""
    owners: dict[str, str] = {}
    claimants: dict[str, list[tuple[str, str]]] = {}
    conflicts: set[str] = set()
    contributed: set[str] = set()
    for entry in plugin_manifest.scan_plugins(
        None if plugins_root is None else Path(plugins_root)
    ):
        manifest = entry["manifest"]
        if entry["error"] or not manifest:
            continue
        plugin = str(manifest["name"])
        for claim in plugin_tools_contract.tool_claims(manifest):
            tool_name = claim.name
            if tool_name in owners and owners[tool_name] != plugin:
                conflicts.add(tool_name)
            else:
                owners[tool_name] = plugin
            claimants.setdefault(tool_name, []).append((plugin, claim.suffix))
            if claim.contributed:
                contributed.add(tool_name)
                if plugin_tools_contract.reserved_namespace(tool_name):
                    conflicts.add(tool_name)
    reasons = tuple(
        (name, _conflict_reason(name, claimants.get(name, ()))) for name in sorted(conflicts)
    )
    return ToolActivations(
        owners=tuple(sorted(owners.items())),
        conflicts=tuple(sorted(conflicts)),
        contributed=tuple(sorted(contributed)),
        _reasons=reasons,
    )


def _conflict_reason(tool_name: str, claims: list[tuple[str, str]]) -> str:
    """The sentence a reader needs to find the two declarations that met on one name."""
    claimed = ", ".join(f"{plugin!r} declares {suffix!r}" for plugin, suffix in claims)
    if not claimed:
        return f"{tool_name}: claimed by more than one plugin"
    return f"{tool_name}: claimed by {claimed}"


@dataclass(frozen=True)
class CapabilityDescriptor:
    id: str
    kind: CapabilityKind
    owner: str
    name: str
    description: str
    source: str
    template: str = ""


@dataclass(frozen=True)
class PluginDescriptor:
    id: str
    version: str
    manifest: dict
    source: str


@dataclass(frozen=True)
class PluginRegistry:
    plugins: tuple[PluginDescriptor, ...]
    _capabilities: tuple[CapabilityDescriptor, ...]
    _owners: frozenset[str]
    _activations: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        ids = [capability.id for capability in self._capabilities]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate capability id in the registry")
        orphans = {capability.owner for capability in self._capabilities} - set(
            self._owners
        )
        if orphans:
            raise ValueError(f"orphan capability owner(s): {sorted(orphans)}")
        plugin_ids = {plugin.id for plugin in self.plugins}
        activation_owners = {
            owner for _, owner in self._activations
        } - plugin_ids
        if activation_owners:
            raise ValueError(
                "tool activation owner(s) are not plugins: "
                f"{sorted(activation_owners)}"
            )

    @classmethod
    def load(cls, plugins_root: Path | None, skills_root: Path) -> PluginRegistry:
        plugins: list[PluginDescriptor] = []
        capabilities: list[CapabilityDescriptor] = []
        owners: set[str] = {"core-skills", "mcp-catalog", "kernel"}
        scanned = _scan_or_raise(plugins_root)
        activations = scanned.owners
        contributed = set(scanned.contributed)

        for entry in plugin_manifest.scan_plugins(
            None if plugins_root is None else Path(plugins_root)
        ):
            manifest = entry["manifest"]
            if entry["error"] or not manifest:
                continue
            plugin = PluginDescriptor(
                id=str(manifest["name"]),
                version=str(manifest["version"]),
                manifest=dict(manifest),
                source=str(entry["dir"]),
            )
            plugins.append(plugin)
            owners.add(plugin.id)
            capabilities.extend(ManifestV1Adapter(plugin).capabilities())

        loader = SkillLoader(
            skills_dir=Path("/nonexistent-ephe-user-skills"),
            builtin_dir=Path(skills_root),
            plugin_root=(
                Path(plugins_root)
                if plugins_root is not None
                else plugin_manifest.plugins_root()
            ),
        )
        capabilities.extend(
            SkillAdapter(
                loader.load_all(), source_root=Path(skills_root)
            ).capabilities()
        )
        capabilities.extend(McpAdapter(mcp_catalog.catalog_entries()).capabilities())
        for tool, plugin_id in activations:
            is_contributed = tool in contributed
            capabilities.append(
                CapabilityDescriptor(
                    id=f"tool:{tool}",
                    kind=(
                        CapabilityKind.PLUGIN_TOOL
                        if is_contributed
                        else CapabilityKind.BUILTIN_TOOL
                    ),
                    owner=plugin_id if is_contributed else "kernel",
                    name=tool,
                    description=(
                        f"contributed by {plugin_id}"
                        if is_contributed
                        else f"activated by {plugin_id}"
                    ),
                    source=f"plugins/{plugin_id}/{plugin_manifest.MANIFEST_FILENAME}",
                )
            )

        plugins.sort(key=lambda p: p.id)
        capabilities.sort(key=lambda c: (c.kind.value, c.id))
        return cls(
            plugins=tuple(plugins),
            _capabilities=tuple(capabilities),
            _owners=frozenset(owners),
            _activations=activations,
        )

    def tool_activations(self) -> tuple[tuple[str, str], ...]:
        return self._activations

    def activation_owner(self, tool_name: str) -> str | None:
        return dict(self._activations).get(tool_name)

    def capabilities(
        self, kind: CapabilityKind | None = None
    ) -> tuple[CapabilityDescriptor, ...]:
        if kind is None:
            return self._capabilities
        return tuple(c for c in self._capabilities if c.kind is kind)

    def owner_of(self, capability_id: str) -> str:
        by_id = {c.id: c.owner for c in self._capabilities}
        return by_id[capability_id]

    def owner_ids(self) -> frozenset[str]:
        return self._owners


class ManifestV1Adapter:
    def __init__(self, plugin: PluginDescriptor) -> None:
        self._plugin = plugin

    def capabilities(self) -> tuple[CapabilityDescriptor, ...]:
        out: list[CapabilityDescriptor] = []
        for command in self._plugin.manifest.get("components", {}).get("commands", []):
            name = str(command["name"])
            if (self._plugin.id, name) in DUPLICATE_COMMANDS:
                continue
            out.append(
                CapabilityDescriptor(
                    id=f"{self._plugin.id}.{name}",
                    kind=CapabilityKind.COMMAND,
                    owner=self._plugin.id,
                    name=f"/{name}",
                    description=str(command.get("description", "")),
                    source=f"{self._plugin.source}/{plugin_manifest.MANIFEST_FILENAME}",
                    template=str(command.get("template", "")),
                )
            )
        return tuple(out)


class SkillAdapter:
    def __init__(self, skills: Iterable[Skill], source_root: Path) -> None:
        self._skills = tuple(skills)
        self._source_root = Path(source_root)

    def capabilities(self) -> tuple[CapabilityDescriptor, ...]:
        return tuple(
            CapabilityDescriptor(
                id=f"skill:{skill.name}",
                kind=CapabilityKind.SKILL,
                owner="core-skills",
                name=skill.name,
                description=skill.description,
                source=f"{self._source_root}/{skill.name}/SKILL.md",
            )
            for skill in self._skills
        )


class McpAdapter:
    def __init__(
        self, entries: Iterable[dict], source: str = "core/mcp_catalog.py"
    ) -> None:
        self._entries = tuple(entries)
        self._source = source

    def capabilities(self) -> tuple[CapabilityDescriptor, ...]:
        return tuple(
            CapabilityDescriptor(
                id=f"mcp:{entry['id']}",
                kind=CapabilityKind.MCP_SERVER,
                owner="mcp-catalog",
                name=str(entry.get("name", entry["id"])),
                description=str(
                    entry.get("description_en") or entry.get("description", "")
                ),
                source=self._source,
            )
            for entry in self._entries
        )


class BuiltinToolAdapter:
    def __init__(self, names: Iterable[str]) -> None:
        self._names = tuple(sorted(set(names)))

    def capabilities(self) -> tuple[CapabilityDescriptor, ...]:
        return tuple(
            CapabilityDescriptor(
                id=f"tool:{name}",
                kind=CapabilityKind.BUILTIN_TOOL,
                owner="kernel",
                name=name,
                description="",
                source="core/tools/registry.py",
            )
            for name in self._names
        )
