"""
◑ Ephe – Plugin-Store light (wave 5 P3)
core/plugin_store.py

Two segments, one directory (analogous to the skill catalogues):
1. CURATED OFFLINE LIST — `plugin-catalog.json` in the repo root, with
   a schema version and two segments (`public`, `personal`). No network
   on the read path.
2. INSTALLED REGISTRY — `plugins.json` in the device folder (EPHE_CONFIG_DIR).

Restricting parallels to the skill catalogues: JSON, read-only,
fail-soft (faulty entry → skip the entry, the rest stays readable).

Core API (anchored in tests/test_r53_plugin_store.py):
- `sha256_hex(data)`                         — hash helper
- `detect_orphans(catalog, installed)`      — catalogue vs. installed
- `RefreshThrottle`                         — throttle (fake-clock capable)
- `load_catalog(path)`                      — two-segment reader
- `CATALOG_VERSION`, `MIN_REFRESH_INTERVAL_S`

Ephe – Bad Liebenzell, Black Forest
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Callable
from core.engine_config import config_root

# Schema version of the catalogue (identifies the format independently of versions).
CATALOG_VERSION = 1

# Shortest throttle interval for auto-refresh (s). Void when manual (force).
MIN_REFRESH_INTERVAL_S = 600

# Catalogue filename in the repo root; registry filename in the device.
CATALOG_FILENAME = "plugin-catalog.json"
REGISTRY_FILENAME = "plugins.json"

#: The one shape a plugin id may have before it becomes a directory name: a single
#: lower-case slug segment. `plugin_versions.plugin_dir` is the only joiner.
PLUGIN_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


# Path helpers

def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def catalog_path() -> Path:
    """Canonical path of the curated catalogue (repo root)."""
    return _repo_root() / CATALOG_FILENAME


def registry_path() -> Path:
    """Canonical path of the installed registry (device, best effort)."""
    return config_root() / REGISTRY_FILENAME


# Hash helper

def sha256_hex(data: bytes) -> str:
    """Hex digest of the bytes — identical to hashlib.sha256(data).hexdigest()."""
    return hashlib.sha256(data).hexdigest()


# Segment 1: curated offline catalogue (two-segment reader)

def load_catalog(path: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Reads the curated catalogue. Fail-soft: missing/corrupt → empty.

    Returns:
        {"public": [...], "personal": [...]} — per segment a list of
        entries (dicts with `name`). A faulty segment value is treated as
        empty, the other segment stays usable.
    """
    target = Path(path) if path is not None else catalog_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"public": [], "personal": []}
    if not isinstance(raw, dict):
        return {"public": [], "personal": []}
    out: dict[str, list[dict[str, Any]]] = {}
    for seg in ("public", "personal"):
        items = raw.get(seg)
        if not isinstance(items, list):
            items = []
        # Faulty entry → skip it, the rest stays readable.
        out[seg] = [e for e in items if isinstance(e, dict) and e.get("name")]
    return out


# Segment 2: installed registry (device)

def _read_json(path: Path) -> Any:
    try:
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_registry(path: Path | None = None) -> list[dict[str, Any]]:
    """Reads the installed registry. Missing/faulty → []."""
    target = Path(path) if path is not None else registry_path()
    raw = _read_json(target)
    if isinstance(raw, dict) and isinstance(raw.get("plugins"), list):
        return migrate_registry_items(
            [p for p in raw["plugins"] if isinstance(p, dict) and p.get("name")]
        )
    if isinstance(raw, list):
        return migrate_registry_items(
            [p for p in raw if isinstance(p, dict) and p.get("name")]
        )
    return []


# Extensions v2: legacy slug migration (E1)
# Old capability slugs → new product slugs. document-factory was
# split: the old state counts for all three successors.

LEGACY_SLUG_MAP: dict[str, list[str]] = {
    "web-search": ["web-research"],
    "image-gen": ["image-studio"],
    "tts": ["voice"],
    "mcp": ["mcp-connector"],
    "shell": ["code-shell"],
    "coding-suite": ["code-shell"],
    "document-factory": ["documents", "spreadsheets", "presentations"],
}


def migrate_registry_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Maps legacy slugs onto the v2 portfolio slugs (fail-soft, dedupe).

    An old entry produces the new entries with the same enabled state;
    new slugs already present explicitly win (no downgrade).
    """
    if not items:
        return items
    {str(e.get("name") or "") for e in items if str(e.get("name") or "") in LEGACY_SLUG_MAP}
    explicit_new = {
        str(e.get("name") or "")
        for e in items
        if str(e.get("name") or "") not in LEGACY_SLUG_MAP
    }
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        name = str(item.get("name") or "")
        if name in LEGACY_SLUG_MAP:
            for new_name in LEGACY_SLUG_MAP[name]:
                if new_name in seen or new_name in explicit_new:
                    continue
                clone = dict(item)
                clone["name"] = new_name
                out.append(clone)
                seen.add(new_name)
            continue
        if name in seen:
            continue
        out.append(dict(item))
        seen.add(name)
    # Order: explicit new entries first, then migrations (stable).
    out.sort(key=lambda e: 0 if str(e.get("name") or "") in explicit_new else 1)
    return out


def _write_registry(items: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps({"plugins": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def set_enabled(name: str, enabled: bool, path: Path | None = None) -> bool:
    """Set the enabled switch of a plugin in the registry (best effort).

    Returns True on success, False on a write/read error.
    """
    target = Path(path) if path is not None else registry_path()
    items = load_registry(target)
    for item in items:
        if item.get("name") == name:
            item["enabled"] = bool(enabled)
            break
    else:
        items.append({"name": name, "enabled": bool(enabled)})
    try:
        _write_registry(items, target)
    except OSError:
        return False
    return True


# Orphan detection

def detect_orphans(
    catalog: dict[str, list[dict[str, Any]]],
    installed: list[str],
) -> list[str]:
    """Installed names no longer listed in ANY catalogue segment.

    A plugin folder without a catalogue entry is still a loadable plugin
    (folder presence suffices); the orphan list is only a hint.
    Deterministically sorted.
    """
    known: set[str] = set()
    for seg in ("public", "personal"):
        for entry in catalog.get(seg, []) or []:
            if isinstance(entry, dict) and entry.get("name"):
                known.add(str(entry["name"]))
    return sorted({str(n) for n in installed if str(n) not in known})


# Auto-refresh throttle

class RefreshThrottle:
    """Throttles auto-refresh to `min_interval_s`; `force=True` ignores it.

    The clock is injectable (`clock`) so that tests work deterministically.
    """

    def __init__(
        self,
        min_interval_s: int = MIN_REFRESH_INTERVAL_S,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._min_interval_s = min_interval_s
        self._clock = clock or (lambda: __import__("time").monotonic())
        self._last: float | None = None

    def should_refresh(self, force: bool = False) -> bool:
        if force:
            return True
        if self._last is None:
            return True
        return (self._clock() - self._last) >= self._min_interval_s

    def mark_refreshed(self) -> None:
        self._last = self._clock()


# Installed bundles (GET /api/plugins `installed`)

#: The state word a row carries when its folder cannot be read as a manifest. Every other
#: word is a lifecycle state (`enabled`, `disabled`, `failed`, `paused`, ...), so a surface
#: can render one column without a second vocabulary.
INSTALLED_STATE_ERROR = "error"


def _capabilities(manifest: dict[str, Any] | None) -> dict[str, Any]:
    """What one manifest declares, normalized for a read-only row.

    The names are the contract's own: `tool_claims` is what the mount publishes and
    `ui_descriptor` is what the shell opens, so the row cannot drift from either.
    """
    empty: dict[str, Any] = {"tools": [], "surface": None, "commands": [], "skills": []}
    if not isinstance(manifest, dict):
        return empty
    from core import plugin_ui_capabilities
    from core.plugin_tools_contract import tool_claims

    components = manifest.get("components")
    components = components if isinstance(components, dict) else {}
    tools = [
        {
            "name": claim.name,
            "family": claim.family,
            "description": claim.description,
        }
        for claim in tool_claims(manifest)
    ]
    commands = []
    raw_commands = components.get("commands")
    for command in raw_commands if isinstance(raw_commands, list) else []:
        name = command.get("name") if isinstance(command, dict) else None
        if not isinstance(name, str) or not name:
            continue
        commands.append(
            {
                "name": f"/{name}",
                "description": str(command.get("description") or ""),
            }
        )
    skills = [
        pack
        for pack in (
            components.get("skills")
            if isinstance(components.get("skills"), list)
            else []
        )
        if isinstance(pack, str) and pack
    ]
    descriptor = plugin_ui_capabilities.ui_descriptor(manifest)
    surface = None
    if descriptor.get("entry"):
        surface = {
            "title": str(descriptor.get("title") or ""),
            "type": str(descriptor.get("type") or ""),
            "entry": str(descriptor["entry"]),
        }
    return {"tools": tools, "surface": surface, "commands": commands, "skills": skills}


def _installed_lifecycle(registry_file: Path | None) -> Any:
    from core.plugin_lifecycle import STATE_FILENAME

    state_path = (
        Path(registry_file).parent / STATE_FILENAME if registry_file is not None else None
    )
    try:
        from core import plugin_runtime

        return plugin_runtime.lifecycle(state_path)
    except Exception:
        return None


def _installed_switch(
    reader: Any, name: str, registry_enabled: bool | None
) -> tuple[str, bool]:
    """The switch word and the boolean for one installed bundle.

    The lifecycle is the only switch truth (`plugins_view` reads it the same way); the
    registry is the fallback for a bundle the process has not scanned yet.
    """
    if reader is not None:
        try:
            snapshot = reader.effective(name)
            return snapshot.state.value, bool(snapshot.enabled)
        except Exception:
            pass
    enabled = True if registry_enabled is None else bool(registry_enabled)
    return ("enabled" if enabled else "disabled"), enabled


def installed_bundles(
    catalog_file: Path | None = None,
    registry_file: Path | None = None,
    *,
    catalog: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """Every bundle directory this device can load, one row per name.

    The scan is the installed authority (`core.plugin_manifest.scan_plugins`), so a
    folder a user copied or Creator Mode installed appears here even without a catalogue
    line. A folder whose manifest is quarantined stays in the list with
    ``state: "error"`` and its reason, because "installed but broken" is a row a reader
    has to see. Sorted by name; the scan already resolves a user bundle over a builtin
    identity, so no name appears twice.
    """
    from core import plugin_manifest, plugin_mount_trust, plugin_rail

    try:
        scanned = plugin_manifest.scan_plugins()
        builtin_root = plugin_manifest.builtin_plugins_root().resolve()
    except Exception:
        return []
    catalog = catalog if catalog is not None else load_catalog(catalog_file)
    catalog_names = {
        str(entry.get("name") or "")
        for segment in ("public", "personal")
        for entry in catalog.get(segment, []) or []
        if isinstance(entry, dict) and entry.get("name")
    }
    registry_enabled = {
        str(item.get("name")): item.get("enabled") is not False
        for item in load_registry(registry_file)
        if item.get("name")
    }
    reader = _installed_lifecycle(registry_file)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in scanned:
        directory = Path(entry["dir"])
        manifest = entry.get("manifest")
        name = str(manifest["name"]) if manifest else directory.name
        if not name or name in seen:
            continue
        seen.add(name)
        error = str(entry.get("error") or "")
        if error or not isinstance(manifest, dict):
            state, enabled = INSTALLED_STATE_ERROR, False
            rail = ""
        else:
            state, enabled = _installed_switch(reader, name, registry_enabled.get(name))
            try:
                rail = plugin_rail.rail_fact(manifest)["rail"]
            except Exception:  # noqa: BLE001 — a row still names the bundle
                rail = ""
        try:
            source = (
                "builtin" if directory.resolve().is_relative_to(builtin_root) else "user"
            )
        except (OSError, ValueError):
            source = "user"
        try:
            capabilities = _capabilities(manifest)
        except Exception:  # noqa: BLE001 — one unreadable manifest never breaks the list
            capabilities = {"tools": [], "surface": None, "commands": [], "skills": []}
        try:
            trust = plugin_mount_trust.bundle_trust(directory)
        except OSError:
            # The signature record sits in a folder this process may not traverse; the
            # row still names the bundle instead of the view failing on it.
            trust = "local"
        rows.append(
            {
                "id": name,
                "name": name,
                "version": str((manifest or {}).get("version") or ""),
                "description": str((manifest or {}).get("description") or ""),
                "source": source,
                "trust": trust,
                "origin": str((manifest or {}).get("origin") or ""),
                "state": state,
                "enabled": enabled,
                "rail": rail,
                "in_catalog": name in catalog_names,
                "error": error,
                "capabilities": capabilities,
            }
        )
    return sorted(rows, key=lambda row: row["name"])


# Aggregated view (GET /api/plugins)

def _mapp_entry(entry: dict[str, Any], enabled_lookup: dict[str, bool]) -> dict[str, Any]:
    name = str(entry.get("name") or "")
    if name in enabled_lookup:
        enabled = enabled_lookup[name]
    else:
        enabled = bool(entry.get("enabled", True))
    tags = entry.get("tags")
    prompts = entry.get("example_prompts")
    out = {
        "id": name,
        "name": name,
        "description": str(entry.get("description") or ""),
        "tags": [str(t) for t in tags] if isinstance(tags, list) else [],
        "example_prompts": [str(p) for p in prompts] if isinstance(prompts, list) else [],
        "enabled": enabled,
    }
    # E2: catalog entries may declare manifest-based artifacts.
    if "manifest" in entry:
        out["manifest"] = bool(entry.get("manifest"))
    if entry.get("version"):
        out["version"] = str(entry["version"])
    if entry.get("sha256"):
        out["sha256"] = str(entry["sha256"])
    # E3: provenance — own development vs. external (store badge).
    if entry.get("origin"):
        out["origin"] = str(entry["origin"])
    return out


def plugins_view(catalog_file: Path | None = None, registry_file: Path | None = None) -> dict[str, Any]:
    """Aggregated view: catalogue (both segments) + lifecycle switches.

    The lifecycle state is the only switch truth; a missing per-plugin entry
    keeps the one-release default. If the state cannot be read, the view is
    ``unproven``: every switch is off, a stable notice explains it, and the
    legacy ``master_enabled`` value is never consulted. ``read_only`` mirrors the
    operator brake on the switch surface.
    """
    from core import plugin_switch_policy

    catalog = load_catalog(catalog_file)
    reg_items = load_registry(registry_file)
    names = [
        str(entry.get("name") or "")
        for seg in ("public", "personal")
        for entry in catalog[seg]
    ]
    read_only = plugin_switch_policy.read_only()
    unproven = False
    try:
        from core import plugin_runtime

        state = plugin_runtime.store_state(names, registry_file)
        enabled_lookup = state.enabled
        master = not state.pause_all
        notices = list(plugin_runtime.notices(registry_file))
        unproven = state.unproven
    except Exception:
        enabled_lookup = {name: False for name in names}
        master = False
        notices = []
        unproven = True
    if unproven and not any(
        notice.get("code") == "plugin_state_unproven" for notice in notices
    ):
        notices.append(
            {
                "code": "plugin_state_unproven",
                "message": (
                    "The plugin state could not be read; every switch stays off "
                    "until it can."
                ),
            }
        )
    view = {
        "version": CATALOG_VERSION,
        "master_enabled": master,
        "read_only": read_only,
        "unproven": unproven,
        "notices": notices,
        "public": [_mapp_entry(e, enabled_lookup) for e in catalog["public"]],
        "personal": [_mapp_entry(e, enabled_lookup) for e in catalog["personal"]],
    }
    # E4a: orphan hint — installed names without a catalogue entry. The UI has
    # shown this line since E4, but nobody produced it; now it comes from the
    # same registry as the switches. Folder presence still suffices for loading
    # (see the detect_orphans docs) — the list explains, it does not block.
    # Two bundles that claim one tool or one memory provider: neither serves it, and this
    # section names both so the conflict is visible instead of silent.
    try:
        from core import plugin_runtime

        view["contested"] = plugin_runtime.contested_names()
    except Exception:  # noqa: BLE001 — the list stays readable, the section stays coded
        view["contested"] = {"tools": [], "memory_providers": []}
    view["orphans"] = detect_orphans(
        catalog, sorted({str(i["name"]) for i in reg_items if i.get("name")})
    )
    # PE2E 3b: the catalogue is not the installed set. A bundle Creator Mode made on
    # this machine has no catalogue line, so it used to reach the surface as an orphan
    # name only. `installed` is the folder truth, with the switch and the capabilities.
    view["installed"] = installed_bundles(
        catalog_file, registry_file, catalog=catalog
    )
    # E4b: attach manifest facts (source, permissions) where a dir exists —
    # the detail sheet shows what a plugin declares, best-effort, never fatal.
    try:
        from core import plugin_manifest
        from core.plugin_ui_capabilities import ui_descriptor

        by_name = {
            str(e["manifest"]["name"]): e
            for e in plugin_manifest.scan_plugins()
            if e["manifest"]
        }
        for seg in ("public", "personal"):
            for entry in view[seg]:
                found = by_name.get(str(entry["name"]))
                if not found:
                    continue
                entry["source"] = "builtin" if found["dir"].parent == plugin_manifest.BUILTIN_PLUGINS_ROOT else "user"
                if entry["source"] == "user":
                    # A user install that shadows a catalog identity must show
                    # its own version, description and content hash.
                    catalog_origin = entry.get("origin")
                    manifest = found["manifest"]
                    entry["version"] = str(manifest.get("version") or "")
                    entry["description"] = str(manifest.get("description") or "")
                    entry["sha256"] = plugin_manifest.dir_sha256(found["dir"])
                    entry["origin"] = str(manifest.get("origin") or "user")
                    if catalog_origin == "first-party":
                        entry["shadowed_builtin"] = True
                families = found["manifest"].get("permissions", {}).get("tool_families", [])
                entry["permissions"] = [str(f) for f in families] if isinstance(families, list) else []
                # The rail this bundle runs on, read off its own manifest. A catalog entry
                # with no directory behind it carries no rail: the surface shows nothing
                # rather than a guess about code it has not seen.
                from core import plugin_rail

                fact = plugin_rail.rail_fact(found["manifest"])
                entry["rail"] = fact["rail"]
                entry["contributed_tools"] = fact["contributed"]
                entry["activated_tools"] = fact["activated"]
                # W1-7: the one surface this bundle declares, already defaulted and
                # flattened by the contract's own view. A bundle without a surface
                # carries no `surface` key at all, which is what the switch row
                # reads as "there is nothing here to open".
                descriptor = ui_descriptor(found["manifest"])
                if descriptor.get("entry"):
                    entry["surface"] = descriptor
    except Exception:
        pass
    # #106: the Extensions row says how much of its ceiling a bundle has spent.
    # Names and the host path stay off this payload; the state route lists files.
    from core import plugin_state

    manifests: dict = {}
    try:
        from core import plugin_manifest

        manifests = {
            str(item["manifest"]["name"]): item["manifest"]
            for item in plugin_manifest.scan_plugins()
            if item.get("manifest")
        }
    except Exception:
        manifests = {}
    for seg in ("public", "personal"):
        for entry in view[seg]:
            plugin_id = str(entry.get("id") or "")
            try:
                entry["state_usage"] = plugin_state.summary_for(
                    plugin_id, manifests.get(plugin_id)
                )
            except Exception:
                entry["state_usage"] = {
                    "used_mb": 0,
                    "cap_mb": plugin_state.DEFAULT_STATE_CAP_MB,
                    "file_count": 0,
                }
    from core.plugin_scope import annotate_view

    annotate_view(view, manifests)
    return view
