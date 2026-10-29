"""One switch per capability, in the user's own hands.

Every tool the agent can call — built-in, plugin, MCP remote, skill — has one
entry here and one persisted state. The same file carries the extra names the
user adds to the read-only whitelist a sub-agent runs under.

The two readers are the places that already own the decision: the offer list
(`core/tools/registry.get_tool_schemas`) hides a switched-off tool from the
model, and `execute_tool` refuses it by name, so a guess or a deferred bridge
call cannot get past the switch. Off is a state, never a silent drop: the
catalog reports it and the refusal names the setting.

Storage is a small JSON file beside the settings (EPHE_CONFIG_DIR, otherwise
`~/.ephe`), written atomically. A broken file reads as "nothing switched off" —
the product keeps working, the user just sees the default.
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

FILE_NAME = "capabilities.json"
STATE_VERSION = 1

#: The turn cannot run without these: they are the bridge to the deferred tools
#: and the pause for a question. Refusing to switch them off keeps one click from
#: turning the agent mute.
ALWAYS_ON = frozenset({"tool_search", "tool_describe", "tool_call", "ask_user"})

#: The stock read-only whitelist a sub-agent runs under, before the user's additions.
SUBAGENT_BASE_WHITELIST = (
    "web_search",
    "fetch_url",
    "read_file",
    "list_directory",
    "file_search",
    "load_workspace",
    "get_datetime",
    "analyze_image",
    "query_source_notebook",
)


def store_path() -> Path:
    base = os.environ.get("EPHE_CONFIG_DIR")
    root = Path(base) if base else Path.home() / ".ephe"
    return root / FILE_NAME


def _read() -> dict:
    try:
        data = json.loads(store_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write(data: dict) -> None:
    path = store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.part")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temp, path)


def _names(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def state() -> dict:
    data = _read()
    return {
        "version": STATE_VERSION,
        "disabled": sorted(set(_names(data.get("disabled")))),
        "subagent_extra": sorted(set(_names(data.get("subagent_extra")))),
    }


def disabled() -> set[str]:
    return set(state()["disabled"])


def is_enabled(name: str) -> bool:
    return name not in disabled()


def set_enabled(name: str, enabled: bool) -> bool:
    """Persist one switch. Returns False when the name may not be switched off."""
    name = (name or "").strip()
    if not name:
        return False
    current = state()
    names = set(current["disabled"])
    if enabled:
        names.discard(name)
    else:
        if name in ALWAYS_ON:
            return False
        names.add(name)
    _write({**current, "disabled": sorted(names)})
    return True


def tool_names() -> list[str]:
    """Every capability the registry can offer right now."""
    from core.tools.registry import get_all_tool_schemas

    out: list[str] = []
    for schema in get_all_tool_schemas():
        function = schema.get("function") or {}
        name = str(function.get("name") or "")
        if name:
            out.append(name)
    return sorted(set(out))


def filter_schemas(schemas: list[dict]) -> list[dict]:
    """Drop the switched-off tools from an offer list. Fails open on a broken file."""
    try:
        off = disabled()
    except Exception:
        return schemas
    if not off:
        return schemas
    out = []
    for schema in schemas:
        name = str((schema.get("function") or {}).get("name") or "")
        if name and name in off:
            continue
        out.append(schema)
    return out


def subagent_allowlist() -> list[str]:
    """The stock read-only whitelist plus the user's additions, minus everything off."""
    off = disabled()
    merged = list(SUBAGENT_BASE_WHITELIST)
    for name in state()["subagent_extra"]:
        if name not in merged:
            merged.append(name)
    return [name for name in merged if name not in off]


def set_subagent_extra(names: list[str]) -> list[str]:
    """Replace the user's additions; unknown names are refused by the caller's check."""
    current = state()
    clean = sorted({str(name).strip() for name in names if str(name).strip()})
    _write({**current, "subagent_extra": clean})
    return clean


def kind_of(name: str) -> str:
    if name.startswith("mcp_"):
        return "mcp"
    if name in {"plugin_manager"}:
        return "plugin"
    if name == "skill_manage":
        return "skills"
    return "builtin"


def catalog() -> list[dict]:
    """One row per capability: what it is, whether it runs without asking, its state."""
    from core.tools.approval_rules import SAFE_TOOLS
    from core.tools.registry import get_all_tool_schemas

    off = disabled()
    rows = []
    seen: set[str] = set()
    for schema in get_all_tool_schemas():
        function = schema.get("function") or {}
        name = str(function.get("name") or "")
        if not name or name in seen:
            continue
        seen.add(name)
        rows.append(
            {
                "name": name,
                "description": str(function.get("description") or ""),
                "kind": kind_of(name),
                "safe": name in SAFE_TOOLS,
                "enabled": name not in off,
                "locked": name in ALWAYS_ON,
            }
        )
    rows.sort(key=lambda row: row["name"])
    return rows
