"""Local agent profiles behind the Agent Center.

One agent is one JSON file under ``<config>/agents/<id>.json``, owner-only and
written atomically. The file is also what ``core.agent_profiles`` reads for
``spawn_agent``, so the editor and the runtime share one contract instead of a
second registry.

Validation lives in ``core.agent_schema``; the run ledger in ``core.agent_runs``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import tempfile
from pathlib import Path
from typing import Any

from core import agent_profiles, path_guard
from core.agent_runs import list_runs, record_run, run_agent
from core.agent_schema import (
    BUILTIN_ID,
    BUILTIN_NAME,
    EDITABLE_FIELDS,
    ID_RE,
    TURNS_DEFAULT,
    AgentError,
    _avatar,
    _name,
    _normalize,
    effective_tools,
    now_iso,
)

__all__ = [
    "AgentError",
    "agents_dir",
    "builtin_agent",
    "create_agent",
    "duplicate_agent",
    "effective_tools",
    "get_agent",
    "list_agents",
    "list_runs",
    "plugin_agents",
    "record_run",
    "run_agent",
    "set_archived",
    "update_agent",
    "write_json_private",
]


def agents_dir() -> Path:
    return agent_profiles.agents_root()


def _record_path(agent_id: str) -> Path:
    """A record file under the agents root: id-pattern checked and confined."""
    target = path_guard.child(agents_dir(), agent_id, pattern=ID_RE, suffix=".json")
    if target is None:
        raise AgentError("invalid_agent_id", f"invalid agent id: {agent_id}", 400)
    return target


def _etag(record: dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "etag"}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return "agent-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def write_json_private(path: Path, record: dict[str, Any]) -> None:
    """Atomic, owner-only JSON write shared by the agent and team stores."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".agent-", suffix=".tmp")
    try:
        os.chmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:56]
    return slug or "agent"


def _unique_id(name: str, taken: set[str]) -> str:
    base = _slug(name)
    if base not in taken and base != BUILTIN_ID:
        return base
    for n in range(2, 1000):
        candidate = f"{base}-{n}"
        if candidate not in taken and candidate != BUILTIN_ID:
            return candidate
    return f"{base}-{secrets.token_hex(3)}"


def _local_names(exclude: str = "") -> set[str]:
    names: set[str] = set()
    for path in sorted(agents_dir().glob("*.json")):
        if path.name == f"{exclude}.json":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("name"):
            names.add(str(data["name"]).casefold())
    return names


def _read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _local_records() -> tuple[list[dict[str, Any]], dict[str, str]]:
    records: list[dict[str, Any]] = []
    quarantined: dict[str, str] = {}
    for path in sorted(agents_dir().glob("*.json")):
        raw = _read(path)
        if raw is None:
            quarantined[path.name] = "unreadable json"
            continue
        try:
            record = _normalize(
                raw,
                agent_id=str(raw.get("id") or path.stem),
                origin="local",
                created_at=str(raw.get("created_at") or now_iso()),
                updated_at=str(raw.get("updated_at") or raw.get("created_at") or now_iso()),
            )
        except AgentError as exc:
            quarantined[path.name] = exc.detail
            continue
        if not ID_RE.match(record["id"]):
            quarantined[path.name] = "invalid id"
            continue
        records.append(record)
    return records, quarantined


def plugin_agents() -> list[dict[str, Any]]:
    """Read-only rows for agents bundled by active manifest plugins."""
    try:
        manifests = agent_profiles._manifest_agents()
        profiles, _ = agent_profiles.load_profiles(manifest_agents=manifests)
    except Exception:  # noqa: BLE001 — a broken plugin never hides the editor
        return []
    local_names = {r["name"].casefold() for r in _local_records()[0]}
    origin_by_name = {
        str(entry.get("name")): str(entry.get("plugin") or "")
        for entry in manifests
        if isinstance(entry, dict) and entry.get("name")
    }
    rows: list[dict[str, Any]] = []
    for name, profile in sorted(profiles.items()):
        if name.casefold() in local_names:
            continue
        plugin = origin_by_name.get(name)
        if not plugin:
            continue
        rows.append(
            {
                "id": f"plugin:{plugin}:{name}",
                "name": name,
                "description": profile["description"],
                "avatar": _avatar(None, name),
                "instructions": profile.get("instructions", ""),
                "model": (
                    {"provider": None, "model": profile["model"], "tier": "auto"}
                    if profile.get("model")
                    else None
                ),
                "tools": list(profile["tools"]),
                "permissions": {"approval": "inherit", "rules": []},
                "limits": {
                    "max_turns": profile.get("max_turns", TURNS_DEFAULT),
                    "timeout": int(profile["timeout"]),
                },
                "origin": f"plugin:{plugin}",
                "enabled": True,
                "archived": False,
                "created_at": "",
                "updated_at": "",
                "read_only": True,
                "etag": None,
            }
        )
    return rows


def builtin_agent() -> dict[str, Any]:
    from core.subagent import SUBAGENT_TIMEOUT, SUBAGENT_TOOL_WHITELIST

    return {
        "id": BUILTIN_ID,
        "name": BUILTIN_NAME,
        "description": "The default read-only helper. Always available.",
        "avatar": {"seed": BUILTIN_NAME, "pattern": "drop"},
        "instructions": "",
        "model": None,
        "tools": list(SUBAGENT_TOOL_WHITELIST),
        "permissions": {"approval": "inherit", "rules": []},
        "limits": {"max_turns": TURNS_DEFAULT, "timeout": int(SUBAGENT_TIMEOUT)},
        "origin": "ephe",
        "enabled": True,
        "archived": False,
        "created_at": "",
        "updated_at": "",
        "read_only": True,
        "etag": None,
    }


def list_agents() -> dict[str, Any]:
    local, quarantined = _local_records()
    for record in local:
        record["etag"] = _etag(record)
        record["read_only"] = False
    local.sort(key=lambda row: (row["archived"], row["name"].casefold()))
    return {
        "agents": [builtin_agent(), *local, *plugin_agents()],
        "quarantined": quarantined,
    }


def get_agent(agent_id: str) -> dict[str, Any] | None:
    if agent_id == BUILTIN_ID:
        return builtin_agent()
    target = path_guard.child(agents_dir(), agent_id, pattern=ID_RE, suffix=".json")
    if target is None:
        return None
    raw = _read(target)
    if raw is not None:
        try:
            record = _normalize(
                raw,
                agent_id=str(raw.get("id") or agent_id),
                origin="local",
                created_at=str(raw.get("created_at") or now_iso()),
                updated_at=str(raw.get("updated_at") or raw.get("created_at") or now_iso()),
            )
        except AgentError:
            return None
        record["etag"] = _etag(record)
        return record
    for row in plugin_agents():
        if row["id"] == agent_id:
            return row
    return None


def create_agent(payload: dict[str, Any]) -> dict[str, Any]:
    name = _name(payload.get("name"))
    if name.casefold() in _local_names():
        raise AgentError("duplicate_name", f"an agent named '{name}' already exists", 409)
    taken = {path.stem for path in agents_dir().glob("*.json")}
    agent_id = _unique_id(name, taken)
    record = _normalize(payload, agent_id=agent_id, origin="local", created_at=now_iso())
    write_json_private(_record_path(agent_id), record)
    record["etag"] = _etag(record)
    record["read_only"] = False
    return record


def update_agent(agent_id: str, payload: dict[str, Any], *, etag: str) -> dict[str, Any]:
    current = get_agent(agent_id)
    if current is None:
        raise AgentError("unknown_agent", f"unknown agent: {agent_id}", 404)
    if current.get("read_only"):
        raise AgentError("read_only", "plugin and default agents are read-only", 409)
    if not etag or etag != current["etag"]:
        raise AgentError("etag_conflict", "the agent changed since it was loaded", 412)
    merged = {
        **current,
        **{k: v for k, v in payload.items() if k in EDITABLE_FIELDS},
    }
    name = _name(merged.get("name"))
    if name.casefold() in _local_names(exclude=agent_id):
        raise AgentError("duplicate_name", f"an agent named '{name}' already exists", 409)
    record = _normalize(
        merged,
        agent_id=agent_id,
        origin="local",
        created_at=current.get("created_at") or now_iso(),
    )
    write_json_private(_record_path(agent_id), record)
    record["etag"] = _etag(record)
    record["read_only"] = False
    return record


def duplicate_agent(agent_id: str) -> dict[str, Any]:
    source = get_agent(agent_id)
    if source is None:
        raise AgentError("unknown_agent", f"unknown agent: {agent_id}", 404)
    base_name = str(source["name"])
    if source["id"] == BUILTIN_ID:
        base_name = BUILTIN_NAME
    taken = {path.stem for path in agents_dir().glob("*.json")}
    names = _local_names()
    name = f"{base_name} copy"
    counter = 2
    while name.casefold() in names:
        name = f"{base_name} copy {counter}"
        counter += 1
    agent_id_new = _unique_id(name, taken)
    payload = {
        key: source.get(key)
        for key in (
            "description", "avatar", "instructions", "model", "tools",
            "permissions", "limits",
        )
    }
    payload["name"] = name
    record = _normalize(
        payload, agent_id=agent_id_new, origin="local", created_at=now_iso()
    )
    write_json_private(_record_path(agent_id_new), record)
    record["etag"] = _etag(record)
    record["read_only"] = False
    return record


def set_archived(agent_id: str, archived: bool) -> dict[str, Any]:
    if not isinstance(archived, bool):
        raise AgentError("invalid_field", "archived must be a boolean")
    current = get_agent(agent_id)
    if current is None:
        raise AgentError("unknown_agent", f"unknown agent: {agent_id}", 404)
    if current.get("read_only"):
        raise AgentError("read_only", "plugin and default agents are read-only", 409)
    record = _normalize(
        {**current, "archived": archived},
        agent_id=agent_id,
        origin="local",
        created_at=current.get("created_at") or now_iso(),
    )
    write_json_private(_record_path(agent_id), record)
    record["etag"] = _etag(record)
    record["read_only"] = False
    return record

