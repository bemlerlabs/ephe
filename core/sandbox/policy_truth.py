"""One function that says, per platform, which ceiling is enforced — `report == enforced`.

The discipline this copies is `core/cell_policy.py`: no panel may show a cap the
runner does not write, and a cap nobody enforces is written here as not-enforced.
Task #38 surfaces these words in the UI; task #9's receipts carry the same
boundary verdict the supervisor acted on. Every line below is what the code in
`core/sandbox/supervisor.py` and the reused `core/mcp_sandbox` builders actually
does on the machine this runs on — measured on the lane's macOS, unmeasured
paths are named as such.
"""
from __future__ import annotations

import sys
from typing import Any

from core import mcp_sandbox

#: The words task #38 renders. A ceiling is `enforced`, `bounded`, or `not_enforced`.
CEILING_LEVELS = ("enforced", "bounded", "not_enforced")


def policy_snapshot() -> dict[str, Any]:
    """Effective worker policy truth: boundary available here, per-ceiling verbs, per-OS notes."""
    boundary = mcp_sandbox.platform_boundary()
    has_boundary = boundary != "unavailable"
    return {
        "boundary_here": boundary,
        "platform": sys.platform,
        "ceilings": {
            "wall_clock_seconds": (
                "enforced — the supervisor waits out the spec's timeout, then kills "
                "and proves the death of the whole process group (start_new_session + "
                "killpg TERM then KILL)"
            ),
            "cpu_seconds": (
                "not_enforced — no per-process CPU ceiling is written; the wall-clock "
                "kill is the only bound, so a busy child costs CPU until it dies"
            ),
            "memory_mb": (
                "enforced in the child via RLIMIT_AS when the spec declares it and the OS "
                "takes the call; the child reports the verdict on every capped run and "
                "`WorkerOutcome.memory_ceiling` carries it (`applied`, `refused`, "
                "`unknown`, or empty when nothing was declared). Measured on this macOS at "
                "256 MB, 512 MB, 1 GB, 2 GB and 4 GB with both limits unbounded: "
                "setrlimit refuses every finite RLIMIT_AS, so a declared cap here runs "
                "uncapped and says `refused`. Declared 0 asks for no ceiling. The `oom` "
                "status comes from the exit status (unasked SIGKILL), its Linux signature, "
                "and no kernel kill was observed on this machine"
            ),
            "output_bytes": (
                f"enforced — head 1/4 + tail 3/4 bounded buffers; the dropped middle "
                "is counted and the cap is stated in the text the reader receives"
            ),
            "filesystem_reach": (
                "enforced where a boundary exists: whole-home deny with child home, "
                "temp and measured runtime prefixes re-opened (Seatbelt last-rule-"
                "wins; bubblewrap tmpfs + ro-bind), plus exactly the roots the "
                "descriptor declared, read-only; not_enforced — and execution "
                "refused as sandbox_unavailable — where the boundary is missing"
            )
            if has_boundary
            else (
                "not_enforced — no boundary on this machine, so no worker spawns at "
                "all (fail-closed)"
            ),
            "filesystem_capacity": (
                "not_enforced — no disk quota is written by this layer; a worker can "
                "fill its writable home/temp"
            ),
            "network": (
                "enforced for a plugin worker on both rails — the macOS profile "
                "carries (deny network*) and bubblewrap runs --unshare-net, because a "
                "measured child reached the host\u2019s own loopback API with no token "
                "before that. The MCP connector rail keeps its network: a server there "
                "may legitimately be a client, and it is not this boundary\u2019s child"
            ),
            "orphan_process_group": (
                "enforced — the timeout path SIGTERM/SIGKILLs the group and waits "
                "until killpg reports no such group (bounded at 2s, stated on the "
                "outcome)"
            ),
            "env_scrub": (
                "enforced — the child gets core.secret_broker.child_env: allowlisted "
                "names only, sanitized HOME and TMPDIR; inherited host credentials "
                "never reach it"
            ),
        },
        "platform_notes": {
            "darwin": (
                "Seatbelt via sandbox-exec: available and enforcing on this macOS. "
                "Deprecated-but-working with no documented Apple removal timeline; "
                "cannot confine raw socket()/fd creation or Mach IPC — measured in "
                "the ecosystem at 40 of 42 escape vectors blocked, not 42."
            ),
            "linux": (
                "bubblewrap: needs bwrap installed and unprivileged user namespaces "
                "permitted — stock Ubuntu 24.04 gates the latter behind AppArmor. "
                "Without either, the boundary is unavailable and workers are "
                "refused, not run bare."
            ),
            "windows": (
                "no confinement rung exists in this tree — platform_boundary "
                "answers `unavailable` and every worker is denied on that verdict "
                "(deny-on-failure), with sandbox_unavailable as the coded refusal."
            ),
        },
        "restart_budget": (
            "enforced — consecutive worker deaths are counted; after the bound the "
            "tool is refused for the turn instead of respawning (see restart_budget)"
        ),
        "statuses": (
            "ok", "timeout", "crashed", "nonzero", "oom", "sandbox_unavailable",
            "protocol_error",
        ),
    }
