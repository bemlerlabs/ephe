"""
◑ Ephe – core.tools.source_tools (Phase 0.8 TDD)
tests/test_tools_source.py

Covers create_source_notebook, query_source_notebook, export_source_brief.

Given / When / Then – strict adherence.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.tools.source_tools import (
    create_source_notebook,
    export_source_brief,
    query_source_notebook,
)


class TestCreateSourceNotebook:

    @pytest.mark.asyncio
    async def test_creates_notebook_with_paths(self):
        """
        GIVEN  a list of file paths
        WHEN   create_source_notebook(paths=["~/doc.md"]) is called
        THEN   the return contains "Quellen-Notebook erstellt"  # language-gate: ignore (German product label asserted verbatim below)
        AND    core.source_notebook.create_source_notebook_index was called
        """
        with patch("core.tools.source_tools.create_source_notebook_index", new_callable=MagicMock) as mock_index, \
             patch("core.tools.source_tools.format_notebook_created") as mock_fmt:
            mock_index.return_value = {"status": "created", "notebook_id": "nb123"}
            mock_fmt.return_value = "Quellen-Notebook erstellt (ID: nb123)"

            result = await create_source_notebook(paths=["~/doc.md"])

            assert "Quellen-Notebook erstellt" in result
            mock_index.assert_called_once()
            assert mock_index.call_args[1]["paths"] == ["~/doc.md"]

    @pytest.mark.asyncio
    async def test_passes_extensions(self):
        """
        GIVEN  an extensions filter
        WHEN   create_source_notebook is called with extensions=[".pdf"]
        THEN   the parameter is passed through correctly
        """
        with patch("core.tools.source_tools.create_source_notebook_index", new_callable=MagicMock) as mock_index, \
             patch("core.tools.source_tools.format_notebook_created") as mock_fmt:
            mock_index.return_value = {}
            mock_fmt.return_value = "OK"

            await create_source_notebook(paths=["~/docs"], extensions=[".pdf"])

            assert mock_index.call_args[1].get("extensions") == [".pdf"]


class TestQuerySourceNotebook:

    @pytest.mark.asyncio
    async def test_returns_answer_for_question(self):
        """
        GIVEN  a notebook path and a question
        WHEN   query_source_notebook(notebook_path, question) is called
        THEN   the return contains the answer with source references
        """
        with patch("core.tools.source_tools.query_source_notebook_index", new_callable=MagicMock) as mock_query, \
             patch("core.tools.source_tools.format_notebook_query") as mock_fmt:
            mock_query.return_value = {"answer": "Laut Quelle S001: ..."}
            mock_fmt.return_value = "Antwort: Laut Quelle S001: ..."

            result = await query_source_notebook(
                notebook_path="/tmp/nb.json",
                question="Was steht in S001?"
            )

            assert "S001" in result
            mock_query.assert_called_once()
            assert mock_query.call_args[1]["question"] == "Was steht in S001?"

    @pytest.mark.asyncio
    async def test_passes_max_chunks(self):
        """
        GIVEN  max_chunks=3
        WHEN   query_source_notebook is called
        THEN   the parameter is passed through
        """
        with patch("core.tools.source_tools.query_source_notebook_index", new_callable=MagicMock) as mock_query, \
             patch("core.tools.source_tools.format_notebook_query") as mock_fmt:
            mock_query.return_value = {}
            mock_fmt.return_value = "OK"

            await query_source_notebook(
                notebook_path="/tmp/nb.json",
                question="Test?",
                max_chunks=3
            )

            assert mock_query.call_args[1]["max_chunks"] == 3


class TestExportSourceBrief:

    @pytest.mark.asyncio
    async def test_returns_brief_file_path(self):
        """
        GIVEN  a notebook path
        WHEN   export_source_brief(notebook_path) is called
        THEN   the return contains "SOURCE_BRIEF_FILE:"
        """
        with patch("core.tools.source_tools.export_source_brief_file", new_callable=MagicMock) as mock_export:
            mock_export.return_value = "/path/to/brief.md"

            result = await export_source_brief(notebook_path="/tmp/nb.json")

            assert "SOURCE_BRIEF_FILE:" in result
            assert "/path/to/brief.md" in result
