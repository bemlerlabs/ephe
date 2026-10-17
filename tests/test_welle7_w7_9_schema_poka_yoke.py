"""W7-9 — poka-yoke over the tool schemas: a malformed call is refused, named.

Every schema the registry serves rejects a malformed call through one validator,
and the refusal it returns is NAMED: it carries a repair class in brackets and it
states the repair it wants. Both the class and the hint are rendered from the
registry's repair taxonomy, the single mechanism — so the prose around the token
carries no behaviour, and a reader reads the token.

These tests read the live schema array and the taxonomy. Nothing here pins a tool
name, a count, or the words around the token: they iterate whatever the registry
advertises and assert the shape of the refusal, so adding or moving a tool does
not red this file.
"""
from __future__ import annotations

import asyncio
import inspect

from core.tools.registry import (
    _REPAIR_TAXONOMY,
    _classify_tool_error,
    _typed_repair,
    _validate_tool_arguments,
    execute_tool,
    get_tool_schemas,
)

#: A key no schema declares and no handler accepts — the hallucinated parameter
#: a small model invents, and (parked under one key) the payload that failed to
#: parse. Named once so the tests share one sentinel.
_UNDECLARED = "__w79_undeclared__"


def _schemas() -> list[dict]:
    return get_tool_schemas()


def _params(function: dict) -> dict:
    params = function.get("parameters")
    return params if isinstance(params, dict) else {}


def _properties(function: dict) -> dict:
    properties = _params(function).get("properties")
    return properties if isinstance(properties, dict) else {}


def _sample(spec: dict) -> object:
    """A value that satisfies one property spec (enum first, then the type)."""
    enum = spec.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    declared = spec.get("type")
    if isinstance(declared, list):
        declared = next((t for t in declared if t != "null"), declared[0] if declared else None)
    return {
        "string": "x", "number": 1.0, "integer": 1,
        "boolean": True, "array": [], "object": {},
    }.get(declared, "x")


def _satisfying(function: dict) -> dict:
    """A call that satisfies every declared property, so only the injected fault
    can be the reason a refusal fires."""
    return {key: _sample(spec) for key, spec in _properties(function).items()}


def _handler_rejects_extras(name: str) -> bool:
    """True when the handler would TypeError on an undeclared keyword.

    Mirrors what the validator introspects: no ``**kwargs`` and the sentinel is
    absent from the signature. An un-introspectable handler is treated as
    tolerant (it is not a case this file can assert on).
    """
    from core.tools.registry import TOOL_MAP

    func = TOOL_MAP.get(name)
    if func is None:
        return False
    try:
        parameters = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return False
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()):
        return False
    return _UNDECLARED not in parameters


class TestTaxonomyIsTheMechanism:
    def test_every_class_the_validator_emits_is_a_taxonomy_entry(self):
        """GIVEN a refusal WHEN its class is read THEN the taxonomy names it."""
        assert _REPAIR_TAXONOMY, "the repair taxonomy is empty"
        for name, entry in _REPAIR_TAXONOMY.items():
            assert name == entry.name, (name, entry.name)
            assert entry.hint.strip(), f"{name} carries no repair hint"

    def test_the_repair_hint_in_the_refusal_comes_from_the_taxonomy(self, monkeypatch):
        """GIVEN a taxonomy hint WHEN a refusal is rendered THEN it is that hint.

        This is the mechanism, not the wording: swap the taxonomy entry and the
        refusal changes with it.
        """
        from core.tools import registry

        sentinel = "REPAIR-SENTINEL-7f3a"
        monkeypatch.setitem(
            registry._REPAIR_TAXONOMY,
            "missing-param",
            registry._RepairClass("missing-param", sentinel + " {names}"),
        )
        error = registry._validate_tool_arguments("read_file", {})
        assert error and sentinel in error, error

    def test_classification_reads_the_class_token_not_the_prose(self):
        """GIVEN a refusal WHEN its prose is garbled THEN the class still reads."""
        for cls in _REPAIR_TAXONOMY:
            garbled = f"[TOOL-ERROR] tool [{cls}]: %%% nonsense %%%. Repair: %%%."
            assert _classify_tool_error(garbled) == cls

    def test_an_unclassifiable_string_has_no_repair(self):
        """GIVEN a string with no class token WHEN read THEN nothing is repaired."""
        assert _classify_tool_error("[TOOL-ERROR] x: some other error") is None
        assert _typed_repair("read_file", {}, "[TOOL-ERROR] x: some other error") is None

    def test_repair_re_derives_the_parameters_not_the_message(self):
        """GIVEN a token-only refusal WHEN repaired THEN the schema supplies the fix."""
        repaired = _typed_repair(
            "manage_tasks", {"action": "__not_in_enum__"},
            "[TOOL-ERROR] t [enum-mismatch]: whatever. Repair: whatever.",
        )
        assert repaired is not None
        properties = next(
            f["function"] for f in _schemas() if f["function"]["name"] == "manage_tasks"
        )
        enum = _properties(properties)["action"]["enum"]
        assert repaired["action"] == enum[0]


class TestEverySchemaRefusesNamed:
    def test_a_missing_required_parameter_is_refused_named(self):
        """GIVEN schemas with required args WHEN called empty THEN each is named."""
        checked = 0
        for entry in _schemas():
            function = entry["function"]
            if not _params(function).get("required"):
                continue
            checked += 1
            error = _validate_tool_arguments(function["name"], {})
            assert error, f"{function['name']} accepted an empty call"
            assert _classify_tool_error(error) == "missing-param", error
        assert checked, "no schema declares a required parameter — the gate vanished"

    def test_a_value_outside_a_declared_enum_is_refused_named(self):
        """GIVEN a schema with an enum WHEN it is violated THEN it is named."""
        checked = 0
        for entry in _schemas():
            function = entry["function"]
            for key, spec in _properties(function).items():
                enum = spec.get("enum")
                if not isinstance(enum, list) or not enum:
                    continue
                checked += 1
                arguments = _satisfying(function)
                arguments[key] = {"__w79_outside_enum__": True}  # never a member
                error = _validate_tool_arguments(function["name"], arguments)
                assert error, f"{function['name']}.{key} accepted a non-member"
                assert _classify_tool_error(error) == "enum-mismatch", error
        assert checked, "no schema declares an enum — the gate vanished"

    def test_a_parameter_the_handler_cannot_take_is_refused_named(self):
        """GIVEN a hallucinated key WHEN the handler would reject it THEN it is named.

        The unnamed alternative is ``func(**arguments)`` raising
        ``unexpected keyword argument`` — the observed failure mode this
        mistake-proofs away.
        """
        checked = 0
        for entry in _schemas():
            function = entry["function"]
            name = function["name"]
            if not _properties(function) or not _handler_rejects_extras(name):
                continue
            checked += 1
            arguments = _satisfying(function)
            arguments[_UNDECLARED] = "x"
            error = _validate_tool_arguments(name, arguments)
            assert error, f"{name} accepted a key its handler would reject"
            assert _classify_tool_error(error) == "unknown-param", error
            # the repair drops exactly the undeclared key and keeps the rest
            repaired = _typed_repair(name, arguments, error)
            assert repaired is not None
            assert _UNDECLARED not in repaired
            assert _validate_tool_arguments(name, repaired) is None
        assert checked, "no handler rejects an undeclared keyword — the gate vanished"

    def test_a_valid_call_from_the_schema_is_still_accepted(self):
        """GIVEN a satisfying call WHEN validated THEN nothing is refused."""
        for entry in _schemas():
            function = entry["function"]
            assert _validate_tool_arguments(function["name"], _satisfying(function)) is None


class TestRefusalShape:
    def test_the_refusal_carries_the_token_and_a_repair_clause(self):
        """GIVEN a malformed call WHEN refused THEN the shape is uniform."""
        checked = 0
        for entry in _schemas():
            function = entry["function"]
            if not _params(function).get("required"):
                continue
            checked += 1
            error = _validate_tool_arguments(function["name"], {}) or ""
            assert error.startswith("[TOOL-ERROR] "), error
            assert f"[{_classify_tool_error(error)}]" in error, error
            assert "repair:" in error.lower(), error
        assert checked

    def test_execute_tool_serves_the_named_refusal_when_no_repair_is_possible(self):
        """GIVEN an unparsed payload WHEN executed THEN the model gets the name.

        The repair refuses to fill required parameters next to a parked key (an
        empty program is not a call the model made), so the named refusal is what
        the loop shows — never a bare ``unexpected keyword argument``.
        """
        envelope = {"_raw": '{"code": "print(1)"}'}
        result = asyncio.run(execute_tool("execute_code", dict(envelope)))
        assert "[TOOL-ERROR]" in result
        assert f"[{_classify_tool_error(result)}]" in result
        assert "unexpected keyword argument" not in result
