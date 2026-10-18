"""P5: model trajectory — numbered steps per turn (panel trajectory tab).

    core/trajectory.py

One last-turn timeline per session, built from events of the SSE stream:
creation time per step (ms), type (SYSTEM/TOOL/SUBAGENT/USAGE/…), title,
token axis (IN/OUT) when usage was measured. Data source for
GET /api/trajectory?session=<id>. The in-process registry is the truth
during the service; the last snapshot (~/.ephe/trajectory.json) is lazy-
reloaded on first access — a restart does not clear the view.

Capture parameters stay tiny: one entry per event, entries per turn capped
at 60, titles at 160 characters. Text bodies (user prompt, thinking,
assistant answer, tool output) sit as a `text` field per step —
capped at MAX_TEXT_CHARS (P6: trajectory text contents like the reference
renderer model: USER-/Reasoning-/Output sections with real content).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

MAX_TURNS_PER_SESSION = 20
MAX_STEPS_PER_TURN = 60
MAX_TITLE_CHARS = 160
MAX_TEXT_CHARS = 4000
#: G7: how many injected facts a single turn may carry. The injection is already
#: bounded by `memory.inject_max_entries`; this is the second lock, so a turn that
#: assembled its prompt more than once cannot grow without a ceiling.
MAX_MEMORIES_PER_TURN = 50

_turns: dict[str, list[dict[str, Any]]] = {}   # sid -> turns (newest first)
_open: dict[str, dict[str, Any]] = {}          # sid -> current turn
_loaded = False


def _path() -> Path:
    base = os.environ.get("EPHE_CONFIG_DIR") or str(Path.home() / ".ephe")
    return Path(base) / "trajectory.json"


def _ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        raw = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(raw, dict):
        for sid, turns in raw.items():
            if isinstance(turns, list) and sid not in _turns:
                _turns[sid] = turns


def _persist() -> None:
    try:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(_turns, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def begin_turn(session_id: str, model: str = "", turn_id: str = "") -> None:
    """Turn start — clears the step list of the active turn (not the history)."""
    _ensure_loaded()
    sid = session_id or ""
    _open[sid] = {
        "sid": sid,
        "model": model,
        # A3 backwards: without this id the replay would be a list of steps
        # that nobody can assign to a request.
        "turn_id": turn_id,
        "steps": [],
        # G7: the facts this turn's prompt was built from, filled by
        # `record_memories` when the prompt is assembled.
        "memories": [],
        "t0": time.perf_counter(),
        "ts": time.time(),
    }


def record_memories(session_id: str, entries: list[dict[str, Any]]) -> None:
    """G7: note which stored facts this turn's prompt was built from.

    Called from the prompt assembly with the very rows ``get_injection`` lifted —
    the same query that wrote the block names them, so the run's record and the
    model's context cannot describe two different turns. A turn that assembled
    its prompt more than once (a reverified answer) shows the union: deduped by
    id, first-seen order kept. Unknown or empty ids are dropped rather than
    stored as a fact without a handle — a row nobody can correct is not provenance.

    Best-effort by design: a caller may run without a live turn (CLI, tests) and
    then this is a no-op, never an error.
    """
    turn = _open.get(session_id or "")
    if turn is None or not entries:
        return
    memories = turn.setdefault("memories", [])
    have = {str(e.get("id")) for e in memories}
    for e in entries:
        if not isinstance(e, dict):
            continue
        doc_id = str(e.get("id") or "")
        if not doc_id or doc_id in have:
            continue
        memories.append(
            {
                "id": doc_id,
                "text": str(e.get("text") or ""),
                "score": float(e.get("score") or 0.0),
                "source": str(e.get("source") or ""),
            }
        )
        have.add(doc_id)
    if len(memories) > MAX_MEMORIES_PER_TURN:
        del memories[MAX_MEMORIES_PER_TURN:]


def _title(event: dict) -> str:
    for key in ("cmd", "msg", "reason", "summary", "text", "message", "topic", "target"):
        val = event.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()[:MAX_TITLE_CHARS]
    if event.get("type") == "subagent_started":
        bits = [str(event.get("agent_id") or ""), str(event.get("role") or "")]
        return " · ".join(b for b in bits if b)[:MAX_TITLE_CHARS]
    return str(event.get("type", ""))[:MAX_TITLE_CHARS]


def _body_text(event: dict) -> str:
    """Body text of the event (P6: USER-/Reasoning-/Output contents), capped.

    `text` carries the synthetic user/thinking/assistant events and
    replace_text; `result`/`data` the tool results (tool_done/stdout).
    """
    for key in ("text", "result", "data"):
        val = event.get(key)
        if isinstance(val, str) and val.strip():
            return val[:MAX_TEXT_CHARS]
    return ""


def record(session_id: str, event: dict) -> None:
    """Append one non-chunk event of the SSE stream as a step."""
    sid = session_id or ""
    turn = _open.get(sid)
    if turn is None:
        return
    etype = str(event.get("type", ""))
    inc: dict[str, Any] | None = None
    if etype == "usage":
        u = event.get("usage") or {}
        inc = {
            "in": u.get("prompt_tokens"),
            "out": u.get("completion_tokens"),
            "model": u.get("model") or "",
        }
    title = _title(event)
    if not title or title == etype:
        # Tool events usually carry the name as 'name'/'tool' — that
        # makes a better title than the bare event type.
        label = str(event.get("name") or event.get("tool") or "").strip()
        if label:
            title = label
    step = {
        "n": len(turn["steps"]) + 1,
        "type": etype.upper(),
        "title": title,
        "ms": int((time.perf_counter() - turn["t0"]) * 1000),
        "state": str(event.get("status", "")),
    }
    if inc:
        step["usage"] = inc
    body = _body_text(event)
    if body:
        step["text"] = body
    turn["steps"].append(step)
    if len(turn["steps"]) > MAX_STEPS_PER_TURN:
        turn["steps"] = turn["steps"][-MAX_STEPS_PER_TURN:]


def end_turn(session_id: str) -> None:
    """Turn end — write the timeline into the history, persist."""
    _ensure_loaded()
    sid = session_id or ""
    turn = _open.pop(sid, None)
    if turn is None:
        return
    turn.pop("t0", None)
    entry = {
        "sid": sid,
        "turn_id": turn.get("turn_id", ""),
        "model": turn.get("model", ""),
        "ts": turn.get("ts"),
        "duration_ms": int((time.time() - (turn.get("ts") or time.time())) * 1000),
        "steps": turn.get("steps", []),
        # G7: the injected facts survive the turn — the reason a past answer
        # reads the way it does has to outlive the run that produced it.
        "memories": turn.get("memories", []),
    }
    _turns.setdefault(sid, [])
    _turns[sid] = [entry] + _turns[sid][: MAX_TURNS_PER_SESSION - 1]
    _persist()


def _with_ledger(turn: dict[str, Any]) -> dict[str, Any]:
    """The turn plus the run ledger's five-phase projection (None when no lines)."""
    out = dict(turn)
    try:
        from core.run.ledger import snapshot_if_present

        out["ledger"] = snapshot_if_present(str(turn.get("turn_id") or ""))
    except Exception:
        out["ledger"] = None
    return out


def get_turns(session_id: str) -> list[dict[str, Any]]:
    """The last turns of a session (newest first)."""
    _ensure_loaded()
    sid = session_id or ""
    history = _turns.get(sid, [])
    live = _open.get(sid)
    if live and live.get("steps"):
        return [_with_ledger({
            "sid": sid,
            "turn_id": live.get("turn_id", ""),
            "model": live.get("model", ""),
            "ts": live.get("ts"),
            "duration_ms": int((time.perf_counter() - live["t0"]) * 1000) if "t0" in live else None,
            "steps": live["steps"],
            "memories": live.get("memories", []),
        })] + history
    return [_with_ledger(turn) for turn in history]


def reset_for_test() -> None:
    global _loaded
    _turns.clear()
    _open.clear()
    _loaded = False
