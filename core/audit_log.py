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

import hashlib
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from core.redact import args_hash, args_summary, redact

logger = logging.getLogger(__name__)

def _default_audit_file() -> Path:
    base = os.environ.get("EPHE_CONFIG_DIR")
    return (Path(base) if base else Path.home() / ".ephe") / "audit.log"


AUDIT_LOG_FILE = Path(
    os.environ.get("EPHE_AUDIT_LOG", str(_default_audit_file()))
)

_lock = threading.Lock()

#: How many entries this process has dropped because the log is unwritable. The
#: first drop is logged (see `_note_drop`); the rest only move this counter.
_dropped = 0
_drop_warned = False
#: sha256 of the last line this process wrote (or found on disk), so each record
#: carries the digest of the one before it. A removed or edited line breaks the
#: chain at that point; a removed tail needs an external anchor to be noticed.
_last_line_sha: str | None = None
_last_line_path: Path | None = None
_TAIL_WINDOW = 1 << 20


def _previous_line_sha() -> str:
    global _last_line_sha, _last_line_path
    if _last_line_sha is not None and _last_line_path == AUDIT_LOG_FILE:
        return _last_line_sha
    try:
        with AUDIT_LOG_FILE.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            size = fh.tell()
            fh.seek(max(0, size - _TAIL_WINDOW))
            chunk = fh.read()
    except OSError:
        return ""
    last = chunk.rstrip(b"\n").split(b"\n")[-1]
    return hashlib.sha256(last).hexdigest() if last else ""


def verify_chain(path: Path | None = None) -> list[str]:
    """Problems in the hash chain, as `<line>: <reason>`; empty means intact.

    Detects an edited line, a removed middle line and a torn record. A removed
    last line is not detectable from the file alone.
    """
    target = Path(path) if path is not None else AUDIT_LOG_FILE
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        return [f"0: unreadable ({type(exc).__name__})"]
    problems: list[str] = []
    previous = ""
    chained = False
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            problems.append(f"{number}: not JSON (torn or truncated)")
            previous = hashlib.sha256(line.encode()).hexdigest()
            continue
        if not isinstance(entry, dict):
            problems.append(f"{number}: not an object")
            previous = hashlib.sha256(line.encode()).hexdigest()
            continue
        # Lines from before the chain carry no `prev` and promise nothing. Once
        # one chained line exists, a later line without the link is a finding:
        # otherwise stripping the field would be a way to edit the log.
        if "prev" in entry:
            chained = True
            if entry["prev"] != previous:
                problems.append(f"{number}: chain mismatch")
        elif chained:
            problems.append(f"{number}: missing chain link")
        previous = hashlib.sha256(line.encode()).hexdigest()
    return problems


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


def _append_private(path: Path, payload: str) -> None:
    """Append one already-redacted line to an owner-only file.

    Every field in `payload` passed through core.redact and the mode is asserted
    to 0600 by the caller; the query sees a write of a tainted string and cannot
    model the masker, so the sink carries a named suppression.
    """
    with path.open("a", encoding="utf-8") as fh:
        # codeql[py/clear-text-storage-sensitive-data]
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())


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
    actor: str = "",
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
        # Metadata is not exempt from the masker: a tool name can carry a server
        # URL, and an actor or id is a caller-supplied string.
        turn = turn_id or _current_turn()
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "kind": redact(kind)[:80],
            "tool": redact(tool)[:200],
            "args_hash": args_hash(args) if args is not None else "",
            "args": args_summary(args),
            "decision": redact(decision)[:80],
            "status": redact(status)[:120],
            "duration_ms": duration_ms,
            "detail": redact((detail or ""))[:300],
            # Taken under the lock below: two writers that read the same tail
            # would fork the chain.
            "prev": "",
            # R4/A3: the three axes of traceability. Only set when
            # known — a line without a turn is a line with an unknown turn, and
            # that should be visible in the line rather than left to guessing.
            **({"session_id": redact(session_id)[:200]} if session_id else {}),
            **({"turn_id": redact(turn)[:200]} if turn else {}),
            **({"call_id": redact(call_id)[:200]} if call_id else {}),
            **({"actor": redact(actor)[:200]} if actor else {}),
        }
        with _lock:
            global _last_line_sha, _last_line_path
            entry["prev"] = _previous_line_sha()
            line = json.dumps(entry, ensure_ascii=False)
            size = len(line.encode("utf-8"))
            if size > _MAX_LINE:
                # A sliced line is not JSON, so the readers skip it and the chain
                # breaks at a record that looks torn. The oversized entry says so
                # and stays parseable; the detail and the argument text are what go.
                entry["detail"] = f"[oversized entry: {size} bytes, detail dropped]"
                entry["args"] = ""
                line = json.dumps(entry, ensure_ascii=False)
            AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            payload = line + "\n"
            _append_private(AUDIT_LOG_FILE, payload)
            _last_line_path = AUDIT_LOG_FILE
            _last_line_sha = hashlib.sha256(payload.rstrip("\n").encode()).hexdigest()
            # Re-assert on every append: an older or manually widened log must not
            # stay world-readable just because it already existed.
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
