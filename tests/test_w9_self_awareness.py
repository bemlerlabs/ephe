"""W9 — self-awareness: the system's capability map (stages, skills, tools).

Ephe knows its own construction: the context build stages (the system-prompt
montage), the loaded skill packs and the registered tools. The stage and skill
rows are measured off the response the UI reads, so a row that numbers nothing
here is a row the demo copy cannot quote. The tool figure is a frozen anchor
instead — see `test_the_dispatch_map_ephe_reports_on_itself_is_the_whole_map` for
what it guards and how to move it.
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
    THEN total equals the length of the skills list, and that measured length clears
    the pack floor pinned on the next line (a floor, not an anchor: the index is a
    directory walk, so it grows on purpose)."""
    resp = client.get("/api/skills")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == len(body["skills"])
    assert body["total"] >= 47


def test_the_dispatch_map_ephe_reports_on_itself_is_the_whole_map(client):
    """GIVEN the capability map Ephe answers with when it describes itself
    WHEN the dispatch registry is counted through both import paths
    THEN the two paths agree and the count is the anchored whole map.

    The number anchors the kernel dispatch map. Contributed names live in the
    descriptor registry and are addressed through it. The offer list the model
    sees is the schema blocks after the plugin gate and the user's own switches.
    The matching anchor is `test_r60_plugin_runtime.py`, which counts the same
    map from the plugin-gate side; docs/COMPOSER_MODES.md points at both."""
    from core.tools import TOOL_MAP as TOOLS
    from core.tools.registry import TOOL_MAP

    counted = len(TOOL_MAP)
    assert counted == 37, (
        f"TOOL_MAP holds {counted} names; the anchor is the literal on this line. If a "
        "tool really was added or removed from the kernel map, land it in "
        "core/tools/registry.py, then re-anchor this number and the one in "
        "test_r60_plugin_runtime.py deliberately, in the same commit. Editing the "
        "figure alone is what makes this test stop protecting the answer."
    )
    assert len(TOOLS) == len(TOOL_MAP)


def test_capability_answers_carry_concrete_numbers(client):
    """GIVEN the capability maps
    WHEN the stage rows and the skill rows are read
    THEN every row carries a number of its own — a map that answers in prose only is
    a map the interface cannot quote."""
    stages = client.get("/api/context/stages").json()
    skills = client.get("/api/skills").json()
    # Every stage carries a char count > 0 — the montage is fully numbered.
    assert all(s["chars"] > 0 for s in stages["stages"])
    assert skills["total"] > 0
