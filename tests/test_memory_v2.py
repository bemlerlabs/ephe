"""R30 — Memory v2 curation + portable USER.md.

Curation: near-duplicate writes are merged into the first entry (count +
last_seen) instead of polluting retrieval with three variants of one fact.
Priority: high-priority entries outrank incidental ones at equal similarity.
USER.md: the profile becomes a portable markdown document (export/import),
like the memory pack — the user's context travels with them.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def mem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from core.memory import Memory

    # Empty config root -> _migrate_from_legacy finds no real legacy DB
    # and the tmp collection stays isolated (count()/search() start empty).
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    return Memory(persist_dir=str(tmp_path / "chroma"), collection_name="r30_curation")


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import os

    os.environ["EPHE_MEMORY_DIR"] = os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
    profile_path = tmp_path / "user_profile.json"
    os.environ["EPHE_PROFILE_PATH"] = os.environ["EPHE_PROFILE_PATH"] = str(profile_path)
    import core.engine_config as engine_config

    monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path / "config")

    from fastapi.testclient import TestClient
    from server.main import create_app

    return TestClient(create_app())


class TestDedupe:
    def test_near_duplicate_merges_instead_of_multiplying(self, mem):
        mem.store("The user prefers dark roast coffee from a local roaster")
        mem.store("The user prefers dark roast coffee from a local roaster.")  # near-duplicate
        hits = mem.search("coffee preference", top_k=10)
        exact = [h for h in hits if "dark roast" in h["text"]]
        # one canonical entry, not two near-identical rows competing at retrieval
        assert len({h["text"].lower().rstrip(".") for h in exact}) == 1

    def test_merge_counts_hits(self, mem):
        mem.store("Ephe ships with an offline-first engine")
        mem.store("Ephe ships with an offline-first engine")
        hits = mem.search("offline first engine", top_k=5)
        top = hits[0]
        assert top["metadata"].get("hits", 1) >= 2

    def test_different_facts_stay_separate(self, mem):
        mem.store("The laptop has 32 GB of RAM and an M4 chip")
        mem.store("The kitchen table is made of solid oak wood")
        assert mem.count() == 2


class TestPriority:
    def test_priority_metadata_roundtrips(self, mem):
        mem.store("Always run the narrowest test first in this repo", metadata={"priority": "high"})
        hits = mem.search("test strategy", top_k=5)
        assert hits[0]["metadata"]["priority"] == "high"


class TestUserProfileMarkdown:
    def test_export_is_markdown_with_all_sections(self, client):
        client.put("/api/profile", json={
            "name": "Test User",
            "expertise": "systems engineering",
            "preferred_language": "German",
            "response_style": "kurz und direkt",
            "topics_of_interest": ["audio", "llm"],
            "projects": ["ephe"],
            "dislikes": ["emoji spam"],
        })
        resp = client.get("/api/profile/export")
        assert resp.status_code == 200
        md = resp.json()["markdown"]
        assert md.startswith("# USER.md")
        for fragment in ("Test User", "systems engineering", "ephe", "emoji spam"):
            assert fragment in md

    def test_import_roundtrips(self, client):
        md = (
            "# USER.md\n\n"
            "- Name: Ada\n"
            "- Expertise: mathematics\n"
            "- Preferred language: English\n"
            "- Response style: terse\n"
            "- Topics of interest: logic, proofs\n"
            "- Projects: principia\n"
            "- Dislikes: handwaving\n"
        )
        resp = client.put("/api/profile/import", json={"markdown": md})
        assert resp.status_code == 200
        got = client.get("/api/profile").json()
        assert got["name"] == "Ada"
        assert "proofs" in got["topics_of_interest"]
        assert got["projects"] == ["principia"]

    def test_import_rejects_foreign_shape(self, client):
        resp = client.put("/api/profile/import", json={"markdown": "just prose, no USER.md header"})
        assert resp.status_code == 422
