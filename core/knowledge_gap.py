"""Ephe — knowledge-gap detection loop (wave 7, variant B).

Flow per answer:
  1. The agent answers normally; missing knowledge is marked in the text with
     ``[[GAP: topic]]`` (marker protocol, invisible to the user).
  2. Each marker resolves autonomously: ``search`` delivers sources.
  3. Only when the research is broken (no hit, timeout) or two
     sources deliver contradictory core values does a yes/no go to the user.
  4. The research result is injected as a context block into the answer.

Guarantees:
  - B1  Dialogue only when unclear — one hit is enough, no follow-up questions.
  - B2  Every gap lands in the gap table (``gaps.json``), status
        ``open`` → ``covered``; that keeps the state traceable across
        sessions.
  - B3  Hard budget: at most ``MAX_GAP_RESEARCH_ROUNDS`` researches per
        answer — the answer does not sink into researching.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path

#: B3 — hard research budget per answer (a lid against endless sinking).
MAX_GAP_RESEARCH_ROUNDS: int = 3

#: Marker protocol in the answer text: ``[[GAP: topic]]``.
_GAP_MARKER_RE = re.compile(r"\[\[GAP:\s*(.+?)\s*\]\]", re.DOTALL)


def parse_gap_markers(text: str) -> list[str]:
    """Topics of all ``[[GAP: …]]`` markers, in order of appearance.

    Empty markers (only brackets, no content) are ignored.
    """
    out: list[str] = []
    for match in _GAP_MARKER_RE.finditer(text or ""):
        topic = " ".join(match.group(1).split())
        if topic:
            out.append(topic)
    return out


def _snippets_distinct(notes: list[dict], threshold: int) -> bool:
    """Two sources with sufficiently different core values → contradictory."""
    distinct = {str(n.get("snippet") or "").strip() for n in notes}
    distinct.discard("")
    return len(distinct) >= max(2, threshold)


def resolve_gap(
    topic: str,
    search,
    contradiction_threshold: int = 2,
) -> dict:
    """Resolve one knowledge gap autonomously — B1/B3.

    ``search(query)`` delivers a list of ``{title,url,snippet}`` dicts.
    Return: ``{"topic", "status": covered|needs_user, "notes": [...]}``.
    """
    notes: list[dict] = []
    for _round in range(MAX_GAP_RESEARCH_ROUNDS):
        try:
            hits = search(topic) or []
        except Exception:
            # Timeout / network error: broken research → user dialogue.
            return {"topic": topic, "status": "needs_user", "notes": notes}
        if hits:
            notes = [
                {
                    "title": str(h.get("title") or ""),
                    "url": str(h.get("url") or ""),
                    "snippet": str(h.get("snippet") or ""),
                }
                for h in hits[:5]
            ]
            break

    if not notes:
        return {"topic": topic, "status": "needs_user", "notes": []}
    if _snippets_distinct(notes, contradiction_threshold):
        # Too large a contradiction between two sources → the user decides.
        return {"topic": topic, "status": "needs_user", "notes": notes}
    return {"topic": topic, "status": "covered", "notes": notes}


# B2 — gap table (persistence across sessions)


def _default_home() -> Path:
    import core.engine_config as _ec

    return _ec.config_root()


def _gaps_file(home: Path | None) -> Path:
    return (home if home is not None else _default_home()) / "gaps.json"


def load_gaps(home: Path | None = None) -> list[dict]:
    """Every row of the gap table, in the order rows were added."""
    try:
        data = json.loads(_gaps_file(home).read_text(encoding="utf-8"))
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _save_gaps(rows: list[dict], home: Path | None = None) -> None:
    path = _gaps_file(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def record_gap(topic: str, status: str = "open", home: Path | None = None) -> dict:
    """Enter a gap into the table; returns the row."""
    row = {
        "id": hashlib.sha1(f"{topic}|{time.time()}".encode()).hexdigest()[:10],
        "topic": topic,
        "status": status,
        "ts": round(time.time(), 3),
    }
    rows = load_gaps(home)
    rows.append(row)
    _save_gaps(rows, home)
    return row


def mark_covered(gap_id: str, home: Path | None = None) -> bool:
    """Set a row's status to ``covered``; True on a hit."""
    rows = load_gaps(home)
    changed = False
    for row in rows:
        if row.get("id") == gap_id:
            row["status"] = "covered"
            changed = True
    if changed:
        _save_gaps(rows, home)
    return changed
