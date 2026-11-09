"""Bridge-dispatched tool calls carry the inner tool name.

The meta-tool `tool_call` wraps an inner tool: the engine calls tool_call(name="read_file",
arguments={...}), and the host dispatches to read_file. The on_tool_start and on_tool_done
callbacks receive "read_file" — the activity line, the audit row and the tool card all say
the tool that ran, with the wrapper name hidden.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.tool_call_ids import _parse_tool_calls


class _FakeFunction:
    def __init__(self, name: str, arguments: dict | str):
        self.name = name
        self.arguments = arguments


class _FakeToolCall:
    def __init__(self, name: str, arguments: dict | str, call_id: str = "call-1"):
        self.function = _FakeFunction(name, arguments)
        self.id = call_id


class _FakeMessage:
    def __init__(self, tool_calls):
        self.tool_calls = tool_calls


class _FakeResponse:
    def __init__(self, tool_calls):
        self.message = _FakeMessage(tool_calls)


def test_parse_tool_call_resolves_the_inner_name():
    """When the engine calls tool_call, the callback sees the inner tool name."""
    inner_name = "read_file"
    inner_args = {"path": "/tmp/test.txt"}
    response = _FakeResponse([
        _FakeToolCall("tool_call", {"name": inner_name, "arguments": inner_args})
    ])

    callback = MagicMock()
    parsed, call_ids = _parse_tool_calls(response, "turn-1", callback, round_no=0)

    # The callback received the inner name, not "tool_call"
    callback.assert_called_once()
    called_name = callback.call_args[0][0]
    assert called_name == inner_name, f"expected {inner_name!r}, got {called_name!r}"

    # The parsed list also carries the inner name
    assert parsed[0][1] == inner_name


def test_parse_tool_call_with_string_arguments_resolves_the_inner_name():
    """The inner name is in args even when arguments is a JSON string."""
    import json

    inner_name = "write_file"
    inner_args = {"path": "/tmp/out.txt", "content": "hello"}
    response = _FakeResponse([
        _FakeToolCall("tool_call", json.dumps({"name": inner_name, "arguments": inner_args}))
    ])

    callback = MagicMock()
    parsed, _ = _parse_tool_calls(response, "turn-2", callback, round_no=0)

    callback.assert_called_once()
    assert callback.call_args[0][0] == inner_name
    assert parsed[0][1] == inner_name


def test_parse_non_bridge_tool_call_keeps_its_name():
    """A direct tool call (not through tool_call) keeps its own name."""
    response = _FakeResponse([
        _FakeToolCall("read_file", {"path": "/tmp/test.txt"})
    ])

    callback = MagicMock()
    parsed, _ = _parse_tool_calls(response, "turn-3", callback, round_no=0)

    callback.assert_called_once()
    assert callback.call_args[0][0] == "read_file"
    assert parsed[0][1] == "read_file"


def test_a_bridged_call_carries_the_inner_arguments_to_the_dispatcher():
    """The name is half the contract; the parameters are the other half.

    create_plugin_scaffold requires (name, description). Called through the bridge with
    the envelope left in place, the dispatcher reads `name` from the wrapper and reports
    `description` missing — the refusal live 2026-11-09 in
    /private/tmp/ephe-creation-eval/run2: three identical missing-param rows and a loop
    that stopped with reason `repair` having staged nothing.
    """
    inner_args = {
        "name": "floating-countdown",
        "description": "A floating countdown window with start, pause and reset.",
    }
    response = _FakeResponse([
        _FakeToolCall("tool_call", {"name": "create_plugin_scaffold", "arguments": inner_args})
    ])

    parsed, _ = _parse_tool_calls(response, "turn-4", MagicMock(), round_no=3)

    _idx, name, args = parsed[0]
    assert name == "create_plugin_scaffold"
    assert args == inner_args, f"the wrapper envelope reached the dispatcher: {args!r}"


def test_a_bridged_json_string_envelope_is_parsed_before_the_inner_arguments():
    """Small models send `arguments` as a JSON string; the inner dict is what runs.

    tool_call's own handler parses that string (core/tools/discovery.py). Renaming the
    call without unwrapping skips that handler, so the parse has to happen here.
    """
    import json

    inner_args = {"path": "ui/app.js", "content": "export const role = 'line';"}
    response = _FakeResponse([
        _FakeToolCall(
            "tool_call",
            json.dumps({"name": "write_plugin_source", "arguments": json.dumps(inner_args)}),
        )
    ])

    callback = MagicMock()
    parsed, _ = _parse_tool_calls(response, "turn-5", callback, round_no=1)

    assert parsed[0][1] == "write_plugin_source"
    assert parsed[0][2] == inner_args
    assert callback.call_args[0][1] == inner_args, "the audit row and card read the callback args"


def test_a_bridged_call_without_arguments_names_the_tool_and_passes_none():
    """An envelope without an `arguments` key is a call with no parameters."""
    response = _FakeResponse([_FakeToolCall("tool_call", {"name": "tool_describe"})])

    parsed, _ = _parse_tool_calls(response, "turn-6", MagicMock(), round_no=0)

    assert parsed[0][1] == "tool_describe"
    assert parsed[0][2] == {}
