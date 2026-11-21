"""
Ephe — R40c: deck-/briefing refinements (slidev-/NomaDiname-parity).

Pins:
  1. Labeled Markdown cases: 'Title:'/'Claim:'/'Body:'/'Note:' are parsed as
     separate fields (title/body split, note as speaker_note).
  2. Unlabeled cases: the previous line protocol stays (fallback).
  3. Mixed: labeled title + unlabeled following lines.
  4. Brief: the evidence register carries the section budget (max 8 entries)
     plus a ' further' pointer to the rest; section order stays stable.

RULE: tests written BEFORE the implementation. Given / When / Then — strict.
"""
from __future__ import annotations

import pytest


# 1–3: title/body separation in the Markdown path

def test_parse_deck_slides_labeled_fields_split():
    """GIVEN a labeled slide block (Title/Claim/Body/Note)
    WHEN _parse_deck_slides()
    THEN all four fields come out separate, note as speaker_note."""
    from core.tools.deck_tools import _parse_deck_slides

    md = "Title: Alpha\nClaim: Beta\nBody: Gamma first. Gamma second.\nNote: Presenter cue"
    out = _parse_deck_slides(md, "Topic", "Audience", "Thesis")
    assert out[0]["title"] == "Alpha"
    assert out[0]["claim"] == "Beta"
    assert out[0]["body"] == "Gamma first. Gamma second."
    assert out[0]["speaker_note"] == "Presenter cue"


def test_parse_deck_slides_unlabeled_fallback_unchanged():
    """GIVEN an unlabeled block (line1 = title, line2 = claim, rest = body)
    WHEN _parse_deck_slides()
    THEN the previous protocol stays (Hinters compatibility)."""
    from core.tools.deck_tools import _parse_deck_slides

    md = "Alpha\nBeta\nGamma one\nGamma two"
    out = _parse_deck_slides(md, "Topic", "Audience", "Thesis")
    assert out[0]["title"] == "Alpha"
    assert out[0]["claim"] == "Beta"
    assert out[0]["body"] == "Gamma one Gamma two"


def test_parse_deck_slides_mixed_labeled_title_unlabeled_rest():
    """GIVEN a labeled title plus unlabeled following lines
    WHEN _parse_deck_slides()
    THEN the title takes the label, the rest follows the line protocol."""
    from core.tools.deck_tools import _parse_deck_slides

    md = "Title: A\nplain claim line\nplain body line"
    out = _parse_deck_slides(md, "Topic", "Audience", "Thesis")
    assert out[0]["title"] == "A"
    assert out[0]["claim"] == "plain claim line"
    assert out[0]["body"] == "plain body line"


# 4: brief section budget

def test_source_brief_evidence_register_has_section_budget(tmp_path, monkeypatch):
    """GIVEN a notebook with >8 matched chunks
    WHEN export_source_brief_file()
    THEN the Evidence Register lists max 8 entries + a ' further' pointer;
    the section order (Summary/Register/Manifest) stays stable."""
    from core.source_notebook import create_source_notebook_index, export_source_brief_file

    monkeypatch.setenv("HOME", str(tmp_path))
    source = tmp_path / "research.md"
    # ~13k characters => 11 chunks at the 1200 cap, so the register budget (8)
    # runs against the hit count (export max 10): 8 listed + 2 as a pointer.
    body = "\n".join(
        f"Alpha fact {i}: the measured value is {i * 7} units in sector {i}, "
        f"confirmed by the quarterly report with a margin of {i} percent, "
        f"audited against prior period baseline {i * 3}."
        for i in range(1, 121)
    )
    source.write_text(body, encoding="utf-8")
    notebook = create_source_notebook_index(paths=str(source), title="Budget Test")

    brief_path = export_source_brief_file(
        notebook_path=str(notebook),
        question="Which alpha facts carry the measured values in sector terms?",
        filename="r40c_brief.md",
    )
    text = brief_path.read_text(encoding="utf-8")

    register_items = [line for line in text.splitlines() if line.startswith("- `S001-C")]
    assert len(register_items) <= 8
    assert "further evidence chunks in the notebook" in text
    assert text.index("## Executive Summary") < text.index("## Evidence Register") < text.index("## Source Manifest")
