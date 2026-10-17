"""An unparsed tool-call payload must not become an executed call.

core.model_provider._parse_json_arguments parks a payload it cannot JSON-parse
under a single key ("_raw"). The P1-2 missing-param repair in core.tools.registry
then filled the required parameters next to that key, so the call reached the tool
with both: execute_code ran with empty code and raised over the parked key, and
write_file would have run with an empty path and empty content. Measured in the
product's own audit log: four tool_exec lines, detail
"execute_code() got an unexpected keyword argument '_raw'"
(2026-10-06 19:51, 2026-10-09 22:05, 2026-10-09 22:11, 2026-10-10 08:12 UTC).
"""
from __future__ import annotations

import asyncio

from core.tools.registry import (
    _classify_tool_error,
    _typed_repair,
    _validate_tool_arguments,
    execute_tool,
)

ENVELOPE = {"_raw": '{"code":"import os\nprint(os.path.isdir(\\"/work\\"))"}'}


def _missing_param_error(name: str) -> str:
    """The validation error an unparsed payload produces (repair class checked,
    not the message text — the text is under a language sweep)."""
    err = _validate_tool_arguments(name, ENVELOPE) or ""
    assert _classify_tool_error(err) == "missing-param"
    return err


def test_unparsed_envelope_is_not_repaired_into_an_empty_program():
    assert _typed_repair("execute_code", dict(ENVELOPE), _missing_param_error("execute_code")) is None


def test_unparsed_envelope_is_not_repaired_into_an_empty_file_write():
    assert _typed_repair("write_file", dict(ENVELOPE), _missing_param_error("write_file")) is None


def test_execute_tool_never_shows_the_parked_key_as_a_keyword():
    result = asyncio.run(execute_tool("execute_code", dict(ENVELOPE)))
    assert "unexpected keyword argument" not in result


def test_a_payload_without_the_envelope_is_still_repaired():
    """The P1-2 repair keeps working where nothing failed to parse."""
    err = _validate_tool_arguments("generate_chart", {}) or ""
    assert _classify_tool_error(err) == "missing-param"
    repaired = _typed_repair("generate_chart", {}, err)
    assert repaired and all(key in repaired for key in ("chart_type", "title"))
