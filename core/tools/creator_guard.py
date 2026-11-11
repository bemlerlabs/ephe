"""The three Creator privileges: what a call asks for, where a grant lives, where a call stops.

Task #26 (the A2 decision, owner ruling 2026-11-08): Creator mode asks the user for
``code``, ``files`` and ``network``, and one granted permission is enough for the calls
that permission covers. A call whose permission the session never granted is refused at
the point where it would run — beside ``chat_gate.mode_denial``, which keeps the other
modes' promises the same way — and the tools behind a missing permission leave the offer
list, so the model is not invited to ask for a call that will be refused.

Two authorities answer the question "what does this name ask for", and both already
rule elsewhere in the tree: ``core.tools.registry.TOOL_MAP`` for a kernel name, and the
tool family a plugin manifest declares (``core.plugin_tools_contract.tool_claims``) for a
contributed one. Nothing here is a third name list that can drift from the dispatch it
describes; `tests/test_creator_guard.py` asserts the tables against both authorities on
every run, so a new kernel tool or a new family has to be ruled to land at all.

A grant lives in a backend file keyed by session id. A ContextVar would answer only one
process and only the current turn; browser storage would answer only one client. This
store is read by the route that shows the dialog, by the tool loop that enforces it, and
by a second process, and it loses a row only when the session itself is deleted
(``core.session_lifecycle.remove_sessions``), because that module states that pruning is
never a side effect of a write.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.engine_config import config_root
from core.tools.chat_gate import Denied, denial_message
from core.tools.creator_tools import CREATOR_TOOL_SCHEMAS
from core.tools.session_ctx import get_current_mode, get_current_session

#: The whole vocabulary the consent dialog can ask for. A fourth name would be a new
#: promise, so it is refused at the store rather than silently held.
PRIVILEGES = frozenset({"code", "files", "network"})

#: The mode this gate is a promise about. Every other mode is untouched: Creator added a
#: consent rule, it did not take a privilege away from Analyst, Architect or Operator.
CREATOR_MODE = "creator"

#: The file the grants live in, beside the other app-owned state in the config root.
STORE_FILENAME = "creator-consent.json"

#: What an MCP server name asks for. A remote tool runs whatever its server runs, so the
#: call is covered by the widest of the three permissions.
MCP_PRIVILEGE = "code"

#: The calls that build a plugin, read from the schemas that offer them. They live inside
#: Creator mode and nowhere else, which is the boundary task #26 owns on top of the
#: privilege rule.
CREATOR_TOOL_NAMES = frozenset(
    str(entry["function"]["name"]) for entry in CREATOR_TOOL_SCHEMAS
)

#: Ruling for every name the kernel dispatch map holds. The three groups are the three
#: answers: a permission, or nothing this gate is the authority for. A name missing here
#: is answered with the widest ask, and the totality test lets that state never ship.
KERNEL_PRIVILEGES: dict[str, str] = {
    # Runs something on a host or in a cell.
    "bash": "code",
    "execute_code": "code",
    "run_sandboxed_code": "code",
    "process_manage": "code",
    "create_video": "code",
    "start_workspace_dev_server": "code",
    "stop_workspace_dev_server": "code",
    "task_stop": "code",
    "install_plugin_bundle": "code",
    # Reads or writes files of the user's workspace.
    "read": "files",
    "edit": "files",
    "delete_file": "files",
    "discover_projects": "files",
    "query_codebase": "files",
    "create_plugin_scaffold": "files",
    "read_plugin_source": "files",
    "write_plugin_source": "files",
    "verify_plugin_bundle": "files",
    # The agent's own state, which the app keeps under ~/.ephe. The same reading
    # `approval_rules.CHAT_AUTO_RUN_TOOLS` already documents for memory and skill_manage.
    "todo_list": "",
    "manage_tasks": "",
    "skill_manage": "",
    "plugin_manager": "",
    # Reaches the open web for a question; every request still passes net_guard.
    "web_research": "network",
    # Reads or describes an index, or forwards to a call that is judged on its own name
    # one frame deeper (the ruling `chat_gate.READ_ONLY_MODE_TOOLS` makes for tool_call).
    "tool_search": "",
    "tool_describe": "",
    "tool_call": "",
    "spawn_agent": "",
    "agent_message": "",
    # Answers without touching the host at all.
    "ask_user": "",
    "get_datetime": "",
    "validate_json": "",
    "task_output": "",
    "read_transcript": "",
    "read_cell_journal": "",
    # Host capture and the pasteboard: governed by the approval dialog, whose rule this
    # gate deliberately does not replace (a grant here would auto-run a whole-screen read).
    "take_screenshot": "",
    "get_display_info": "",
    "clipboard_read": "",
    "clipboard_write": "",
}

#: Ruling for the family vocabulary in `core.plugin_manifest.KNOWN_TOOL_FAMILIES`, which
#: is what a contributed name is judged by. A family missing here cannot be declared by a
#: manifest either, so the two sets are pinned against each other in the same run.
FAMILY_PRIVILEGES: dict[str, str] = {
    "read": "files",
    "write": "files",
    "docs": "files",
    "shell": "code",
    "network": "network",
    "browser": "network",
    # `memory` writes only into the app's own files under ~/.ephe, the boundary the
    # approval rules already state. `vision` and `voice` are capture and synthesis, which
    # the approval dialog asks about; a Creator grant would answer for both modes at once.
    "memory": "",
    "vision": "",
    "voice": "",
}


class UnknownPrivilege(ValueError):
    """A grant asked for a permission outside the three the dialog states."""


class UnknownSession(ValueError):
    """A grant was keyed by something that cannot name a session file."""


def _store_path() -> Path:
    return config_root() / STORE_FILENAME


def _read_store() -> dict:
    try:
        data = json.loads(_store_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_store(data: dict) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    payload = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    tmp.write_text(payload, encoding="utf-8")
    # The same ceiling as the other app-owned state files: a grant is a permission, and
    # a group or world readable copy of it invites another local user to answer for it.
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def privileges_for(session_id: str) -> frozenset[str]:
    """The permissions one session holds. Unknown key, no file, no row: nothing."""
    row = _read_store().get(session_id)
    if not isinstance(row, dict):
        return frozenset()
    held = row.get("privileges")
    if not isinstance(held, (list, tuple, set)):
        return frozenset()
    return frozenset(str(value) for value in held) & PRIVILEGES


def set_privileges(session_id: str, privileges) -> frozenset[str]:
    """Replace what one session holds, and answer with the state that was written.

    The whole set is replaced because the dialog states the complete answer each time it
    is saved; an additive write would make "un-tick network" impossible to express.
    """
    from core.session_lifecycle import known_id

    if not known_id(session_id):
        raise UnknownSession(f"{session_id!r} cannot name a session")
    wanted = frozenset(str(value) for value in privileges)
    unknown = sorted(wanted - PRIVILEGES)
    if unknown:
        raise UnknownPrivilege(
            f"unknown privilege(s): {', '.join(unknown)} — this gate states "
            f"{', '.join(sorted(PRIVILEGES))}"
        )
    data = _read_store()
    data[session_id] = {
        "privileges": sorted(wanted),
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _write_store(data)
    return wanted


def forget_session(session_id: str) -> None:
    """Drop one session's row, from the delete path that already drops its file."""
    data = _read_store()
    if session_id not in data:
        return
    data.pop(session_id, None)
    _write_store(data)


_FAMILY_MAP: dict[str, str] | None = None
_FAMILY_MAP_KEY: str | None = None


def _family_map_key() -> str:
    """The roots the map was built from, so a moved profile retargets it.

    ``plugins_root()`` reads ``EPHE_CONFIG_DIR`` per call and a test moves it; a key of
    the override seam alone would keep answering with the portfolio of the previous root.
    """
    from core import plugin_manifest

    override = plugin_manifest.PLUGINS_ROOT_OVERRIDE
    return (
        f"{plugin_manifest.plugins_root()}|{plugin_manifest.BUILTIN_PLUGINS_ROOT}"
        f"|{'' if override is None else override}"
    )


def _family_map() -> dict[str, str]:
    """The contributed names the scanned portfolio declares, each with its family.

    First claim wins, in the order `scan_plugins` already hands out its rows, because a
    name two bundles claim is reported by `scan_tool_activations().conflicts` and hidden
    from every session by the plugin gate long before this map is asked about it.
    """
    global _FAMILY_MAP, _FAMILY_MAP_KEY
    key = _family_map_key()
    if _FAMILY_MAP is not None and _FAMILY_MAP_KEY == key:
        return _FAMILY_MAP
    from core import plugin_manifest
    from core.plugin_tools_contract import tool_claims

    rows: dict[str, str] = {}
    try:
        scanned = plugin_manifest.scan_plugins(None)
    except Exception:  # noqa: BLE001 - an unreadable portfolio declares no families
        return rows
    for entry in scanned:
        manifest = entry.get("manifest")
        if entry.get("error") or not isinstance(manifest, dict):
            continue
        for claim in tool_claims(manifest):
            if claim.family in plugin_manifest.KNOWN_TOOL_FAMILIES:
                rows.setdefault(claim.name, claim.family)
    _FAMILY_MAP = rows
    _FAMILY_MAP_KEY = key
    return rows


def invalidate_family_map() -> None:
    """A mount, an unmount or a reload retargets the name-to-family answer."""
    global _FAMILY_MAP, _FAMILY_MAP_KEY
    _FAMILY_MAP = None
    _FAMILY_MAP_KEY = None


def judge(name: str) -> tuple[str, str]:
    """The permission one tool name asks for, and the authority that answered.

    ``basis`` is part of the answer because a reader of a refusal has to be able to check
    it: ``kernel`` names the dispatch map, ``family`` names a manifest declaration, ``mcp``
    names the remote namespace, and ``unlisted`` means no authority here can dispatch the
    name at all, so nothing is asked for it.
    """
    if not name:
        return "", "unlisted"
    from core.tools.registry import TOOL_MAP

    if name in TOOL_MAP:
        return KERNEL_PRIVILEGES.get(name, "code"), "kernel"
    family = _family_map().get(name)
    if family is not None:
        return FAMILY_PRIVILEGES[family], "family"
    if name.startswith("mcp_"):
        from core.tools import mcp_client

        if name in mcp_client._MCP_TOOLS:
            return MCP_PRIVILEGE, "mcp"
    return "", "unlisted"


def is_creator_tool(name: str) -> bool:
    """Whether the name is one of the calls that build a plugin."""
    return name in CREATOR_TOOL_NAMES


def _active_session_privileges() -> frozenset[str]:
    return privileges_for(get_current_session())


def denial_for(name: str) -> Optional[Denied]:
    """The refusal for a call this gate stops, or None while it holds still.

    Only Creator mode is judged. A call that asks for nothing is never refused here, and
    an ask the session does not hold is refused before the handler is reached.
    """
    if get_current_mode() != CREATOR_MODE:
        return None
    privilege, _basis = judge(name)
    if not privilege:
        return None
    if privilege in _active_session_privileges():
        return None
    return denial_message(name, "creator_privilege_missing", privilege=privilege)


def _name_of(entry) -> str:
    """The offered name inside one schema envelope, or an empty string."""
    function = entry.get("function") if isinstance(entry, dict) else None
    return str((function or {}).get("name") or "")


def filter_offer(schemas: list[dict]) -> list[dict]:
    """The offer list after the Creator rule, applied to any schema array.

    The creator calls belong to Creator mode alone: offered anywhere else, they
    would be an invitation the mode's own notice contradicts. Inside the mode, a name the
    session holds no permission for is dropped, so the model is never asked to plan around
    a call the gate has already decided to refuse.
    """
    in_creator = get_current_mode() == CREATOR_MODE
    held = _active_session_privileges() if in_creator else frozenset()
    kept: list[dict] = []
    for entry in schemas:
        name = _name_of(entry)
        if is_creator_tool(name) and not in_creator:
            continue
        privilege, _basis = judge(name)
        if in_creator and privilege and privilege not in held:
            continue
        kept.append(entry)
    return kept


__all__ = [
    "CREATOR_MODE",
    "CREATOR_TOOL_NAMES",
    "FAMILY_PRIVILEGES",
    "KERNEL_PRIVILEGES",
    "MCP_PRIVILEGE",
    "PRIVILEGES",
    "STORE_FILENAME",
    "UnknownPrivilege",
    "UnknownSession",
    "denial_for",
    "filter_offer",
    "forget_session",
    "is_creator_tool",
    "invalidate_family_map",
    "judge",
    "privileges_for",
    "set_privileges",
]
