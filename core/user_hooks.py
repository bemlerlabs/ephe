"""Ephe — User hooks (Extensions wave E5)
core/user_hooks.py

User-defined tool hooks from `~/.ephe/hooks.json`:

    {
      "pre_tool":  [{"command": "…", "match": "read_file|*", "priority": 100}],
      "post_tool": [{"command": "…"}],
      "session_start": [...], "turn_end": [...], "pre_compact": [...]
    }

Contract (pinned in tests/test_r65_agent_hooks.py):
- A hook COMMAND receives one JSON line on stdin:
    {"event": "pre_tool"|"post_tool"|…, "tool": <name>, "args": {...}, "result": <str>}
  and may print ONE JSON line on stdout:
    pre_tool:  {"args": {...}} (transform) or {"block": "reason"} (deny)
    post_tool: {"result": "..."}
- Fail-tolerant: a crashing / non-JSON / non-zero hook is ignored, the tool
  flow continues; every execution leaves an audit line.
- match filters per tool name (exact match or "*"); priority orders hooks
  (lower first, like the internal R40 hooks).
- Execution uses shlex-split argv (no shell), 10 s cap — config-file trust
  level, same as engine.json.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path
from typing import Any

from core.secret_broker import child_env

HOOKS_FILENAME = "hooks.json"
_HOOK_TIMEOUT_S = 10.0

_cache: dict[str, Any] = {"mtime": None, "hooks": {}}


def hooks_path() -> Path:
    base = os.environ.get("EPHE_CONFIG_DIR") or str(Path.home() / ".ephe")
    return Path(base) / HOOKS_FILENAME


def reset_cache() -> None:
    """Test seam + future PUT route: force a re-read of hooks.json."""
    _cache["mtime"] = None


#: The events the core actually fires. The docstring above lists more
#: (session_start / turn_end / pre_compact) — those only run through the generic
#: `fire_event`, which has no production caller. The view therefore marks them as
#: having no caller instead of selling them as active control (I6-4).
LIVE_EVENTS = ("pre_tool", "post_tool")


def hooks_enabled() -> bool:
    """I6-4: the main switch of the area (`hooks.enabled` in the settings register).

    Off = not a single child process gets started from hooks.json; the tool
    chain runs through unchanged. This is the only way to switch hooks off
    without deleting the file — and it acts at the source, not
    just in the surface."""
    from core.settings_schema import deep_bool

    return deep_bool("hooks.enabled")


def hooks_view() -> dict[str, Any]:
    """The read side of the Hooks area: the switch, the file, the hooks per event,
    plus the latest hook runs from the audit.

    Deliberately without a write path: a hook is a command that inherits
    process rights in this environment. Editing the file is a decision made at
    the device, not a click in the surface.
    """
    from core.audit_log import tail

    path = hooks_path()
    events = load_user_hooks()
    seen: set[str] = set(events) | set(LIVE_EVENTS)
    return {
        "enabled": hooks_enabled(),
        "path": str(path),
        "exists": path.exists(),
        "events": [
            {
                "key": key,
                "live": key in LIVE_EVENTS,
                "hooks": events.get(key, []),
            }
            for key in sorted(seen)
        ],
        "recent": [
            {
                "ts": entry.get("ts", ""),
                "tool": entry.get("tool", ""),
                "status": entry.get("status", ""),
                "detail": entry.get("detail", ""),
            }
            for entry in tail(limit=200, kind="hook")[:12]
        ],
    }


def load_user_hooks(path: Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Fail-soft read with mtime cache: {event: [{command, match, priority}]}."""
    target = Path(path) if path is not None else hooks_path()
    try:
        mtime = target.stat().st_mtime
    except OSError:
        _cache["mtime"], _cache["hooks"] = None, {}
        return {}
    if _cache["mtime"] == mtime and isinstance(_cache["hooks"], dict):
        return _cache["hooks"]
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw = {}
    out: dict[str, list[dict[str, Any]]] = {}
    if isinstance(raw, dict):
        for event, specs in raw.items():
            if not isinstance(specs, list):
                continue
            clean = []
            for spec in specs:
                if isinstance(spec, dict) and isinstance(spec.get("command"), str) and spec["command"].strip():
                    clean.append({
                        "command": spec["command"],
                        "match": str(spec.get("match", "*")),
                        "priority": int(spec.get("priority", 100)),
                    })
            out[str(event)] = sorted(clean, key=lambda s: s["priority"])
    _cache["mtime"], _cache["hooks"] = mtime, out
    return out


def _run_command(spec: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any] | None:
    """Run one hook command; returns its stdout JSON or None (any problem)."""
    try:
        proc = subprocess.run(  # noqa: S603 — argv list, no shell; user-config trust level
            shlex.split(spec["command"]),
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            capture_output=True,
            timeout=_HOOK_TIMEOUT_S,
            env=child_env(),
        )
        if proc.returncode != 0:
            return None
        out = json.loads(proc.stdout.decode("utf-8", errors="replace").strip().splitlines()[-1])
        return out if isinstance(out, dict) else None
    except Exception:  # noqa: BLE001 — hooks are fail-tolerant by contract
        return None


def _matches(spec: dict[str, Any], tool: str) -> bool:
    match = spec.get("match", "*")
    return match == "*" or match == tool


def _audit(kind: str, tool: str, status: str, detail: str) -> None:
    try:
        from core.audit_log import audit_event

        audit_event("hook", tool=tool, status=status, detail=detail)
    except Exception:
        pass


def pre_tool_gate(tool: str, args: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    """Run pre_tool hooks. Returns (args, block_reason|None) — args may be
    transformed by hooks; a block reason short-circuits the tool."""
    specs = load_user_hooks().get("pre_tool", []) if hooks_enabled() else []
    if not specs:
        return args, None
    transformed = args
    for spec in specs:
        if not _matches(spec, tool):
            continue
        out = _run_command(spec, {"event": "pre_tool", "tool": tool, "args": transformed})
        if out is None:
            _audit("hook", tool, "ignored", "pre_tool hook failed")
            continue
        if isinstance(out.get("block"), str) and out["block"]:
            _audit("hook", tool, "blocked", str(out["block"])[:120])
            return transformed, str(out["block"])
        if isinstance(out.get("args"), dict):
            transformed = out["args"]
            _audit("hook", tool, "ok", "pre_tool transform")
    return transformed, None


def post_tool_transform(tool: str, args: dict[str, Any], result: str) -> str:
    """Run post_tool hooks; the LAST successful transform wins."""
    specs = load_user_hooks().get("post_tool", []) if hooks_enabled() else []
    for spec in specs:
        if not _matches(spec, tool):
            continue
        out = _run_command(spec, {"event": "post_tool", "tool": tool, "args": args, "result": result})
        if out is None:
            _audit("hook", tool, "ignored", "post_tool hook failed")
            continue
        if isinstance(out.get("result"), str):
            result = out["result"]
            _audit("hook", tool, "ok", "post_tool transform")
    return result


def fire_event(event: str, payload: dict[str, Any]) -> None:
    """Fire an informational event (session_start / turn_end / pre_compact);
    output is audit-logged, the flow is never affected."""
    specs = load_user_hooks().get(event, []) if hooks_enabled() else []
    for spec in specs:
        out = _run_command(spec, {"event": event, **payload})
        _audit("hook", str(payload.get("tool", "")), "ok" if out is not None else "ignored", event)
