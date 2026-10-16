"""W7-6 — the context-window table against a live probe of the named engine.

``core.model_config.TIER_CONTEXT_WINDOWS`` keys a window by routing class and
its POWER row was reconciled with a live probe of the DGX engine (W3-44). This
task is the engine-named half: the wave gate says every engine number names the
engine under which it was taken, and the named engine for measurements is now
the DeepSeek API (owner decision 2026-10-12).

``core.engine_config`` carries the engine side — the field names a live engine
writes for its window, the reader over them, and a verdict that compares a tier
row with a live probe and names the engine in every branch. The cases here are
hermetic: the live probe of the DeepSeek API is recorded as a named constant
(the W3-44 pattern for the POWER row) and no network is touched.
"""
from __future__ import annotations

import pytest

from core.engine_config import (
    CONTEXT_WINDOW_FIELDS,
    WindowReconciliation,
    engine_window_name,
    reconcile_tier_window,
    window_from_model_entry,
)
from core.model_config import TIER_CONTEXT_WINDOWS, ModelTier

#: What the named engine (DeepSeek) reported to a live probe on 2026-10-12,
#: GET https://api.deepseek.com/v1/models: deepseek-flash and deepseek-v4-pro
#: both carry ``context_window = 1048576`` (field the product's own probe does
#: not read). The key came from the environment and is written to no file.
DEEPSEEK_LIVE_WINDOW = 1048576


def test_the_field_set_carries_the_named_engine_field():
    """GIVEN the canonical engine window fields
    WHEN the set is read
    THEN the DeepSeek field (context_window) and the vLLM field (max_model_len)
    are both in it — a probe of either named engine reads its own field."""
    assert "context_window" in CONTEXT_WINDOW_FIELDS
    assert "max_model_len" in CONTEXT_WINDOW_FIELDS
    assert len(set(CONTEXT_WINDOW_FIELDS)) == len(CONTEXT_WINDOW_FIELDS)


@pytest.mark.parametrize("field", CONTEXT_WINDOW_FIELDS)
def test_the_reader_takes_each_engine_field(field):
    """GIVEN one model entry per known field
    WHEN the window is read
    THEN each field is recognised (no engine's spelling is silently dropped)."""
    assert window_from_model_entry({"id": "m", field: 4096}) == 4096


def test_the_reader_reads_the_live_deepseek_shape():
    """GIVEN the entry the named engine returns
    WHEN the window is read
    THEN the reader returns the engine's number. This is the field the product's
    own probe tuple misses."""
    entry = {"id": "deepseek-v4-pro", "context_window": DEEPSEEK_LIVE_WINDOW}
    assert window_from_model_entry(entry) == DEEPSEEK_LIVE_WINDOW


def test_the_reader_refuses_non_windows():
    """GIVEN entries without a positive integer window
    WHEN the window is read
    THEN None comes back — a boolean, a zero, a negative, a string and a
    non-dict are not a window, and the caller owns the fallback."""
    assert window_from_model_entry({"context_window": True}) is None
    assert window_from_model_entry({"context_window": 0}) is None
    assert window_from_model_entry({"context_window": -5}) is None
    assert window_from_model_entry({"context_window": "8192"}) is None
    assert window_from_model_entry({"id": "m"}) is None
    assert window_from_model_entry(None) is None
    assert window_from_model_entry([1, 2]) is None


def test_engine_window_name_names_the_engine():
    """GIVEN a provider and a model
    WHEN the engine name is built
    THEN it is '<provider>/<model>'; a half-set pair falls back, and only an
    empty pair is 'unnamed' — the gate's forbidden case."""
    assert engine_window_name("openai_compatible", "deepseek-v4-pro") == (
        "openai_compatible/deepseek-v4-pro"
    )
    assert engine_window_name("", "deepseek-flash") == "deepseek-flash"
    assert engine_window_name("openai_compatible", "") == "openai_compatible"
    assert engine_window_name("", "") == "unnamed"


def test_match_when_the_row_equals_the_probe():
    """GIVEN a tier row that equals a live probe of the named engine
    WHEN they are reconciled
    THEN the verdict is 'match' and names the engine."""
    verdict = reconcile_tier_window(
        provider="openai_compatible",
        model="deepseek-v4-pro",
        table_window=1048576,
        probe_window=1048576,
    )
    assert isinstance(verdict, WindowReconciliation)
    assert verdict.verdict == "match"
    assert verdict.engine == "openai_compatible/deepseek-v4-pro"
    assert verdict.engine in verdict.detail


def test_the_shipped_power_row_is_stale_next_to_a_probe_that_differs():
    """GIVEN the shipped POWER row and a probe that reports another window
    WHEN they are reconciled
    THEN the verdict is 'table-stale' — the row no longer describes the engine."""
    row = TIER_CONTEXT_WINDOWS[ModelTier.POWER]
    verdict = reconcile_tier_window(
        provider="openai_compatible",
        model="deepseek-v4-pro",
        table_window=row,
        probe_window=row * 4,
    )
    assert verdict.verdict == "table-stale"
    assert verdict.table_window == row
    assert verdict.engine == "openai_compatible/deepseek-v4-pro"


def test_the_named_engine_reports_a_window_the_tier_table_does_not_carry():
    """GIVEN the number the DeepSeek API live-reported on 2026-10-12
    WHEN it meets the shipped POWER row
    THEN the tier table cannot equal it (the row is the DGX engine's number) and
    the reconciliation names the engine and calls the row stale."""
    row = TIER_CONTEXT_WINDOWS[ModelTier.POWER]
    entry = {"id": "deepseek-v4-pro", "context_window": DEEPSEEK_LIVE_WINDOW}
    assert window_from_model_entry(entry) == DEEPSEEK_LIVE_WINDOW
    assert row != DEEPSEEK_LIVE_WINDOW
    verdict = reconcile_tier_window(
        provider="openai_compatible",
        model="deepseek-v4-pro",
        table_window=row,
        probe_window=DEEPSEEK_LIVE_WINDOW,
    )
    assert verdict.verdict == "table-stale"
    assert verdict.engine == "openai_compatible/deepseek-v4-pro"


def test_probe_missing_names_the_engine_and_the_effective_row():
    """GIVEN an engine that names no window (unreachable, or a field it does not
    write) and a tier row that remains
    WHEN they are reconciled
    THEN the verdict is 'probe-missing' and says the tier row is the effective
    value and belongs to a different engine."""
    verdict = reconcile_tier_window(
        provider="openai_compatible",
        model="deepseek-v4-pro",
        table_window=262144,
        probe_window=None,
    )
    assert verdict.verdict == "probe-missing"
    assert verdict.probe_window is None
    assert verdict.engine in verdict.detail


def test_no_row_when_the_table_carries_no_window_for_the_engine():
    """GIVEN a live probe and no tier row for the engine
    WHEN they are reconciled
    THEN the verdict is 'no-row' and the probe is the only number — the tier
    table is keyed by routing class and carries no engine row."""
    verdict = reconcile_tier_window(
        provider="openai_compatible",
        model="deepseek-v4-pro",
        table_window=None,
        probe_window=DEEPSEEK_LIVE_WINDOW,
    )
    assert verdict.verdict == "no-row"
    assert verdict.table_window is None
    assert verdict.engine in verdict.detail


def test_every_verdict_names_the_engine():
    """GIVEN the four verdicts the reconciliation can return
    WHEN each is produced
    THEN the engine name field is set and appears in the detail — no engine
    number can leave here without its engine."""
    base = dict(provider="openai_compatible", model="deepseek-v4-pro")
    verdicts = [
        reconcile_tier_window(**base, table_window=100, probe_window=100),
        reconcile_tier_window(**base, table_window=100, probe_window=200),
        reconcile_tier_window(**base, table_window=100, probe_window=None),
        reconcile_tier_window(**base, table_window=None, probe_window=200),
    ]
    assert {v.verdict for v in verdicts} == {"match", "table-stale", "probe-missing", "no-row"}
    for v in verdicts:
        assert v.engine == "openai_compatible/deepseek-v4-pro"
        assert v.engine in v.detail
