"""Ephe — Plugin manifest v1 (Extensions wave E2)
core/plugin_manifest.py

Format + validation contract for `ephe-plugin.json`, the manifest that turns
a directory into an Ephe plugin (spec: docs/PLUGINS.md).

Layout convention:
    <plugins_root>/<plugin>/ephe-plugin.json     manifest (required)
    <plugins_root>/<plugin>/skills/<pack>/SKILL.md   bundled skill packs

Fail-closed validation (a violation QUARANTINES the whole plugin — never a
half-loaded state): bad JSON, bad slug/semver, name/directory mismatch, an
unknown permission tool family, or a declared skill pack that does not ship.

Fail-soft scanning (a broken plugin directory never breaks the others).

Plugins root: EPHE_CONFIG_DIR/plugins (default ~/.ephe/plugins), overridable
via PLUGINS_ROOT_OVERRIDE for tests.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = "ephe-plugin.json"
SIG_FILENAME = "ephe-plugin.sig.json"
MANIFEST_VERSION = 1
PLUGINS_DIRNAME = "plugins"

#: First-party manifests shipped inside the repo (catalog-backed bundles).
BUILTIN_PLUGINS_ROOT = Path(__file__).resolve().parent.parent / "plugins"

#: Permission families a manifest may declare. Anything outside this set
#: fails closed (declared-but-absent capabilities never run).
KNOWN_TOOL_FAMILIES = {"read", "write", "shell", "network", "memory", "vision", "docs", "browser"}

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")

#: Test seam — when set, plugins_root() returns this path.
PLUGINS_ROOT_OVERRIDE: Path | None = None


def plugins_root() -> Path:
    if PLUGINS_ROOT_OVERRIDE is not None:
        return Path(PLUGINS_ROOT_OVERRIDE)
    base = os.environ.get("EPHE_CONFIG_DIR") or str(Path.home() / ".ephe")
    return Path(base) / PLUGINS_DIRNAME


# Validation

def _validate(manifest: Any, plugin_dir: Path) -> str | None:
    """Full contract check. Returns an error string or None."""
    if not isinstance(manifest, dict):
        return "manifest: object expected"
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        return f"manifest_version: must be {MANIFEST_VERSION}"
    name = manifest.get("name")
    if not isinstance(name, str) or not _SLUG_RE.match(name or ""):
        return "name: lowercase slug expected (a-z0-9-)"
    if name != plugin_dir.name:
        return f"name: {name!r} does not match directory {plugin_dir.name!r}"
    version = manifest.get("version")
    if not isinstance(version, str) or not _SEMVER_RE.match(version or ""):
        return "version: semver X.Y.Z expected"
    if not isinstance(manifest.get("description"), str) or not manifest.get("description", "").strip():
        return "description: non-empty string expected"

    perms = manifest.get("permissions", {})
    if perms is not None:
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

    components = manifest.get("components", {})
    if components is not None:
        if not isinstance(components, dict):
            return "components: object expected"
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
        for cmd in commands:
            if not isinstance(cmd, dict) or not isinstance(cmd.get("name"), str) or not _SLUG_RE.match(cmd.get("name", "")):
                return f"components.commands: bad command name {cmd!r}"
            if not isinstance(cmd.get("description"), str) or not cmd.get("description", "").strip():
                return f"components.commands.{cmd.get('name')}: description required"
        # agents / hooks / mcp: reserved for E4/E5 — accepted structurally,
        # never executed by the E2 runtime.
        for reserved in ("agents", "hooks", "mcp"):
            if reserved in components and not isinstance(components[reserved], (dict, list)):
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


def dir_sha256(path: Path, exclude_names: frozenset[str] = frozenset({SIG_FILENAME})) -> str:
    """Deterministic directory hash over sorted relative paths + bytes.

    The identity of a shipped first-party plugin: catalog entries carry this
    hash so a drift between catalog and directory is detectable (E4 verifies
    against it before signing). Signature records (SIG_FILENAME, E4b) are
    excluded by default — signing does not change the hash it signs."""
    digest = hashlib.sha256()
    for f in sorted(p for p in Path(path).rglob("*") if p.is_file()):
        if f.name in exclude_names:
            continue
        rel = f.relative_to(path).as_posix()
        digest.update(rel.encode("utf-8") + b"\x00" + f.read_bytes() + b"\x00")
    return digest.hexdigest()


def load_manifest(plugin_dir: Path) -> tuple[dict | None, str | None]:
    """Read + validate one plugin directory. Returns (manifest, error)."""
    plugin_dir = Path(plugin_dir)
    mfile = _under(plugin_dir, MANIFEST_FILENAME)
    if mfile is None or not mfile.is_file():
        return None, f"{MANIFEST_FILENAME} missing"
    try:
        manifest = json.loads(mfile.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, f"manifest unreadable: {exc}"
    err = _validate(manifest, plugin_dir)
    if err:
        return None, err
    return manifest, None


# Scanning (fail-soft)

def scan_plugins(root: Path | None = None) -> list[dict[str, Any]]:
    """Scan plugin directories. One entry per directory:
    {dir, manifest (dict|None), error (str|None)}.

    Root resolution: explicit arg → only that root; PLUGINS_ROOT_OVERRIDE
    (test seam) → only that root; otherwise the USER root first (it overrides
    builtin identities) and the repo builtin root second."""
    if root is not None:
        bases = [Path(root)]
    elif PLUGINS_ROOT_OVERRIDE is not None:
        bases = [Path(PLUGINS_ROOT_OVERRIDE)]
    else:
        bases = [plugins_root(), BUILTIN_PLUGINS_ROOT]
    out: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for base in bases:
        if not base.is_dir():
            continue
        for pdir in sorted(p for p in base.iterdir() if p.is_dir()):
            manifest, err = load_manifest(pdir)
            name = str(manifest["name"]) if manifest else pdir.name
            if name in seen_names:
                continue  # user manifests override builtin identities
            seen_names.add(name)
            out.append({"dir": pdir, "manifest": manifest, "error": err})
    return out


def _plugin_active(name: str) -> bool:
    from core.plugin_runtime import is_plugin_active

    return is_plugin_active(name)


def active_skill_roots(root: Path | None = None) -> list[Path]:
    """Skill-pack dirs of ACTIVE, valid manifest plugins (skill loader roots)."""
    out: list[Path] = []
    for entry in scan_plugins(root):
        manifest = entry["manifest"]
        if entry["error"] or not manifest:
            continue
        if not _plugin_active(str(manifest["name"])):
            continue
        for pack in manifest.get("components", {}).get("skills", []):
            out.append(entry["dir"] / "skills" / pack)
    return out


def manifest_commands(root: Path | None = None) -> list[dict[str, str]]:
    """Normalized slash commands across all valid plugins (active only)."""
    out: list[dict[str, str]] = []
    for entry in scan_plugins(root):
        manifest = entry["manifest"]
        if entry["error"] or not manifest:
            continue
        if not _plugin_active(str(manifest["name"])):
            continue
        for cmd in manifest.get("components", {}).get("commands", []):
            out.append({
                "name": f"/{cmd['name']}",
                "description": str(cmd.get("description", "")),
                "template": str(cmd.get("template", "")),
                "plugin": str(manifest["name"]),
            })
    return out
