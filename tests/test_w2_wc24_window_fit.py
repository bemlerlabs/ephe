"""WC-24: context-window fitting at the boundary — drops and tool schemas.

`_fit_messages_to_window` (core/chat_context.py) is the hard server-side ceiling
(P0-2). Two edges went unpinned:

* the array it measures must price provider message objects. The tool loop appends
  ``response.message`` (assistant content + tool_call arguments) as an object, and
  ``serialize_prompt`` skips non-dicts — so those turns cost 0 tokens and the cap
  leaked past the window;
* the visible tool array ships with every call and shares the window with the
  messages, but its cost was never charged against it.

Both are exercised here; the surrounding drop/floor/window<=0 behaviour is pinned
so a later change cannot quietly move the boundary.
"""
from __future__ import annotations

import types

import pytest

from core import chat_context as cc
from core.usage import estimate_tokens, serialize_prompt


@pytest.fixture(autouse=True)
def _clean_module_state(monkeypatch):
    """Each test starts from an empty reserve, an empty schema cache, and a pinned counter.

    The two globals live on the module, and ``_tools_for_messages`` sets the reserve on the
    running context — a leak would silently shift the next test's boundary.

    The counter is pinned because ``estimate_tokens`` prefers tiktoken whenever it is
    importable and falls back to the two-bucket heuristic otherwise. BPE prices a repeated
    filler run far below the heuristic, so a runner that carries tiktoken moves every
    boundary in this file. This module pins the fitting; the counter stays free to differ.
    """
    from core import usage as usage_mod

    monkeypatch.setattr(usage_mod, "_get_tiktoken_encoding", lambda: None)
    cc._TOOL_SCHEMA_TOKENS.set(None)
    cc._TOOL_SCHEMA_CACHE = None
    yield
    cc._TOOL_SCHEMA_TOKENS.set(None)
    cc._TOOL_SCHEMA_CACHE = None


def _history(count: int, *, size: int = 800) -> list[dict]:
    return [{"role": "user", "content": f"{i}" + "u" * size} for i in range(count)]


# Drops at the boundary

class TestDropsAtTheBoundary:

    def test_window_at_or_below_zero_is_a_noop(self):
        """GIVEN a non-positive window WHEN the fit runs THEN nothing is trimmed."""
        messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "u" * 4000}]
        assert cc._fit_messages_to_window(messages, 0) == 0
        assert cc._fit_messages_to_window(messages, -5) == 0
        assert [m["role"] for m in messages] == ["system", "user"]

    def test_within_window_drops_nothing(self):
        """GIVEN a prompt inside the window WHEN the fit runs THEN 0 drops, order kept."""
        messages = [{"role": "system", "content": "S"}, {"role": "user", "content": "u" * 100}]
        assert cc._fit_messages_to_window(messages, 2000) == 0
        assert [m["role"] for m in messages] == ["system", "user"]

    def test_exactly_at_the_window_is_not_over(self):
        """GIVEN a prompt whose estimate equals the window WHEN the fit runs
        THEN it stays — the cap trips on strictly greater, not on equal."""
        messages = [{"role": "system", "content": "S"}] + _history(6)
        window = estimate_tokens(serialize_prompt(messages))
        assert cc._fit_messages_to_window(messages, window) == 0
        assert len(messages) == 7

    def test_over_window_trims_from_the_front_and_keeps_system_and_newest(self):
        """GIVEN a prompt above the window WHEN the fit runs THEN the oldest
        history entries go, the system block and the newest message stay, and the
        estimate lands back inside the window."""
        messages = [{"role": "system", "content": "S" * 400}] + _history(12)
        trimmed = cc._fit_messages_to_window(messages, 2000)
        assert trimmed > 0
        assert messages[0]["role"] == "system"
        assert messages[-1]["content"].startswith("11")
        assert estimate_tokens(serialize_prompt(messages)) <= 2000

    def test_two_message_floor_stands_even_when_still_over_budget(self):
        """GIVEN only the system block and one oversized user message WHEN the fit
        runs THEN 0 are dropped and the floor (system + newest) stands, even though
        the estimate is still over budget — there is nothing left to trim."""
        messages = [{"role": "system", "content": "S" * 4000}, {"role": "user", "content": "u" * 4000}]
        assert cc._fit_messages_to_window(messages, 100) == 0
        assert [m["role"] for m in messages] == ["system", "user"]

    def test_object_assistant_messages_are_counted(self):
        """GIVEN a non-dict assistant message (the tool-loop shape) WHEN the fit
        runs THEN it prices its content and trims — before the fix it cost 0 tokens
        and the cap leaked."""
        assistant = types.SimpleNamespace(content="A" * 4000, tool_calls=[])
        messages = [{"role": "system", "content": "S"}, assistant, {"role": "user", "content": "u"}]
        trimmed = cc._fit_messages_to_window(messages, 500)
        assert trimmed == 1
        assert len(messages) == 2
        assert isinstance(messages[0], dict) and messages[0]["role"] == "system"

    def test_object_tool_call_arguments_are_counted(self):
        """GIVEN a non-dict assistant message carrying large tool_call arguments
        WHEN the fit runs THEN the arguments count toward the estimate too."""
        bare = types.SimpleNamespace(content="", tool_calls=[])
        fat = types.SimpleNamespace(
            content="",
            tool_calls=[{"id": "1", "function": {"name": "write_file", "arguments": {"path": "x" * 4000}}}],
        )
        small = cc._fit_messages_to_window(
            [{"role": "system", "content": "S"}, bare, {"role": "user", "content": "u"}], 500
        )
        large = cc._fit_messages_to_window(
            [{"role": "system", "content": "S"}, fat, {"role": "user", "content": "u"}], 500
        )
        assert small == 0
        assert large == 1


# The tool schema's window share

class TestToolSchemaShare:

    def test_explicit_tool_array_is_reserved_from_the_window(self):
        """GIVEN a messages list that fits the window WHEN the visible tool array is
        passed THEN its estimated cost is reserved and more is trimmed."""
        messages = [{"role": "system", "content": "S" * 400}] + _history(12)
        tools = [{"function": {"name": f"t{i}", "description": "d" * 4000}} for i in range(20)]
        plain = cc._fit_messages_to_window(list(messages), 2000)
        reserved = cc._fit_messages_to_window(list(messages), 2000, tools=tools)
        assert cc._tool_schema_tokens(tools) > 0
        assert reserved > plain

    def test_recorded_array_reserves_without_an_explicit_argument(self, monkeypatch):
        """GIVEN _tools_for_messages recorded the array this context ships WHEN the
        fit runs without ``tools`` THEN that array's cost is reserved."""
        big = [{"function": {"name": f"t{i}", "description": "d" * 4000}} for i in range(20)]
        monkeypatch.setattr(cc, "_cached_tool_schemas", lambda: big)
        cc._tools_for_messages(
            [{"role": "user", "content": "hi"}],
            allowed_tool_names=[t["function"]["name"] for t in big],
        )
        messages = [{"role": "system", "content": "S" * 400}] + _history(12)
        reserved = cc._fit_messages_to_window(list(messages), 2000)
        cc._TOOL_SCHEMA_TOKENS.set(None)
        plain = cc._fit_messages_to_window(list(messages), 2000)
        assert reserved > plain

    def test_empty_tool_array_reserves_nothing(self):
        """GIVEN an empty array WHEN the fit runs THEN nothing extra is trimmed."""
        messages = [{"role": "system", "content": "S" * 400}] + _history(12)
        assert cc._fit_messages_to_window(list(messages), 2000, tools=[]) == cc._fit_messages_to_window(
            list(messages), 2000
        )

    def test_cached_schemas_are_served_within_ttl_and_refreshed_after(self, monkeypatch):
        """GIVEN the tool-schema cache WHEN the TTL has not elapsed THEN the same
        list is served; WHEN it has elapsed THEN the registry is asked again."""
        calls: list[int] = []

        def fake_schemas():
            calls.append(1)
            return [{"function": {"name": "read_file", "description": "ok"}}]

        monkeypatch.setattr(cc, "get_tool_schemas", fake_schemas)
        clock = {"t": 1000.0}
        monkeypatch.setattr(cc.time, "monotonic", lambda: clock["t"])

        first = cc._cached_tool_schemas()
        second = cc._cached_tool_schemas()
        assert first is second
        assert len(calls) == 1

        clock["t"] += cc.TOOL_SCHEMA_CACHE_TTL_SECONDS + 1
        third = cc._cached_tool_schemas()
        assert third == first
        assert len(calls) == 2
