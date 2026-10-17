"""TUI context meter (P2-9): the status bar's fill comes from the budget logic.

Parity fixtures this file pins against:
  - app/src/lib/contextMeter.test.ts (chars->token ratio, CJK 1:1, 0-window clamp)
  - server/routes/context.py (window precedence env > engine > tier > legacy)
"""
from __future__ import annotations

import asyncio

from ui.context_meter import (
    WARN_THRESHOLD,
    ContextUsage,
    estimate_context_usage,
    meter_text,
    resolve_window,
)


def test_latin_ratio_matches_the_usage_ssot():
    """GIVEN 420 Latin characters (the TypeScript meter's own fixture)
    THEN the estimate is 100 tokens, the same count core.usage returns."""
    usage = estimate_context_usage([{"role": "user", "content": "a" * 420}], 8192)
    assert usage.total == 100
    assert usage.user == 100


def test_cjk_counts_one_token_per_character():
    """GIVEN four ideographs (a contextMeter.test.ts fixture)
    THEN they count 4 tokens, one apiece."""
    assert estimate_context_usage([{"role": "user", "content": "你好世界"}], 8192).total == 4


def test_breakdown_splits_by_role_and_sums_to_total():
    """GIVEN one message per role
    THEN system/user/assistant each carry tokens and add up to the total."""
    messages = [
        {"role": "system", "content": "s" * 42},
        {"role": "user", "content": "u" * 42},
        {"role": "assistant", "content": "a" * 42},
    ]
    usage = estimate_context_usage(messages, 8192)
    assert usage.system > 0
    assert usage.user > 0
    assert usage.assistant > 0
    assert usage.total == usage.system + usage.user + usage.assistant


def test_unknown_role_counts_as_user():
    """GIVEN a role the breakdown does not know
    THEN its tokens land in the user bucket, the safe default."""
    usage = estimate_context_usage([{"role": "tool", "content": "x" * 42}], 8192)
    assert usage.user == usage.total
    assert usage.system == 0
    assert usage.assistant == 0


def test_percent_clamps_at_100_and_remaining_floors_at_zero():
    """GIVEN a session far larger than the window
    THEN percent reads 100 and remaining reads 0."""
    usage = estimate_context_usage([{"role": "user", "content": "x" * 500_000}], 8192)
    assert usage.percent == 100
    assert usage.remaining == 0


def test_zero_window_reads_full_and_stays_nan_free():
    """GIVEN a window of 0 (no engine chosen yet, the R36/B12 edge)
    THEN percent is 100 and remaining is a finite 0."""
    usage = estimate_context_usage([{"role": "user", "content": "hello"}], 0)
    assert usage.percent == 100
    assert usage.remaining == 0


def test_empty_session_is_zero_and_leaves_the_whole_window_free():
    """GIVEN an empty session
    THEN nothing is used and the full window stays free."""
    usage = estimate_context_usage([], 8192)
    assert usage.total == 0
    assert usage.percent == 0
    assert usage.remaining == 8192


def test_warn_flips_at_the_shared_threshold():
    """GIVEN the shared 75 % line
    THEN warn is False just under it and True from it on."""
    window = 1000
    just_below = ContextUsage(user=int(window * WARN_THRESHOLD) - 1, window=window)
    at_threshold = ContextUsage(user=int(window * WARN_THRESHOLD), window=window)
    assert just_below.warn is False
    assert at_threshold.warn is True
    assert WARN_THRESHOLD == 0.75


def test_meter_text_is_a_compact_one_line_chip():
    """GIVEN half of a 2k window used
    THEN the chip reads the percent and both token figures."""
    assert meter_text(ContextUsage(user=1000, window=2000)) == "ctx 50% · 1.0k/2.0k tok"


def test_env_override_wins_over_every_other_window_source(monkeypatch):
    """GIVEN EPHE_CONTEXT_WINDOW is set
    THEN resolve_window reports that number with the env source."""
    monkeypatch.setenv("EPHE_CONTEXT_WINDOW", "262144")
    assert resolve_window("any-model") == (262144, "env")


def test_window_resolution_reports_a_positive_value_with_a_known_source(monkeypatch):
    """GIVEN no env override and a model no engine or tier names
    THEN resolve_window still yields a positive window and one of the four sources."""
    monkeypatch.delenv("EPHE_CONTEXT_WINDOW", raising=False)
    window, source = resolve_window("model-that-no-tier-matches")
    assert window > 0
    assert source in {"engine", "tier", "legacy"}


def test_status_bar_renders_and_clears_the_meter_chip():
    """GIVEN a composed StatusBar
    WHEN a fill arrives and is then cleared
    THEN #status-meter carries the chip and empties again."""
    from textual.app import App, ComposeResult

    from ui.widgets import StatusBar

    class _Harness(App):
        def compose(self) -> ComposeResult:
            yield StatusBar(id="status-bar")

    async def run():
        app = _Harness()
        async with app.run_test(size=(120, 10)) as pilot:
            status = app.query_one(StatusBar)
            status.post_message(StatusBar.SetMeter(ContextUsage(user=1000, window=2000)))
            await pilot.pause()
            shown = str(status.query_one("#status-meter").render())
            status.post_message(StatusBar.SetMeter(None))
            await pilot.pause()
            cleared = str(status.query_one("#status-meter").render())
            return shown, cleared

    shown, cleared = asyncio.run(run())
    assert "ctx 50%" in shown
    assert "2.0k tok" in shown
    assert cleared == ""


def test_app_pushes_the_meter_from_the_session(tmp_session_dir, monkeypatch):
    """GIVEN a running EpheApp
    WHEN its session holds one message and the meter is posted
    THEN the status bar's meter line carries the chip."""
    from ui.app import EpheApp

    async def noop() -> None:
        return None

    async def run():
        app = EpheApp(model="test-model", reset=False)
        monkeypatch.setattr(app, "_async_check_connection", noop)
        monkeypatch.setattr(app, "_async_init_mcp", noop)
        async with app.run_test(size=(120, 30)) as pilot:
            app._session = [{"role": "user", "content": "x" * 420}]
            app._post_context_meter()
            await pilot.pause()
            return str(app.query_one("#status-meter").render())

    assert "ctx " in asyncio.run(run())
