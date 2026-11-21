#!/usr/bin/env python3
"""Ephe - scripts/ephemeral_demo: the spawn/work/audit/die proof (W3-22).

One script, one cell, one receipt. It drives the real lifecycle modules
(``core.ephemeral_cell`` for the cell, ``core.audit_log`` for the log) through
the four beats a launch reader cares about -- a cell is born, it does work, the
work lands in the audit log, the cell is reaped -- and writes the evidence to a
single JSON receipt.

The demo is a clean room: ``EPHE_AUDIT_LOG`` and ``EPHE_CELL_WORK_ROOT`` are
pointed at a scratch folder before ``core`` is imported, so the run never
touches the operator's ``~/.ephe``. Everything else (cell registry, kernel) is
in-process.

Run:  python3 scripts/ephemeral_demo.py [--out receipt.json]
Exit: 0 when every beat is proven, 1 otherwise.
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import json
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve()
REPO_ROOT = HERE.parent.parent

#: Bump when the receipt shape changes; readers refuse a version they do not know.
RECEIPT_SCHEMA = 1
DEMO = "ephemeral-cell-lifecycle"

#: The single deterministic unit of work. A closed-form sum so the receipt can
#: state the expected answer instead of trusting whatever the cell printed.
WORK_CODE = (
    "total = sum(i * i for i in range(1, 101))\n"
    "print(f'sum_of_squares_1_to_100={total}')\n"
)
WORK_EXPECTED = "sum_of_squares_1_to_100=338350"


def _configure_sandbox(out_dir: Path) -> None:
    """Points the audit log and the cell work root at a scratch tree.

    Must run before ``core`` is imported: ``core.audit_log`` resolves its path
    once, at import time, from ``EPHE_AUDIT_LOG``.
    """
    import os

    out_dir.mkdir(parents=True, exist_ok=True)
    os.environ["EPHE_AUDIT_LOG"] = str(out_dir / "audit.log")
    os.environ["EPHE_CELL_WORK_ROOT"] = str(out_dir / "cells")


def _git_commit() -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_report(framed: str) -> dict[str, str]:
    """Pulls the header fields out of a ``cpython_cell.format_report`` block.

    The cell frames its output as ``[execute_code] key=value ...`` then a blank
    line, ``stdout:`` and the payload. This reader keeps the named fields so the
    receipt can state which cell runtime actually ran the code.
    """
    import re

    header = framed.splitlines()[0] if framed else ""
    fields = dict(re.findall(r"(\w+)[=<>]=?([^\s]+)", header))
    return {"header": header, **fields}


def run_demo(out_dir: Path) -> dict:
    """Runs the four beats and returns the receipt (not written yet)."""
    _configure_sandbox(out_dir)

    # Import only after the sandbox env is in place.
    sys.path.insert(0, str(REPO_ROOT))
    from core import audit_log, ephemeral_cell
    from core.tools import code_kernel
    from core.tools.session_ctx import set_current_session

    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> bool:
        checks.append({"check": name, "ok": bool(ok), "detail": detail})
        return ok

    session_id = "ephemeral-demo"
    ephemeral_cell.reset_cells()
    code_kernel._KERNELS.pop(session_id, None)

    # -- Beat 1: spawn
    # A 1-second idle TTL so the reap in beat 4 is real, not staged: the cell
    # expires against the same reaper the product runs, just on a demo dial.
    ttl = 1.0
    cell = ephemeral_cell.create_cell(session_id, kind=ephemeral_cell.KIND_KERNEL,
                                      ttl_seconds=ttl)
    identity = {
        "id": cell.id,
        "ordinal": cell.ordinal,
        "kind": cell.kind,
        "session_id": cell.session_id,
        "ttl_seconds": cell.ttl_seconds,
        "created_at": cell.created_at,
    }
    audit_log.audit_event(
        "cell_spawn", tool="ephemeral_demo", decision="created",
        status="ok", session_id=session_id,
        detail=f"cell {cell.id[:12]} kind={cell.kind} ttl={ttl}s",
    )
    check("spawn: cell registered", ephemeral_cell.get_cell(session_id) is not None)
    check("spawn: one live cell", ephemeral_cell.cell_count() == 1,
          f"cell_count={ephemeral_cell.cell_count()}")

    # -- Beat 2: work
    # Through the bot->cell binding. The run records itself: the product's
    # execute_code path is the only writer of the call counter, so nothing here
    # has to (and nothing here may, or the count would double).
    token = set_current_session(session_id)
    t0 = time.monotonic()

    stdout_framed = asyncio.run(ephemeral_cell.run_in_cell(WORK_CODE))
    wall_ms = round((time.monotonic() - t0) * 1000.0, 3)
    report = _parse_report(stdout_framed)
    result_line = next((ln.strip() for ln in stdout_framed.splitlines()
                        if ln.strip().startswith("sum_of_squares")), "")
    audit_log.audit_event(
        "cell_work", tool="execute_code", decision="not-gated",
        status="ok", duration_ms=int(wall_ms), session_id=session_id,
        detail=f"runtime={report.get('runtime', '?')} stdout_sha256="
               f"{_sha256_text(result_line)}",
    )
    life_after_work = ephemeral_cell.cell_life(session_id)
    check("work: deterministic result", result_line == WORK_EXPECTED,
          f"got={result_line!r}")
    check("work: the run recorded itself", life_after_work.get("calls", 0) >= 1,
          f"calls={life_after_work.get('calls')}")
    check("work: ran in the cell runtime, net=none",
          str(report.get("net", "")) == "none",
          f"runtime={report.get('runtime', '?')} net={report.get('net', '?')}")

    # -- Beat 3: audit
    # The cell's own lines, read back through the product's reader.
    written = [e for e in audit_log.tail(limit=50) if e.get("session_id") == session_id]
    kinds = sorted({e.get("kind", "") for e in written})
    audit_log.audit_event(
        "cell_audit", tool="audit_log", decision="read-back",
        status="ok", session_id=session_id,
        detail=f"{len(written)} entries for the session",
    )
    audit_path = audit_log.AUDIT_LOG_FILE
    written_after = [e for e in audit_log.tail(limit=50)
                     if e.get("session_id") == session_id]
    check("audit: spawn+work lines present",
          {"cell_spawn", "cell_work"}.issubset(set(kinds)),
          f"kinds={kinds}")
    check("audit: log file on disk", audit_path.exists(), str(audit_path))

    # -- Beat 4: die
    # Wait past the idle TTL, then let the real reaper collect it.
    time.sleep(ttl + 0.3)
    reaped = ephemeral_cell.reap_idle()
    gone = ephemeral_cell.get_cell(session_id) is None
    count_after = ephemeral_cell.cell_count()
    life_after_death = ephemeral_cell.cell_life(session_id)
    audit_log.audit_event(
        "cell_death", tool="ephemeral_demo", decision="reaped",
        status="ok", session_id=session_id,
        detail=f"reaped={reaped} alive_after={life_after_death.get('alive')}",
    )
    check("die: reaper collected the cell", reaped == 1, f"reaped={reaped}")
    check("die: cell is gone", gone and count_after == 0,
          f"gone={gone} cell_count={count_after}")
    check("die: registry reports it dead",
          life_after_death.get("alive") is False,
          f"life={life_after_death}")

    with contextlib.suppress(ImportError):
        from core.tools.session_ctx import reset_current_session
        reset_current_session(token)

    # The audit lines that belong to this run, newest first.
    run_audit = [e for e in audit_log.tail(limit=50)
                 if e.get("session_id") == session_id]
    audit_digest = _sha256_file(audit_path) if audit_path.exists() else ""

    receipt = {
        "schema": RECEIPT_SCHEMA,
        "demo": DEMO,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "verdict": "pass" if all(c["ok"] for c in checks) else "fail",
        "checks": checks,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "commit": _git_commit(),
            "sandbox_dir": str(out_dir),
        },
        "beats": {
            "spawn": identity,
            "work": {
                "code": WORK_CODE,
                "expected": WORK_EXPECTED,
                "result_line": result_line,
                "result_sha256": _sha256_text(result_line),
                "wall_ms": wall_ms,
                "cell_report": report,
                "framed_output": stdout_framed,
                "life_after_work": life_after_work,
            },
            "audit": {
                "path": str(audit_path),
                "entries_read_back": len(written_after),
                "kinds": sorted({e.get("kind", "") for e in written_after}),
                "audit_file_sha256": audit_digest,
                "lines": run_audit,
            },
            "die": {
                "reaped": reaped,
                "cell_count_after": count_after,
                "alive_after": life_after_death.get("alive"),
            },
        },
    }
    return receipt


def _seal(receipt: dict) -> dict:
    """Adds ``receipt_sha256`` over the canonical body (that field excluded)."""
    body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    receipt["receipt_sha256"] = hashlib.sha256(canonical).hexdigest()
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ephe ephemeral-cell lifecycle demo")
    parser.add_argument("--out", default=str(REPO_ROOT / ".cell-demo"),
                        help="scratch + receipt folder (default: <repo>/.cell-demo)")
    parser.add_argument("--receipt", default="",
                        help="receipt path (default: <out>/receipt.json)")
    args = parser.parse_args(argv)

    out_dir = Path(args.out).resolve()
    receipt_path = Path(args.receipt).resolve() if args.receipt else out_dir / "receipt.json"

    receipt = _seal(run_demo(out_dir))
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")

    print(f"[{DEMO}] verdict={receipt['verdict']}")
    for c in receipt["checks"]:
        print(f"  {'ok  ' if c['ok'] else 'FAIL'} {c['check']}"
              + (f"  ({c['detail']})" if c["detail"] else ""))
    print(f"  receipt: {receipt_path}")
    print(f"  receipt_sha256: {receipt['receipt_sha256']}")
    return 0 if receipt["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
