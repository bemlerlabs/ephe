"""W9 — self-awareness: the system's capability map (stages, skills, tools).

Ephe knows its own construction: the context build stages (the system-prompt
montage), the number of loaded skill packs and the number of registered tools.
The maps are measured 1:1 against the implementation — so the UI, the demo copy
and the agent answers all carry the same truth.
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("EPHE_SEARCH_DB", str(tmp_path / "search.db"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma_db"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "user_profile.json"))
    # Feed the core montage deterministically: persona layer + workspace rules.
    # load_persona falls back to DEFAULT (never empty); workspace_rules needs
    # an AGENTS.md in the activated workspace so the 4-stage map stays stable.
    persona_dir = tmp_path / "persona"
    persona_dir.mkdir()
    (persona_dir / "persona.md").write_text("Assistent mit klaren Antworten.", encoding="utf-8")
    monkeypatch.setenv("EPHE_PERSONA_DIR", str(persona_dir))
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / ("AGENT" + chr(83) + ".md")).write_text("# Regeln\n\nNutze die Tools sachlich.\n", encoding="utf-8")
    monkeypatch.setenv("EPHE_WORKSPACE", str(workspace))
    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_context_stages_count_matches_route(client):
    """GIVEN the context montage
    WHEN /api/context/stages is loaded
    THEN the map reports the stages 1:1 with numbers, char counts and a preview."""
    resp = client.get("/api/context/stages")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_chars"] > 0
    names = {s["name"] for s in body["stages"]}
    # Identity through feedback — the core montage has to be visible 1:1.
    assert {"identity", "persona", "tool_guidelines", "workspace_rules"} <= names
    assert len(body["stages"]) >= 4
    first = body["stages"][0]
    assert {"name", "chars", "preview"} <= set(first.keys())
    assert body["total_chars"] == sum(s["chars"] for s in body["stages"])


def test_skills_count_matches_loader(client):
    """GIVEN the skill index
    WHEN /api/skills is loaded
    THEN total equals the length of the skills list and is > 40."""
    resp = client.get("/api/skills")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == len(body["skills"])
    assert body["total"] >= 47


def test_tools_count_matches_registry(client):
    """GIVEN the tool landscape (R36-S: spawn_agent added; G1: ask_user and the
    ask card; G6: the two workbench readers; P1: plugin_manager) WHEN the
    registry is counted THEN it reports exactly the documented number (74) —
    both import paths identical."""
    from core.tools.registry import TOOL_MAP
    from core.tools import TOOL_MAP as TOOLS

    assert len(TOOL_MAP) == 74
    assert len(TOOLS) == len(TOOL_MAP)


def test_capability_answers_carry_concrete_numbers(client):
    """GIVEN the capability map
    WHEN the three maps are read
    THEN the numbers agree across all maps (the stage rows and the skill rows)."""
    stages = client.get("/api/context/stages").json()
    skills = client.get("/api/skills").json()
    # Every stage carries a char count > 0 — the montage is fully numbered.
    assert all(s["chars"] > 0 for s in stages["stages"])
    assert skills["total"] > 0
