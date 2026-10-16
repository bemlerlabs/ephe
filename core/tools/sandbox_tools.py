"""Ephe – run_sandboxed_code: WASM execution in the Ephemora cell sandbox.

Security model (docs/SECURITY_THREAT_MODEL.md §7, three layers):
    injection guard = content, approval gate = intent, Ephemora cell = execution.

Ephemora cell is a deliberate opt-in dependency (``ephe[sandbox]``):
- Lazy import like edge_tts (RAM): wasmtime is only loaded on real use.
- Fail-closed: without the package the tool refuses (install hint), runtime unchanged.
- Execution always via ``run_isolated()`` (OS walls: rlimits, I/O watchdog,
  hard kill) — never via the library's in-process default.
- No ``allow_dirs`` parameter: the default preopen deny stays untouchable;
  whoever needs file access uses the approval-gate path via run_shell.
"""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

# Defaults (identical to the Ephemora cell README)

DEFAULT_MAX_MEMORY_MB = 128
DEFAULT_MAX_FUEL = 1_000_000
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_IO_CPU_SECONDS = 2.0
DEFAULT_IO_BUDGET_BYTES = 64 * 1024 * 1024

INSTALL_HINT = (
    "⚠️ Security: sandbox not installed. Install `pip install 'ephe[sandbox]'` (Ephemora Cell) to activate run_sandboxed_code."
)


def is_available() -> bool:
    """Lightweight opt-in check (without a wasmtime import) — for the schema register."""
    return importlib.util.find_spec("ephemora_cell") is not None


def _ephemora_api():
    """Lazy import: returns ``(WASIConfig, run_isolated)`` or ``None`` (fail-closed)."""
    try:
        from ephemora_cell import WASIConfig, run_isolated
        return WASIConfig, run_isolated
    except ImportError:
        return None


async def run_sandboxed_code(
    wasm_path: str,
    max_fuel: int = DEFAULT_MAX_FUEL,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Runs a WASM module isolated (no network, no exec/fork, limits).

    Returns an observability report (status/fuel/elapsed/preopens + stdout/stderr),
    so ToolCallDisplay/ActivityFeed can show the execution.
    """
    api = _ephemora_api()
    if api is None:
        return INSTALL_HINT
    WASIConfig, run_isolated = api

    path = Path(wasm_path)
    if not path.is_file():
        return f"⚠️ Security: WASM module not found: {wasm_path}"

    config = WASIConfig(
        max_memory_mb=DEFAULT_MAX_MEMORY_MB,
        max_fuel=max_fuel,
        timeout_seconds=timeout_seconds,
        io_cpu_seconds=DEFAULT_IO_CPU_SECONDS,
        io_budget_bytes=DEFAULT_IO_BUDGET_BYTES,
    )
    try:
        result = await asyncio.to_thread(run_isolated, str(path), config)
    except Exception as exc:  # noqa: BLE001 — tool boundary: never pass through to the chat pipeline
        return f"⚠️ Sandbox error: {exc.__class__.__name__}: {exc}"

    status = str(result.get("status", "UNKNOWN")).split(".")[-1]
    fuel = result.get("fuel_consumed")
    elapsed = result.get("elapsed_ms") or 0.0
    lines = [
        f"[Sandbox-Execution] status={status} exit={result.get('exit_code')} "
        f"fuel={fuel} elapsed={elapsed:.1f}ms "
        f"preopens={result.get('effective_preopens', [])}"
    ]
    if result.get("stdout"):
        lines.append("stdout (Cap 10 KB):")
        lines.append(str(result["stdout"]).rstrip())
    if result.get("stderr"):
        lines.append("stderr:")
        lines.append(str(result["stderr"]).rstrip())
    return "\n".join(lines)


SANDBOX_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "run_sandboxed_code",
            "description": (
                "Executes a WASM module in the Ephemora Cell WASI sandbox: no network, no exec/fork, fuel/memory/timeout limits, signed execution report. For LLM-generated or untrusted code instead of run_shell. Requires opt-in install `ephe[sandbox]`."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "wasm_path": {"type": "string", "description": "Absolute or ~-relative path to the .wasm file to execute."},
                    "max_fuel": {
                        "type": "integer",
                        "description": f"CPU budget in fuel units (default {DEFAULT_MAX_FUEL})",
                    },
                    "timeout_seconds": {
                        "type": "integer",
                        "description": f"Wall-clock timeout in seconds (default {DEFAULT_TIMEOUT_SECONDS})",
                    },
                },
                "required": ["wasm_path"],
            },
        },
    },
]
