"""The Tier-1 declarative-surface checks of the plugin definition-of-done gate.

scripts/plugin_dod_surface.py

A manifest v2 bundle is accepted by `scripts/plugin_dod.py` through the checks below,
which hold the one thing a manifest read cannot answer: every file the entry document
names arrives from inside the bundle. Everything the shipped manifest contract already
decides — the descriptor fields, the capability vocabulary, the entry suffix and its place
inside the plugin directory, the vendored-library hashes, the data roots, the shape of a
declared tool — is read from `core.plugin_manifest.load_manifest`, and the rule stated once
there needs no second statement here. What a `components.tools` entry further promises the
bundle itself carries is `scripts/plugin_dod_tools.py`'s question.

The entry-document scan is a text read of one file. It refuses a reference that
carries a scheme or an authority (a surface fetches nothing outside its bundle —
`server/plugin_surface_policy.py` emits a `default-src 'self'` the mount cannot
widen, so a remote reference would fail closed at the engine anyway and the gate
names it while the author can still fix it), a reference that is absolute or
steps out of the entry directory, and a relative reference to a file that does
not ship, which is a surface that half-loads. Two names are the mount's own:
`ephe.js`, the page SDK the route serves at the mount root, and
`ephe-storage.js`, the page-storage shim it injects and reserves at every depth.
A document that names one is addressing the mount, not forgetting a file.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import re
from pathlib import Path

from core.plugin_manifest import _under, load_manifest

#: What an entry document names: one of these attributes, one value.
ENTRY_REFERENCE = re.compile(r"""(?:src|href)\s*=\s*["']([^"'\\]+)["']""", re.IGNORECASE)

#: A reference with a scheme (`https:`, `data:`) or a network path (`//host`).
REMOTE_REFERENCE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:|^//")

#: The two names the mount answers itself, so a document that names one is not
#: pointing at a file it forgot. `server/routes/plugin_ui.py` serves the build's page
#: SDK exactly when the remainder is `ephe.js`, and its storage shim whenever the
#: basename is `ephe-storage.js`; a bundle never has to ship either.
MOUNT_SERVED_SDK = "ephe.js"
MOUNT_SERVED_SHIM = "ephe-storage.js"


def _is_mount_served(value: str) -> bool:
    """Whether the entry's URL resolves to one of the files the route serves itself."""
    path = Path(value)
    if path.name == MOUNT_SERVED_SHIM:
        return True
    return path.name == MOUNT_SERVED_SDK and path.parent == Path(".")


def _entry_reference_problems(plugin_dir: Path, entry: str) -> list[str]:
    """Every file the entry document names arrives from inside the bundle."""
    entry_path = _under(plugin_dir, entry)
    if entry_path is None:
        return [f"components.ui.entry: {entry!r} resolves outside the plugin directory"]
    try:
        if not entry_path.is_file():
            return [f"components.ui.entry: {entry!r} does not ship"]
        document = entry_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"components.ui.entry: {entry!r} is not readable ({exc.__class__.__name__})"]
    problems: list[str] = []
    for raw in ENTRY_REFERENCE.findall(document):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        if REMOTE_REFERENCE.match(value):
            problems.append(f"entry reference {value!r} leaves the bundle")
            continue
        if value.startswith("/"):
            problems.append(f"entry reference {value!r} is absolute")
            continue
        if ".." in Path(value).parts:
            problems.append(f"entry reference {value!r} steps out of the entry directory")
            continue
        if _is_mount_served(value.split("?")[0].split("#")[0]):
            continue
        target = entry_path.parent / value.split("?")[0].split("#")[0]
        if not target.is_file():
            problems.append(f"entry reference {value!r} names a file that does not ship")
    return problems


def surface_problems(plugin_dir: Path) -> list[str]:
    """The v2 declarative-surface DoD, as a problem list."""
    loaded, error = load_manifest(plugin_dir)
    if error or not isinstance(loaded, dict):
        return [f"manifest: {error or 'unreadable'}"]
    components = loaded.get("components") or {}
    surface = components.get("ui")
    problems: list[str] = []
    if not isinstance(surface, dict):
        problems.append("components.ui: a v2 bundle accepted here declares one surface")
    if isinstance(surface, dict):
        problems.extend(_entry_reference_problems(plugin_dir, str(surface.get("entry") or "")))
    return problems
