"""The two SOL settings and their explanations, in both languages.

A field in the register needs a reader and a text in the same slice; the readers
are `core/sol/session.py` (the switch) and `core/sol/consolidator.py` (the cap on
active rules). The file sits beside the engine it explains so the register keeps
its own size.
"""
from __future__ import annotations

from typing import Final

SOL_HINTS: Final[dict[str, tuple[str, str]]] = {
    "sol.enabled": (
        "Nach einer fehlgeschlagenen Runde benennt Ephe Fehlerklasse, widerlegte "  # language-gate: ignore (German UI hint — the product's German settings surface)
        "Annahme und Korrektur für die nächste Anfrage; eine Korrektur, die den "  # language-gate: ignore (German UI hint — the product's German settings surface)
        "Lauf beendet hat, wird als Regel unter .ephe/learning/ abgelegt. Der "  # language-gate: ignore (German UI hint — the product's German settings surface)
        "Haken schaltet beides ab.",  # language-gate: ignore (German UI hint — the product's German settings surface)
        "After a failed round Ephe names the class, the broken assumption and "
        "the correction for the next request. A correction that ended the run "
        "becomes a readable rule under .ephe/learning/; this switch turns both off.",
    ),
    "sol.max_active_rules": (
        "Wie viele gelernte Projektregeln im Prompt mitreisen (5-50). Ältere Regeln "  # language-gate: ignore (German UI hint — the product's German settings surface)
        "wandern in heuristics-archive.md; keine wird gelöscht, die Datei bleibt "  # language-gate: ignore (German UI hint — the product's German settings surface)
        "von Hand editierbar.",  # language-gate: ignore (German UI hint — the product's German settings surface)
        "How many learned project rules ride along in the prompt (5-50). Older "
        "rules move to heuristics-archive.md; none is deleted, and the file stays "
        "editable by hand.",    ),
}
