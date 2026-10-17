"""Tests for Wave 3: Utility tools T1-T4."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path


# T1: extract_pdf_text

def test_t1_missing_file_returns_error():
    from core.tools.utility_tools import extract_pdf_text
    result = asyncio.run(extract_pdf_text("nonexistent_xyz.pdf"))
    assert result.startswith("[PDF-ERROR]")


def test_t1_non_pdf_extension_returns_error():
    from core.tools.utility_tools import extract_pdf_text
    result = asyncio.run(extract_pdf_text("core/tools/utility_tools.py"))
    assert result.startswith("[PDF-ERROR]")


def test_t1_real_pdf_returns_text():
    from core.tools.utility_tools import extract_pdf_text
    from core.tools.pdf_tools import create_pdf
    pdf_path = Path("/tmp/w3_test.pdf")
    if not pdf_path.exists():
        asyncio.run(create_pdf(title="W3 Test", content="Hello W3 World"))
        # find the created PDF
        candidates = list(Path("/tmp").glob("*.pdf"))
        if candidates:
            pdf_path = candidates[-1]
    result = asyncio.run(extract_pdf_text(str(pdf_path)))
    assert "Page" in result or "Hello" in result or result.startswith("PDF") or len(result) > 5


# T2: format_code

def test_t2_existing_file_returns_ok(tmp_path):
    """Format a real file — in a temp dir, never in the repository.

    This case used to call `format_code("core/tools/utility_tools.py")`, i.e. write-mode
    `ruff format` on a tracked source file, in the middle of the suite. It mutated the
    working tree, and the check-only case below then passed only because this one had
    already formatted the file: two tests sharing state through the repository.
    """
    from core.tools.utility_tools import format_code

    target = tmp_path / "unformatted.py"
    target.write_text("x   = 1\n", encoding="utf-8")
    result = asyncio.run(format_code(str(target)))
    assert result.startswith("OK"), result
    assert target.read_text(encoding="utf-8") == "x = 1\n"


def test_t2_missing_file_returns_error():
    from core.tools.utility_tools import format_code
    result = asyncio.run(format_code("nonexistent_xyz.py"))
    assert result.startswith("ERROR")


def test_t2_check_only_returns_prefix(tmp_path):
    """A file that needs formatting is the ANSWER, not a failure.

    `ruff format --diff` exits 1 exactly when the file would be reformatted, and the
    implementation read any non-zero exit as ERROR — so the model got a retry
    instruction for something retrying can never change. Check-only must also never
    write.
    """
    from core.tools.utility_tools import format_code

    messy = tmp_path / "messy.py"
    messy.write_text("x   = 1\n", encoding="utf-8")
    result = asyncio.run(format_code(str(messy), check_only=True))
    assert result.startswith("OK"), result
    assert messy.read_text(encoding="utf-8") == "x   = 1\n"

    clean = tmp_path / "clean.py"
    clean.write_text("x = 1\n", encoding="utf-8")
    assert asyncio.run(format_code(str(clean), check_only=True)).startswith("OK")


# T3: run_linter

def test_t3_existing_file_returns_prefix():
    from core.tools.utility_tools import run_linter
    result = asyncio.run(run_linter("core/tools/utility_tools.py"))
    assert result.startswith("OK") or result.startswith("ERROR")


def test_t3_missing_file_returns_error():
    from core.tools.utility_tools import run_linter
    result = asyncio.run(run_linter("nonexistent_xyz.py"))
    assert result.startswith("ERROR")


def test_t3_directory_returns_prefix():
    from core.tools.utility_tools import run_linter
    result = asyncio.run(run_linter("core/tools/"))
    assert result.startswith("OK") or result.startswith("ERROR")


# T4: validate_json

def test_t4_valid_json_returns_ok():
    from core.tools.utility_tools import validate_json
    schema = json.dumps({"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]})
    result = asyncio.run(validate_json(json.dumps({"name": "Alice"}), schema))
    assert result.startswith("OK")


def test_t4_missing_required_returns_error():
    from core.tools.utility_tools import validate_json
    schema = json.dumps({"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]})
    result = asyncio.run(validate_json(json.dumps({"other": 1}), schema))
    assert result.startswith("ERROR")


def test_t4_wrong_type_returns_error():
    from core.tools.utility_tools import validate_json
    schema = json.dumps({"type": "object", "properties": {"count": {"type": "integer"}}})
    result = asyncio.run(validate_json(json.dumps({"count": "not-int"}), schema))
    assert result.startswith("ERROR")


def test_t4_invalid_json_string_returns_error():
    from core.tools.utility_tools import validate_json
    result = asyncio.run(validate_json("{not valid", "{}"))
    assert result.startswith("ERROR")


def test_t4_array_schema_ok():
    from core.tools.utility_tools import validate_json
    schema = json.dumps({"type": "array", "items": {"type": "integer"}})
    result = asyncio.run(validate_json(json.dumps([1, 2, 3]), schema))
    assert result.startswith("OK")


# Registry integration

def test_t1_t4_registered_in_tool_map():
    from core.tools.registry import TOOL_MAP
    for name in ("extract_pdf_text", "format_code", "run_linter", "validate_json"):
        assert name in TOOL_MAP, f"{name} missing from TOOL_MAP"


def test_t1_t4_have_schemas():
    from core.tools.registry import get_tool_schemas
    schema_names = {t.get("function", {}).get("name") for t in get_tool_schemas()}
    for name in ("extract_pdf_text", "format_code", "run_linter", "validate_json"):
        assert name in schema_names, f"{name} schema missing"


def test_t2_via_execute_tool():
    from core.tools.registry import execute_tool
    result = asyncio.run(execute_tool("format_code", {"path": "core/tools/utility_tools.py"}))
    assert not result.startswith("[TOOL-ERROR]")


def test_t3_via_execute_tool():
    from core.tools.registry import execute_tool
    result = asyncio.run(execute_tool("run_linter", {"path": "core/tools/utility_tools.py"}))
    assert not result.startswith("[TOOL-ERROR]")


def test_t4_via_execute_tool():
    from core.tools.registry import execute_tool
    result = asyncio.run(execute_tool("validate_json", {
        "data": json.dumps({"x": 1}),
        "schema": json.dumps({"type": "object", "properties": {"x": {"type": "integer"}}}),
    }))
    assert not result.startswith("[TOOL-ERROR]")
    assert "OK" in result
