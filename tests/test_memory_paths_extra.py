"""Failure and edge coverage for the memory and compaction paths (WS6-40).

Complements tests/test_memory_failure_paths.py (store outages, checkpoint repair)
and tests/test_r25_compaction_v2.py (incremental preservation) with the
structural edges those suites leave open: the window-proportional threshold
fallbacks, the boundary of the message/token OR-condition, the Q/A-pair rules,
the ledger formatting cap, and the checkpoint plumbing.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import compaction_memory as cm
from core import conversation_compactor as cc
from core.conversation_compactor import (
    DEFAULT_THRESHOLD_TOKENS,
    _build_working_memory,
    _preserve_pairs,
    compact_history,
    default_memory_sink,
    window_threshold,
)


def _history(pairs: int, *, keyword: str = "project") -> list[dict]:
    """A history whose discarded window always holds complete Q/A pairs."""
    out: list[dict] = [{"role": "system", "content": "task"}]
    for i in range(pairs):
        out.append({"role": "user", "content": f"question {i} {keyword}"})
        out.append({"role": "assistant", "content": f"answer {i}"})
    return out


@pytest.fixture(autouse=True)
def _no_registry_assertions(monkeypatch):
    """The ledger pre-fills from the tool registry; tests need a fixed input."""
    import core.tools.registry as registry

    monkeypatch.setattr(registry, "get_assertions", lambda: [], raising=False)


# window_threshold — the P5-2 fallbacks


def test_a_raising_window_lookup_falls_back_to_the_legacy_threshold(monkeypatch):
    def boom(_model):
        raise RuntimeError("no window")

    import core.model_config as model_config

    monkeypatch.setattr(model_config, "resolve_context_window", boom)
    assert window_threshold("any-model") == DEFAULT_THRESHOLD_TOKENS


def test_a_nonpositive_window_falls_back_to_the_legacy_threshold(monkeypatch):
    import core.model_config as model_config

    for window in (0, -4096):
        monkeypatch.setattr(
            model_config, "resolve_context_window", lambda _m, w=window: (w, "probe")
        )
        assert window_threshold("any-model") == DEFAULT_THRESHOLD_TOKENS


def test_a_small_window_is_floored_at_two_thousand_and_forty_eight(monkeypatch):
    import core.model_config as model_config

    for window in (500, 1000, 2000):
        monkeypatch.setattr(
            model_config, "resolve_context_window", lambda _m, w=window: (w, "probe")
        )
        assert window_threshold("any-model") == 2048


def test_a_large_window_scales_to_eighty_percent(monkeypatch):
    import core.model_config as model_config

    monkeypatch.setattr(
        model_config, "resolve_context_window", lambda _m: (100_000, "probe")
    )
    assert window_threshold("any-model") == 80_000


def test_a_missing_model_is_looked_up_as_an_empty_string(monkeypatch):
    import core.model_config as model_config

    seen: list[str] = []

    def record(model):
        seen.append(model)
        return (16_384, "probe")

    monkeypatch.setattr(model_config, "resolve_context_window", record)
    assert window_threshold(None) == int(16_384 * 0.8)
    assert seen == [""]


# compact_history — the message and structure boundaries


def test_history_at_exactly_the_message_limit_is_untouched():
    history = _history(5)
    assert compact_history(history, max_messages=len(history)) == history


def test_an_empty_history_is_returned_unchanged():
    assert compact_history([]) == []


def test_an_empty_middle_window_returns_the_history_untouched():
    # protect_first_n + keep_recent cover every message, so there is nothing to compress.
    history = _history(20)
    compacted = compact_history(history, protect_first_n=35, keep_recent=10)
    assert compacted == history


def test_keep_recent_zero_returns_the_history_untouched():
    # history[-0:] is the whole list, which leaves the middle window empty.
    history = _history(20)
    assert compact_history(history, keep_recent=0) == history


def test_the_ledger_is_truncated_to_max_summary_chars():
    compacted = compact_history(_history(20), max_summary_chars=50)
    assert compacted[1]["role"] == "system"
    assert len(compacted[1]["content"]) == 50


def test_the_ledger_always_carries_every_section_header():
    compacted = compact_history(_history(20))
    ledger = compacted[1]["content"]
    for header in (
        "## User preferences",
        "## Project facts",
        "## Decisions",
        "## Artifacts",
        "## Open tasks and validation",
        "## Other relevant context",
    ):
        assert header in ledger


def test_messages_that_match_no_bucket_render_the_no_facts_placeholder():
    history = [{"role": "user", "content": "alpha"} for _ in range(30)]
    ledger = compact_history(history)[1]["content"]
    assert "- No stable facts recognized." in ledger


# compact_history — the token OR-condition


def test_the_token_threshold_is_exclusive(monkeypatch):
    from core.usage import estimate_tokens

    history = _history(10)
    tokens = sum(estimate_tokens(m["content"]) for m in history)
    assert compact_history(history, threshold_tokens=tokens) == history
    assert len(compact_history(history, threshold_tokens=tokens - 1)) < len(history)


def test_a_token_threshold_of_zero_switches_the_condition_off():
    history = _history(10)
    history[1]["content"] = "x" * 5000
    assert compact_history(history, threshold_tokens=0) == history


def test_many_messages_compact_even_when_the_token_threshold_is_far_above():
    history = _history(15)
    compacted = compact_history(history, threshold_tokens=10**9)
    assert len(compacted) < len(history)
    assert compacted[1]["role"] == "system"


# _preserve_pairs — the Q/A pairing rules


def _recorder():
    seen: list[tuple[str, str]] = []

    def sink(user_text: str, assistant_text: str) -> None:
        seen.append((user_text, assistant_text))

    return seen, sink


def test_consecutive_user_messages_pair_the_last_one_only():
    seen, sink = _recorder()
    _preserve_pairs(
        [
            {"role": "user", "content": "first"},
            {"role": "user", "content": "second"},
            {"role": "assistant", "content": "answer"},
        ],
        sink,
    )
    assert seen == [("second", "answer")]


def test_an_assistant_before_any_user_is_ignored():
    seen, sink = _recorder()
    _preserve_pairs(
        [
            {"role": "assistant", "content": "prologue"},
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ],
        sink,
    )
    assert seen == [("question", "answer")]


def test_content_that_is_absent_or_empty_is_skipped():
    seen, sink = _recorder()
    _preserve_pairs(
        [
            {"role": "user", "content": None},
            {"role": "user", "content": ""},
            {"role": "user"},
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ],
        sink,
    )
    assert seen == [("question", "answer")]


def test_system_messages_are_never_paired():
    seen, sink = _recorder()
    _preserve_pairs(
        [
            {"role": "system", "content": "instructions"},
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ],
        sink,
    )
    assert seen == [("question", "answer")]


def test_a_raising_sink_does_not_stop_the_later_pairs():
    seen: list[str] = []

    def sink(user_text: str, assistant_text: str) -> None:
        seen.append(user_text)
        if user_text == "question 1 project":
            raise RuntimeError("store down")

    _preserve_pairs(_history(4)[1:], sink)
    assert seen == [
        "question 0 project",
        "question 1 project",
        "question 2 project",
        "question 3 project",
    ]


# _build_working_memory — formatting


def test_identical_messages_collapse_to_one_bullet():
    ledger = _build_working_memory(
        [{"role": "user", "content": "alpha beta"}] * 2, max_chars=5000
    )
    assert ledger.count("- user: alpha beta") == 1


def test_whitespace_is_collapsed_and_blank_messages_are_dropped():
    collapsed = _build_working_memory(
        [{"role": "user", "content": "line one\n\nline   two"}], max_chars=5000
    )
    assert "- user: line one line two" in collapsed
    blank = _build_working_memory(
        [{"role": "user", "content": "   \n  "}], max_chars=5000
    )
    assert "user:" not in blank


# compaction_memory._pairs — the pairing rules of the checkpoint path


def test_a_user_without_an_answer_is_dropped():
    assert cm._pairs([{"role": "user", "content": "only"}]) == []


def test_consecutive_users_keep_only_the_last():
    pairs = cm._pairs(
        [
            {"role": "user", "content": "first"},
            {"role": "user", "content": "second"},
            {"role": "assistant", "content": "answer"},
        ]
    )
    assert pairs == [("second", "answer")]


def test_an_assistant_before_a_user_is_ignored():
    pairs = cm._pairs(
        [
            {"role": "assistant", "content": "prologue"},
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ]
    )
    assert pairs == [("question", "answer")]


def test_empty_content_is_skipped():
    pairs = cm._pairs(
        [
            {"role": "user", "content": None},
            {"role": "assistant", "content": "stray"},
            {"role": "user", "content": "question"},
            {"role": "assistant", "content": "answer"},
        ]
    )
    assert pairs == [("question", "answer")]


# compaction_memory — checkpoint plumbing


def test_a_checkpoint_file_holding_a_json_array_or_scalar_reads_as_empty(tmp_path):
    array = tmp_path / "array.json"
    array.write_text("[1, 2, 3]", encoding="utf-8")
    assert cm._load_checkpoints(array) == {}
    scalar = tmp_path / "scalar.json"
    scalar.write_text("5", encoding="utf-8")
    assert cm._load_checkpoints(scalar) == {}


def test_the_default_checkpoint_path_follows_ephe_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_DIR", str(tmp_path))
    stored = cm.preserve_compacted_pairs(
        "session-a", messages=_history(20), sink=lambda u, a: True
    )
    assert stored == 15
    assert (tmp_path / cm.CHECKPOINT_FILENAME).exists()


def test_a_sink_returning_a_non_dict_result_counts_as_stored(tmp_path):
    stored = cm.preserve_compacted_pairs(
        "session-a", messages=_history(20), sink=lambda u, a: None, path=tmp_path / "cp.json"
    )
    assert stored == 15


def test_a_run_that_preserves_nothing_writes_no_checkpoint(tmp_path):
    def boom(user_text: str, assistant_text: str):
        raise RuntimeError("store down")

    checkpoint = tmp_path / "cp.json"
    assert (
        cm.preserve_compacted_pairs(
            "session-a", messages=_history(20), sink=boom, path=checkpoint
        )
        == 0
    )
    assert not checkpoint.exists()

    short = tmp_path / "short.json"
    short_history = [{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}]
    assert (
        cm.preserve_compacted_pairs(
            "session-a", messages=short_history, sink=lambda u, a: True, path=short
        )
        == 0
    )
    assert not short.exists()


def test_sessions_share_one_checkpoint_file_independently(tmp_path):
    checkpoint = tmp_path / "cp.json"
    cm.preserve_compacted_pairs(
        "alpha", messages=_history(20), sink=lambda u, a: True, path=checkpoint
    )
    cm.preserve_compacted_pairs(
        "beta", messages=_history(20), sink=lambda u, a: True, path=checkpoint
    )
    data = json.loads(checkpoint.read_text(encoding="utf-8"))
    # Both counters live side by side; the reserved fingerprint block carries
    # their proof (count + prefix hash), never a session id.
    assert {k: data[k] for k in ("alpha", "beta")} == {"alpha": 15, "beta": 15}
    assert set(data["__fingerprints__"]) == {"alpha", "beta"}
    assert all(
        isinstance(v, str) and len(v) == 64 for v in data["__fingerprints__"].values()
    )


def test_the_checkpoint_file_and_directory_are_owner_only(tmp_path):
    checkpoint = tmp_path / "cp.json"
    cm.preserve_compacted_pairs(
        "alpha", messages=_history(20), sink=lambda u, a: True, path=checkpoint
    )
    assert (checkpoint.stat().st_mode & 0o077) == 0
    assert (tmp_path.stat().st_mode & 0o077) == 0


def test_keep_recent_zero_preserves_the_whole_history(tmp_path):
    seen: list[str] = []
    stored = cm.preserve_compacted_pairs(
        "alpha",
        messages=_history(20),
        sink=lambda u, a: seen.append(u),
        path=tmp_path / "cp.json",
        keep_recent=0,
    )
    assert stored == 20
    assert seen == [f"question {i} project" for i in range(20)]


# default_memory_sink — the productive sink wiring


def test_the_product_sink_delegates_under_the_compaction_source(monkeypatch):
    import core.auto_memory as auto_memory

    seen: list[str] = []

    def fake(user_text: str, assistant_text: str, source: str = "auto_memory"):
        seen.append(source)
        return {"stored": True, "source": source}

    monkeypatch.setattr(auto_memory, "maybe_store_turn", fake)
    assert default_memory_sink("question", "answer") == {
        "stored": True,
        "source": "compaction",
    }
    assert seen == ["compaction"]


def test_an_unbuildable_product_sink_returns_none(monkeypatch):
    monkeypatch.setattr(cc, "_default_memory_sink", lambda: None)
    assert default_memory_sink("question", "answer") is None
