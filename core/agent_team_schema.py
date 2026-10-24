"""Validation for agent-team records.

One place decides what a team may declare: a leader outside the member list,
one to four members, a known orchestration and model policy, and bounded
budgets. Store and runner import these rules instead of restating them.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
NAME_MAX = 80
DESCRIPTION_MAX = 500
INSTRUCTIONS_MAX = 32000
MEMBERS_MAX = 4
ORCHESTRATIONS = ("leader", "parallel", "sequential", "review")
MODEL_POLICIES = ("inherit", "team", "per_member")
RUNS_KEEP = 50
TEAM_TIMEOUT_MIN_S = 30
TEAM_TIMEOUT_MAX_S = 1800
TEAM_TIMEOUT_DEFAULT_S = 300
ROUNDS_MIN = 1
ROUNDS_MAX = 12
ROUNDS_DEFAULT = 4
REPORT_MAX_CHARS = 8000

class TeamError(ValueError):
    def __init__(self, code: str, detail: str, status: int = 400) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status = status



def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def etag_for(record: dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "etag"}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)
    return "team-" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _name(raw: Any) -> str:
    name = str(raw or "").strip()
    if not name:
        raise TeamError("invalid_name", "a team needs a name")
    if len(name) > NAME_MAX:
        raise TeamError("invalid_name", f"name is longer than {NAME_MAX} characters")
    return name


def _text(raw: Any, field_name: str, limit: int) -> str:
    text = str(raw or "")
    if len(text) > limit:
        raise TeamError(
            "invalid_field", f"{field_name} is longer than {limit} characters"
        )
    return text


def _budget(raw: Any) -> dict[str, int]:
    data = raw if isinstance(raw, dict) else {}
    try:
        rounds = int(data.get("max_rounds", ROUNDS_DEFAULT))
    except (TypeError, ValueError):
        rounds = ROUNDS_DEFAULT
    try:
        wall = int(data.get("wall_timeout", TEAM_TIMEOUT_DEFAULT_S))
    except (TypeError, ValueError):
        wall = TEAM_TIMEOUT_DEFAULT_S
    return {
        "max_rounds": max(ROUNDS_MIN, min(ROUNDS_MAX, rounds)),
        "wall_timeout": max(TEAM_TIMEOUT_MIN_S, min(TEAM_TIMEOUT_MAX_S, wall)),
    }


def _shared_context(raw: Any) -> dict[str, bool]:
    data = raw if isinstance(raw, dict) else {}
    return {
        "session": bool(data.get("session", True)),
        "workspace": bool(data.get("workspace", True)),
        "artifacts": bool(data.get("artifacts", False)),
        "memory": bool(data.get("memory", True)),
    }


def _model(raw: Any) -> dict[str, Any] | None:
    if raw in (None, "", {}):
        return None
    if isinstance(raw, str):
        return {"provider": None, "model": raw.strip(), "tier": "auto"}
    if not isinstance(raw, dict):
        raise TeamError("invalid_model", "model must be an object, a string or null")
    model = str(raw.get("model") or "").strip()
    if not model:
        return None
    return {
        "provider": raw.get("provider") or None,
        "model": model,
        "tier": raw.get("tier") or "auto",
    }

