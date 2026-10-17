"""Ephe – the cell's policy truth for settings, doctor and panel (wave I1).

Third security layer (docs/SANDBOX_EXECUTION.md): whatever runs inside the cell
is capped. This module is the *only* place the settings card, `ephe doctor` and
the status page take their numbers from — so no panel shows a cap that
`core.cpython_cell` does not write into the WASIConfig.

Two rules live here and must not be invented somewhere else:

- report == enforced: the values come from the runner (`fuel_budget()`, the
  `DEFAULT_*` caps), not from a second table.
- proven on the artefact: the cell licence comes from the installed package
  (Dist-Info). A hardcoded string would be a licence claim into thin air the
  moment another version carries another licence. The PyPI ladder behind this
  is the watch of `tests/test_dependency_license_fence.py`.
"""
from __future__ import annotations

from typing import Any

from core.cell_output import (
    GUEST_FORWARD_BYTES,
    GUEST_TEE_CAP_BYTES,
    OUTPUT_CAP_BYTES,
    SINK_CEILING_BYTES,
)
from core.cpython_cell import (
    DEFAULT_DISK_QUOTA_BYTES,
    DEFAULT_IO_BUDGET_BYTES,
    DEFAULT_IO_CPU_SECONDS,
    DEFAULT_MAX_MEMORY_MB,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_WORK_QUOTA_BYTES,
    exec_runtime,
    fuel_budget,
)
from core.cpython_guest import guest_state, manifest


def cell_runtime_license() -> str:
    """What the cell runtime costs and which version is installed."""
    try:
        from importlib.metadata import metadata, version

        lizenz = (metadata("ephemora-cell").get("License") or "unbekannt").strip()
        return f"{lizenz} (ephemora-cell {version('ephemora-cell')})"
    except Exception:  # noqa: BLE001 — the card must not be missing over an unknown licence
        return "ephemora-cell: Version unbestimmt"


def policy_snapshot() -> dict[str, Any]:
    """Effective cell policy — the same values run_python writes into the WASIConfig."""
    state = guest_state()
    return {
        "runtime": exec_runtime(),
        "max_fuel": fuel_budget(),
        "max_memory_mb": DEFAULT_MAX_MEMORY_MB,
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "io_cpu_seconds": DEFAULT_IO_CPU_SECONDS,
        "io_budget_bytes": DEFAULT_IO_BUDGET_BYTES,
        "disk_quota_bytes": DEFAULT_DISK_QUOTA_BYTES,
        "work_quota_bytes": DEFAULT_WORK_QUOTA_BYTES,
        # A cap without its scope is a number someone will misread. Measured:
        # `disk_quota_bytes` acts per file (RLIMIT_FSIZE -> EFBIG); the sum across
        # files stays invisible to the engine, and `io_budget_bytes` only scans its
        # own sandbox folder — not Ephe's /work preopen, which stays at 0.
        "quota_scopes": {
            "disk_quota_bytes": "je Datei — durchgesetzt von der Engine (RLIMIT_FSIZE, EFBIG)",
            "work_quota_bytes": "je Session ueber alle Dateien — durchgesetzt von ephe (sweep_work_dir)",
            "io_budget_bytes": "nur der Sandbox-Ordner der Engine, nicht /work — meldet hier stets 0",
            "io_cpu_seconds": "Host-CPU-Wall des Workers — deckelt Schreiblast im Preopen zeitlich",
        },
        "output_cap_bytes": OUTPUT_CAP_BYTES,
        # The wall the pass-through keeps its headroom against, and what ephe does about it.
        # Without these three numbers output_cap_bytes is a figure without meaning.
        "sink_ceiling_bytes": SINK_CEILING_BYTES,
        "guest_forward_bytes": GUEST_FORWARD_BYTES,
        "guest_tee_cap_bytes": GUEST_TEE_CAP_BYTES,
        "preopens": ["/work (beschreibbar, je Session)", "stdio/gast-root (nur gelesen)"],
        "network": "none",
        "guest": {
            "version": state["version"],
            "installed": state["installed"],
            "library": state["library"],
            "entry_hash_ok": state["entry_ok"],
            "stdlib_hash_ok": state["tree_ok"],
            "path": state["path"],
            "reason": state["reason"],
        },
        "license": {
            "guest": str((manifest().get("guest") or {}).get("license") or ""),
            "cell_runtime": cell_runtime_license(),
        },
        "measured": dict((manifest().get("provenance") or {}).get("measured") or {}),
        "gaps": list((manifest().get("provenance") or {}).get("guest_gaps") or []),
    }


def doctor_snapshot() -> tuple[bool, str]:
    """(ok, detail) for ``ephe doctor`` — fail-soft, never flips the exit code."""
    try:
        state = guest_state()
        if state["entry_ok"] and state["tree_ok"]:
            return True, (
                f"CPython {state['version']} verifiziert "
                f"(fuel<={fuel_budget()}, mem<={DEFAULT_MAX_MEMORY_MB}MB, net=none)"
            )
        if not state["library"]:
            return True, (
                "Cell runtime missing (opt-in) — execute_code runs in the kernel "
                "behind the approval gate. pip install 'ephe[sandbox]'"
            )
        if not state["installed"]:
            return True, (
                f"Guest missing — execute_code runs in the kernel behind the approval gate. "
                f"{state['reason']}"
            )
        return False, f"Gast unverifiziert: {state['reason']}"
    except Exception as exc:  # noqa: BLE001 — doctor must never fail on the sandbox
        return True, f"cell check skipped ({exc.__class__.__name__})"

