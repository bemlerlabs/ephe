"""W3-39 — the poka-yoke pass over tool schemas: absolute paths, required fields.

A schema is only as mistake-proof as its weakest field. Three invariants, read
live from ``get_tool_schemas()`` (no pinned counts — the registry owns those):

  * every declared property carries a description — an undescribed field is the
    single biggest source of small-model tool errors;
  * every path-like field *names* its accepted path form — absolute or
    ~-relative for inputs, a deliberate workspace-relative directory for the
    runners, or a bare output name for ``filename`` — so the model cannot
    silently prefix a bare name and land outside the intended folder; and
  * every parameter a handler hard-requires is listed in ``required`` with a
    declared type, so the registry validator gates the call before dispatch.

The ``mcp_``-prefixed schemas are foreign (an MCP server authors them); this
contract covers only the schemas Ephe itself authors.
"""

from __future__ import annotations

import re
from typing import Any

#: Exact keys whose value is a filesystem path the model must supply.
_PATH_KEYS = frozenset(
    {
        "path",
        "paths",
        "root",
        "cwd",
        "dir",
        "directory",
        "folder",
        "target_dir",
        "source_paths",
        "asset_paths",
        "wasm_path",
    }
)

#: The path form a field must state: absolute, ~-relative, workspace-relative,
#: an allowed-root hint, resolution against the workspace, or — for a bare
#: output name — the word "file name".
_PATH_FORM = re.compile(
    r"absolute"
    r"|~-relative|~/"
    r"|workspace-relative|inside the active workspace"
    r"|inside an allowed root|resolved against the workspace"
    r"|bare name|file ?name",
    re.IGNORECASE,
)


def _schemas() -> list[dict]:
    from core.tools.registry import get_tool_schemas

    out = []
    for entry in get_tool_schemas():
        fn = entry.get("function") or {}
        name = str(fn.get("name") or "")
        if name.startswith("mcp_"):
            continue  # foreign schema, not Ephe's to police
        out.append(entry)
    return out


def _properties(function: dict) -> dict[str, Any]:
    params = function.get("parameters") or {}
    props = params.get("properties")
    return props if isinstance(props, dict) else {}


def _is_path_like(key: str) -> bool:
    k = key.lower()
    if k in _PATH_KEYS:
        return True
    return k.endswith(("_path", "_paths"))


def _iter_fields():
    for entry in _schemas():
        function = entry["function"]
        for key, spec in _properties(function).items():
            yield function["name"], key, (spec or {})


def test_every_property_carries_a_description():
    """GIVEN every advertised tool schema
    WHEN a declared property is inspected
    THEN it has a non-empty description — no silent, guessable field."""
    missing = [
        f"{name}.{key}" for name, key, spec in _iter_fields() if not str(spec.get("description") or "").strip()
    ]
    assert not missing, f"undocumented tool parameters: {missing}"


def test_path_like_parameters_name_their_path_form():
    """GIVEN a parameter that names a file, folder or output name
    WHEN its description is read
    THEN it states the accepted form (absolute/~-relative/workspace/bare name)."""
    offenders = []
    for name, key, spec in _iter_fields():
        if not _is_path_like(key) and key.lower() != "filename":
            continue
        desc = str(spec.get("description") or "")
        if not _PATH_FORM.search(desc):
            offenders.append(f"{name}.{key}: {desc!r}")
    assert not offenders, "path fields without a stated path form: " + "; ".join(offenders)


def test_required_parameters_are_declared_and_typed():
    """GIVEN a schema with a `required` list
    WHEN it is validated against its own properties
    THEN it is a duplicate-free subset and each key declares a type or enum."""
    for entry in _schemas():
        fn = entry["function"]
        params = fn.get("parameters") or {}
        required = params.get("required")
        if required is None:
            continue
        assert isinstance(required, list), f"{fn['name']}: required is not a list"
        assert len(required) == len(set(required)), f"{fn['name']}: duplicate required keys"
        props = _properties(fn)
        for key in required:
            assert key in props, f"{fn['name']}: required {key!r} is not a declared property"
            spec = props[key]
            assert spec.get("type") or spec.get("enum"), f"{fn['name']}.{key}: neither type nor enum declared"


def test_required_parameters_are_described():
    """GIVEN a parameter the handler hard-requires
    WHEN the schema is inspected
    THEN the field is described — a required field the model cannot reason about is a trap."""
    missing = []
    for entry in _schemas():
        fn = entry["function"]
        required = (fn.get("parameters") or {}).get("required") or []
        props = _properties(fn)
        for key in required:
            if not str((props.get(key) or {}).get("description") or "").strip():
                missing.append(f"{fn['name']}.{key}")
    assert not missing, f"required fields without a description: {missing}"


#: The file/artifact tools and the parameters a correct call cannot omit.
_MANDATORY = {
    "read_file": {"path"},
    "edit_file": {"path", "old_string", "new_string"},
    "write_file": {"path", "content"},
    "delete_file": {"path"},
    "list_directory": {"path"},
    "load_workspace": {"path"},
    "analyze_project": {"path"},
    "analyze_image": {"path"},
    "inspect_pptx_template": {"path"},
    "edit_pptx_template": {"template_path", "replacements"},
    "qa_pptx_deck": {"pptx_path"},
    "create_source_notebook": {"paths"},
    "query_source_notebook": {"notebook_path", "question"},
    "export_source_brief": {"notebook_path"},
    "verify_artifact": {"path"},
    "scaffold_project": {"target_dir"},
    "extract_pdf_text": {"path"},
    "format_code": {"path"},
    "run_linter": {"path"},
    "run_sandboxed_code": {"wasm_path"},
}


def _by_name() -> dict[str, dict]:
    return {entry["function"]["name"]: entry["function"] for entry in _schemas()}


def test_mandatory_path_fields_are_required():
    """GIVEN a tool whose handler cannot proceed without a target
    WHEN its schema is inspected
    THEN that target sits in `required` (the validator gates on that list)."""
    by_name = _by_name()
    from core.tools.sandbox_tools import is_available as sandbox_is_available

    # The registry advertises this one only while its optional runtime is importable, which
    # the CI install excludes on purpose. Its schema is covered where the runtime exists.
    optional = {"run_sandboxed_code": sandbox_is_available()}
    for name, expected in _MANDATORY.items():
        fn = by_name.get(name)
        if fn is None and not optional.get(name, True):
            continue
        assert fn is not None, f"tool {name!r} is no longer advertised"
        required = set((fn.get("parameters") or {}).get("required") or [])
        assert expected <= required, f"{name}: missing required {sorted(expected - required)}"


def test_file_tool_paths_pin_absolute_or_home_relative():
    """GIVEN the read/write file tools
    WHEN their `path` description is read
    THEN it names the absolute-or-~-relative form the resolver expects."""
    by_name = _by_name()
    for name in (
        "read_file",
        "edit_file",
        "write_file",
        "delete_file",
        "list_directory",
        "load_workspace",
        "analyze_image",
    ):
        desc = str((_properties(by_name[name]).get("path") or {}).get("description") or "")
        assert re.search(r"absolute", desc, re.IGNORECASE), f"{name}.path does not mention an absolute path"


def test_runner_cwd_is_marked_workspace_relative():
    """GIVEN the shell/test runners
    WHEN their `cwd` description is read
    THEN it is marked workspace-relative, so the model does not pass a foreign absolute path."""
    by_name = _by_name()
    for name in ("run_shell", "run_tests"):
        desc = str((_properties(by_name[name]).get("cwd") or {}).get("description") or "")
        assert "workspace" in desc.lower(), f"{name}.cwd is not marked workspace-relative"


def test_output_filename_fields_are_names_not_paths():
    """GIVEN a tool that emits an artifact
    WHEN its `filename` description is read
    THEN it is framed as an output name (the result line names the file), never an input path."""
    offenders = []
    for name, key, spec in _iter_fields():
        if key.lower() != "filename":
            continue
        desc = str(spec.get("description") or "")
        if not re.search(r"file ?name|artifact", desc, re.IGNORECASE):
            offenders.append(f"{name}.{key}: {desc!r}")
    assert not offenders, "output filename fields not framed as output names: " + "; ".join(offenders)
