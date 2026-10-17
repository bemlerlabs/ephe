"""
◑ Ephe – server/routes/ephemeris.py – GET /api/ephemeris (S4 workbench parity)

Make the ephemerides visible: the sky as read-only JSON — WHEN Ephe had
encounters, never WHAT. Purely read via core.ephemeris (d/h/k/n,
privacy through physics); fail-soft: any failure answers with an empty
sky instead of a 500.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Query

router = APIRouter(tags=["Ephemeris"])

_KINDS = ("session", "tool", "artifact")
_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")

_EMPTY = lambda days: {  # noqa: E731 — fail-soft baseline payload, never a 500
    "available": False,
    "days": days,
    "today": None,
    "empty": True,
    "total": 0,
    "faded": 0,
    "kinds": {k: 0 for k in _KINDS},
    "rows": [],
}


def _sky(events: list[dict], *, days: int, today: date) -> dict:
    horizon = [today - timedelta(days=offset) for offset in range(days)]
    iso_days = {d.isoformat() for d in horizon}

    by_day: dict[str, dict[int, int]] = {}
    kinds = {k: 0 for k in _KINDS}
    total = 0
    faded = 0
    for ev in events:
        d = ev.get("d")
        h = ev.get("h")
        n = ev.get("n", 0)
        if not isinstance(n, int):
            n = 0
        if d in iso_days and isinstance(h, int) and 0 <= h <= 23:
            bucket = by_day.setdefault(d, {})
            bucket[h] = bucket.get(h, 0) + n
            total += n
            k = ev.get("k")
            if k in kinds:
                kinds[k] += n
        else:
            faded += n

    rows = []
    for day in horizon:
        key = day.isoformat()
        bucket = by_day.get(key, {})
        # Peak hour: the earliest hour when the counts tie (stable).
        peak = max(bucket.items(), key=lambda kv: (kv[1], -kv[0]))[0] if bucket else None
        rows.append(
            {
                "d": key,
                "weekday": _WEEKDAYS[day.weekday()],
                "label": f"{day.day:02d}.{day.month:02d}",
                "total": sum(bucket.values()),
                "peak_hour": peak,
                "hours": {str(h): n for h, n in sorted(bucket.items())},
            }
        )

    return {
        "available": True,
        "days": days,
        "today": today.isoformat(),
        "empty": total == 0,
        "total": total,
        "faded": faded,
        "kinds": kinds,
        "rows": rows,
    }


@router.get("/ephemeris")
def ephemeris_sky(days: int = Query(default=7, ge=1, le=31)) -> dict:
    """The sky as JSON — read-only, default store, fail-soft (never 500)."""
    try:
        from core import ephemeris as eph  # function import: the test seams stay monkeypatchable

        events = eph.load(eph.default_store())
        return _sky(events, days=days, today=datetime.now().date())
    except Exception:
        return _EMPTY(days)
