"""Y3 — intent search: a task word has to find the entry, offline."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import discover_intent, discover_search  # noqa: E402


class TestVocabulary:
    def test_both_languages_land_on_the_same_intent(self):
        assert discover_intent.tags_for("Rechnung als PDF auslesen") == ["invoices"]
        assert discover_intent.tags_for("read an invoice") == ["invoices"]

    def test_an_inflected_word_still_counts(self):
        assert "invoices" in discover_intent.tags_for("monthly invoices")
        assert "calendar" in discover_intent.tags_for("Termine")

    def test_a_longer_word_that_starts_the_same_is_not_the_intent(self):
        # "Terminal" begins with "Termin"; a prefix test once tagged every terminal
        # agent as a calendar entry.
        assert "calendar" not in discover_intent.tags_for("Terminal Command Agent")

    def test_umlauts_survive_folding(self):
        assert discover_intent.fold("Prüfen") == "prufen"


class TestSearch:
    def test_a_short_query_asks_nothing(self):
        assert discover_search.search("") == []
        assert discover_search.search("a") == []

    def test_a_german_task_finds_an_english_entry(self):
        hits = discover_search.search("Rechnung als PDF auslesen", 10)
        assert hits
        assert any("invoice" in str(hit["id"]) or "ekwo" in str(hit["id"]) for hit in hits)

    def test_our_own_catalog_leads_on_a_tie(self):
        hits = discover_search.search("memory knowledge graph", 30)
        assert hits
        assert hits[0]["id"].startswith("mcp-")

    def test_the_limit_is_respected(self):
        hits = discover_search.search("web search", 5)
        assert len(hits) <= 5

    def test_the_committed_index_covers_the_curated_tier(self):
        import json

        from core import mcp_catalog

        payload = json.loads(
            (ROOT / "marketplace" / "search-intents.json").read_text(encoding="utf-8")
        )
        curated = {str(entry["id"]) for entry in mcp_catalog.curated_entries()}
        assert curated <= set(payload["entries"])
        tagged = sum(1 for tags in payload["entries"].values() if tags)
        assert tagged > len(curated) // 2


class TestRoute:
    def test_the_search_route_answers_from_the_committed_index(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        monkeypatch.setenv("EPHE_SESSIONS_DIR", str(tmp_path / "sessions"))
        from fastapi.testclient import TestClient

        from server.main import create_app

        with TestClient(create_app()) as client:
            r = client.get("/api/discover/search", params={"q": "Rechnung als PDF auslesen"})
            empty = client.get("/api/discover/search", params={"q": ""})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["query"] == "Rechnung als PDF auslesen"
        assert body["entries"]
        assert set(body["entries"][0]) == {"id", "score"}
        assert empty.json()["entries"] == []
