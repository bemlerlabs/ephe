'''server/routes/audit.py – R23: Read-only Audit-Log-Inspektion.'''
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Query

from core.audit_log import AUDIT_LOG_FILE, tail
from server.refusals import Refused

router = APIRouter(tags=["Audit"])


def count_matching(kind: str = "") -> int | None:
    """That many entries of the kind really lie in the log.

    N1 (proof chain): the surface shows one page of 80 lines and has to be able
    to say how many counterparts stand behind it — otherwise a slice
    through ten thousand entries reads like the whole log. The same read rule as
    `tail`: empty and broken lines are not entries.

    None when the file cannot be read — "I don't know" is not turned here
    into 0 (and thereby into "the log is empty").
    """
    try:
        if not AUDIT_LOG_FILE.exists():
            return 0
        total = 0
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
                total += 1
        return total
    except Exception:
        return None


@router.get("/audit")
async def get_audit(limit: int = 100, kind: str = "") -> dict:
    """Append-only audit log (newest first) — time, kind, tool, args_hash,
    redacted arguments, approval decision, exit status, duration.

    `total_matching` counts the matching total in the log; the surface puts
    the actually delivered page against it ("80 of N").

    If the file exists but is not readable, the route answers with 500 instead of
    an empty list: `tail` swallows read errors, and for a proof log
    "cannot read" is not the same as "is empty"."""
    total = count_matching(kind)
    if total is None:
        raise Refused("audit_log_unreadable")
    return {
        "entries": tail(limit=limit, kind=kind),
        "total_limit": min(max(int(limit), 1), 500),
        "total_matching": total,
    }
