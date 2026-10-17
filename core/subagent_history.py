"""P4-D: Persistent subagent history with REST read access.

    core/subagent_history.py

One record per agent_id, filled by ``Subagent.run()`` (begin → tool_call* →
finish): timings (total + per tool), the report and a compact transcript. The
REST layer (GET /api/subagents, GET /api/subagents/<id>) reads exactly this
history — the frontend detail tab hangs on it.

Lifecycle: the in-process registry (dict) is the truth source while the service
runs; the last snapshot (~/.ephe/subagent_history.json) is reloaded on first
access so the tab is not empty after a restart. Writing the file is fail-safe —
a broken snapshot path never blocks the run. No stdout, no async: pure data
storage.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

#: How many records survive a restart (file truncation).
MAX_RECORDS = 50
#: Content sizes in the snapshot (line lengths of the detail view).
MAX_REPORT_CHARS = 4000
MAX_TRANSCRIPT_ITEMS = 20
MAX_TRANSCRIPT_CHARS = 400

#: Visibility wave: every helper run carries its own chat session. The id is
#: the key under which the surface (sidebar branch, chat, way back) and the
#: ledger mean the same run — so it may never be empty.
HELPER_SESSION_PREFIX = "helper-"


def chat_session_id_for(agent_id: str, run_tag: str = "") -> str:
    """Helper session id: with a run tag unique per run, without one
    derived deterministically from the agent_id (older snapshot rows)."""
    return f"{HELPER_SESSION_PREFIX}{run_tag or agent_id}"


_mem: dict[str, dict[str, Any]] = {}
_loaded = False


def _path() -> Path:
    base = os.environ.get("EPHE_CONFIG_DIR") or str(Path.home() / ".ephe")
    return Path(base) / "subagent_history.json"


def _ensure_loaded() -> None:
    """Merge the one-time file snapshot into the in-process registry."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if not isinstance(raw, list):
        return
    for rec in raw:
        if isinstance(rec, dict) and isinstance(rec.get("agent_id"), str):
            # Legacy of older snapshots: the helper session id is missing because
            # it did not exist yet. Without it the surface is left guessing,
            # so it is filled in once here, deterministically.
            rec.setdefault("chat_session_id", chat_session_id_for(rec["agent_id"]))
            rec.setdefault("parent_session", "")
            _mem.setdefault(rec["agent_id"], rec)


def _persist() -> None:
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(_sorted_records()[:MAX_RECORDS], ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        pass  # the snapshot is best-effort, the run continues


def _sorted_records() -> list[dict[str, Any]]:
    return sorted(_mem.values(), key=lambda r: r.get("started_ts") or 0.0, reverse=True)


def begin(
    agent_id: str,
    *,
    role: str,
    task: str,
    description: str,
    model: str,
    chat_session_id: str = "",
    parent_session: str = "",
) -> None:
    """Start of a run — creates the record (status='running').

    ``chat_session_id`` is the helper's own chat session, ``parent_session``
    the parent task it was started from (the way back). Both empty means
    derived from the agent_id and no known parent, respectively.
    """
    _ensure_loaded()
    _mem[agent_id] = {
        "agent_id": agent_id,
        "role": role,
        "description": description,
        "task": task,
        "model": model,
        "chat_session_id": chat_session_id or chat_session_id_for(agent_id),
        "parent_session": parent_session or "",
        "status": "running",
        "started_ts": time.time(),
        "finished_ts": None,
        "duration_ms": None,
        "report": "",
        "tool_calls": [],
        "transcript": [],
    }


def tool_call(agent_id: str, tool: str, args_preview: str, ms: int, gate: str = "") -> None:
    """One processed tool step together with its duration.

    ``gate`` is the sentence the approval gate answered with for this call
    (``core.tools.chat_gate.gate_delegated_tool``): the exemption a read-only tool
    carries, the user's yes, or the denial. An empty string means nothing asked
    the gate here — a direct caller, or a snapshot row from before the field.
    """
    _ensure_loaded()
    rec = _mem.get(agent_id)
    if rec is None:
        begin(agent_id, role="general-purpose", task="", description="", model="")
        rec = _mem[agent_id]
    rec.setdefault("tool_calls", []).append(
        {"tool": tool, "args_preview": args_preview[:160], "ms": int(ms), "gate": gate}
    )


def finish(
    agent_id: str,
    *,
    status: str,
    report: str,
    duration_ms: int,
    transcript: list[dict[str, str]],
) -> None:
    """Completion — status, total duration, report + transcript; persists."""
    _ensure_loaded()
    rec = _mem.get(agent_id)
    if rec is None:  # finish without begin (e.g. only events after a restart) — create it
        begin(agent_id, role="general-purpose", task="", description="", model="")
        rec = _mem[agent_id]
    rec.update(
        status=status,
        finished_ts=time.time(),
        duration_ms=int(duration_ms),
        report=report[:MAX_REPORT_CHARS],
        transcript=transcript[-MAX_TRANSCRIPT_ITEMS:],
    )
    _persist()


def get(agent_id: str) -> dict[str, Any] | None:
    """Full record for the detail tab; None for an unknown id."""
    _ensure_loaded()
    return _mem.get(agent_id)


def summaries(cursor: str | None = None, limit: int = 10) -> dict[str, Any]:
    """Compact list (newest first) for the tab overview.

    P6 B1 (ref-02): cursor pagination — `cursor` is the absolute
    position number as a string (the 1st page index is `limit`), the response
    carries `nextCursor` (null when exhausted). No cursor = first page.
    """
    _ensure_loaded()
    all_recs = _sorted_records()
    start = int(cursor) if cursor else 0
    page = all_recs[start : start + limit]
    out: list[dict[str, Any]] = []
    for rec in page:
        out.append(
            {
                "agent_id": rec.get("agent_id"),
                "role": rec.get("role", ""),
                "description": rec.get("description", ""),
                "task": str(rec.get("task", ""))[:120],
                "status": rec.get("status", "running"),
                "started_ts": rec.get("started_ts"),
                "duration_ms": rec.get("duration_ms"),
                "tool_count": len(rec.get("tool_calls") or []),
                # Visibility: the history row opens the same chat as a
                # live event — both paths need the same id for that.
                "chat_session_id": rec.get("chat_session_id")
                or chat_session_id_for(str(rec.get("agent_id") or "")),
                "parent_session": rec.get("parent_session", ""),
            }
        )
    next_start = start + limit
    return {
        "agents": out,
        "nextCursor": str(next_start) if next_start < len(all_recs) else None,
    }


def reset_for_test(path: Path | None = None) -> None:
    """Isolation for tests: clear the registry, optionally set the snapshot path."""
    global _loaded
    _mem.clear()
    _loaded = False
    if path is not None:
        os.environ["EPHE_CONFIG_DIR"] = str(path)
