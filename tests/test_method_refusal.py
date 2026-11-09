"""
tests/test_method_refusal.py — a refused method says what it means

Measured on trunk 5ac75dc1 (2026-11-03): POST /api/file answered 405 with the
body code "not_found" and no Allow header. A client reading that concluded the
file did not exist, while the path was there and the verb was what got refused.
These cases pin the corrected answer: its own code, the verbs the matched path
supports, and the 404 that stays a separate refusal.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    import os
    os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
    os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
    os.environ["EPHE_CORRECTIONS_PATH"] = str(tmp_path / "corrections.md")
    os.environ["EPHE_FEEDBACK_DIR"] = str(tmp_path)
    os.environ["EPHE_SKILLS_DIR"] = str(tmp_path / "skills")
    from server.routes.memory import _get_memory
    _get_memory.cache_clear()
    from server.main import create_app
    return TestClient(create_app())


@pytest.fixture
def served_file(client, monkeypatch, tmp_path):
    """A real file inside an allowed root — the GET side of /api/file works here."""
    monkeypatch.setattr("server.routes.files._get_artifact_roots", lambda: [tmp_path])
    f = tmp_path / "chart.svg"
    f.write_text("<svg/>", encoding="utf-8")
    return f


class TestRefusedMethod:

    def test_post_on_a_get_route_answers_the_method_code(self, client, served_file):
        """GIVEN GET /api/file WHEN POST /api/file?path=… THEN 405, code
        method_not_allowed, and an Allow header naming GET."""
        r = client.post("/api/file", params={"path": str(served_file)})
        assert r.status_code == 405
        error = r.json()["error"]
        assert error["code"] == "method_not_allowed"
        assert "GET" in r.headers["allow"].split(", ")
        assert "POST" in error["message"] and "GET" in error["message"]

    def test_head_on_the_same_path_answers_with_metadata_only(self, client, served_file):
        """GIVEN the same route WHEN HEAD /api/file THEN 200 with the file's own size and
        its range support, and no body. #80 gave the route a HEAD verb so a surface can ask
        what a file weighs without downloading it; the refused-method contract stays pinned
        on the POST twin above, which is where a body could not hide the code anyway."""
        r = client.head("/api/file", params={"path": str(served_file)})
        assert r.status_code == 200
        assert r.headers["content-length"] == str(served_file.stat().st_size)
        assert r.headers["accept-ranges"] == "bytes"
        assert r.content == b""

    def test_the_working_verb_is_undisturbed(self, client, served_file):
        """GIVEN the refusal above WHEN GET /api/file?path=… THEN 200 + content."""
        r = client.get("/api/file", params={"path": str(served_file)})
        assert r.status_code == 200
        assert r.text == "<svg/>"

    def test_an_unknown_path_still_reads_not_found(self, client):
        """The two refusals stay separate: 404 answers not_found and carries no Allow."""
        r = client.get("/api/no-such-route")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "not_found"
        assert "allow" not in r.headers

    def test_a_post_only_route_refuses_get_the_same_way(self, client):
        """The answer is general: GET /api/chat (a POST-only route) names POST back."""
        r = client.get("/api/chat")
        assert r.status_code == 405
        assert r.json()["error"]["code"] == "method_not_allowed"
        assert "POST" in r.headers["allow"].split(", ")
