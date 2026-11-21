"""The watchable run: which audit row a frame may stand beside, and the user's hold.

A frame is a picture of the page. The audit row is the proof that a step happened.
A picture published while this session has no browser ``tool_exec`` carries no row,
and the surface says so. The hold is the other half: pause, stop, and a takeover
the agent has to read before it acts on the page again.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass

_BROWSER_TOOLS = frozenset(
    {
        "browser_go",
        "browser_click",
        "browser_type",
        "browser_press",
        "browser_screenshot",
        "browser_scroll",
        "browser_evaluate",
        "browser_exec",
    }
)
_HOLD_ACTIONS = frozenset({"pause", "resume", "stop", "takeover", "handback"})
_ACT_KINDS = frozenset({"click", "type", "press"})
_KEYS = frozenset(
    {
        "Enter",
        "Tab",
        "Escape",
        "Backspace",
        "ArrowUp",
        "ArrowDown",
        "ArrowLeft",
        "ArrowRight",
    }
)
_TEXT_LIMIT = 500
_COORD_LIMIT = 8_192
_HOLD_BUDGET_S = 120.0
_EVIDENCE = "STEP_EVIDENCE:"

_lock = threading.Lock()
_rows: dict[str, dict] = {}


@dataclass
class _Hold:
    mode: str = "running"
    before: dict | None = None
    note: str = ""


_holds: dict[str, _Hold] = {}


def reset_run_view() -> None:
    """Drop every binding and hold. Tests call this so a note cannot leak."""
    with _lock:
        _rows.clear()
        _holds.clear()


def browser_session(name: str, arguments: dict | None) -> str | None:
    """The browser session a tool call watches, or None when the tool has no page."""
    if name not in _BROWSER_TOOLS:
        return None
    raw = arguments.get("session") if isinstance(arguments, dict) else None
    if raw is None:
        return "default"
    text = str(raw).strip()
    return text or "default"


def _evidence(detail: str) -> tuple[str, dict]:
    index = detail.find(_EVIDENCE)
    if index < 0:
        return "unproven", {}
    line = detail[index + len(_EVIDENCE) :].split("\n", 1)[0]
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return "unproven", {}
    if not isinstance(payload, dict):
        return "unproven", {}
    verdict = payload.get("verdict")
    if verdict not in ("observed", "unproven"):
        verdict = "unproven"
    raw = payload.get("delta")
    delta: dict[str, int] = {}
    if isinstance(raw, dict):
        for key, value in raw.items():
            if isinstance(value, bool) or not isinstance(value, int):
                continue
            delta[str(key)[:40]] = value
    return str(verdict), delta


def _remember(session: str, row: dict) -> None:
    kind = str(row.get("kind") or "")
    ts = str(row.get("ts") or "")
    if not kind or not ts:
        return
    verdict, delta = _evidence(str(row.get("detail") or ""))
    with _lock:
        _rows[session] = {
            "kind": kind,
            "ts": ts,
            "tool": str(row.get("tool") or ""),
            "verdict": verdict,
            "delta": delta,
        }


def stamp_browser_exec(name: str, arguments: dict | None, detail: str) -> None:
    """Copy the ``tool_exec`` row this call just wrote onto the session's frames.

    The row is read back from the log. A write that was dropped leaves the frame
    with no row, which is the unproven state.
    """
    session = browser_session(name, arguments)
    if session is None:
        return
    try:
        from core.audit_log import args_hash, tail

        wanted = args_hash(arguments) if isinstance(arguments, dict) else ""
        for row in tail(limit=12, kind="tool_exec"):
            if row.get("tool") != name:
                continue
            if wanted and row.get("args_hash") != wanted:
                continue
            _remember(session, row)
            return
    except Exception:
        return


def bind_user_hold(session: str, line: str) -> None:
    """Record the hand-back as its own ``tool_exec`` and bind the session to it."""
    try:
        from core.audit_log import audit_event, tail

        audit_event(
            "tool_exec",
            tool="user_hold",
            status="ok",
            decision="user",
            detail=(line or "")[:300],
        )
        for row in tail(limit=6, kind="tool_exec"):
            if row.get("tool") == "user_hold":
                _remember(session, row)
                return
    except Exception:
        return


def public_binding(session: str) -> dict | None:
    """The row a frame may carry. No arguments, because those can hold typed text."""
    with _lock:
        row = _rows.get(session)
        if row is None:
            return None
        return {
            "kind": row["kind"],
            "ts": row["ts"],
            "tool": row["tool"],
            "verdict": row["verdict"],
            "delta": dict(row["delta"]),
        }


def frame_audit(session: str) -> dict:
    """The audit field of one published frame. Null when the session has no row."""
    return {"audit": public_binding(session)}


def _hold(session: str) -> _Hold:
    return _holds.setdefault(session, _Hold())


def mode_of(session: str) -> str:
    with _lock:
        hold = _holds.get(session)
        return hold.mode if hold is not None else "running"


def pause(session: str) -> bool:
    with _lock:
        hold = _hold(session)
        if hold.mode != "running":
            return False
        hold.mode = "paused"
        return True


def resume(session: str) -> bool:
    with _lock:
        hold = _holds.get(session)
        if hold is None or hold.mode != "paused":
            return False
        hold.mode = "running"
        return True


def stop(session: str) -> None:
    with _lock:
        _hold(session).mode = "stopped"


def begin_takeover(session: str, before: dict | None) -> bool:
    with _lock:
        hold = _hold(session)
        if hold.mode not in ("running", "paused"):
            return False
        hold.mode = "takeover"
        hold.before = dict(before) if isinstance(before, dict) else None
        hold.note = ""
        return True


def before_of(session: str) -> dict | None:
    with _lock:
        hold = _holds.get(session)
        if hold is None or not isinstance(hold.before, dict):
            return None
        return dict(hold.before)


def finish_takeover(session: str, line: str) -> None:
    with _lock:
        hold = _hold(session)
        hold.mode = "running"
        hold.before = None
        hold.note = line


def accepts_user_act(session: str) -> bool:
    return mode_of(session) == "takeover"


def claim_reconciliation() -> str:
    """The hand-back note, once. The next tool result is this sentence."""
    with _lock:
        for hold in _holds.values():
            if hold.note:
                note = hold.note
                hold.note = ""
                return note
    return ""


async def gate_action(session: str) -> str | None:
    """None when the agent may act. A sentence when it must stop or reconcile.

    Pause and takeover wait, up to the budget. A hand-back leaves a note, and
    that note is the tool result: the action the model asked for does not run.
    """
    deadline = time.monotonic() + _HOLD_BUDGET_S
    while True:
        with _lock:
            hold = _holds.get(session)
            if hold is None or hold.mode == "running":
                if hold is None or not hold.note:
                    return None
                note = hold.note
                hold.note = ""
                return note
            if hold.mode == "stopped":
                hold.mode = "running"
                return "The user stopped this browser run."
        if time.monotonic() >= deadline:
            return "The user is still holding this page."
        await asyncio.sleep(0.05)


def parse_hold(body: object) -> str:
    if not isinstance(body, dict) or set(body) != {"action"}:
        raise ValueError("hold")
    action = body.get("action")
    if action not in _HOLD_ACTIONS:
        raise ValueError("hold")
    return str(action)


def parse_act(body: object) -> dict:
    if not isinstance(body, dict):
        raise ValueError("act")
    kind = body.get("kind")
    if kind == "click":
        if set(body) != {"kind", "x", "y"}:
            raise ValueError("act")
        x, y = body["x"], body["y"]
        if isinstance(x, bool) or isinstance(y, bool):
            raise ValueError("act")
        if not isinstance(x, int) or not isinstance(y, int):
            raise ValueError("act")
        if x < 0 or y < 0 or x > _COORD_LIMIT or y > _COORD_LIMIT:
            raise ValueError("act")
        return {"kind": "click", "x": x, "y": y}
    if kind == "type":
        if set(body) != {"kind", "text"}:
            raise ValueError("act")
        text = body.get("text")
        if not isinstance(text, str) or text == "" or len(text) > _TEXT_LIMIT:
            raise ValueError("act")
        return {"kind": "type", "text": text}
    if kind == "press":
        if set(body) != {"kind", "key"}:
            raise ValueError("act")
        key = body.get("key")
        if key not in _KEYS:
            raise ValueError("act")
        return {"kind": "press", "key": key}
    raise ValueError("act")
