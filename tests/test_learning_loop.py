"""R31 — Learning loop: automatic pattern detection + validated skill install.

Referenz-A generates skills from experience automatically. Ephe does the same  # language-gate: ignore (Referenz-A is the repo's own name for the anonymised reference client, used verbatim in the module it tests — core/learning_loop.py:3)
AND runs them through a quality gate: structural validation (already inside
skill_builder._parse_skill) plus a proposals pipeline so nothing installs
without the user accepting it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture()
def learn_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "learning"
    monkeypatch.setenv("EPHE_LEARNING_DIR", str(d))
    return d


def _user(text: str) -> dict:
    return {"role": "user", "content": text}


def _asst(text: str) -> dict:
    return {"role": "assistant", "content": text}


class TestPatternDetector:
    def test_repeated_request_becomes_candidate(self):
        from core.learning_loop import detect_patterns

        msgs = (
            [_user("Exportiere alle Kunden aus der CRM-Tabeller als CSV mit Umlauten"),
             _asst("ok")] * 3
        )
        cands = detect_patterns(msgs)
        assert any(c["kind"] == "repeated_request" and c["count"] >= 3 for c in cands)

    def test_correction_becomes_candidate(self):
        from core.learning_loop import detect_patterns

        msgs = [
            _asst("Hier die Antwort …"),
            _user("Nein, genau in Tabellenstatt antworten, nie Fließtext."),
            _asst("Verstanden."),
            _user("Immer mit Datum im Format YYYY-MM-DD arbeiten."),
        ]
        cands = detect_patterns(msgs)
        kinds = {c["kind"] for c in cands}
        assert "correction" in kinds

    def test_small_talk_produces_nothing(self):
        from core.learning_loop import detect_patterns

        assert detect_patterns([_user("hi"), _asst("hey!"), _user("danke"), _asst("stets")]) == []

    def test_short_requests_are_ignored_even_if_repeated(self):
        from core.learning_loop import detect_patterns

        assert detect_patterns([_user("ja")] * 6) == []


class TestProposalStore:
    def test_add_list_dismiss_flow(self, learn_dir):
        from core.learning_loop import ProposalStore

        store = ProposalStore()
        pid = store.add({"kind": "repeated_request", "topic": "csv export", "evidence": "x", "count": 3})
        assert store.pending() and store.pending()[0]["id"] == pid
        store.dismiss(pid)
        assert store.pending() == []

    def test_same_topic_is_never_proposed_twice(self, learn_dir):
        from core.learning_loop import ProposalStore

        store = ProposalStore()
        store.add({"kind": "repeated_request", "topic": "CSV Export", "evidence": "a", "count": 3})
        second = store.add({"kind": "repeated_request", "topic": "csv   export", "evidence": "b", "count": 4})
        assert second is None  # deduped by normalized topic
        assert len(store.pending()) == 1

    def test_store_is_capped(self, learn_dir):
        from core.learning_loop import MAX_PROPOSALS, ProposalStore

        store = ProposalStore()
        for i in range(MAX_PROPOSALS + 10):
            store.add({"kind": "correction", "topic": f"topic number {i}", "evidence": "x", "count": 2})
        assert len(store.pending()) == MAX_PROPOSALS

    def test_record_turn_throttles_per_session(self, learn_dir):
        from core.learning_loop import record_turn_and_detect

        # one qualifying correction creates a proposal
        made = record_turn_and_detect("sess-a", [_user("Immer mit USt-Ausweis und Nummernkreis rechnen")])
        assert made == 1
        # while a session still has a pending proposal, further turns stay quiet
        again = record_turn_and_detect("sess-a", [_user("Immer Quellenangaben in Fußnoten liefern")])
        assert again == 0
        # a different session is unaffected
        other = record_turn_and_detect("sess-b", [_user("Immer Quellenangaben in Fußnoten liefern")])
        assert other == 1


class TestLearningRoutes:
    @pytest.fixture()
    def client(self, tmp_path, monkeypatch):
        import os

        os.environ["EPHE_MEMORY_DIR"] = os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
        os.environ["EPHE_PROFILE_PATH"] = os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
        import core.engine_config as engine_config

        monkeypatch.setattr(engine_config, "CONFIG_DIR", tmp_path / "config")
        from fastapi.testclient import TestClient
        from server.main import create_app

        return TestClient(create_app())

    def test_list_and_dismiss(self, client, learn_dir):
        from core.learning_loop import ProposalStore

        pid = ProposalStore().add({"kind": "correction", "topic": "tabellen", "evidence": "x", "count": 2})
        resp = client.get("/api/learning/proposals")
        assert resp.status_code == 200
        assert any(p["id"] == pid for p in resp.json()["proposals"])
        assert client.post(f"/api/learning/proposals/{pid}/dismiss").status_code == 200
        assert client.get("/api/learning/proposals").json()["proposals"] == []

    def test_accept_builds_skill_with_evidence(self, client, learn_dir, monkeypatch):
        from core.learning_loop import ProposalStore
        import server.routes.learning as learning

        pid = ProposalStore().add({"kind": "correction", "topic": "rechnungen", "evidence": "Immer mit USt", "count": 2})

        captured: dict = {}

        async def fake_build(*, topic: str, model: str, **kw):
            captured["topic"] = topic
            captured["model"] = model
            class S:
                name = "rechnungen"
            return S()

        monkeypatch.setattr(learning, "build_skill", fake_build)
        resp = client.post(f"/api/learning/proposals/{pid}/accept", json={"model": "test-model"})
        assert resp.status_code == 200
        assert resp.json()["installed"] == "rechnungen"
        # evidence traveled into the build topic so the skill learns from the real exchange
        assert "USt" in captured["topic"]
        assert ProposalStore().pending() == []

    def test_accept_invalid_skill_is_refused(self, client, learn_dir, monkeypatch):
        from core.learning_loop import ProposalStore
        from core.skills import SkillLoadError
        import server.routes.learning as learning

        pid = ProposalStore().add({"kind": "correction", "topic": "kaputt", "evidence": "x", "count": 2})

        async def broken_build(*, topic: str, model: str, **kw):
            raise SkillLoadError("structural gate: missing System Prompt block")

        monkeypatch.setattr(learning, "build_skill", broken_build)
        resp = client.post(f"/api/learning/proposals/{pid}/accept", json={"model": "test-model"})
        assert resp.status_code == 422
        assert "structural gate" in resp.json()["error"]["message"]
        # a refused build leaves the proposal for another attempt
        assert [p["id"] for p in ProposalStore().pending()] == [pid]

    def test_unknown_proposal_404(self, client, learn_dir):
        assert client.post("/api/learning/proposals/nope/dismiss").status_code == 404
