"""P2: Expect-Contains tightening — distinctive tokens instead of 3-letter words.

Every `## Test` block carries an `**Expect Contains**` token of >=4 characters
that ideally only hits when the tool-/fast-path is correct (evidence anchors
such as XLSX_FILE, SVG_FILE, PNG_FILE, DOCX_FILE, or a structure anchor of the
system prompt).
"""
from __future__ import annotations

import re
from pathlib import Path

SKILLS = Path(__file__).resolve().parent.parent / "skills"


def _skill_files() -> list[str]:
    return sorted(p.name for p in SKILLS.iterdir() if (p / "SKILL.md").exists())


def _field(text: str, label: str) -> str:
    m = re.search(rf"\*\*{label}\*\*:\s*(.+)", text)
    return m.group(1).strip() if m else ""


def test_every_skill_has_distinctive_expect_contains():
    missing = []
    for name in _skill_files():
        text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        tok = _field(text, "Expect Contains")
        if len(tok) < 4:
            missing.append((name, tok))
    assert not missing, f"Expect-Contains-Token zu kurz/leer: {missing}"


def test_artifact_skills_use_evidenz_anke():
    """Artifact skills must carry an evidence anchor (an uppercase constant)."""
    anker = {"XLSX_FILE", "SVG_FILE", "PNG_FILE", "DOCX_FILE", "CHART_FILE",
             "PPTX_DECK_FILE", "PITCH_DECK_FILE", "SOURCE_NOTEBOOK_FILE"}
    for name in ("xlsx-creator", "svg-creator", "diagram-creator", "qrcode-creator",
                 "image-creator", "docx-creator"):
        text = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
        tok = _field(text, "Expect Contains")
        assert tok in anker, f"{name}: kein Evidenz-Anker, sondern {tok!r}"
