"""W3-67 — the tool registry contract: every schema valid, every handler reachable.

Two gates, no pinned counts. A schema must be a well-formed function tool whose name
the registry can dispatch; a handler must be reachable — through the advertised schema
array, as a declared alias of a schema-backed tool (the opencode marker names), or as a
tool a plugin owns and currently hides. Counts and name sets live in the registry, not
here, so adding or moving a tool does not red this file.
"""

from __future__ import annotations

import inspect
import re
from typing import Any

#: A function name the model can address: a snake/camel identifier, bounded length.
_SCHEMA_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")

#: The JSON-schema primitive types a parameter may declare.
_JSON_TYPES = frozenset({"string", "number", "integer", "boolean", "array", "object"})

#: The stub a parameter of each type is filled with when a satisfying call is built.
_TYPE_SAMPLE: dict[object, object] = {
    "string": "x",
    "number": 1.0,
    "integer": 1,
    "boolean": True,
    "array": [],
    "object": {},
}


def _schemas() -> list[dict]:
    from core.tools.registry import get_tool_schemas

    return get_tool_schemas()


def _params(function: dict) -> dict[str, Any]:
    params = function.get("parameters")
    return params if isinstance(params, dict) else {}


def _properties(function: dict) -> dict[str, Any]:
    properties = _params(function).get("properties")
    return properties if isinstance(properties, dict) else {}


def _plugin_gated(name: str) -> bool:
    """True when a plugin owns the tool and is currently off (so it is hidden)."""
    try:
        from core import plugin_runtime

        gate = plugin_runtime.tool_gate(name)
    except Exception:  # noqa: BLE001 — the gate is best-effort, absence means not gated
        return False
    return (not gate.visible) and bool(getattr(gate, "plugin", None))


def _sample_value(spec: dict) -> object:
    """A value that satisfies one property spec (enum first, then the type)."""
    enum = spec.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    declared = spec.get("type")
    if isinstance(declared, list):
        declared = next((t for t in declared if t != "null"), declared[0])
    return _TYPE_SAMPLE.get(declared, "x")


def _satisfying_args(function: dict) -> dict:
    return {key: _sample_value(spec) for key, spec in _properties(function).items()}


class TestSchemaValidity:
    def test_every_entry_is_a_well_formed_function_tool(self):
        """GIVEN the schema array WHEN each entry is read THEN it is an OpenAI function tool."""
        for entry in _schemas():
            function = entry.get("function")
            assert entry.get("type") == "function", entry
            assert isinstance(function, dict), entry
            name = function.get("name")
            assert isinstance(name, str) and _SCHEMA_NAME.match(name), name
            description = function.get("description")
            assert isinstance(description, str) and description.strip(), name

    def test_every_parameter_object_declares_an_object_schema(self):
        """GIVEN a function schema WHEN its parameters are read THEN they are an object schema."""
        for entry in _schemas():
            function = entry["function"]
            params = function.get("parameters")
            if params is None:
                continue
            assert isinstance(params, dict), function["name"]
            assert params.get("type") == "object", function["name"]
            properties = params.get("properties", {})
            assert isinstance(properties, dict), function["name"]
            required = params.get("required", [])
            assert isinstance(required, list), function["name"]

    def test_no_required_key_sits_outside_properties(self):
        """GIVEN a required list WHEN it is checked THEN every key exists in properties."""
        for entry in _schemas():
            function = entry["function"]
            params = function.get("parameters") or {}
            properties = params.get("properties") or {}
            orphans = [
                key for key in params.get("required", []) if key not in properties
            ]
            assert not orphans, f"{function['name']} requires undeclared {orphans}"

    def test_every_property_names_a_json_type_or_a_non_empty_enum(self):
        """GIVEN a property spec WHEN it is read THEN it names a JSON type or an enum."""
        for entry in _schemas():
            function = entry["function"]
            properties = (function.get("parameters") or {}).get("properties") or {}
            for key, spec in properties.items():
                where = f"{function['name']}.{key}"
                assert isinstance(spec, dict), where
                enum = spec.get("enum")
                if enum is not None:
                    assert isinstance(enum, list) and enum, where
                    continue
                declared = spec.get("type")
                if isinstance(declared, list):
                    assert declared, where
                    declared = declared[0]
                assert declared in _JSON_TYPES, f"{where} declares type {declared!r}"

    def test_schema_names_are_unique(self):
        """GIVEN the schema array WHEN names are counted THEN none repeats."""
        names = [entry["function"]["name"] for entry in _schemas()]
        duplicates = sorted({n for n in names if names.count(n) > 1})
        assert not duplicates, f"duplicate schema names: {duplicates}"


class TestHandlerReachability:
    def test_every_schema_name_has_a_handler(self):
        """GIVEN a schema WHEN it is called by name THEN a handler or an MCP tool exists."""
        from core.tools.mcp_client import get_mcp_tools
        from core.tools.registry import TOOL_MAP

        mcp_names = set(get_mcp_tools())
        for entry in _schemas():
            name = entry["function"]["name"]
            assert name in TOOL_MAP or name in mcp_names, (
                f"{name} has no dispatch target"
            )

    def test_every_registered_handler_is_callable(self):
        """GIVEN TOOL_MAP WHEN each value is read THEN it is a callable, not None."""
        from core.tools.registry import TOOL_MAP

        for name, handler in TOOL_MAP.items():
            assert callable(handler), f"{name} maps to a non-callable"

    def test_every_handler_is_reachable(self):
        """GIVEN a handler WHEN reachability is checked THEN it is visible, an alias, or gated."""
        from core.tools.registry import TOOL_MAP
        from core.tools.sandbox_tools import is_available as sandbox_is_available

        # A handler behind an optional runtime is advertised only while that runtime is
        # importable. Asking the predicate the registry itself asks keeps this a contract
        # instead of a claim about the machine the suite happens to run on.
        optional_runtime_absent = {"run_sandboxed_code": not sandbox_is_available()}
        schema_backed = {entry["function"]["name"] for entry in _schemas()}
        unreachable = []
        for name, handler in TOOL_MAP.items():
            if name in schema_backed:
                continue
            if optional_runtime_absent.get(name):
                continue
            aliases = {n for n in schema_backed if TOOL_MAP.get(n) is handler}
            if aliases or _plugin_gated(name):
                continue
            unreachable.append(name)
        assert not unreachable, (
            f"handlers neither schema-backed nor aliases nor plugin-gated: {unreachable}"
        )

    def test_alias_handlers_share_a_schema_backed_function(self):
        """GIVEN the marker aliases WHEN resolved THEN each points at a schema-backed handler."""
        from core.tools.registry import TOOL_MAP

        schema_backed = {entry["function"]["name"] for entry in _schemas()}
        for name in ("bash", "read", "edit"):
            handler = TOOL_MAP.get(name)
            if handler is None:
                continue  # the alias set is owned by the registry; a dropped one is not ours
            canonical = {n for n in schema_backed if TOOL_MAP.get(n) is handler}
            assert canonical, (
                f"alias '{name}' is not the same object as a schema-backed tool"
            )

    def test_core_tools_stay_dispatchable_and_visible(self):
        """GIVEN CORE_TOOLS WHEN the array is built THEN each is a live, visible name."""
        from core.tools.discovery import CORE_TOOLS
        from core.tools.registry import TOOL_MAP

        schema_backed = {entry["function"]["name"] for entry in _schemas()}
        for name in CORE_TOOLS:
            assert name in TOOL_MAP, f"core tool '{name}' has no handler"
            assert name in schema_backed, (
                f"core tool '{name}' is missing from the array"
            )
            assert not _plugin_gated(name), f"core tool '{name}' is hidden by a plugin"

    def test_meta_tools_are_in_the_array(self):
        """GIVEN the discovery meta tools WHEN the array is read THEN all three are present."""
        from core.tools.discovery import META_TOOL_NAMES

        schema_backed = {entry["function"]["name"] for entry in _schemas()}
        assert META_TOOL_NAMES <= schema_backed, META_TOOL_NAMES - schema_backed

    def test_every_handler_accepts_its_declared_arguments(self):
        """GIVEN a schema WHEN its handler is inspected THEN it binds every property or **kwargs."""
        from core.tools.registry import TOOL_MAP

        missing: list[str] = []
        for entry in _schemas():
            function = entry["function"]
            handler: Any = TOOL_MAP.get(function["name"])
            if handler is None:
                continue
            if not callable(handler):
                continue
            try:
                signature = inspect.signature(handler)
            except (TypeError, ValueError):
                continue  # a builtin or C-callable has no introspectable signature
            takes_kwargs = any(
                p.kind is p.VAR_KEYWORD for p in signature.parameters.values()
            )
            if takes_kwargs:
                continue
            properties = (function.get("parameters") or {}).get("properties") or {}
            for key in properties:
                if key not in signature.parameters:
                    missing.append(f"{function['name']}.{key}")
        assert not missing, f"declared arguments no handler accepts: {missing}"

    def test_validator_accepts_a_schema_satisfying_call(self):
        """GIVEN args built from a schema WHEN validated THEN the registry accepts them."""
        from core.tools.registry import _validate_tool_arguments

        for entry in _schemas():
            function = entry["function"]
            if not (function.get("parameters") or {}).get("properties"):
                continue
            error = _validate_tool_arguments(
                function["name"], _satisfying_args(function)
            )
            assert error is None, f"{function['name']}: {error}"

    def test_validator_rejects_a_missing_required_argument(self):
        """GIVEN a tool with required args WHEN none are passed THEN validation fails loudly."""
        from core.tools.registry import _validate_tool_arguments

        checked = 0
        for entry in _schemas():
            function = entry["function"]
            required = (function.get("parameters") or {}).get("required") or []
            if not required:
                continue
            checked += 1
            error = _validate_tool_arguments(function["name"], {})
            assert error is not None, f"{function['name']} accepted an empty call"
            assert "[TOOL-ERROR]" in error, error
        assert checked, (
            "no schema declares a required parameter — the registry lost its gate"
        )
