"""Ephe — Plugin manifest: load, hash and scan the plugin portfolio.

core/plugin_manifest.py

The loader half of the manifest: read a directory into a manifest, hash it, and scan a
root into the portfolio the runtime gate, the skill loader and the slash menu all read.
What a manifest has to *say* lives in `core/plugin_manifest_contract.py` and the one
module per capability section beside it (`core/plugin_tools_contract.py`,
`core/plugin_ui_capabilities.py`, `core/plugin_libraries.py`,
`core/plugin_memory_contract.py`).

Layout convention:
    <plugins_root>/<plugin>/ephe-plugin.json     manifest (required)
    <plugins_root>/<plugin>/skills/<pack>/SKILL.md   bundled skill packs

Fail-closed validation (a violation QUARANTINES the whole plugin — never a
half-loaded state): bad JSON, bad slug/semver, name/directory mismatch, an
unknown permission tool family, or a declared skill pack that does not ship.

Fail-soft scanning (a broken plugin directory never breaks the others).

Plugins root: EPHE_CONFIG_DIR/plugins (default ~/.ephe/plugins), overridable
via PLUGINS_ROOT_OVERRIDE for tests. Builtin root: EPHE_BUILTIN_PLUGINS_ROOT
(default: the `plugins/` folder of this checkout), resolved per call like the
config root so an isolated run can own it instead of reading the source tree.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from core.engine_config import config_root
from core.plugin_manifest_contract import (
    _SEMVER_RE as _SEMVER_RE,
)
from core.plugin_manifest_contract import (
    _SLUG_RE as _SLUG_RE,
)

# The contract's vocabulary is re-exported here: it was defined in this module until the
# split, and `core/plugin_libraries.py`, `core/tools/creator_tools.py` and the evals read
# it through this name. `X as X` is the explicit re-export the linter reads as one.
from core.plugin_manifest_contract import (
    KNOWN_COMPONENT_KEYS as KNOWN_COMPONENT_KEYS,
)
from core.plugin_manifest_contract import (
    KNOWN_MANIFEST_FIELDS as KNOWN_MANIFEST_FIELDS,
)
from core.plugin_manifest_contract import (
    KNOWN_TOOL_FAMILIES as KNOWN_TOOL_FAMILIES,
)
from core.plugin_manifest_contract import (
    MANIFEST_VERSION as MANIFEST_VERSION,
)
from core.plugin_manifest_contract import (
    MANIFEST_VERSION_V2 as MANIFEST_VERSION_V2,
)
from core.plugin_manifest_contract import (
    SUPPORTED_MANIFEST_VERSIONS as SUPPORTED_MANIFEST_VERSIONS,
)
from core.plugin_manifest_contract import (
    _under as _under,
)
from core.plugin_manifest_contract import (
    validate_manifest,
)

MANIFEST_FILENAME = "ephe-plugin.json"
SIG_FILENAME = "ephe-plugin.sig.json"
PLUGINS_DIRNAME = "plugins"

#: Env seam - when set, the second scan root is this path. Resolved per call, like
#: EPHE_CONFIG_DIR, so an isolated eval run can point it at a folder it owns.
ENV_BUILTIN_PLUGINS_ROOT = "EPHE_BUILTIN_PLUGINS_ROOT"

#: First-party manifests shipped inside the repo (catalog-backed bundles).
BUILTIN_PLUGINS_ROOT = Path(__file__).resolve().parent.parent / "plugins"


def builtin_plugins_root() -> Path:
    """The first-party plugin root, read at call time.

    With ``EPHE_BUILTIN_PLUGINS_ROOT`` set this is the only builtin root a scan reads.
    An empty value falls back the way ``config_root()`` does, so `""` keeps the shipped
    folder.
    """
    override = os.environ.get(ENV_BUILTIN_PLUGINS_ROOT)
    if override:
        return Path(override)
    return BUILTIN_PLUGINS_ROOT


#: Test seam — when set, plugins_root() returns this path.
PLUGINS_ROOT_OVERRIDE: Path | None = None


def plugins_root() -> Path:
    if PLUGINS_ROOT_OVERRIDE is not None:
        return Path(PLUGINS_ROOT_OVERRIDE)
    return config_root() / PLUGINS_DIRNAME


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


def load_manifest(
    plugin_dir: Path, *, require_dir_name: bool = True
) -> tuple[dict | None, str | None]:
    """Read + validate one plugin directory. Returns (manifest, error).

    A one-slot rollback backup (`.previous-<name>`) cannot satisfy the
    name-equals-directory rule; signature verification passes
    `require_dir_name=False` and binds identity through the signed record
    instead."""
    plugin_dir = Path(plugin_dir)
    mfile = _under(plugin_dir, MANIFEST_FILENAME)
    if mfile is None:
        return None, f"{MANIFEST_FILENAME} missing"
    # `is_file()` is not total: a directory the process may not traverse answers
    # `PermissionError` here rather than False, measured with a plugin folder at mode 000.
    # Asking the same question inside the try is what makes the reader total, so one
    # unreadable folder reports an error the surface can show instead of failing the whole
    # scan (task #59, the 500 on `/api/plugins`).
    try:
        if not mfile.is_file():
            return None, f"{MANIFEST_FILENAME} missing"
        manifest = json.loads(mfile.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, f"manifest unreadable: {type(exc).__name__}"
    except ValueError:
        return None, "manifest unreadable"
    err = validate_manifest(manifest, plugin_dir, require_dir_name=require_dir_name)
    if err:
        return None, err
    return manifest, None


# Scanning (fail-soft)

def _is_dir(path: Path) -> bool:
    """`Path.is_dir()` that answers False instead of raising.

    The stdlib version swallows the errors it expects (no such path, not a directory) and
    lets the others through, so an unreadable folder raises `PermissionError` out of it.
    Every directory question this scanner asks is a question about someone else's folder,
    and the answer this file can act on is a boolean.
    """
    try:
        return path.is_dir()
    except OSError:
        return False


def scan_plugins(root: Path | None = None) -> list[dict[str, Any]]:
    """Scan plugin directories. One entry per directory:
    {dir, manifest (dict|None), error (str|None)}.

    Root resolution: explicit arg → only that root; PLUGINS_ROOT_OVERRIDE
    (test seam) → only that root; otherwise the USER root first (it overrides
    builtin identities) and the builtin root second (``builtin_plugins_root()``,
    the repo `plugins/` folder unless EPHE_BUILTIN_PLUGINS_ROOT moves it)."""
    if root is not None:
        bases = [Path(root)]
    elif PLUGINS_ROOT_OVERRIDE is not None:
        bases = [Path(PLUGINS_ROOT_OVERRIDE)]
    else:
        bases = [plugins_root(), builtin_plugins_root()]
    out: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for base in bases:
        if not _is_dir(base):
            continue
        # Both halves of this line can fail on a real filesystem: `iterdir` raises on an
        # unreadable root, and `is_dir()` on a child can answer `PermissionError` or
        # `OSError` for a folder whose metadata cannot be read. Neither is a reason the
        # settings page should fail; the root that cannot be listed simply contributes
        # nothing to this list, and its reason is not carried here — a caller that needs
        # to know whether the root exists has `plugins_root()`.
        try:
            children = sorted(p for p in base.iterdir() if _is_dir(p))
        except OSError:
            continue
        for pdir in children:
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
