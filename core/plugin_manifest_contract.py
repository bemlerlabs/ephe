"""Ephe — the manifest contract: what one `ephe-plugin.json` has to say.

core/plugin_manifest_contract.py

Split out of `core/plugin_manifest.py`, which keeps the loading and scanning half: this
module answers "may this manifest load at all", and the loader answers "what does the
portfolio hold". The split exists because the contract is the part that grows — each
capability class adds its section here or in the module beside it
(`core/plugin_tools_contract.py`, `core/plugin_ui_capabilities.py`,
`core/plugin_libraries.py`, `core/plugin_memory_contract.py`), while the loader stays one
screen of reading, hashing and scanning.

Fail-closed, in the loader's words: a violation QUARANTINES the whole plugin, never a
half-loaded state. The sub-contracts are imported inside `validate_manifest` on purpose —
each one reads the module-level constants below, and a top-level import would make that
cycle real at load time.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

MANIFEST_VERSION = 1
MANIFEST_VERSION_V2 = 2
SUPPORTED_MANIFEST_VERSIONS = frozenset({MANIFEST_VERSION, MANIFEST_VERSION_V2})

#: Every top-level field a manifest may carry. An unknown one fails closed.
KNOWN_MANIFEST_FIELDS = frozenset(
    {
        "manifest_version",
        "name",
        "version",
        "description",
        "publisher",
        "license",
        "engines",
        "dependencies",
        "permissions",
        "components",
        "capabilities",
        "origin",
        "icon",
        "displayName",
        "description_i18n",
        "categories",
        "keywords",
        "homepage",
        "repository",
        "support",
        "securityContact",
        "changelog",
        "releaseNotes",
        "deprecated",
        "replacement",
        "signature",
        "sha256",
    }
)

KNOWN_COMPONENT_KEYS = frozenset(
    {
        "skills",
        "commands",
        "agents",
        "hooks",
        "mcp",
        "resources",
        "prompts",
        "instructions",
        "rules",
        "outputStyles",
        "workflows",
        "tools",
        "ui",
    }
)

#: Permission families a manifest may declare. Anything outside this set
#: fails closed (declared-but-absent capabilities never run).
KNOWN_TOOL_FAMILIES = {"read", "write", "shell", "network", "memory", "vision", "docs", "browser", "voice"}

#: The sections a `capabilities` object may carry. Each one's body is validated by the
#: module beside this file (`core/plugin_memory_contract.py`,
#: `core/plugin_planner_contract.py`, `core/plugin_evaluator_contract.py`); this is the one
#: list a new section is added to, so a section nobody implements stays a typo and stays
#: refused.
CAPABILITY_SECTIONS = frozenset({"memory", "planner", "evaluator"})

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")


def validate_manifest(
    manifest: Any, plugin_dir: Path, *, require_dir_name: bool = True
) -> str | None:
    """Full contract check. Returns an error string or None."""
    if not isinstance(manifest, dict):
        return "manifest: object expected"
    manifest_version = manifest.get("manifest_version")
    # `True == 1` and `1.0 == 1` in Python; the wire format is an integer.
    if (
        type(manifest_version) is not int
        or manifest_version not in SUPPORTED_MANIFEST_VERSIONS
    ):
        return (
            "manifest_version: must be one of "
            f"{sorted(SUPPORTED_MANIFEST_VERSIONS)}"
        )
    unknown_fields = sorted(set(manifest) - KNOWN_MANIFEST_FIELDS)
    if unknown_fields:
        return f"unknown top-level field(s): {', '.join(unknown_fields)}"
    if manifest["manifest_version"] == MANIFEST_VERSION_V2:
        publisher = manifest.get("publisher")
        if isinstance(publisher, dict):
            publisher_name = publisher.get("name")
        else:
            publisher_name = publisher
        if not isinstance(publisher_name, str) or not publisher_name.strip():
            return "publisher: name expected (string or object with name)"
        license_id = manifest.get("license")
        if not isinstance(license_id, str) or not license_id.strip():
            return "license: SPDX identifier expected"
        engines = manifest.get("engines")
        if engines is not None:
            if not isinstance(engines, dict):
                return "engines: object expected"
            if not isinstance(engines.get("ephe"), str) or not engines.get("ephe", "").strip():
                return "engines.ephe: SemVer range expected"
    name = manifest.get("name")
    if not isinstance(name, str) or not _SLUG_RE.match(name or ""):
        return "name: lowercase slug expected (a-z0-9-)"
    if require_dir_name and name != plugin_dir.name:
        return f"name: {name!r} does not match directory {plugin_dir.name!r}"
    version = manifest.get("version")
    if not isinstance(version, str) or not _SEMVER_RE.match(version or ""):
        return "version: semver X.Y.Z expected"
    if not isinstance(manifest.get("description"), str) or not manifest.get("description", "").strip():
        return "description: non-empty string expected"

    perms = manifest.get("permissions", {})
    if not isinstance(perms, dict):
        return "permissions: object expected"
    families = perms.get("tool_families", [])
    if not isinstance(families, list):
        return "permissions.tool_families: list expected"
    for family in families:
        if family not in KNOWN_TOOL_FAMILIES:
            return f"permissions.tool_families: unknown family {family!r} (fail-closed quarantine)"
    roots = perms.get("data_roots", [])
    if not isinstance(roots, list) or any(not isinstance(r, str) for r in roots):
        return "permissions.data_roots: list of strings expected"
    from core.capability_policy import validate_data_roots

    root_error = validate_data_roots(roots)
    if root_error:
        return root_error
    state_cap = perms.get("state_cap_mb")
    if state_cap is not None:
        # #24: the ceiling on the folder a bundle keeps. A bundle that says nothing is bound
        # by the default, so this line is a request to be trusted with more, and a reviewer
        # reads a whole number of megabytes against a stated maximum. A bool is refused by
        # name: `True` is an integer in Python and would read back as one byte of ceiling.
        from core.plugin_state import MAX_STATE_CAP_MB

        if isinstance(state_cap, bool) or not isinstance(state_cap, int) or state_cap <= 0:
            return "permissions.state_cap_mb: a positive whole number of megabytes expected"
        if state_cap > MAX_STATE_CAP_MB:
            return (
                f"permissions.state_cap_mb: {state_cap} MB is above the {MAX_STATE_CAP_MB} MB "
                "a bundle may ask for"
            )

    dependencies = manifest.get("dependencies", [])
    if dependencies is not None:
        if not isinstance(dependencies, list):
            return "dependencies: list of plugin slugs expected"
        for dependency in dependencies:
            if not isinstance(dependency, str) or not _SLUG_RE.match(dependency):
                return f"dependencies: bad plugin slug {dependency!r}"

    components = manifest.get("components", {})
    if not isinstance(components, dict):
        return "components: object expected"
    unknown_components = sorted(set(components) - KNOWN_COMPONENT_KEYS)
    if unknown_components:
        return f"components: unknown component(s): {', '.join(unknown_components)}"
    skills = components.get("skills", [])
    if not isinstance(skills, list):
        return "components.skills: list expected"
    for pack in skills:
        if not isinstance(pack, str) or not _SLUG_RE.match(pack):
            return f"components.skills: bad pack name {pack!r}"
        pack_manifest = _under(plugin_dir, "skills", pack, "SKILL.md")
        if pack_manifest is None or not pack_manifest.is_file():
            return f"components.skills: declared pack {pack!r} does not ship a SKILL.md"
    commands = components.get("commands", [])
    if not isinstance(commands, list):
        return "components.commands: list expected"
    command_names: set[str] = set()
    for cmd in commands:
        if not isinstance(cmd, dict) or not isinstance(cmd.get("name"), str) or not _SLUG_RE.match(cmd.get("name", "")):
            return f"components.commands: bad command name {cmd!r}"
        if cmd["name"] in command_names:
            return f"components.commands: duplicate name {cmd['name']!r}"
        command_names.add(cmd["name"])
        if not isinstance(cmd.get("description"), str) or not cmd.get("description", "").strip():
            return f"components.commands.{cmd.get('name')}: description required"
    from core.plugin_tools_contract import validate_tools

    tools_error = validate_tools(manifest, plugin_dir)
    if tools_error:
        return tools_error
    from core.plugin_ui_capabilities import validate_ui

    ui_error = validate_ui(manifest, plugin_dir)
    if ui_error:
        return ui_error
    from core.plugin_libraries import validate_libraries

    library_error = validate_libraries(manifest, plugin_dir)
    if library_error:
        return library_error
    from core.plugin_hooks_contract import validate_hooks

    hooks_error = validate_hooks(manifest, plugin_dir)
    if hooks_error:
        return hooks_error
    # agents / mcp and the later declarative components: accepted structurally, never
    # executed by the P1 runtime. `hooks` is not in this list: a version 2 turn hook is
    # validated above and dispatched by `core/plugin_turn_hooks.py`.
    for reserved in (
        "agents",
        "mcp",
        "resources",
        "prompts",
        "instructions",
        "rules",
        "outputStyles",
        "workflows",
    ):
        if reserved in components and not isinstance(
            components[reserved], (dict, list)
        ):
            return f"components.{reserved}: dict or list expected"
    # Extensions v2 (E2): optional icon. Registered by path (no traversal, no
    # absolute paths), only .svg/.png, and it has to sit inside the plugin dir.
    icon = manifest.get("icon")
    if icon is not None:
        if not isinstance(icon, str) or not icon.strip():
            return "icon: non-empty relative path expected"
        icon_path = Path(icon)
        if icon_path.is_absolute() or ".." in icon_path.parts:
            return "icon: must be a relative path inside the plugin directory"
        if icon_path.suffix.lower() not in {".svg", ".png"}:
            return "icon: only .svg or .png allowed"
        icon_file = _under(plugin_dir, icon)
        if icon_file is None or not icon_file.is_file():
            return f"icon: declared file {icon!r} does not exist in the plugin directory"
        limit = 64 * 1024 if icon_path.suffix.lower() == ".svg" else 256 * 1024
        if icon_file.stat().st_size > limit:
            return f"icon: file exceeds the {'64 KB (svg)' if icon_path.suffix.lower() == '.svg' else '256 KB (png)'} limit"
    from core.plugin_memory_contract import validate_memory

    memory_error = validate_memory(manifest)
    if memory_error:
        return memory_error
    from core.plugin_planner_contract import validate_planner

    planner_error = validate_planner(manifest)
    if planner_error:
        return planner_error
    from core.plugin_evaluator_contract import validate_evaluator

    evaluator_error = validate_evaluator(manifest)
    if evaluator_error:
        return evaluator_error
    return None


def _under(plugin_dir: Path, *parts: str) -> Path | None:
    """The real path of `parts` below `plugin_dir`, or None when it leaves it.

    Everything a manifest names is one entry inside its own plugin directory; the
    path is built from the real path of that directory and checked against its
    prefix, so symlinks and `..` parts included cannot step out (py/path-injection).
    """
    root = os.path.realpath(plugin_dir)
    target = os.path.realpath(os.path.join(root, *parts))
    if not target.startswith(root + os.sep):
        return None
    return Path(target)
