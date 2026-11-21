"""P0-1: trace-shaped few-shots — the schema-conformity invariant.

Every skills/*/examples/golden.md carries canonical traces in the format
`Input / ToolCall(JSON) / Observation / Final`. This test checks it
deterministically: every argument key of a ToolCall must exist in the
parameter properties of the registered schema.
"""
from __future__ import annotations

import json
import os
import re

from core.tools import get_tool_schemas

_SKILLS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "skills")


def _schema_props() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for e in get_tool_schemas():
        fn = e.get("function", {})
        name = fn.get("name")
        props = (fn.get("parameters", {}) or {}).get("properties", {}) or {}
        if name:
            out[name] = set(props)
    return out


def _golden_files() -> list[str]:
    files = []
    for d in sorted(os.listdir(_SKILLS)):
        gm = os.path.join(_SKILLS, d, "examples", "golden.md")
        if os.path.isfile(gm):
            files.append(gm)
    return files


def test_all_skills_have_trace_format():
    files = _golden_files()
    assert files, "keine golden.md gefunden"
    for gm in files:
        body = open(gm, encoding="utf-8").read()
        assert "## Trace" in body, f"{gm}: kein Trace-Format"


def test_toolcall_args_conform_to_schema():
    props = _schema_props()
    checked = 0
    for gm in _golden_files():
        body = open(gm, encoding="utf-8").read()
        for line in body.splitlines():
            s = line.strip()
            # numbered trace steps: '2. ToolCall: {...}' → strip the prefix
            s = re.sub(r"^\d+\.\s*", "", s)
            if not s.startswith("ToolCall:"):
                continue
            payload = json.loads(s[len("ToolCall:"):].strip())
            name = payload.get("name")
            args = payload.get("arguments", {}) or {}
            assert name in props, f"{gm}: Tool {name!r} nicht in Registry"
            unknown = set(args) - props[name]
            assert not unknown, (
                f"{gm}: {name} Argument-Key(s) {sorted(unknown)} "
                f"nicht im Schema (erlaubt: {sorted(props[name])})"
            )
            checked += 1
    assert checked >= 40, f"zu wenige ToolCall-Traces geprueft: {checked}"


def test_no_rule_echo_duplication():
    """A1: the duplicated rule echo (old lines 5-11 == 16-21) is removed."""
    for gm in _golden_files():
        body = open(gm, encoding="utf-8").read()
        # In the trace format there are no 'Expected behavior:' prose blocks left.
        assert "Expected behavior:" not in body, f"{gm}: altes Regel-Echo noch vorhanden"
