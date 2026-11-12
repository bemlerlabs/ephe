"""The one mode-to-plugin table.

``resolve`` is the resolution point for one session. ``MODE_PLUGINS`` is the
only mapping from a composer mode to plugin ids. Callers pass the committed
``enabled`` bit and the pause-all brake. This module writes no lifecycle
state.

Order: pause-all keeps the plugin out of effect. A globally enabled plugin
is in effect with reason ``global``. A plugin the active mode names is in
effect with reason ``preset``. Every other plugin is out of effect with
reason ``off``.

The shipped table names no plugin. A mode composes a bundle only after that
bundle's id is written into ``MODE_PLUGINS`` in this file. Tests pass their
own mapping. Tool families do not decide membership.

Tool execution still reads the committed switch. A later change that lets a
preset supply a plugin calls ``resolve`` and reads this table.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from core.plugin_hooks_contract import hook_facts

MODES: tuple[str, ...] = ("analyst", "architect", "operator", "creator")

# Spellings the composer already resolves. edit-auto stays its own factor.
_CANON = {
    "ask": "analyst",
    "analyst": "analyst",
    "plan": "architect",
    "architect": "architect",
    "full_access": "operator",
    "operator": "operator",
    "creator": "creator",
}

MODE_PLUGINS: dict[str, frozenset[str]] = {mode: frozenset() for mode in MODES}


@dataclass(frozen=True)
class ScopeDecision:
    plugin_id: str
    in_effect: bool
    reason: str
    mode: str


def canon_mode(mode: str) -> str:
    raw = (mode or "").strip().lower().replace("-", "_")
    return _CANON.get(raw, "")


def _table(
    mapping: Mapping[str, frozenset[str] | set[str]] | None,
) -> Mapping[str, frozenset[str] | set[str]]:
    return MODE_PLUGINS if mapping is None else mapping


def modes_providing(
    plugin_id: str,
    mapping: Mapping[str, frozenset[str] | set[str]] | None = None,
) -> list[str]:
    table = _table(mapping)
    return [mode for mode in MODES if plugin_id in table.get(mode, frozenset())]


def resolve(
    plugin_id: str,
    *,
    enabled: bool,
    pause_all: bool,
    mode: str,
    mapping: Mapping[str, frozenset[str] | set[str]] | None = None,
) -> ScopeDecision:
    canonical = canon_mode(mode)
    if pause_all:
        return ScopeDecision(plugin_id, False, "paused", canonical)
    if enabled:
        return ScopeDecision(plugin_id, True, "global", canonical)
    named = _table(mapping).get(canonical, frozenset())
    if plugin_id in named:
        return ScopeDecision(plugin_id, True, "preset", canonical)
    return ScopeDecision(plugin_id, False, "off", canonical)


def describe(
    plugin_id: str,
    *,
    enabled: bool,
    pause_all: bool,
    mode: str,
    mapping: Mapping[str, frozenset[str] | set[str]] | None = None,
) -> dict[str, object]:
    decision = resolve(
        plugin_id,
        enabled=enabled,
        pause_all=pause_all,
        mode=mode,
        mapping=mapping,
    )
    provided = modes_providing(plugin_id, mapping)
    return {
        "plugin_id": plugin_id,
        "enabled": bool(enabled),
        "pause_all": bool(pause_all),
        "in_effect": decision.in_effect,
        "reason": decision.reason,
        "mode": decision.mode,
        "scope": "session" if provided else "global",
        "provided_by_modes": provided,
    }


def module_text(manifest: Mapping[str, object] | None) -> str:
    if not isinstance(manifest, Mapping):
        return ""
    components = manifest.get("components")
    if not isinstance(components, Mapping):
        return ""
    tools = components.get("tools")
    if isinstance(tools, list):
        for tool in tools:
            if not isinstance(tool, Mapping):
                continue
            entry = tool.get("entry")
            if isinstance(entry, str) and entry.strip():
                return entry.strip()
    surface = components.get("ui")
    if isinstance(surface, Mapping):
        entry = surface.get("entry")
        if isinstance(entry, str) and entry.strip():
            return entry.strip()
    return ""


def configuration_text(manifest: Mapping[str, object] | None) -> str:
    if not isinstance(manifest, Mapping):
        return ""
    permissions = manifest.get("permissions")
    if not isinstance(permissions, Mapping):
        return ""
    families = permissions.get("tool_families")
    if not isinstance(families, list):
        return ""
    names = [str(item) for item in families if isinstance(item, str) and item]
    return ", ".join(names)


def annotate_view(
    view: dict[str, object],
    manifests: Mapping[str, Mapping[str, object]] | None = None,
    mapping: Mapping[str, frozenset[str] | set[str]] | None = None,
) -> dict[str, object]:
    known = manifests or {}
    buckets: dict[str, list[dict[str, object]]] = {"global": [], "session": []}
    for segment in ("public", "personal"):
        rows = view.get(segment) or []
        if not isinstance(rows, list):
            continue
        for entry in rows:
            if not isinstance(entry, dict):
                continue
            plugin_id = str(entry.get("id") or entry.get("name") or "")
            provided = modes_providing(plugin_id, mapping)
            manifest = known.get(plugin_id)
            entry["scope"] = "session" if provided else "global"
            entry["provided_by_modes"] = provided
            entry["module"] = module_text(manifest)
            entry["configuration"] = configuration_text(manifest)
            entry["hooks"] = hook_facts(manifest)
            buckets[str(entry["scope"])].append(entry)
    view["global"] = buckets["global"]
    view["session"] = buckets["session"]
    return view
