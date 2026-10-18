"""The append-only run ledger.

One JSONL file per run under the config root, one line per fact. The ledger is
content-free by default: a line may name a tool, a call id, an argument digest, a
duration, a status and a failure class, and it may never carry a prompt, an answer
or a tool's raw output. `SEC-1` redaction runs over every line regardless, so even a
field that slips through the whitelist cannot carry a key.

The five phases the surface reads are a projection of the same lines:

  * ``Now``     — what the run is doing (latest activity or tool start)
  * ``Waiting`` — an approval or an engine that has not answered
  * ``Changed`` — a file or artifact the run wrote
  * ``Result``  — the last tool result's status
  * ``Next``    — how the run ended, or what it will do

The envelope carries ``run_id``, ``request_id``, ``seq`` and a timestamp per line, so
a reader can order two processes' records and a kill -9 leaves every started call
visible: the start line is written before the tool runs, the result line after.
"""
from __future__ import annotations

import json
import os
import threading
import time
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from core.redact import args_hash, redact_deep

SCHEMA = 1
PHASES = ("now", "waiting", "changed", "result", "next")

#: The only payload keys a line may carry. A key outside this set is dropped, not
#: passed through: "content-free by default" is a whitelist, not a promise.
PAYLOAD_KEYS = frozenset(
    {
        "tool",
        "call_id",
        "args_hash",
        "duration_ms",
        "status",
        "reason_code",
        "phase",
        "finish_reason",
        "failure_class",
        "paths",
        "artifact_ids",
        "count",
        "tool_round",
        "budget_cap",
        "wait_seconds",
        "activity",
    }
)

_PHASE_FOR_EVENT = {
    "tool_start": "now",
    "tool_done": "result",
    "activity": "now",
    "sandbox_confirm": "waiting",
    "ask": "waiting",
    "artifact": "changed",
    "error": "result",
    "done": "next",
}


def _root() -> Path:
    return Path(os.environ.get("EPHE_CONFIG_DIR") or str(Path.home() / ".ephe")) / "run"


class RunLedger:
    def __init__(self, run_id: str, request_id: str = "") -> None:
        self.run_id = run_id
        self.request_id = request_id
        self.seq = 0
        self._lock = threading.Lock()
        self._path = _root() / f"{run_id}.jsonl"

    def append(self, phase: str, kind: str, **payload: Any) -> dict:
        if phase not in PHASES:
            phase = "now"
        allowed = {key: value for key, value in payload.items() if key in PAYLOAD_KEYS}
        with self._lock:
            self.seq += 1
            line = {
                "schema": SCHEMA,
                "run_id": self.run_id,
                "request_id": self.request_id,
                "seq": self.seq,
                "ts": round(time.time(), 3),
                "phase": phase,
                "kind": kind,
                **redact_deep(allowed),
            }
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                with self._path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(line, ensure_ascii=False) + "\n")
                if self.seq == 1:
                    try:
                        self._path.chmod(0o600)
                    except OSError:
                        pass
            except OSError:
                # The ledger must never take a run down; the drop is visible in the
                # sequence gap the caller can see in memory.
                pass
            return line

    def start(self, **payload: Any) -> dict:
        return self.append("now", "run_started", **payload)

    def finish(self, finish_reason: str, failure_class: str = "") -> dict:
        return self.append(
            "next",
            "run_finished",
            finish_reason=finish_reason,
            **({"failure_class": failure_class} if failure_class else {}),
        )


def _current() -> RunLedger | None:
    return _LEDGER.get()


_LEDGER: ContextVar[RunLedger | None] = ContextVar("ephe_run_ledger", default=None)


def start(run_id: str, request_id: str = "") -> RunLedger:
    ledger = RunLedger(run_id, request_id)
    _LEDGER.set(ledger)
    ledger.start()
    return ledger


def finish(finish_reason: str = "complete", failure_class: str = "") -> None:
    ledger = _current()
    if ledger is not None:
        ledger.finish(finish_reason, failure_class)


def record_event(event: dict) -> dict | None:
    """Records one SSE event as a ledger line, or None for content-bearing frames."""
    ledger = _current()
    if ledger is None or not isinstance(event, dict):
        return None
    kind = str(event.get("type") or "")
    phase = _PHASE_FOR_EVENT.get(kind)
    if phase is None:
        return None
    payload: dict[str, Any] = {}
    if kind == "tool_start":
        payload = {
            "tool": str(event.get("tool") or ""),
            "call_id": str(event.get("call_id") or ""),
            "args_hash": args_hash(event.get("args") if isinstance(event.get("args"), dict) else {}),
        }
    elif kind == "tool_done":
        payload = {
            "tool": str(event.get("tool") or ""),
            "call_id": str(event.get("call_id") or ""),
            "duration_ms": event.get("duration_ms"),
            "status": str(event.get("status") or ""),
            "reason_code": str(event.get("reason_code") or ""),
        }
    elif kind == "sandbox_confirm":
        payload = {"tool": str(event.get("tool") or ""), "status": "awaiting"}
    elif kind == "artifact":
        artifact = event.get("artifact") or {}
        payload = {
            "artifact_ids": [str(artifact.get("id") or "")][:20] if isinstance(artifact, dict) else [],
            "count": 1,
        }
    elif kind == "error":
        payload = {"status": "error", "reason_code": str(event.get("reason_code") or "")}
    elif kind == "done":
        payload = {"finish_reason": str(event.get("finish_reason") or "complete")}
    else:
        payload = {
            "status": str(event.get("status") or ""),
            "activity": str(event.get("cmd") or "")[:80],
        }
    return ledger.append(phase, kind, **payload)


def read_run(run_id: str) -> list[dict]:
    path = _root() / f"{run_id}.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict] = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def snapshot(run_id: str) -> dict:
    """The five-phase projection the surface reads.

    Every phase is present with a null body when the run never reached it, so a
    client renders the same shape for a new run and a finished one.
    """
    rows = read_run(run_id)
    now = waiting = changed = result = next_ = None
    for row in rows:
        phase = row.get("phase")
        if phase == "now":
            now = row
        elif phase == "waiting":
            waiting = row
        elif phase == "changed":
            changed = row
        elif phase == "result":
            result = row
        elif phase == "next":
            next_ = row
    return {
        "run_id": run_id,
        "seq": rows[-1].get("seq") if rows else 0,
        "phases": {
            "Now": now,
            "Waiting": waiting,
            "Changed": changed,
            "Result": result,
            "Next": next_,
        },
        "lines": len(rows),
    }


def snapshot_if_present(run_id: str) -> dict | None:
    """The projection for a run that has ledger lines, else None (no empty rows)."""
    if not run_id:
        return None
    try:
        if not (_root() / f"{run_id}.jsonl").exists():
            return None
    except OSError:
        return None
    return snapshot(run_id)


def active_run_ids() -> list[str]:
    try:
        return sorted(path.stem for path in _root().glob("*.jsonl"))
    except OSError:
        return []
