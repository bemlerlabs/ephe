"""W2: run_sandboxed_code — LLM-generated code in the Ephemora Cell WASI sandbox.

Security model (three layers, docs/SECURITY_THREAT_MODEL.md §7):
  injection guard = content, approval gate = intent, Ephemora Cell = execution.

Ephemora Cell is an OPT-IN dependency (`ephe[sandbox]`). Without
the package the tool must fail-closed and refuse, while the rest of the runtime
stays unchanged (lazy import, no hard import — compare edge_tts).
"""
from __future__ import annotations

import pytest
from pathlib import Path

import core.tools.sandbox_tools as sandbox_tools
from core.tools.approval import ApprovalPolicy, classify_tool

FIXTURES = Path(__file__).parent / "fixtures" / "sandbox"
HELLO = FIXTURES / "hello.wasm"
EXPLOIT = FIXTURES / "exploit.wasm"
CODE_REVIEW = FIXTURES / "code_review.wasm"

needs_ephemora = pytest.importorskip.__name__  # noqa: F841  (marker applied per test below)


def _ephemora_installed() -> bool:
    try:
        import ephemora_cell  # noqa: F401
        return True
    except ImportError:
        return False


live = pytest.mark.skipif(not _ephemora_installed(), reason="ephemora-cell nicht installiert (opt-in)")


# Fail-closed without the package (always runs)

@pytest.mark.asyncio
async def test_fail_closed_without_package(monkeypatch):
    """Without ephemora-cell: execution is refused, no traceback, install hint."""
    monkeypatch.setattr(sandbox_tools, "_ephemora_api", lambda: None)
    result = await sandbox_tools.run_sandboxed_code(str(HELLO))
    assert "not installed" in result
    assert "ephemora" in result.lower()


# Registry/approval integration (always runs)

def test_tool_registered():
    from core.tools.registry import TOOL_MAP
    assert "run_sandboxed_code" in TOOL_MAP


def test_tool_classified_as_mutating():
    """Sandbox execution counts conservatively as mutating → approval gate required."""
    classification = classify_tool("run_sandboxed_code")
    assert classification.is_mutating is True
    assert classification.auto_approve_by_default is False


def test_schema_present():
    schemas = {s["function"]["name"] for s in sandbox_tools.SANDBOX_TOOL_SCHEMAS}
    assert "run_sandboxed_code" in schemas


# Defaults

def test_config_defaults_match_ephemora_readme():
    from core.tools.sandbox_tools import (
        DEFAULT_MAX_FUEL,
        DEFAULT_MAX_MEMORY_MB,
        DEFAULT_TIMEOUT_SECONDS,
    )
    assert DEFAULT_MAX_MEMORY_MB == 128
    assert DEFAULT_MAX_FUEL == 1_000_000
    assert DEFAULT_TIMEOUT_SECONDS == 30


# Live execution (only with an installed ephemora-cell)

@live
@pytest.mark.asyncio
async def test_hello_wasm_succeeds():
    result = await sandbox_tools.run_sandboxed_code(str(HELLO))
    assert "SUCCESS" in result
    assert "Hello from Ephemora Cell!" in result


@live
@pytest.mark.asyncio
async def test_exploit_module_blocked():
    """exploit.wasm pulls in blocked WASI functions → no SUCCESS, the reason stays visible."""
    result = await sandbox_tools.run_sandboxed_code(str(EXPLOIT))
    assert "SUCCESS" not in result.split("stdout", 1)[0]  # the status line is not SUCCESS
    assert "Blocked" in result or "ERROR" in result


@live
@pytest.mark.asyncio
async def test_fuel_exhaustion_reported():
    """Too little fuel for code_review.wasm → FUEL_EXHAUSTED in the report."""
    result = await sandbox_tools.run_sandboxed_code(str(CODE_REVIEW), max_fuel=100)
    assert "FUEL_EXHAUSTED" in result


@live
@pytest.mark.asyncio
async def test_missing_wasm_path_rejected():
    result = await sandbox_tools.run_sandboxed_code("/nonexistent/modul.wasm")
    assert "not found" in result


@live
@pytest.mark.asyncio
async def test_execution_report_contains_observability_fields():
    """Status, fuel and elapsed are in the report (the basis for ToolCallDisplay/ActivityFeed)."""
    result = await sandbox_tools.run_sandboxed_code(str(HELLO))
    assert "fuel=" in result
    assert "status=" in result
