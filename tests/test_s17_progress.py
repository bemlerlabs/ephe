"""S17: the turn reports progress and ends with an answer."""
from __future__ import annotations

from core.loop_observability import LoopObserver, bind_observer, note_tool_round, reset_observer
from core.quality import normalize_tool_result
from server.routes.chat import (
    PROGRESS_HEARTBEAT_SECONDS,
    _make_stream_callbacks,
    search_budget_answer,
)


def _callbacks():
    events: list[dict] = []
    on_chunk, on_thinking, on_start, on_done, on_phase = _make_stream_callbacks(
        events.append, [], [], "s1", "t1"
    )
    return events, on_start, on_done


def test_start_and_done_frames_carry_round_query_and_providers():
    events, on_start, on_done = _callbacks()
    observer = LoopObserver(budget_cap=10, turn_id="t1")
    token = bind_observer(observer)
    try:
        note_tool_round(2)
        on_start("web_search", {"query": "dgx spark"}, "c1")
        started = [e for e in events if e["type"] == "progress"][-1]
        assert started["phase"] == "tool_start"
        assert started["round"] == 2
        assert started["round_cap"] == 10
        assert started["query"] == "dgx spark"
        assert started["turn_id"] == "t1"
        assert started["elapsed_ms"] == 0

        on_done("web_search", "Providers: startpage 200, google 403\n[1] hit", "c1")
        done = [e for e in events if e["type"] == "progress"][-1]
        assert done["phase"] == "tool_done"
        assert done["providers"] == "startpage 200, google 403"
        assert done["elapsed_ms"] >= 0
    finally:
        reset_observer(token)


def test_the_heartbeat_is_shorter_than_ten_seconds():
    assert PROGRESS_HEARTBEAT_SECONDS == 5.0


def test_a_mute_search_turn_still_ends_with_its_sources():
    row = normalize_tool_result(
        "web_search", "Providers: startpage 200\n[1] Spark\n    URL: https://example.test/x"
    )
    answer = search_budget_answer([row])
    assert "search budget" in answer
    assert "startpage 200" in answer
    assert "https://example.test/x" in answer


def test_a_turn_without_a_search_gets_no_fallback_answer():
    row = normalize_tool_result("read_file", "file contents")
    assert search_budget_answer([row]) == ""
    assert search_budget_answer([]) == ""
