"""Tool-surface tests for generate_chart: no silent shortcuts, no fake files.

Exercises core/tools/chart_tools.py on the shapes a model actually sends — one
data point, a label containing a comma, three categories as one string, a NaN,
the same title twice — and pins that the answer either names what happened or
refuses with the index and value that caused it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core.tools.chart_tools import generate_chart


@pytest.fixture(autouse=True)
def output_dir(tmp_path, monkeypatch):
    """Charts land in tmp_path — never in the real workbench."""
    out = tmp_path / "charts"
    out.mkdir(parents=True, exist_ok=True)
    import core.engine_config as engine_config

    monkeypatch.setattr(engine_config, "artifact_output_dir", lambda: out)
    return out


def path_of(answer: str) -> Path:
    """The file a CHART_FILE: answer names (notes ride on later lines)."""
    return Path(answer.split("CHART_FILE:", 1)[1].splitlines()[0])


async def chart(**kwargs) -> str:
    args = {"chart_type": "bar", "title": "Sales", "labels": ["Q1", "Q2"], "values": [3, 5]}
    args.update(kwargs)
    return await generate_chart(**args)


class TestSinglePointShapes:
    @pytest.mark.asyncio
    async def test_one_data_point_bar_still_writes(self):
        answer = await chart(labels=["Q1"], values=[7])
        assert answer.startswith("CHART_FILE:")
        assert "<rect" in path_of(answer).read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_one_data_point_line_says_a_line_needs_two(self):
        answer = await chart(chart_type="line", labels=["Q1"], values=[7])
        assert answer.startswith("CHART_FILE:")
        assert "one data point" in answer

    @pytest.mark.asyncio
    async def test_single_slice_pie_draws_a_full_circle(self):
        answer = await chart(chart_type="pie", labels=["Only"], values=[7])
        svg = path_of(answer).read_text(encoding="utf-8")
        assert "<circle" in svg
        # An arc whose start equals its end renders as nothing: that was the
        # empty chart this case used to produce.
        assert "A150,150 0 1,1 344.0,162.0" not in svg


class TestSeriesShapes:
    @pytest.mark.asyncio
    async def test_labels_given_as_one_string_are_split(self):
        answer = await chart(labels="Q1, Q2, Q3", values=[1, 2, 3])
        assert answer.startswith("CHART_FILE:")
        svg = path_of(answer).read_text(encoding="utf-8")
        for label in ("Q1", "Q2", "Q3"):
            assert label in svg

    @pytest.mark.asyncio
    async def test_label_containing_a_comma_stays_one_label(self):
        answer = await chart(labels=["Q1, revenue", "Q2"], values=[3, 4])
        assert answer.startswith("CHART_FILE:")
        assert "Q1, revenue" in path_of(answer).read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_a_non_list_series_is_named_as_a_type_problem(self):
        answer = await chart(labels=7, values=[1])
        assert "labels must be a list" in answer

    @pytest.mark.asyncio
    async def test_empty_values_says_values_must_not_be_empty(self):
        answer = await chart(labels=["Q1"], values=[])
        assert "must not be empty" in answer

    @pytest.mark.asyncio
    async def test_length_mismatch_reports_both_counts(self):
        answer = await chart(labels=["a", "b"], values=[1])
        assert "must have equal length" in answer
        assert "2 labels, 1 values" in answer


class TestNumberGuard:
    @pytest.mark.asyncio
    async def test_non_numeric_value_names_index_and_value(self):
        answer = await chart(labels=["a", "b"], values=["x", 2])
        assert "values[0]" in answer
        assert "'x'" in answer

    @pytest.mark.asyncio
    @pytest.mark.parametrize("bad,word", [(float("nan"), "NaN"), (float("inf"), "infinite")])
    async def test_non_finite_value_is_refused_with_its_index(self, bad, word):
        answer = await chart(labels=["a", "b"], values=[bad, 2])
        assert "values[0]" in answer
        assert word in answer

    @pytest.mark.asyncio
    async def test_a_written_chart_carries_no_non_finite_coordinate(self):
        answer = await chart(labels=["a", "b"], values=[1, 2])
        assert "nan" not in path_of(answer).read_text(encoding="utf-8").lower()


class TestSilentShortcutsNowNamed:
    @pytest.mark.asyncio
    async def test_unapplied_color_is_named(self):
        answer = await chart(labels=["a"], values=[1], color="red")
        assert "not a #rrggbb hex" in answer

    @pytest.mark.asyncio
    async def test_a_valid_color_is_applied_without_a_note(self):
        answer = await chart(labels=["a"], values=[1], color="#ff0000")
        assert "note:" not in answer
        assert "#ff0000" in path_of(answer).read_text(encoding="utf-8")

    @pytest.mark.asyncio
    async def test_truncated_label_is_named(self):
        answer = await chart(labels=["x" * 40], values=[1])
        assert "shortened" in answer

    @pytest.mark.asyncio
    async def test_negative_pie_values_are_named(self):
        answer = await chart(chart_type="pie", labels=["a", "b"], values=[-5, 5])
        assert "negative" in answer

    @pytest.mark.asyncio
    async def test_unknown_type_lists_allowed_types(self):
        answer = await chart(chart_type="scatter", labels=["a"], values=[1])
        assert "unknown type" in answer
        assert "bar, line, pie" in answer


class TestFileIdentity:
    @pytest.mark.asyncio
    async def test_two_charts_with_the_same_title_write_two_files(self):
        first = await chart(title="Collide", labels=["a"], values=[1])
        second = await chart(title="Collide", labels=["a"], values=[2])
        assert first.splitlines()[0] != second.splitlines()[0]
        assert path_of(first).exists() and path_of(second).exists()

    @pytest.mark.asyncio
    async def test_title_of_only_symbols_still_names_a_real_file(self):
        answer = await chart(title="!!!", labels=["a"], values=[1])
        assert path_of(answer).name.startswith("ephe_chart_chart_")
        assert path_of(answer).exists()
