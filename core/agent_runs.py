"""Content-free run ledger and one test/team run through ``Subagent``.

No prompt text and no report text is stored in the ledger: the record carries
identity, model source, status, duration, tool count and character counts. The
full report belongs to the surface that asked for the run.
"""
from __future__ import annotations

import json
import os
import secrets
import time
from pathlib import Path
from typing import Any

from core import agent_profiles
from core.agent_schema import effective_tools, now_iso

MAX_RUNS_READ = 50


def agents_dir() -> Path:
    return agent_profiles.agents_root()


def record_run(
    *,
    run_id: str,
    agent_id: str,
    agent_name: str,
    model: str | None,
    model_source: str,
    source: str,
    status: str,
    duration_ms: int,
    tool_calls: int,
    prompt_chars: int,
    report_chars: int,
) -> None:
    """Append one content-free run record. Never raises into a live turn."""
    entry = {
        "run_id": run_id,
        "agent_id": agent_id,
        "agent_name": agent_name,
        "model": model or "",
        "model_source": model_source,
        "source": source,
        "status": status,
        "duration_ms": int(duration_ms),
        "tool_calls": int(tool_calls),
        "prompt_chars": int(prompt_chars),
        "report_chars": int(report_chars),
        "finished_at": now_iso(),
    }
    path = agents_dir() / "runs.jsonl"
    try:
        agents_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
    except OSError:
        return


def list_runs(agent_id: str, limit: int = 20) -> list[dict[str, Any]]:
    limit = max(1, min(MAX_RUNS_READ, int(limit)))
    path = agents_dir() / "runs.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and entry.get("agent_id") == agent_id:
            out.append(entry)
            if len(out) >= limit:
                break
    return out


async def run_agent(record: dict[str, Any], prompt: str, *, source: str = "test") -> dict:
    """Run one prompt through the normal Subagent path and record the outcome."""
    from core.model_provider import get_active_provider
    from core.subagent import Subagent

    run_id = f"agent-{source}-{secrets.token_hex(4)}"
    pinned = (record.get("model") or {}).get("model")
    started = time.perf_counter()
    helper = Subagent(
        agent_id=run_id,
        role=str(record["name"]),
        task=prompt,
        model=pinned,
        instructions=str(record.get("instructions") or ""),
        allowed_tools=effective_tools(record),
        timeout=float(record["limits"]["timeout"]),
        max_iterations=int(record["limits"]["max_turns"]),
    )
    result = await helper.run()
    try:
        provider = get_active_provider().provider
    except Exception:  # noqa: BLE001 — the run itself already carries the model
        provider = ""
    record_run(
        run_id=run_id,
        agent_id=str(record["id"]),
        agent_name=str(record["name"]),
        model=pinned,
        model_source="agent" if pinned else "global",
        source=source,
        status=result.status,
        duration_ms=int((time.perf_counter() - started) * 1000),
        tool_calls=len(result.tool_calls),
        prompt_chars=len(prompt),
        report_chars=len(result.report),
    )
    return {
        "run_id": run_id,
        "agent_id": record["id"],
        "agent_name": record["name"],
        "provider": provider,
        "model": pinned or getattr(helper, "model", ""),
        "model_source": "agent" if pinned else "global",
        "status": result.status,
        "report": result.report,
        "tool_calls": result.tool_calls,
    }
