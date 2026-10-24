"""Validation and normalization for local agent records.

One JSON shape is shared by the editor, the runtime loader and the API. The
normalizer is the single place that decides what an agent may declare; an
unknown tool, an empty tool set or an unknown provider fails closed here.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from core import agent_profiles

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
NAME_MAX = 80
DESCRIPTION_MAX = 500
INSTRUCTIONS_MAX = 32000
TURNS_MIN = 1
TURNS_MAX = 24
TURNS_DEFAULT = 8
APPROVALS = ("inherit", "allow", "ask", "block")
TIERS = ("auto", "fast", "balanced", "deep")
AVATAR_PATTERNS = ("orbit", "grid", "drop", "leaf")
PROVIDERS = ("local_ollama", "custom_ollama", "openai_compatible")
BUILTIN_ID = "ephe"
BUILTIN_NAME = "Ephe"
EDITABLE_FIELDS = {
    "name", "description", "avatar", "instructions", "model", "tools",
    "permissions", "limits", "enabled", "archived",
}


class AgentError(ValueError):
    def __init__(self, code: str, detail: str, status: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status



def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _known_tools() -> set[str]:
    from core.tools.registry import TOOL_MAP

    return set(TOOL_MAP.keys())


def _str_list(raw: Any, *, field: str, limit: int = 64) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise AgentError("invalid_field", f"{field} must be a list")
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise AgentError("invalid_field", f"{field} holds a non-string entry")
        text = item.strip()
        if len(text) > 120:
            raise AgentError("invalid_field", f"{field} entry is too long")
        if text not in out:
            out.append(text)
        if len(out) > limit:
            raise AgentError("invalid_field", f"{field} holds too many entries")
    return out


def _tools(raw: Any) -> list[str]:
    tools = _str_list(raw, field="tools")
    if not tools:
        raise AgentError("invalid_tools", "an agent needs at least one tool")
    known = _known_tools()
    unknown = [tool for tool in tools if tool not in known]
    if unknown:
        raise AgentError(
            "invalid_tools", f"unknown tool(s): {', '.join(sorted(unknown))}"
        )
    return tools


def _model(raw: Any) -> dict[str, Any] | None:
    if raw in (None, "", {}):
        return None
    if isinstance(raw, str):
        value = raw.strip()
        return {"provider": None, "model": value, "tier": "auto"} if value else None
    if not isinstance(raw, dict):
        raise AgentError("invalid_model", "model must be an object, a string or null")
    provider = raw.get("provider")
    if provider in ("", None):
        provider = None
    elif provider not in PROVIDERS:
        raise AgentError("invalid_model", f"unknown provider: {provider}")
    model = raw.get("model")
    model = model.strip() if isinstance(model, str) else ""
    if not model:
        if provider is None:
            return None
        raise AgentError("invalid_model", "a provider entry needs a model id")
    tier = raw.get("tier") or "auto"
    if tier not in TIERS:
        raise AgentError("invalid_model", f"unknown tier: {tier}")
    return {"provider": provider, "model": model, "tier": tier}


def _permissions(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {"approval": "inherit", "rules": []}
    if not isinstance(raw, dict):
        raise AgentError("invalid_permissions", "permissions must be an object")
    approval = raw.get("approval") or "inherit"
    if approval not in APPROVALS:
        raise AgentError("invalid_permissions", f"unknown approval: {approval}")
    rules: list[dict[str, str]] = []
    known = _known_tools()
    for entry in raw.get("rules") or []:
        if not isinstance(entry, dict):
            raise AgentError("invalid_permissions", "a rule must be an object")
        tool = str(entry.get("tool") or "").strip()
        access = str(entry.get("access") or "").strip()
        if tool not in known:
            raise AgentError("invalid_permissions", f"unknown tool in rule: {tool}")
        if access not in APPROVALS[1:]:
            raise AgentError("invalid_permissions", f"unknown access: {access}")
        purpose = str(entry.get("purpose") or "").strip()[:200]
        rules.append({"tool": tool, "access": access, "purpose": purpose})
    return {"approval": approval, "rules": rules}


def _limits(raw: Any) -> dict[str, int]:
    data = raw if isinstance(raw, dict) else {}
    try:
        turns = int(data.get("max_turns", TURNS_DEFAULT))
    except (TypeError, ValueError):
        turns = TURNS_DEFAULT
    turns = max(TURNS_MIN, min(TURNS_MAX, turns))
    try:
        timeout = float(data.get("timeout", agent_profiles.TIMEOUT_DEFAULT_S))
    except (TypeError, ValueError):
        timeout = agent_profiles.TIMEOUT_DEFAULT_S
    timeout = max(
        agent_profiles.TIMEOUT_MIN_S, min(agent_profiles.TIMEOUT_MAX_S, timeout)
    )
    return {"max_turns": turns, "timeout": int(timeout)}


def _avatar(raw: Any, seed: str) -> dict[str, str]:
    data = raw if isinstance(raw, dict) else {}
    pattern = str(data.get("pattern") or "")
    return {
        "seed": str(data.get("seed") or seed)[:64],
        "pattern": pattern if pattern in AVATAR_PATTERNS else "orbit",
    }


def _name(raw: Any) -> str:
    name = str(raw or "").strip()
    if not name:
        raise AgentError("invalid_name", "name is required")
    if len(name) > NAME_MAX:
        raise AgentError("invalid_name", f"name is longer than {NAME_MAX} characters")
    if name.casefold() == BUILTIN_NAME.casefold():
        raise AgentError("reserved_name", "the default agent keeps its name", 409)
    return name


def _normalize(
    raw: dict[str, Any],
    *,
    agent_id: str,
    origin: str,
    created_at: str,
    updated_at: str | None = None,
) -> dict[str, Any]:
    name = _name(raw.get("name"))
    description = str(raw.get("description") or "").strip()
    if len(description) > DESCRIPTION_MAX:
        raise AgentError(
            "invalid_description",
            f"description is longer than {DESCRIPTION_MAX} characters",
        )
    instructions = str(raw.get("instructions") or "")
    if len(instructions) > INSTRUCTIONS_MAX:
        raise AgentError(
            "invalid_instructions",
            f"instructions are longer than {INSTRUCTIONS_MAX} characters",
        )
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise AgentError("invalid_field", "enabled must be a boolean")
    archived = raw.get("archived", False)
    if not isinstance(archived, bool):
        raise AgentError("invalid_field", "archived must be a boolean")
    return {
        "id": agent_id,
        "name": name,
        "description": description,
        "avatar": _avatar(raw.get("avatar"), name),
        "instructions": instructions,
        "model": _model(raw.get("model")),
        "tools": _tools(raw.get("tools")),
        "permissions": _permissions(raw.get("permissions")),
        "limits": _limits(raw.get("limits")),
        "origin": origin,
        "enabled": enabled,
        "archived": archived,
        "created_at": created_at,
        "updated_at": updated_at or now_iso(),
    }


def effective_tools(record: dict[str, Any]) -> list[str]:
    blocked = {
        rule["tool"]
        for rule in record.get("permissions", {}).get("rules", [])
        if rule.get("access") == "block"
    }
    return [tool for tool in record.get("tools", []) if tool not in blocked]


