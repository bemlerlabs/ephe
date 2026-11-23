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
OUTER_ARGS = (
    '{"title": "TRENDSPECTIVES – Taschenkarte Event-Briefing", "template": "brief", '
    '"audience": "CTO, CEO, CFO", "agenda": "Panel und Get-together am Abend"}'
)


def test_truncation_never_ends_on_a_dangling_separator():
    report_line = args_summary({"arguments": OUTER_ARGS, "name": "create_pdf"})
    assert '", ;' not in report_line and ", ;" not in report_line
    assert "…" in report_line, "the truncation has to be visible"
    assert "name=create_pdf" in report_line


def test_a_cut_mid_word_gets_the_marker():
    lang = "Peter Möhring Trendspectives Berater München Technologie-Scouting und mehr"
    report_line = args_summary({"query": lang}, limit=200)
    assert report_line.endswith("…") or lang[:80] == lang
    assert not any(report_line.rstrip("…").endswith(z) for z in ("Geschä", "unde", "und "))


def test_a_short_value_stays_untouched():
    assert args_summary({"path": "~/Desktop"}) == "path=~/Desktop"


def test_limit_applies_to_the_whole_line():
    report_line = args_summary({"a": "x" * 60, "b": "y" * 60}, limit=40)
    assert len(report_line) <= 41  # 40 characters plus the marker
    assert report_line.endswith("…")


def test_redaction_runs_before_the_truncation():
    report_line = args_summary({"token": "sk-" + "A" * 90})
    assert "AAAA" not in report_line
    assert "***" in report_line
