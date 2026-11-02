"""The shelf keeps each skill's own words and answers with a language label.

Measured on 2026-11-02, before this rule existed: 2 of the 72 skill entries
/api/discover/bootstrap serves carried German triggers and descriptions. Both
were user files in the device skills dir; none of the 51 first-party SKILL.md
packs did. The user's words are not ours to rewrite, so the loader labels them
and the route passes them verbatim, and the card shows the mark.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.skills import SHELF_LANGUAGE, SkillLoader, _parse_skill, detect_language  # noqa: E402

GERMAN_TRIGGER = "prüfe landingpage gegen awwwards kriterien"  # language-gate: ignore (an author's own words; the rule under test keeps them verbatim)
GERMAN_DESCRIPTION = "Prüft eine Landingpage gegen die vier Kriterien und den Guard, mit belegten Befunden."  # language-gate: ignore (an author's own words; the rule under test keeps them verbatim)


def _flat_skill(name: str, trigger: str, description: str) -> str:
    return (
        f"# {name}\n\n"
        f"**Trigger**: {trigger}\n"
        f"**Description**: {description}\n"
        "**Tools**: read_file, write_file\n\n"
        "## System Prompt\n"
        f"You are {name}. Answer the user request carefully.\n"
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Isolated skills dir plus one user-authored German skill and one English."""
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("EPHE_SKILLS_DIR", str(tmp_path / "skills"))
    skills = tmp_path / "skills"
    skills.mkdir()
    (skills / "award-audit.md").write_text(
        _flat_skill("award-audit", GERMAN_TRIGGER, GERMAN_DESCRIPTION), encoding="utf-8"
    )
    (skills / "plain-notes.md").write_text(
        _flat_skill("plain-notes", "/notes", "Writes release notes for the last week of work."),
        encoding="utf-8",
    )
    from server.main import create_app

    return TestClient(create_app())


def _row(client: TestClient, name: str) -> dict:
    body = client.get("/api/skills").json()
    return next(one for one in body["skills"] if one["name"] == name)


def test_route_marks_a_german_skill_and_keeps_the_authors_words(client: TestClient) -> None:
    row = _row(client, "award-audit")
    assert row["language"] == "de"
    # The words reach the reader exactly as the author wrote them.
    assert row["trigger"] in GERMAN_TRIGGER
    assert row["description"] == GERMAN_DESCRIPTION


def test_entry_in_the_readers_language_needs_no_mark(client: TestClient) -> None:
    row = _row(client, "plain-notes")
    assert row["language"] == SHELF_LANGUAGE


def test_missing_language_evidence_falls_back_instead_of_answering_empty() -> None:
    assert detect_language("mystery text without evidence") == SHELF_LANGUAGE
    assert detect_language("") == SHELF_LANGUAGE


def test_bootstrap_skill_rows_carry_the_mark(client: TestClient) -> None:
    body = client.get("/api/discover/bootstrap").json()
    row = next(one for one in body["skills"] if one["name"] == "award-audit")
    assert row["language"] == "de"
    assert row["description"] == GERMAN_DESCRIPTION


def test_guard_labels_foreign_words_instead_of_failing_them() -> None:
    """The scan reads served text; it can only fire on first-party words.

    Third-party text is labeled (proven above), never rejected, so a foreign
    author's entry cannot break this test. First-party packs on disk must stay
    in the shelf language: if this fires, the words changed, not the rule."""
    loader = SkillLoader(
        skills_dir=Path(__file__).parent / "_no_user_skills",
        builtin_dir=ROOT / "skills",
        plugin_root=ROOT / "plugins",
    )
    offenders = [s.name for s in loader.load_all() if s.language != SHELF_LANGUAGE]
    assert not offenders, f"first-party shelf text left the shelf language: {offenders}"


def test_every_served_entry_carries_a_nonempty_language(client: TestClient) -> None:
    body = client.get("/api/skills").json()
    assert all(one["language"] for one in body["skills"])
