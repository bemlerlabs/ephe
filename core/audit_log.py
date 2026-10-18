"""Ephe – audit_log: append-only tool-/approval audit (R23).

A JSONL file (~/.ephe/audit.log, env EPHE_AUDIT_LOG): time, tool,
argument hash + redacted short form, approval decision, exit status, duration.
Append-only — no deleting/rotating from inside the product (inspection via
GET /api/audit). Every payload runs through core.redact (no secret in the log).

Two decision axes, because "why did nothing happen" has two answers:

- `decision` on `approval` events: `denied` (CLI/session policy) or
  `approved`/`session-approved` (chat layer).
- `decision` on `tool_exec` events: `blocked`, when the tool pronounces its own
  reach blockade (shell sandbox, fetch refusal, unverified guest) — the
  "no error, but no execution either" class of entry. `status`
  stays `ok` there; whoever reads only the status reports an execution that
  never happened. core.quality.result_decision classifies on the real marker
  prefixes, not on a heuristic.

One read rule, held by every reader of this log — `tail` here and the route's
`count_matching`. An entry is a JSON object on its own line. A blank line, a
line that does not parse, and a line whose JSON is a scalar or an array are all
the same thing to both readers: skipped by the listing and left out of the
count, so a delivered page and its "N of M" total can never disagree about what
they were reading. Contract pinned by `tests/test_audit_log_read_rule.py`.

Deliberately simple (no DB): the log is tamper-visible and tangible —
that is exactly the purpose of an audit log.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from core.redact import args_hash, args_summary, redact

logger = logging.getLogger(__name__)

AUDIT_LOG_FILE = Path(
    os.environ.get("EPHE_AUDIT_LOG", str(Path.home() / ".ephe" / "audit.log"))
)

_lock = threading.Lock()

#: How many entries this process has dropped because the log is unwritable. The
#: first drop is logged (see `_note_drop`); the rest only move this counter.
_dropped = 0
_drop_warned = False


def _current_turn() -> str:
    """The turn of the running job, when one is set.

    No caller has to pass it in: chat_with_tools sets it, and every audit line
    from the run carries it — otherwise the chain would break exactly where it
    is worth the most (at the tool calls themselves).
    """
    try:
        from core.artifact_workbench import artifact_turn

        return artifact_turn()
    except Exception:
        return ""
_MAX_LINE = 4096  # single-line cap (the detail is redacted + truncated)


def audit_event(
    kind: str,
    *,
    tool: str = "",
    args: dict | None = None,
    decision: str = "",
    status: str = "",
    duration_ms: int | None = None,
    detail: str = "",
    session_id: str = "",
    turn_id: str = "",
    call_id: str = "",
) -> None:
    """Appends an audit entry. Never raises, by contract.

    Fail-open: the audit log must never disturb the flow. A full disk (ENOSPC),
    a permission change or an obstacle standing at the path loses the entry, and
    the tool keeps running — blocking a user's own tool because the log is full
    would brick the product, which is worse than the missing line.

    The drop is not silent, though. The log is append-only proof, so "the log
    went quiet" must not read as "nothing happened" (repudiation): the first
    drop of a run is logged (`_note_drop`), later ones are counted. Contract
    pinned by `tests/test_wb15_audit_write_contract.py`.
    """
    try:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "kind": kind,
            "tool": tool,
            "args_hash": args_hash(args) if args is not None else "",
            "args": args_summary(args),
            "decision": decision,
            "status": status,
            "duration_ms": duration_ms,
            "detail": redact((detail or ""))[:300],
            # R4/A3: the three axes of traceability. Only set when
            # known — a line without a turn is a line with an unknown turn, and
            # that should be visible in the line rather than left to guessing.
            **({"session_id": session_id} if session_id else {}),
            **({"turn_id": turn_id or _current_turn()} if (turn_id or _current_turn()) else {}),
            **({"call_id": call_id} if call_id else {}),
        }
        line = json.dumps(entry, ensure_ascii=False)
        if len(line) > _MAX_LINE:
            line = line[: _MAX_LINE - 3] + "..."
        with _lock:
            AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            existed = AUDIT_LOG_FILE.exists()
            with AUDIT_LOG_FILE.open("a", encoding="utf-8") as fh:
                # Every field in `line` passed through core.redact (detail, args_summary)
                # and the file is created 0600 below; the query does not model the masker.
                # codeql[py/clear-text-storage-sensitive-data]
                fh.write(line + "\n")
            if not existed:
                # 0600 AFTER creating it (chmod on a missing file would be a no-op).
                # Deliberately on create only: an existing file keeps whatever mode
                # it was given, so this is not a re-assertion loop on every append.
                try:
                    AUDIT_LOG_FILE.chmod(0o600)
                except OSError:
                    pass
    except Exception as exc:  # noqa: BLE001 — fail-open by contract, see docstring
        _note_drop(exc)


def _note_drop(exc: BaseException) -> None:
    """Records a dropped entry: one warning per run, the rest counted.

    Repeated lines would let a full disk drown the operator on every tool call;
    a single line plus `_dropped` keeps the failure visible without the flood.
    """
    global _drop_warned, _dropped
    _dropped += 1
    if _drop_warned:
        return
    _drop_warned = True
    logger.warning(
        "audit entry dropped (%s: %s) — the audit log is full or unwritable; "
        "further drops this run are counted in core.audit_log._dropped",
        type(exc).__name__,
        exc,
    )


def tail(limit: int = 100, kind: str = "", turn_id: str = "") -> list[dict]:
    """Last entries (newest first). Lines that are not JSON objects are skipped.

    The read rule the count shares (see the module docstring): an entry is a JSON
    object on its own line. Blank, unparseable and valid-JSON-non-object lines are
    the same to both readers — never returned here, never counted by
    `count_matching`. Dropping the `isinstance` guard let a bare scalar or array
    through, and, worse, made `entry.get(...)` below raise on the first such line:
    the whole read then fell back to `[]` and the page lied about being empty.
    """
    limit = max(1, min(int(limit), 500))
    try:
        if not AUDIT_LOG_FILE.exists():
            return []
        out: list[dict] = []
        with AUDIT_LOG_FILE.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(entry, dict):
                    continue
                if kind and entry.get("kind") != kind:
                    continue
                if turn_id and entry.get("turn_id") != turn_id:
                    continue
                out.append(entry)
        return list(reversed(out[-limit:]))
    except Exception:
        return []


def clear() -> bool:
    """Only visible for tests/documentation — the product stays append-only."""
    return False
