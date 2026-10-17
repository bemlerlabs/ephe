"""
◑ Ephe – core.tools.chart_tools (Phase 0.8 TDD)
tests/test_tools_chart.py

Covers generate_chart (SVG generation).

Given / When / Then, followed strictly.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core.tools.chart_tools import _generate_svg_chart, generate_chart


class TestGenerateChart:

    @pytest.mark.asyncio
    async def test_returns_chart_file_path(self):
        """
        GIVEN  chart_type="bar", labels/values
        WHEN   generate_chart is called
        THEN   the return contains "CHART_FILE:"
        """
        with patch("core.tools.chart_tools.Path.home") as mock_home, \
             patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_text"):
            mock_home.return_value = Path("/tmp/fake_home")

            result = await generate_chart(
                chart_type="bar",
                title="Test Chart",
                labels=["A", "B"],
                values=[10, 20],
            )

            assert "CHART_FILE:" in result

    @pytest.mark.asyncio
    async def test_raises_on_mismatched_labels_values(self):
        """
        GIVEN  labels and values have different lengths
        WHEN   generate_chart is called
        THEN   the return contains an error message
        """
        with patch("core.tools.chart_tools.Path.home") as mock_home:
            mock_home.return_value = Path("/tmp/fake_home")

            result = await generate_chart(
                chart_type="bar",
                title="Test",
                labels=["A"],
                values=[10, 20],
            )

            assert "must have equal length" in result

    @pytest.mark.asyncio
    async def test_rejects_unknown_chart_type(self):
        """
        GIVEN  chart_type="unknown"
        WHEN   generate_chart is called
        THEN   the return contains "unknown type"
        """
        with patch("core.tools.chart_tools.Path.home") as mock_home, \
             patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_text"):
            mock_home.return_value = Path("/tmp/fake_home")

            result = await generate_chart(
                chart_type="unknown",
                title="Test",
                labels=["A"],
                values=[10],
            )

            assert "unknown type" in result


class TestGenerateSvgChart:

    def test_bar_chart_contains_rect(self):
        """
        GIVEN  chart_type="bar"
        WHEN   _generate_svg_chart is called
        THEN   the SVG file written contains <rect> elements
        """
        written = []
        def _fake_write(self, text, **kwargs):
            written.append(text)
        with patch("core.tools.chart_tools.Path.home") as mock_home, \
             patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_text", _fake_write):
            mock_home.return_value = Path("/tmp/fake_home")
            result = _generate_svg_chart("bar", "Bar Chart", ["A", "B"], [10, 20])
        assert "CHART_FILE:" in result
        assert any("<rect" in w for w in written), "SVG sollte <rect> enthalten"

    def test_line_chart_contains_polyline(self):
        """
        GIVEN  chart_type="line"
        WHEN   _generate_svg_chart is called
        THEN   the SVG file written contains <polyline>
        """
        written = []
        def _fake_write(self, text, **kwargs):
            written.append(text)
        with patch("core.tools.chart_tools.Path.home") as mock_home, \
             patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_text", _fake_write):
            mock_home.return_value = Path("/tmp/fake_home")
            result = _generate_svg_chart("line", "Line Chart", ["A", "B"], [10, 20])
        assert "CHART_FILE:" in result
        assert any("<polyline" in w for w in written), "SVG sollte <polyline> enthalten"

    def test_pie_chart_contains_path(self):
        """
        GIVEN  chart_type="pie"
        WHEN   _generate_svg_chart aufgerufen
        THEN   the written SVG file holds a <path>
        """
        written = []
        def _fake_write(self, text, **kwargs):
            written.append(text)
        with patch("core.tools.chart_tools.Path.home") as mock_home, \
             patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_text", _fake_write):
            mock_home.return_value = Path("/tmp/fake_home")
            result = _generate_svg_chart("pie", "Pie Chart", ["A", "B"], [30, 70])
        assert "CHART_FILE:" in result
        assert any("<path" in w for w in written), "SVG sollte <path> enthalten"

    def test_bar_chart_contains_single_value(self):
        """
        GIVEN  a single data point
        WHEN   _generate_svg_chart("bar", ...)
        THEN   the result carries CHART_FILE:
        """
        with patch("core.tools.chart_tools.Path.home") as mock_home, \
             patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_text"):
            mock_home.return_value = Path("/tmp/fake_home")
            result = _generate_svg_chart("bar", "Single", ["Only"], [42])
        assert "CHART_FILE:" in result

    def test_empty_values_returns_error(self):
        """
        GIVEN  an empty values list
        WHEN   _generate_svg_chart aufgerufen
        THEN   the result carries the error
        """
        with patch("core.tools.chart_tools.Path.home") as mock_home, \
             patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_text"):
            mock_home.return_value = Path("/tmp/fake_home")
            result = _generate_svg_chart("bar", "Empty", ["A"], [])
        assert "must have equal length" in result or "must not be empty" in result
