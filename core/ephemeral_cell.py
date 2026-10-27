"""Ephe – ephemeral cell lifecycle (bot = 1 cell).

A bot (Telegram/CLI/swarm agent) gets exactly one ephemeral cell when it is built
= a mini computer with its own identity and lifetime. The cell carries the
stateful core (in-process namespace or WASI sandbox) and is reused or discarded
after its idle TTL.

Patterns (2025/26, verified): the OpenAI container object (expires_after =
last_active + TTL), agent-sandbox idle-reap, one Grok SessionActor per session.

Isolation is the point: two bots never share a namespace.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

# Idle TTL: a cell unused for this long counts as expired and is discarded on the
# next reaper pass (analogous to agent-sandbox 30min).
CELL_IDLE_TTL_SECONDS = 1800.0

# Cell kinds: "wasi" = Ephemora cell sandbox (run_isolated), "kernel" =
# persistent in-process Python namespace (core.tools.code_kernel).
KIND_WASI = "wasi"
KIND_KERNEL = "kernel"


@dataclass
class EphemeralCell:
    """One ephemeral execution cell with its own identity + lifetime."""

    id: str
    session_id: str
    kind: str
    created_at: float
    last_active_at: float
    ttl_seconds: float
    ordinal: int = 0
    calls: int = 0
    total_ms: float = 0.0
    state: dict[str, Any] = field(default_factory=dict)

    def is_expired(self, now: float) -> bool:
        """True when the cell has not been active for `ttl_seconds`."""
        return (now - self.last_active_at) > self.ttl_seconds

    def touch(self, now: float) -> None:
        """Refresh the usage timestamp (moves the reap boundary)."""
        self.last_active_at = now


# Session-keyed registry: session_id → EphemeralCell. One bot per session, one
# cell per bot. No namespace shared across sessions.
_CELLS: dict[str, EphemeralCell] = {}

# How many cells this process has ever built — the number behind "Zelle 12".
# `reset_cells()` puts it back, so tests see the same number the code does.
_CREATED = 0


def cells_created() -> int:
    """Number of cells built in this process (monotonic until reset)."""
    return _CREATED


def effective_ttl() -> float:
    """Lifetime of new cells in seconds: the dial, otherwise the constant.

    `deep_number` raises on an unknown key — here a raise would be no reason to
    abort a run: without the register the constant governs.
    """
    try:
        from core.settings_schema import deep_number
        minutes = float(deep_number("ephemera.idle_ttl_minutes"))
    except Exception:
        return CELL_IDLE_TTL_SECONDS
    return minutes * 60.0 if minutes > 0 else CELL_IDLE_TTL_SECONDS


def forget(session_id: str) -> bool:
    """Destroy one cell before its lifetime is up: registry entry gone, workbook
    empty. True when there was something to destroy.

    The output path of a run (documents, images) does not live here — this
    function deletes nothing a user might want to keep.
    """
    from core.cpython_guest import reset_work_dir

    had = _CELLS.pop(session_id, None) is not None
    _PREWARMED.pop(session_id, None)
    try:
        reset_work_dir(session_id)
    except OSError:
        return had
    return had


def create_cell(session_id: str, kind: str = KIND_KERNEL,
                 ttl_seconds: float | None = None) -> EphemeralCell:
    """Create a new cell for `session_id` and register it.

    Idempotent per session: on a repeated call the existing cell is returned and
    only marked as active (touch), not rebuilt.
    """
    global _CREATED
    now = time.monotonic()
    existing = _CELLS.get(session_id)
    if existing is not None:
        existing.touch(now)
        return existing
    _CREATED += 1
    cell = EphemeralCell(
        id=uuid.uuid4().hex,
        session_id=session_id,
        kind=kind,
        created_at=now,
        last_active_at=now,
        ttl_seconds=effective_ttl() if ttl_seconds is None else ttl_seconds,
        ordinal=_CREATED,
    )
    _CELLS[session_id] = cell
    return cell


def get_cell(session_id: str) -> EphemeralCell | None:
    """The active cell of a session, or None (after a reap / never built)."""
    cell = _CELLS.get(session_id)
    if cell is None:
        return None
    now = time.monotonic()
    if cell.is_expired(now):
        _CELLS.pop(session_id, None)
        return None
    cell.touch(now)
    return cell


def reap_idle(now: float | None = None) -> int:
    """Discards every expired cell; the number of cells removed.

    Called on each access and/or periodically (the idle reaper).
    """
    now = time.monotonic() if now is None else now
    expired = [sid for sid, cell in _CELLS.items() if cell.is_expired(now)]
    for sid in expired:
        _CELLS.pop(sid, None)
    return len(expired)


def reset_cells() -> None:
    """Empty the registry (test hygiene / process restart)."""
    global _CREATED
    _CELLS.clear()
    _PREWARMED.clear()
    _CREATED = 0


def cell_count() -> int:
    """Current number of registered cells (observability)."""
    return len(_CELLS)


def record_call(session_id: str, elapsed_ms: float, *,
                kind: str = KIND_KERNEL,
                ttl_seconds: float | None = None) -> None:
    """One run of the cell: refresh the active stamp and add up the runtime.

    The only writer of `calls`/`total_ms`. Creates the cell when the session has no
    cell yet — a run IS the birth of the cell.
    """
    cell = create_cell(session_id, kind=kind, ttl_seconds=ttl_seconds)
    cell.calls += 1
    cell.total_ms += max(0.0, float(elapsed_ms))


def _containment_available() -> bool:
    """Would an executing turn run inside a guest rather than on the host?

    The life line used to report a cell's call count and idle time even when no
    guest existed on the machine — the surface then read "cell 1 · 0 ms/call ·
    idle" next to an `execute_code` that could only run on the host. The cheap
    predicate is the one the approval gate already uses (env choice plus a stat),
    so the five-second poll does not hash the guest image.
    """
    try:
        from core.cpython_cell import code_runs_uncontained

        return not code_runs_uncontained()
    except Exception:
        return False


def cell_life(session_id: str) -> dict[str, Any]:
    """What the registry knows about the life of this session cell.

    Only numbers standing here may appear in the life line. Reading does not
    extend life: `get_cell` touches, because *use* is what moves the
    reap boundary — a glance from the interface is not use.
    """
    reap_idle()
    contained = _containment_available()
    cell = _CELLS.get(session_id)
    if cell is None:
        return {"alive": False, "calls": 0, "avg_ms": None, "contained": contained}
    now = time.monotonic()
    idle = now - cell.last_active_at
    return {
        "alive": True,
        "ordinal": cell.ordinal,
        "kind": cell.kind,
        "calls": cell.calls,
        "avg_ms": round(cell.total_ms / cell.calls, 3) if cell.calls else None,
        "age_seconds": round(now - cell.created_at, 1),
        "idle_seconds": round(idle, 1),
        "ttl_seconds": cell.ttl_seconds,
        "seconds_left": round(cell.ttl_seconds - idle, 1),
        "contained": contained,
    }


async def run_in_cell(code: str, reset: bool = False) -> str:
    """Run code in the active cell of the session (bot→cell binding).

    Reads the session cell (freshly created if needed), refreshes its active stamp
    and delegates to the persistent kernel. One task per cell — kernel
    execution is sequential per session.
    """
    from core.tools.session_ctx import get_current_session
    from core.tools.code_kernel import execute_code

    sid = get_current_session()
    create_cell(sid, kind=KIND_KERNEL)  # idempotent: creates or touches
    get_cell(sid)  # reap path + active stamp
    return await execute_code(code, reset=reset)


# Envelope: the only return value a cell gives to the parent context
# Intermediate results stay in the cell (reference paper: intermediate results stay
# in the execution environment). Only this slim package leaves the cell.
SUMMARY_CAP = 2000


@dataclass
class AgentEnvelope:
    """Slim, capped return block of one cell execution."""

    status: str
    summary: str
    facts: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    tokens: int = 0


def envelope_from_cell(stdout: str, *, status: str = "ok",
                       artifacts: list[str] | None = None,
                       tokens: int = 0) -> AgentEnvelope:
    """Build an `AgentEnvelope` from raw cell output (summary capped)."""
    text = stdout or ""
    return AgentEnvelope(
        status=status,
        summary=text[:SUMMARY_CAP],
        facts=[line for line in text.splitlines() if line.strip()][:20],
        artifacts=list(artifacts or []),
        tokens=tokens,
    )


# C5: get-policy observability (parity report == enforced)
def get_policy() -> dict[str, Any]:
    """The effective sandbox policy as a POLICY block (fuel/memory/preopens/network).

    Parity: the values come from the same defaults `run_sandboxed_code` writes
    into the WASIConfig — report == enforced, no drift. These are the caps of a
    *pre-built* WASI module; since wave E1 the model's code runs in the CPython
    cell with its own, larger budget — that one stays unchanged under "code_exec"
    (source: core.cell_policy.policy_snapshot()).
    """
    from core.tools.sandbox_tools import (
        DEFAULT_IO_BUDGET_BYTES,
        DEFAULT_IO_CPU_SECONDS,
        DEFAULT_MAX_FUEL,
        DEFAULT_MAX_MEMORY_MB,
        DEFAULT_TIMEOUT_SECONDS,
    )
    from core import cell_policy

    return {
        "max_memory_mb": DEFAULT_MAX_MEMORY_MB,
        "max_fuel": DEFAULT_MAX_FUEL,
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "io_cpu_seconds": DEFAULT_IO_CPU_SECONDS,
        "io_budget_bytes": DEFAULT_IO_BUDGET_BYTES,
        "preopens": [],          # default preopen deny (no allow_dirs)
        "network": "none",       # egress ADR-002: no network out of the cell
        "code_exec": cell_policy.policy_snapshot(),
    }


# C6: transactional snapshot (restore point per call)
def snapshot_cell(session_id: str) -> dict[str, Any] | None:
    """Restore point of the cell state (shallow copy). None when the cell is gone."""
    cell = get_cell(session_id)
    if cell is None:
        return None
    return {"id": cell.id, "state": dict(cell.state)}


def rollback_cell(session_id: str, snapshot: dict[str, Any] | None) -> bool:
    """Reset the state to a snapshot. True on rollback, False otherwise."""
    if not snapshot:
        return False
    cell = _CELLS.get(session_id)
    if cell is None or cell.id != snapshot.get("id"):
        return False
    cell.state = dict(snapshot.get("state", {}))
    return True


# C7: prewarming (speculative preallocation of the next cell)
_PREWARMED: dict[str, str] = {}   # session_id → cell-id (held ahead, anticipated)


def prewarm_cell(session_id: str, kind: str = KIND_KERNEL,
                 ttl_seconds: float | None = None) -> str:
    """Create the next cell in anticipation (speculative preallocation).

    Idempotent: an existing cell is only touched. Returns the cell ID.
    """
    cell = create_cell(session_id, kind=kind, ttl_seconds=ttl_seconds)
    _PREWARMED[session_id] = cell.id
    return cell.id


def prewarm_count() -> int:
    """Number of anticipated cells (observability)."""
    return len(_PREWARMED)

