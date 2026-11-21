"""
◑ Ephe – parity round J, the quality gate for brief PDFs
tests/test_brief_quality_j.py

Covers the three judge findings of the PDF gate (2026-09-09):
P1: Key-Findings placeholder with no resolving evidence appendix.
P2: dangling Source-Notes reference "(see above)".
P2: duplicated H1 (cover title + content H1).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.tools.factory_tools import _compose_brief_markdown
from core.tools.pdf_tools import create_pdf


class TestComposeBriefMarkdown:

    def test_unprefixed_evidence_lines_become_facts(self):
        """
        GIVEN  evidence as a one-line str() list without a bullet prefix
        WHEN   _compose_brief_markdown is called
        THEN   the line shows as a finding, the placeholder stays unset
        """
        evidence = "[{'title': 'Alpha result for the project', 'body': 'Some detail here'}]"
        out = _compose_brief_markdown("T", "topic", evidence)
        assert "Alpha result for the project" in out
        assert "See the Evidence Appendix below." not in out

    def test_empty_evidence_resolves_to_named_fallback_and_appendix(self):
        """
        GIVEN  empty evidence
        WHEN   _compose_brief_markdown is called
        THEN   the triggering appendix exists and the reference points at it
        """
        out = _compose_brief_markdown("T", "topic", "")
        assert "## Evidence Appendix" in out
        assert "No evidence collected." in out

    def test_source_notes_use_real_sources_else_appendix_reference(self):
        """
        GIVEN  evidence with a '## Source:' line
        WHEN   _compose_brief_markdown is called
        THEN   Source Notes names the source file
        """
        evidence = "## Source: __init__.py\n\nlong docstring line longer than twenty five"
        out = _compose_brief_markdown("T", "topic", evidence)
        assert "- Source: __init__.py" in out

    def test_appendix_contains_raw_evidence_lines(self):
        """
        GIVEN  evidence with two non-blank lines
        WHEN   _compose_brief_markdown is called
        THEN   both lines stand in the evidence appendix
        """
        evidence = "## Source: a.md\nfirst long enough line here"
        out = _compose_brief_markdown("T", "topic", evidence)
        tail = out.split("## Evidence Appendix", 1)[1]
        assert "first long enough line here" in tail


class TestCreatePdfNoDuplicateTitle:

    @pytest.mark.asyncio
    async def test_leading_h1_equal_title_is_not_duplicated(self):
        """
        GIVEN  content starts with '# {title}' (the cover already renders the title)
        WHEN   create_pdf is called
        THEN   the title text appears in the story exactly once
        """
        with patch("core.tools.pdf_tools.Path.home") as mock_home, \
             patch("pathlib.Path.mkdir"), \
             patch("reportlab.platypus.SimpleDocTemplate") as mock_doc:
            mock_home.return_value = Path("/tmp/fake_home")
            mock_instance = MagicMock()
            mock_doc.return_value = mock_instance
            title = "Projekt-Audit: zz-audit-pro"
            content = f"# {title}\n\n## Executive Summary\nsome body text long enough"

            await create_pdf(title=title, content=content)

            story = mock_instance.build.call_args[0][0]
            texts = [getattr(el, "text", None) for el in story]
            hits = [t for t in texts if t == title]
            assert len(hits) == 1


class TestKeepTogetherAndSanitize:

    @pytest.mark.asyncio
    async def test_headings_are_wrapped_in_keep_together(self):
        """
        GIVEN  content with a heading plus following blocks
        WHEN   create_pdf runs
        THEN   KeepTogether groups in the story hold the heading plus at least 1 following block
        """
        with patch("core.tools.pdf_tools.Path.home") as mock_home, \
             patch("pathlib.Path.mkdir"), \
             patch("reportlab.platypus.SimpleDocTemplate") as mock_doc:
            mock_home.return_value = Path("/tmp/fake_home")
            mock_instance = MagicMock()
            mock_doc.return_value = mock_instance
            content = ("## Recommended Next Steps\nsome body text long enough here\n"
                       "- bullet one long enough ok\n\nnext para line long enough yes")

            await create_pdf(title="T", content=content)

            story = mock_instance.build.call_args[0][0]
            groups = [el for el in story if type(el).__name__ == "KeepTogether"]
            assert len(groups) >= 1
            first = groups[0]._content
            assert first is not None and len(list(first)) >= 2

    def test_evidence_glyph_artifacts_are_normalized(self):
        """
        GIVEN  evidence with ■/¶ artifacts and repeated whitespace
        WHEN   _compose_brief_markdown is called
        THEN   the artifacts are normalized (■→'-', ¶ dropped, whitespace collapsed)
        """
        evidence = "## Source: a.md\n■ Cyber Audit Pro Author\nPackaging Projects ¶ This tutorial\nVersion:  1.0.0  A lightweight"
        out = _compose_brief_markdown("T", "topic", evidence)
        assert "■" not in out
        assert "¶" not in out
        assert "  " not in out.split("```")[0]
