"""◑ Ephe · TDD — a heading marker quoted in prose is not a section boundary.

The System Prompt section ends at the next heading. The reader searched for the
two characters anywhere in the tail, so a skill that tells the model to write
`##` headings ended its own prompt at that mention. Measured on the documents
bundle: 492 of 2871 characters served, and the Output Contract and Quality Gate
below the mention reached no model.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.skills import SkillLoader

PACK = """---
name: heading-prose
version: "1.0.0"
trigger: /heading-prose
description: "A skill that names a heading marker in its own instructions."
tools: [write_file]
---

# heading-prose

## System Prompt

Write the file.

Body:

- Use headings (`#`, `##`, `###`) and a source line.

Output Contract:
- The answer gives the path and the evidence line.

Quality Gate:
- Do not simulate a file. Every claim comes from real tool output.

## Test

**Input**: Write a note.
**Expect Tool**: write_file
"""


def _loader(tmp_path: Path) -> SkillLoader:
    pack = tmp_path / "skills" / "heading-prose"
    pack.mkdir(parents=True)
    (pack / "SKILL.md").write_text(PACK, encoding="utf-8")
    return SkillLoader(skills_dir=tmp_path / "skills", builtin_dir=tmp_path / "builtin")


def test_a_quoted_heading_marker_does_not_end_the_prompt(tmp_path):
    """GIVEN a prompt that names `##` inside inline code
    WHEN the skill loads
    THEN the instructions after that mention are still in the served prompt."""
    skill = _loader(tmp_path).load("heading-prose")

    assert "Output Contract:" in skill.system_prompt
    assert "Quality Gate:" in skill.system_prompt
    assert "real tool output" in skill.system_prompt


def test_the_next_section_heading_still_ends_the_prompt(tmp_path):
    """GIVEN a pack with a Test section after the prompt
    WHEN the skill loads
    THEN the Test section stays out of the served prompt."""
    skill = _loader(tmp_path).load("heading-prose")

    assert "## Test" not in skill.system_prompt
    assert "Expect Tool" not in skill.system_prompt


def test_the_shipped_document_skill_serves_its_whole_contract(tmp_path):
    """GIVEN the documents bundle, whose prose names the heading markers
    WHEN the pack loads from the repository
    THEN its output contract and quality gate reach the served prompt."""
    from core.skills import BUILTIN_SKILLS_DIR

    loader = SkillLoader(skills_dir=tmp_path / "none", builtin_dir=BUILTIN_SKILLS_DIR)
    skill = next(s for s in loader.load_all() if s.name == "documents")

    assert "Output Contract:" in skill.system_prompt
    assert "Do not simulate a file." in skill.system_prompt