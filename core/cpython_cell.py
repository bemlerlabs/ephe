"""Ephe – CPython cell: model Python inside a verified WASI cell (wave E1).

Third security layer (docs/SECURITY_THREAT_MODEL.md §7): execution. Until here
``execute_code`` ran in-process Python with full host access. With this module
the same code runs in a pinned CPython guest that Ephemora Cell equips with
fuel, memory, file and network caps.

The other half of the seam is ``core.cpython_guest``: it answers whether the
interpreter is the pinned one at all (manifest, hashes, paths). The decision
sits here — runtime choice, caps, start, report.

Seam decision (A, reasoning in docs/SANDBOX_EXECUTION.md): the library is bound
natively (``ephemora_cell.run_isolated``) instead of dressing the guest up as an
MCP tool — ``run_isolated`` already carries the guest in its own worker
subprocess (a guest crash kills the worker, not Ephe) and the cell rail would
have had the 9,216-byte stdin cap for every program.

Integrity: an installed but unfitting guest is an error case with an actionable
hint, not a silent fallback into the kernel (AGENTS.md: fail closed, never a
hidden fallback).

Guest limits (measured, see the manifest): bootstrap ~1.42G fuel / ~0.95 s
wall, ~9.0G fuel per CPU second, stdout and stderr up to ~10,000 bytes per
stream — beyond that the sink itself throws an I/O error back into the model
code, which is why ``core.cell_boot`` tees the full stream into /work and the
policy cuts it here. No socket, no fork, no OpenSSL/zlib modules.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from core.cell_output import (
    STDERR_LOG_NAME,
    STDOUT_LOG_NAME,
    excerpt,
    read_journal,
    rotate_journal,
)
from core.cpython_guest import (
    cell_ready,
    guest_dir,
    guest_installed,
    guest_state,
    manifest,
    reset_work_dir,
    session_slug,
    sweep_work_dir,
    work_dir,
)

from core.cpython_report import (  # noqa: F401  (re-exported: callers read these from here)
    format_report,
    runtime_of_report_text,
)

#: Cap of one cell run. Fuel is an engine unit, not time: measured ~9.0G fuel
#: per CPU second of guest CPU (wasmtime 47 / wasi-sdk 24 / arm64, manifest
#: provenance.measured). 20G = ~2.2 s of compute — a two-second loop is already
#: an error case at that point. The wall-clock leash is independent of it:
#: timeout_seconds.
DEFAULT_MAX_FUEL = 20_000_000_000
DEFAULT_MAX_MEMORY_MB = 256
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_IO_BUDGET_BYTES = 64 * 1024 * 1024
DEFAULT_IO_CPU_SECONDS = 20.0
#: Per FILE, set by the engine (RLIMIT_FSIZE; a write attempt above it faults
#: with EFBIG/Errno 22). Not the sum: many small files together is the case this
#: value does not see — that is what DEFAULT_WORK_QUOTA_BYTES covers.
DEFAULT_DISK_QUOTA_BYTES = 32 * 1024 * 1024
#: Per SESSION across all files in /work, set and enforced by ephe
#: (``core.cpython_guest.sweep_work_dir``). The value the settings card shows as
#: the workspace quota — a quota without enforcement would be the old number in
#: new clothes. Larger than the per-file cap so a legal file always has room.
DEFAULT_WORK_QUOTA_BYTES = 64 * 1024 * 1024

BOOT_SCRIPT = Path(__file__).with_name("cell_boot.py")

RUNTIME_CELL = "cpython-cell"
RUNTIME_KERNEL = "kernel"

#: Explicit opt-out (AGENTS.md: no silent default in either direction).
ENV_EXEC = "EPHE_CODE_EXEC"
ENV_MAX_FUEL = "EPHE_CELL_MAX_FUEL"

KERNEL_UNSANDBOXED_NOTE = (
    "runtime=kernel UNSANDBOXED — Code laeuft im Ephe-Prozess mit vollem "
    "Host-Zugriff (os, subprocess, Dateien, Netz)"
)


# Which execution carries the turn

def exec_runtime() -> str:
    """Which execution carries the next execute_code turn.

    Order: explicit choice (env) > pinned cell > kernel. The kernel is only the
    case "the guest was never installed" here — an installed but unfitting guest
    does NOT lead into the kernel (no silent fallback); it stays at RUNTIME_CELL
    and answers with a refusal.
    """
    choice = (os.environ.get(ENV_EXEC) or "").strip().lower()
    if choice == RUNTIME_KERNEL:
        return RUNTIME_KERNEL
    if choice in (RUNTIME_CELL, "cell"):
        return RUNTIME_CELL
    if cell_ready():
        return RUNTIME_CELL
    return RUNTIME_CELL if guest_installed() else RUNTIME_KERNEL


def code_runs_uncontained() -> bool:
    """True when the next execute_code turn would run OUTSIDE the cell (host access).

    The pair to ``exec_runtime()`` for the approval gate
    (``core.tools.approval``): containment is the licence for running model code
    without a dialog, so the gate reads the same choice here. It is exactly the
    condition under which ``code_kernel._execute_in_kernel`` execs on the host —
    the one case the cell does not cover — and it must equal
    ``exec_runtime() == RUNTIME_KERNEL``. That equality holds without the
    entry-hash work ``cell_ready()`` does: the env shortcut and ``guest_installed()``
    (a stat) settle it, and ``cell_ready()`` implies ``guest_installed()``. Kept
    cheap on purpose — the gate consults it on every ``execute_code``
    classification.
    """
    choice = (os.environ.get(ENV_EXEC) or "").strip().lower()
    if choice == RUNTIME_KERNEL:
        return True
    if choice in (RUNTIME_CELL, "cell"):
        return False
    return not guest_installed()


def exec_choice_error() -> str:
    """A readable error for an unintelligible opt-out value (no guessing)."""
    choice = (os.environ.get(ENV_EXEC) or "").strip().lower()
    if choice and choice not in (RUNTIME_KERNEL, RUNTIME_CELL, "cell"):
        return (
            f"{ENV_EXEC}={choice!r} ist unbekannt — gueltige Werte sind "
            f"'{RUNTIME_CELL}' (WASI-Cell) und '{RUNTIME_KERNEL}' (In-Process, "
            "ohne Sandbox). Nichts wurde ausgefuehrt."
        )
    return ""


# The execution itself

def fuel_budget() -> int:
    raw = (os.environ.get(ENV_MAX_FUEL) or "").strip()
    try:
        value = int(raw.replace("_", "")) if raw else DEFAULT_MAX_FUEL
    except ValueError:
        return DEFAULT_MAX_FUEL
    return max(value, 1)


_EXIT_NOISE = "Exited with i32 exit status 0"


def _strip_exit_noise(text: str) -> str:
    """Subtract the Wasmtime boilerplate when the guest ended cleanly.

    The guest always calls ``proc_exit(0)`` (the status lives in result.json);
    Ephemora puts the trap text in front of the guest stderr. Without this, every
    successful result would look like a crash.
    """
    idx = text.find(_EXIT_NOISE)
    if idx < 0:
        return text
    tail = text[idx + len(_EXIT_NOISE):]
    return tail.lstrip("\n")


def _normalize_status(sandbox_status: str, boot_status: str) -> str:
    """One status line that tells the truth about both layers."""
    if sandbox_status != "SUCCESS":
        return sandbox_status
    if boot_status == "ok":
        return "OK"
    if not boot_status:
        # The cell ran through but the boot report is missing — do not fake an OK.
        return "NO_REPORT"
    return f"ERROR({boot_status})"





def _run_sync(code: str, session_id: str, *, fuel: int, memory_mb: int,
              timeout_seconds: int) -> dict[str, Any]:
    from ephemora_cell import WASIConfig, run_isolated

    directory = guest_dir()
    assert directory is not None  # guest_state() has already checked
    entry = directory / str(manifest()["guest"].get("entry") or "python.wasm")
    root = directory / str(manifest()["guest"].get("stdlib_dir") or "root")
    work = work_dir(session_id)
    # Before the start, /work sits at the total cap: a run must not write on top
    # of a session that is already over quota.
    pre = sweep_work_dir(work, DEFAULT_WORK_QUOTA_BYTES)

    (work / "cell_boot.py").write_text(BOOT_SCRIPT.read_text(encoding="utf-8"), encoding="utf-8")
    (work / "program.py").write_text(code, encoding="utf-8")
    (work / "result.json").unlink(missing_ok=True)
    # The stream logs stay: they are this session's journal and every run knows
    # its own byte range. Deleting them made "fetch the rest" come back empty.
    # Only when the journal would eat the neighbours' quota is it dropped.
    rotate_journal(work / STDOUT_LOG_NAME)
    rotate_journal(work / STDERR_LOG_NAME)

    config = WASIConfig(
        max_memory_mb=memory_mb,
        max_fuel=fuel,
        timeout_seconds=timeout_seconds,
        allow_dirs=(f"{root}::/", f"{work}::/work"),
        allow_env=(("PYTHONHOME", "/usr/local"), ("PYTHONPYCACHEPREFIX", "/work/pyc")),
        io_budget_bytes=DEFAULT_IO_BUDGET_BYTES,
        io_cpu_seconds=DEFAULT_IO_CPU_SECONDS,
        disk_quota_bytes=DEFAULT_DISK_QUOTA_BYTES,
    )
    raw = dict(run_isolated(str(entry), config, args=["/work/cell_boot.py"]))
    sandbox_status = str(raw.get("status", "UNKNOWN")).split(".")[-1]
    result_file = work / "result.json"
    boot: dict[str, Any] = {}
    if result_file.is_file():
        try:
            boot = json.loads(result_file.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — the report must not fail on a broken by-product
            boot = {}
    boot_status = str(boot.get("status") or "")
    totals = {
        "stdout": int(boot.get("stdout_bytes") or 0),
        "stderr": int(boot.get("stderr_bytes") or 0),
    }
    logged = {
        "stdout": int(boot.get("stdout_log_bytes") or 0),
        "stderr": int(boot.get("stderr_log_bytes") or 0),
    }
    started = {
        "stdout": int(boot.get("stdout_log_start") or 0),
        "stderr": int(boot.get("stderr_log_start") or 0),
    }
    stdout_log = read_journal(work / STDOUT_LOG_NAME, started["stdout"], logged["stdout"])
    stderr_log = read_journal(work / STDERR_LOG_NAME, started["stderr"], logged["stderr"])
    raw_stdout = str(raw.get("stdout") or "")
    raw_stderr = _strip_exit_noise(str(raw.get("stderr") or ""))
    if stdout_log is None:
        stdout, stdout_capped = raw_stdout, False
    else:
        stdout, stdout_capped = excerpt(stdout_log, STDOUT_LOG_NAME,
                                         max(totals["stdout"], len(stdout_log)),
                                         started["stdout"])
    if stderr_log is None:
        stderr, stderr_capped = raw_stderr, False
    else:
        stderr, stderr_capped = excerpt(stderr_log, STDERR_LOG_NAME,
                                         max(totals["stderr"], len(stderr_log)),
                                         started["stderr"])
    # After the run the total cap applies again — and the report names what had
    # to give way for it. A number that is only right after cleaning is honest as
    # long as the cleaning is stated.
    post = sweep_work_dir(work, DEFAULT_WORK_QUOTA_BYTES)
    evicted = pre["evicted"] + post["evicted"]
    evicted_data = pre["evicted_data"] + post["evicted_data"]
    return {
        "runtime": RUNTIME_CELL,
        "guest_version": str((manifest().get("guest") or {}).get("version") or ""),
        "status": _normalize_status(sandbox_status, boot_status),
        "cell_status": sandbox_status,
        "guest_status": boot_status,
        "exit_code": raw.get("exit_code"),
        "fuel_consumed": raw.get("fuel_consumed"),
        "fuel_budget": fuel,
        "elapsed_ms": raw.get("elapsed_ms") or 0.0,
        "memory_mb": memory_mb,
        "timeout_seconds": timeout_seconds,
        "preopens": list(raw.get("effective_preopens") or []),
        "stdout": stdout,
        "stderr": stderr,
        "output_capped": stdout_capped or stderr_capped or bool(
            totals["stdout"] > len(stdout_log or b"") or totals["stderr"] > len(stderr_log or b"")
        ),
        "stdout_bytes": totals["stdout"],
        "stderr_bytes": totals["stderr"],
        "stdout_log_bytes": logged["stdout"],
        "stderr_log_bytes": logged["stderr"],
        "stdout_log_start": started["stdout"],
        "stderr_log_start": started["stderr"],
        # Measured: the engine counter does not see Ephe's preopen (0 while the
        # guest writes) — the total cap therefore hangs on sweep_work_dir.
        "work_bytes": post["work_bytes"],
        "work_quota_bytes": DEFAULT_WORK_QUOTA_BYTES,
        "work_evicted": evicted,
        "work_evicted_data": evicted_data,
        "work_freed_bytes": pre["freed_bytes"] + post["freed_bytes"],
        "work_over_quota": post["over_quota"],
        "io_bytes_written": raw.get("io_bytes_written"),
        "names": list(boot.get("names") or []),
        "dropped": list(boot.get("dropped") or []),
    }


async def run_python(code: str, session_id: str, *, reset: bool = False,
                     memory_mb: int = DEFAULT_MAX_MEMORY_MB,
                     timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> dict[str, Any]:
    """Run model Python in the pinned cell. Returns the report as a dict.

    Never raises for guest behaviour (errors are status values in the report);
    raises RuntimeError when the guest is missing or does not satisfy the
    manifest — exactly the case that must not end up with the in-process kernel
    as a side effect.
    """
    state = guest_state()
    if not (state["entry_ok"] and state["tree_ok"]):
        return {
            "runtime": RUNTIME_CELL,
            "status": "GUEST_UNVERIFIED",
            "stdout": "",
            "stderr": "",
            "reason": state["reason"] or "CPython guest not verified",
            "names": [],
            "dropped": [],
            "preopens": [],
        }
    if reset:
        reset_work_dir(session_id)
    fuel = fuel_budget()
    async with _async_lock_for(session_id):
        return await asyncio.to_thread(
            _run_sync, code, session_id,
            fuel=fuel, memory_mb=memory_mb, timeout_seconds=timeout_seconds,
        )


_async_locks: dict[str, asyncio.Lock] = {}


def _async_lock_for(session_id: str) -> asyncio.Lock:
    key = session_slug(session_id)
    lock = _async_locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _async_locks[key] = lock
    return lock
