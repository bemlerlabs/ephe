"""
◑ Ephe — the ephemeris (S wave "sky")
core/ephemeris.py

The ephemeris is the agent's star catalogue: it records WHEN Ephe
had encounters — never WHAT happened. Each encounter leaves an orbit
(d/h/k/n); the day has a peak hour, the month crystallises into amber.

Privacy contract (by construction): the schema knows only four fields —
  d  day (ISO date)
  h  hour (0–23)
  k  orbit-point kind: session | tool | artifact
  n  number of orbit points
No paths, no messages, no model names — privacy through
physics, not through promises.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from core.engine_config import config_root

# Orbit-point kinds. "message" is deliberately NOT one: content is not an orbit point.
KINDS: tuple[str, ...] = ("session", "tool", "artifact")

_FIELDS = frozenset({"d", "h", "k", "n"})


def default_store() -> Path:
    """Where the orbits live — inside the device config folder.

    WHY ``config_root()`` and not ``Path.home() / ".ephe"``: every other state file
    resolves through the config-dir helper and honours ``EPHE_CONFIG_DIR``; hardcoding
    the home here meant a run with a redirected config dir (and the whole test suite,
    which sets it per test) still appended ``ephemeris.jsonl`` into the developer's real
    ``~/.ephe``. Unset env → ``config_root()`` is ``~/.ephe``, so the default location is
    unchanged for a normal install.
    """
    return config_root() / "ephemeris.jsonl"


def real_today() -> date:
    """Seam for tests: cmd_sky calls chart() without today — that keeps the
    sky testable with a stable calendar."""
    return date.today()


def record(
    kind: str,
    *,
    count: int = 1,
    now: datetime | None = None,
    store: Path | None = None,
) -> dict:
    """Write an orbit into the sky. Fail-closed: unknown kinds
    (such as "message") are refused — so that content never seeps into the
    catalogue. Returns the record that was written."""
    if kind not in KINDS:
        raise ValueError(
            f"unbekannte Bahnpunkt-Art: {kind!r} — erlaubt: {', '.join(KINDS)}"
        )
    now = now or datetime.now()
    event = {
        "d": now.date().isoformat(),
        "h": int(now.hour),
        "k": kind,
        "n": int(count),
    }
    store = store or default_store()
    with open(store, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def load(store: Path | None = None) -> list[dict]:
    """Read all orbits. Fail-soft: a broken line is skipped,
    it never throws — the sky only forgets what was unreadable."""
    store = store or default_store()
    if not store.is_file():
        return []
    events: list[dict] = []
    with open(store, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(ev, dict) and set(ev) == _FIELDS:
                events.append(ev)
    return events


_WEEKDAYS = ("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")
_FULL = "█"
_DOT = "·"


def chart(events: list[dict], *, days: int = 7, today: date | None = None) -> str:
    """The sky as text: one line per day, one column per hour.
    Each day normalises to its own maximum — the brightest light
    of a day always gets the full block (every day its own
    constellation). Orbits outside the sight range merely fade."""
    today = today or real_today()
    horizon = {
        (today - timedelta(days=offset)).isoformat() for offset in range(days)
    }

    by_day: dict[str, dict[int, int]] = {}
    total_n = 0
    faded_n = 0
    for ev in events:
        d = ev.get("d")
        h = ev.get("h")
        n = ev.get("n", 0)
        if not isinstance(n, int):
            n = 0
        if d in horizon and isinstance(h, int) and 0 <= h <= 23:
            by_day.setdefault(d, {})
            by_day[d][h] = by_day[d].get(h, 0) + n
            total_n += n
        else:
            faded_n += n

    lines = [
        f"◍ Ephe Ephemeris — die letzten {days} Tage",
        "Bahnen, keine Inhalte — WANN Ephe lebendig war, nie WAS geschah.",
    ]
    if not any(by_day.values()):
        lines.append("Der Himmel wartet.")

    for offset in range(days - 1, -1, -1):
        day = today - timedelta(days=offset)
        key = day.isoformat()
        label = f"{_WEEKDAYS[day.weekday()]} {day.day:02d}.{day.month:02d}"
        cells = [_DOT] * 24
        bucket = by_day.get(key, {})
        peak = max(bucket.values()) if bucket else 0
        if peak > 0:
            for hour, n in bucket.items():
                if n == peak:
                    cells[hour] = _FULL
        lines.append(f"{label} │{''.join(cells)}│")

    foot = f"Sichtweite {days} Tage · {total_n} Bahnen"
    if faded_n:
        foot += f" · {faded_n} verblasst"
    lines.append(f"({foot})")
    # Hour ruler as the lowest axis; the cells start at column 10.
    lines.append(
        "          0     6     12    18   23h   ← Stunde"
    )
    return "\n".join(lines)


def crystallize(
    events: list[dict], *, month: str, amber_dir: Path | None = None
) -> dict:
    """Crystallise a month into amber: monthly sums per orbit-point
    kind, active days, peak hour. Writes a file only when an
    amber_dir is given — the pure calculation stays side-effect-free."""
    sums = {kind: 0 for kind in KINDS}
    hours: dict[int, int] = {}
    active_days: set[str] = set()
    total = 0
    for ev in events:
        d = ev.get("d")
        if not isinstance(d, str) or not d.startswith(month):
            continue
        n = ev.get("n", 0)
        if not isinstance(n, int):
            n = 0
        k = ev.get("k")
        if k in sums:
            sums[k] += n
        total += n
        active_days.add(d)
        h = ev.get("h")
        if isinstance(h, int) and 0 <= h <= 23:
            hours[h] = hours.get(h, 0) + n

    spitzstunde = None
    if hours:
        peak_hour = max(hours.items(), key=lambda kv: (kv[1], kv[0]))[0]
        spitzstunde = f"{peak_hour:02d}:00"

    amber = {
        "monat": month,
        "sitzungen": sums["session"],
        "werkzeuge": sums["tool"],
        "artefakte": sums["artifact"],
        "bahnen": total,
        "tage_aktiv": len(active_days),
        "spitzstunde": spitzstunde,
    }
    if amber_dir is not None:
        amber_dir.mkdir(parents=True, exist_ok=True)
        out = amber_dir / f"{month}.json"
        out.write_text(
            json.dumps(amber, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return amber
