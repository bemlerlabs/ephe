"""Local team records under ``<config>/agents/teams``.

Owner-only, atomic writes and ETags. A saved team survives a member that was
later archived; the runner refuses to start it until the member is available
again.
"""
from __future__ import annotations

import json
import re
import secrets
from pathlib import Path
from typing import Any

from core import agent_store
from core.agent_team_schema import (
    DESCRIPTION_MAX,
    ID_RE,
    INSTRUCTIONS_MAX,
    MEMBERS_MAX,
    MODEL_POLICIES,
    ORCHESTRATIONS,
    TeamError,
    _budget,
    _model,
    _name,
    _shared_context,
    _text,
    etag_for,
    now_iso,
)
from core.agent_team_templates import from_template


def teams_root() -> Path:
    return agent_store.agents_dir() / "teams"


def _validate_agents(leader_id: str, member_ids: list[str], *, strict: bool = True) -> None:
    if not isinstance(leader_id, str) or not leader_id.strip():
        raise TeamError("invalid_leader", "a team needs a leader")
    if not isinstance(member_ids, list) or not member_ids:
        raise TeamError("invalid_members", "a team needs one to four members")
    if len(member_ids) > MEMBERS_MAX:
        raise TeamError("invalid_members", f"at most {MEMBERS_MAX} members")
    if len(set(member_ids)) != len(member_ids):
        raise TeamError("invalid_members", "a member is listed twice")
    if leader_id in member_ids:
        raise TeamError("invalid_members", "the leader cannot also be a member")
    if not strict:
        return  # a saved team survives a member that was archived or removed
    for agent_id in [leader_id, *member_ids]:
        record = agent_store.get_agent(agent_id)
        if record is None:
            raise TeamError("unknown_agent", f"unknown agent: {agent_id}", 404)
        if record.get("archived"):
            raise TeamError(
                "agent_archived", f"agent '{record['name']}' is archived", 409
            )
        if not record.get("enabled", True):
            raise TeamError(
                "agent_disabled", f"agent '{record['name']}' is disabled", 409
            )


def _normalize(
    raw: dict[str, Any],
    *,
    team_id: str,
    created_at: str,
    updated_at: str | None = None,
    strict: bool = True,
) -> dict[str, Any]:
    name = _name(raw.get("name"))
    description = _text(raw.get("description"), "description", DESCRIPTION_MAX)
    instructions = _text(raw.get("instructions"), "instructions", INSTRUCTIONS_MAX)
    leader_id = str(raw.get("leader_id") or "").strip()
    member_ids = [str(m) for m in raw.get("member_ids") or []]
    _validate_agents(leader_id, member_ids, strict=strict)
    orchestration = str(raw.get("orchestration") or "parallel")
    if orchestration not in ORCHESTRATIONS:
        raise TeamError("invalid_orchestration", f"unknown mode: {orchestration}")
    policy = str(raw.get("model_policy") or "inherit")
    if policy not in MODEL_POLICIES:
        raise TeamError("invalid_model_policy", f"unknown policy: {policy}")
    model = _model(raw.get("model"))
    if policy == "team" and model is None:
        raise TeamError("invalid_model", "team policy needs a team model")
    archived = raw.get("archived", False)
    if not isinstance(archived, bool):
        raise TeamError("invalid_field", "archived must be a boolean")
    return {
        "id": team_id,
        "name": name,
        "description": description,
        "instructions": instructions,
        "leader_id": leader_id,
        "member_ids": member_ids,
        "orchestration": orchestration,
        "shared_context": _shared_context(raw.get("shared_context")),
        "model_policy": policy,
        "model": model,
        "budget": _budget(raw.get("budget")),
        "template": str(raw.get("template") or ""),
        "origin": "local",
        "archived": archived,
        "created_at": created_at,
        "updated_at": updated_at or now_iso(),
    }


def _read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _records() -> tuple[list[dict[str, Any]], dict[str, str]]:
    rows: list[dict[str, Any]] = []
    quarantined: dict[str, str] = {}
    for path in sorted(teams_root().glob("*.json")):
        raw = _read(path)
        if raw is None:
            quarantined[path.name] = "unreadable json"
            continue
        try:
            record = _normalize(
                raw,
                team_id=str(raw.get("id") or path.stem),
                created_at=str(raw.get("created_at") or now_iso()),
                updated_at=str(raw.get("updated_at") or raw.get("created_at") or now_iso()),
                strict=False,
            )
        except TeamError as exc:
            quarantined[path.name] = exc.detail
            continue
        if not ID_RE.match(record["id"]):
            quarantined[path.name] = "invalid id"
            continue
        rows.append(record)
    return rows, quarantined


def list_teams() -> dict[str, Any]:
    rows, quarantined = _records()
    for record in rows:
        record["etag"] = etag_for(record)
        record["read_only"] = False
    rows.sort(key=lambda row: (row["archived"], row["name"].casefold()))
    return {"teams": rows, "quarantined": quarantined}


def _unique_id(name: str, taken: set[str]) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:56] or "team"
    if base not in taken:
        return base
    for n in range(2, 1000):
        if f"{base}-{n}" not in taken:
            return f"{base}-{n}"
    return f"{base}-{secrets.token_hex(3)}"


def get_team(team_id: str) -> dict[str, Any] | None:
    if not ID_RE.match(team_id or ""):
        return None
    raw = _read(teams_root() / f"{team_id}.json")
    if raw is None:
        return None
    try:
        record = _normalize(
            raw,
            team_id=str(raw.get("id") or team_id),
            created_at=str(raw.get("created_at") or now_iso()),
            updated_at=str(raw.get("updated_at") or raw.get("created_at") or now_iso()),
            strict=False,
        )
    except TeamError:
        return None
    record["etag"] = etag_for(record)
    record["read_only"] = False
    return record


def create_team(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    template = str(data.get("template") or "")
    if template and not (data.get("leader_id") and data.get("member_ids")):
        expanded = from_template(template)
        expanded.update({k: v for k, v in data.items() if k != "template"})
        expanded["template"] = template
        data = expanded
    names = {row["name"].casefold() for row in _records()[0]}
    name = _name(data.get("name"))
    if name.casefold() in names:
        raise TeamError("duplicate_name", f"a team named '{name}' already exists", 409)
    taken = {path.stem for path in teams_root().glob("*.json")}
    team_id = _unique_id(name, taken)
    record = _normalize(data, team_id=team_id, created_at=now_iso())
    agent_store.write_json_private(teams_root() / f"{team_id}.json", record)
    record["etag"] = etag_for(record)
    record["read_only"] = False
    return record


def update_team(team_id: str, payload: dict[str, Any], *, etag: str) -> dict[str, Any]:
    current = get_team(team_id)
    if current is None:
        raise TeamError("unknown_team", f"unknown team: {team_id}", 404)
    if not etag or etag != current["etag"]:
        raise TeamError("etag_conflict", "the team changed since it was loaded", 412)
    editable = {
        "name", "description", "instructions", "leader_id", "member_ids",
        "orchestration", "shared_context", "model_policy", "model", "budget",
        "archived",
    }
    merged = {**current, **{k: v for k, v in payload.items() if k in editable}}
    name = _name(merged.get("name"))
    others = {
        row["name"].casefold() for row in _records()[0] if row["id"] != team_id
    }
    if name.casefold() in others:
        raise TeamError("duplicate_name", f"a team named '{name}' already exists", 409)
    record = _normalize(
        merged,
        team_id=team_id,
        created_at=current.get("created_at") or now_iso(),
    )
    agent_store.write_json_private(teams_root() / f"{team_id}.json", record)
    record["etag"] = etag_for(record)
    record["read_only"] = False
    return record


def set_archived(team_id: str, archived: bool) -> dict[str, Any]:
    if not isinstance(archived, bool):
        raise TeamError("invalid_field", "archived must be a boolean")
    current = get_team(team_id)
    if current is None:
        raise TeamError("unknown_team", f"unknown team: {team_id}", 404)
    record = _normalize(
        {**current, "archived": archived},
        team_id=team_id,
        created_at=current.get("created_at") or now_iso(),
    )
    agent_store.write_json_private(teams_root() / f"{team_id}.json", record)
    record["etag"] = etag_for(record)
    record["read_only"] = False
    return record


