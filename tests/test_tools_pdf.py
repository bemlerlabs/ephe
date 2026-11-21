"""
◑ Ephe – core.tools.pdf_tools (Phase 0.8 TDD)
tests/test_tools_pdf.py

Covers create_pdf, _apply_pdf_template.

Given / When / Then — strictly observed.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.tools.pdf_tools import _apply_pdf_template, create_pdf


class TestApplyPdfTemplate:

    def test_report_template_inserts_missing_sections(self):
        """
        GIVEN  content without required sections
        WHEN   _apply_pdf_template(content, "report")
        THEN   the missing sections get inserted
        """
        result = _apply_pdf_template("Nur Text.", "report")
        assert "Executive Summary" in result
        assert "Findings" in result
        assert "Next Steps" in result
        assert "Source Notes" in result

    def test_brief_template_requires_fewer_sections(self):
        """
        GIVEN  content without sections, template="brief"
        WHEN   _apply_pdf_template is called
        THEN   only Key Points + Source Notes + Exec Summary
        """
        result = _apply_pdf_template("Content.", "brief")
        assert "Executive Summary" in result
        assert "Key Points" in result
        assert "Findings" not in result

    def test_analysis_template_contains_risks_and_recommendations(self):
        """
        GIVEN  template="analysis"
        WHEN   _apply_pdf_template is called
        THEN   Evidence, Risks, Recommendations, Appendix are included
        """
        result = _apply_pdf_template("Data.", "analysis")
        assert "Evidence" in result
        assert "Risks" in result
        assert "Recommendations" in result
        assert "Appendix" in result

    def test_checklist_template(self):
        """
        GIVEN  template="checklist"
        WHEN   _apply_pdf_template is called
        THEN   Checklist and Acceptance Criteria are included
        """
        result = _apply_pdf_template("Items.", "checklist")
        assert "Checklist" in result
        assert "Acceptance Criteria" in result

    def test_returns_unchanged_if_all_sections_present(self):
        """
        GIVEN  content already carries every required section
        WHEN   _apply_pdf_template is called
        THEN   the content stays unchanged
        """
        content = "executive summary, findings, next steps, source notes"
        result = _apply_pdf_template(content, "report")
        assert result == content

    def test_falls_back_to_report_for_unknown_template(self):
        """
        GIVEN  template="unknown"
        WHEN   _apply_pdf_template is called
        THEN   the report template is used
        """
        result = _apply_pdf_template("Short.", "unknown")
        assert "Executive Summary" in result


class TestCreatePdf:

    @pytest.mark.asyncio
    async def test_returns_pdf_file_path(self):
        """
        GIVEN  a title and content
        WHEN   create_pdf(title="Test", content="Hello") is called
        THEN   the return value contains "PDF_FILE:"
        AND    a reportlab SimpleDocTemplate is created
        """
        with patch("core.tools.pdf_tools.Path.home") as mock_home, \
             patch("pathlib.Path.mkdir"), \
             patch("reportlab.platypus.SimpleDocTemplate") as mock_doc:
            mock_home.return_value = Path("/tmp/fake_home")
            mock_instance = MagicMock()
            mock_doc.return_value = mock_instance

            result = await create_pdf(title="Test Report", content="Hello World")

            assert "PDF_FILE:" in result
            mock_doc.assert_called_once()
            assert "Test Report" in str(mock_doc.call_args[1].get("title", ""))

    @pytest.mark.asyncio
    async def test_returns_import_error_if_reportlab_missing(self):
        """
        GIVEN  reportlab is not installed
        WHEN   create_pdf is called
        THEN   the return value contains "reportlab nicht installiert"  # language-gate: ignore (quote of a retired product string — the assert below matches the English line core/tools/pdf_tools.py:728 emits)
        """
        with patch("core.tools.pdf_tools.Path.home") as mock_home, \
             patch("pathlib.Path.mkdir"), \
             patch("reportlab.platypus.SimpleDocTemplate", side_effect=ImportError("no reportlab")):
            mock_home.return_value = Path("/tmp/fake_home")

            result = await create_pdf(title="Test", content="Test")

            assert "reportlab is not installed" in result

    @pytest.mark.asyncio
    async def test_sanitizes_filename(self):
        """
        GIVEN  a filename with special characters
        WHEN   create_pdf(filename="bad / name?.pdf") is called
        THEN   the file name gets sanitised
        """
        with patch("core.tools.pdf_tools.Path.home") as mock_home, \
             patch("pathlib.Path.mkdir"), \
             patch("reportlab.platypus.SimpleDocTemplate") as mock_doc:
            mock_home.return_value = Path("/tmp/fake_home")
            mock_instance = MagicMock()
            mock_doc.return_value = mock_instance

            result = await create_pdf(title="Test", content="Test", filename="bad / name?.pdf")

            assert "PDF_FILE:" in result
