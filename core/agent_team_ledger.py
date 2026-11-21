"""Content-free team run ledger.

The per-run result (reports, member status) stays in the process and in the
surface that asked for it; this ledger answers "what ran, when, and how did it
end" without storing task or report text.
"""
from __future__ import annotations

import json
import os
from typing import Any

from core.agent_team_schema import now_iso
from core.agent_team_store import teams_root


def record_run(result: dict[str, Any]) -> None:
    entry = {
        "run_id": result["run_id"],
        "team_id": result["team_id"],
        "status": result["status"],
        "members": len(result.get("members") or []),
        "budget_hit": bool(result.get("budget_hit")),
        "duration_ms": int(result.get("duration_ms") or 0),
        "finished_at": now_iso(),
    }
    path = teams_root() / "runs.jsonl"
    try:
        teams_root().mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError:
        pass


def list_runs(team_id: str, limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(50, int(limit)))
    try:
        lines = (teams_root() / "runs.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("team_id") == team_id:
            out.append(entry)
            if len(out) >= limit:
                break
    return out


