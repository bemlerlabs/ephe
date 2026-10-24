"""Ephe — Agent profiles (Extensions wave E5)
core/agent_profiles.py

User-defined helper-agent profiles for spawn_agent. A profile replaces the
hardcoded read-only default with an explicit, validated tool set:

    ~/.ephe/agents/<name>.json
    { "name": "scout", "description": "Fast explorer",
      "tools": ["read_file", "list_directory"], "model": "…", "timeout": 60 }

Sources, in order: the user agents dir, then `components.agents` of ACTIVE
manifest plugins. Validation is FAIL-CLOSED: a profile referencing an unknown
tool is quarantined (skipped, with reason collected), timeout clamps to
[30, 900], empty tool sets never load. Unknown profile labels in spawn_agent
behave exactly like today (default whitelist) — never break userspace.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

TIMEOUT_MIN_S = 30
TIMEOUT_MAX_S = 900
TIMEOUT_DEFAULT_S = 180


def agents_root() -> Path:
    base = os.environ.get("EPHE_CONFIG_DIR") or str(Path.home() / ".ephe")
    return Path(base) / "agents"


def _valid_tools(tools: Any, known: set[str]) -> list[str] | None:
    if not isinstance(tools, list) or not tools:
        return None
    out: list[str] = []
    for tool in tools:
        if not isinstance(tool, str) or tool not in known:
            return None  # fail-closed: one unknown tool quarantines the profile
        out.append(tool)
    return out


def load_profiles(
    manifest_agents: list[dict[str, Any]] | None = None,
    registry_override: dict[str, Any] | None = None,
) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    """Load validated profiles. Returns ({name: profile}, {name: quarantine_reason}).

    manifest_agents entries carry an extra `plugin` id — they only load when
    that plugin is active (explicit registry toggle, master-switch parity)."""
    from core.tools.registry import TOOL_MAP

    known = set(TOOL_MAP.keys())
    profiles: dict[str, dict[str, Any]] = {}
    quarantined: dict[str, str] = {}

    def _absorb(raw: Any, source: str) -> None:
        if not isinstance(raw, dict):
            return
        if raw.get("archived") is True or raw.get("enabled") is False:
            return  # the Agent Center can park an agent without deleting it
        name = str(raw.get("name") or "").strip()
        if not name or len(name) > 80:
            quarantined[f"{source}:{name or '?'}"] = "bad name"
            return
        if name in profiles:
            return  # first source wins (user dir over plugin bundles)
        tools = _valid_tools(raw.get("tools"), known)
        if tools is None:
            quarantined[name] = "no valid tools (unknown or empty tool list)"
            return
        limits = raw.get("limits") if isinstance(raw.get("limits"), dict) else {}
        try:
            timeout = float(limits.get("timeout", raw.get("timeout", TIMEOUT_DEFAULT_S)))
        except (TypeError, ValueError):
            timeout = TIMEOUT_DEFAULT_S
        try:
            max_turns = int(limits.get("max_turns", 8))
        except (TypeError, ValueError):
            max_turns = 8
        model_raw = raw.get("model")
        if isinstance(model_raw, dict):
            model_raw = model_raw.get("model")
        profiles[name] = {
            "id": str(raw.get("id") or name),
            "name": name,
            "description": str(raw.get("description") or ""),
            "instructions": str(raw.get("instructions") or ""),
            "tools": tools,
            "model": str(model_raw) if model_raw else None,
            "timeout": max(TIMEOUT_MIN_S, min(TIMEOUT_MAX_S, timeout)),
            "max_turns": max(1, min(24, max_turns)),
        }

    # 1) user agents dir
    root = agents_root()
    if root.is_dir():
        for f in sorted(root.glob("*.json")):
            try:
                _absorb(json.loads(f.read_text(encoding="utf-8")), f.name)
            except (OSError, ValueError):
                quarantined[f.name] = "unreadable json"

    # 2) plugin-bundled agents (active plugins only)
    if manifest_agents:
        if registry_override is not None:
            items = [p for p in registry_override.get("plugins", []) if isinstance(p, dict)]
        else:
            from core.plugin_store import load_registry

            items = load_registry()
        disabled = {str(p["name"]) for p in items if p.get("enabled") is False}
        for entry in manifest_agents:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("plugin") or "") in disabled:
                continue
            _absorb(entry, f"plugin:{entry.get('plugin', '?')}")

    return profiles, quarantined


def resolve_for_spawn(label: str | None) -> dict[str, Any] | None:
    """Profile for a spawn_agent subagent_type label, or None (default path)."""
    if not label:
        return None
    profiles, _ = load_profiles(manifest_agents=_manifest_agents())
    return profiles.get(label.strip())


def _manifest_agents() -> list[dict[str, Any]]:
    """components.agents of all valid manifest plugins (active gating happens
    inside load_profiles)."""
    try:
        from core import plugin_manifest

        out: list[dict[str, Any]] = []
        for entry in plugin_manifest.scan_plugins():
            manifest = entry["manifest"]
            if entry["error"] or not manifest:
                continue
            for agent in manifest.get("components", {}).get("agents", []):
                if isinstance(agent, dict):
                    out.append({**agent, "plugin": str(manifest["name"])})
        return out
    except Exception:
        return []
