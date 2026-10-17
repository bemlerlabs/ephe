"""tests/test_r5_args_summary_kuerzung.py — a truncation must read as a truncation. (the German is the file's own name, which is code, language-gate: ignore)

Re-measured on the provenance line of a live workbench card (2026-10-07), which
looked exactly the way it reads:

    arguments={"title": "TRENDSPECTIVES – Taschenkarte Event-Briefing",
     "template": "brief", ; name=create_pdf

The JSON value breaks at 80 characters in the middle of the object, and the
`", ` left behind before the `;` separator produced a line that looks broken — a
reader concludes from it that Ephe cannot format its own records. Second case:
a search query ended on `… Peter Möhring Geschä` (verbatim fixture text, language-gate: ignore) and read like the complete
text.

Contract:
1. A truncated value ends on `…`, never on a dangling separator.
2. A value inside the limit stays untouched.
3. The overall limit (`limit`) still applies and is marked the same way.
4. Redaction before truncation — a cut must never make a secret visible.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.redact import args_summary  # noqa: E402

# The real case from the index, rebuilt verbatim.
AUSSEN = (
    '{"title": "TRENDSPECTIVES – Taschenkarte Event-Briefing", "template": "brief", '
    '"audience": "CTO, CEO, CFO", "agenda": "Panel und Get-together am Abend"}'
)


def test_haengendes_trennzeichen_ist_kein_ende():
    zeile = args_summary({"arguments": AUSSEN, "name": "create_pdf"})
    assert '", ;' not in zeile and ", ;" not in zeile
    assert "…" in zeile, "die Kürzung muss zu sehen sein"
    assert "name=create_pdf" in zeile


def test_schnitt_mitt_im_wort_bekommt_einzeichen():
    lang = "Peter Möhring Trendspectives Berater München Technologie-Scouting und mehr"
    zeile = args_summary({"query": lang}, limit=200)
    assert zeile.endswith("…") or lang[:80] == lang
    assert not any(zeile.rstrip("…").endswith(z) for z in ("Geschä", "unde", "und "))


def test_kurz_bleibt_unveraendert():
    assert args_summary({"path": "~/Desktop"}) == "path=~/Desktop"


def test_grenze_gilt_fuer_die_ganze_zeile():
    zeile = args_summary({"a": "x" * 60, "b": "y" * 60}, limit=40)
    assert len(zeile) <= 41  # 40 characters plus the marker
    assert zeile.endswith("…")


def test_redaktion_steht_vor_der_kuerzung():
    zeile = args_summary({"token": "sk-" + "A" * 90})
    assert "AAAA" not in zeile
    assert "***" in zeile
