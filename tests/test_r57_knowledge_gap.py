"""Wave 7 — the knowledge-gap detection loop (variant B).

Specification:
  B1  Research autonomously up to the budget; dialogue only when the research is
      broken (no hit / timeout) or the contradiction between the sources is too large.
  B2  The gap table is the persistence layer (~/.ephe/gaps.json), status open/covered.
  B3  Budget limit: at most 3 researches per answer.
"""
from __future__ import annotations

import json

from core.knowledge_gap import (
    MAX_GAP_RESEARCH_ROUNDS,
    load_gaps,
    mark_covered,
    parse_gap_markers,
    record_gap,
    resolve_gap,
)


# B-K1: Marker parsing

def test_parse_erkennt_einen_marker():
    text = "Antwort mit Lücke. [[GAP: RAG-Fusion 2026]] Ende."
    assert parse_gap_markers(text) == ["RAG-Fusion 2026"]


def test_parse_erkennt_mehrere_marker_in_reihenfolge():
    text = "[[GAP: thema a]] zwischentext [[GAP: thema b]]"
    assert parse_gap_markers(text) == ["thema a", "thema b"]


def test_parse_ohne_marker_liefert_leere_liste():
    assert parse_gap_markers("ganz normale antwort ohne marker") == []
    assert parse_gap_markers("") == []


def test_parse_ignoriert_leeren_marker_inhalt():
    assert parse_gap_markers("[[GAP:]]") == []


# B1/B3: autonomous research with a budget

def _fake_search_factory(results):
    """A search function returning predefined hit lists; counts the calls."""
    calls = {"n": 0}

    def search(query: str) -> list[dict]:
        calls["n"] += 1
        return results

    return search, calls


def test_resolve_gap_bei_treffern_ist_gedeckt():
    hits = [{"title": "Quelle 1", "url": "https://a.example/1", "snippet": "Snippet 1"}]
    search, calls = _fake_search_factory(hits)
    out = resolve_gap("RAG-Fusion 2026", search=search)
    assert out["status"] == "covered"
    assert out["topic"] == "RAG-Fusion 2026"
    assert out["notes"] and out["notes"][0]["url"] == "https://a.example/1"
    assert calls["n"] == 1  # one hit is enough — no further asking


def test_resolve_gap_ohne_treffer_fraggt_den_user():
    search, _ = _fake_search_factory([])
    out = resolve_gap("unbekanntes thema", search=search)
    assert out["status"] == "needs_user"
    assert out["topic"] == "unbekanntes thema"


def test_resolve_gap_budget_grenzt_recherchen():
    # The search never yields hits → every round up to the budget, then needs_user.
    search, calls = _fake_search_factory([])
    out = resolve_gap("x", search=search)
    assert out["status"] == "needs_user"
    assert calls["n"] == MAX_GAP_RESEARCH_ROUNDS  # hard limit: 3


def test_budget_konstante_ist_drei():
    assert MAX_GAP_RESEARCH_ROUNDS == 3


def test_resolve_gap_timeout_fraggt_den_user():
    def boom(query: str):
        raise TimeoutError("timeout")

    out = resolve_gap("y", search=boom)
    assert out["status"] == "needs_user"


def test_widerspruch_zweier_quellen_fraggt_den_user():
    # Two sources with contradicting core values → dialogue (needs_user).
    hits = [
        {"title": "Q1", "url": "https://a/1", "snippet": "Wert 42"},
        {"title": "Q2", "url": "https://a/2", "snippet": "Wert 17"},
    ]
    search, _ = _fake_search_factory(hits)
    out = resolve_gap("strittig", search=search, contradiction_threshold=2)
    assert out["status"] == "needs_user"
    assert len(out["notes"]) == 2


# B2: the gap table as persistence

def test_record_und_load_roundtrip(tmp_path):
    home = tmp_path / "ephe-home"
    home.mkdir()
    rec = record_gap("thema x", status="open", home=home)
    assert rec["id"] and rec["status"] == "open"
    rows = load_gaps(home=home)
    assert [r["id"] for r in rows] == [rec["id"]]
    assert (home / "gaps.json").is_file()


def test_mark_covered_setzt_status(tmp_path):
    home = tmp_path / "ephe-home"
    home.mkdir()
    rec = record_gap("thema y", status="open", home=home)
    assert mark_covered(rec["id"], home=home) is True
    assert load_gaps(home=home)[0]["status"] == "covered"
    # unknown id → False, no change
    assert mark_covered("unbekannt", home=home) is False


def test_load_gaps_ohne_datei_liefert_leere_liste(tmp_path):
    assert load_gaps(home=tmp_path / "nicht-da") == []


def test_persistenzformat_ist_json_array(tmp_path):
    home = tmp_path / "ephe-home"
    home.mkdir()
    record_gap("z", status="open", home=home)
    data = json.loads((home / "gaps.json").read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert data[0]["topic"] == "z"
