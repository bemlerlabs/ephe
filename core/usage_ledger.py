"""Ephe – core/usage_ledger: content-free token accounting (wave 3).

Working-backwards finding (cockpit comparison 2026-10): users expect a
cost/consumption monitor over 7/30 days. The Ephemeris deliberately does not
provide that — its contract is pure encounter counting (d/h/k/n, never WHAT). This
ledger is the sibling catalogue for quantities: ONLY numbers, never content.

Privacy contract (by construction): each row knows only
  d        day (ISO date)
  h        hour (0–23)
  in/out   measured or documented-estimated prompt/completion tokens
  cached   of those served from the prompt cache (0 when the provider reports nothing)
  est      true = at least one side is the calibrated estimate
No paths, no messages, no model names — privacy through
physics, not through promises. File permissions 0o600 (same model as
the session mirror).
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

_FIELDS = frozenset({"d", "h", "in", "out", "cached", "est"})


def default_store() -> Path:
    return Path.home() / ".ephe" / "usage.jsonl"


def record_usage(
    *,
    in_tokens: int,
    out_tokens: int,
    cached_tokens: int = 0,
    estimated: bool = False,
    now: datetime | None = None,
    store: Path | None = None,
) -> dict:
    """Write a turn into the accounting. Fail-open: a failed
    write must NEVER block the chat stream (the caller wraps it in try/except)."""
    ts = now or datetime.now()
    row = {
        "d": ts.date().isoformat(),
        "h": ts.hour,
        "in": int(in_tokens or 0),
        "out": int(out_tokens or 0),
        "cached": int(cached_tokens or 0),
        "est": bool(estimated),
    }
    target = store or default_store()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    return row


def summarize(
    days: int = 30,
    *,
    today: date | None = None,
    store: Path | None = None,
) -> dict:
    """Per-day aggregation of the last N days (descending), plus the total set.

    Corrupt rows are skipped (crash-safe) — half a log
    is better than none. The est share is reported separately so the
    UI can honestly mark "of which estimated"."""
    span = max(1, min(int(days), 365))
    end = today or date.today()
    start = end - timedelta(days=span - 1)
    by_day: dict[str, dict[str, int]] = {}
    totals = {"in": 0, "out": 0, "cached": 0, "est_turns": 0, "turns": 0}
    target = store or default_store()
    try:
        fh = target.open("r", encoding="utf-8")
    except OSError:
        fh = None
    if fh is not None:
        with fh:
            for line in fh:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                d = row.get("d")
                if not isinstance(d, str) or d < start.isoformat() or d > end.isoformat():
                    continue
                try:
                    i = int(row.get("in") or 0)
                    o = int(row.get("out") or 0)
                    c = int(row.get("cached") or 0)
                except (TypeError, ValueError):
                    continue
                bucket = by_day.setdefault(d, {"in": 0, "out": 0, "cached": 0, "est_turns": 0, "turns": 0})
                bucket["in"] += i
                bucket["out"] += o
                bucket["cached"] += c
                bucket["turns"] += 1
                if row.get("est"):
                    bucket["est_turns"] += 1
                    totals["est_turns"] += 1
                totals["in"] += i
                totals["out"] += o
                totals["cached"] += c
                totals["turns"] += 1
    days_list = []
    for offset in range(span):
        d = (end - timedelta(days=offset)).isoformat()
        b = by_day.get(d, {"in": 0, "out": 0, "cached": 0, "est_turns": 0, "turns": 0})
        days_list.append({"d": d, **b})
    return {"days": span, "totals": totals, "by_day": days_list}
