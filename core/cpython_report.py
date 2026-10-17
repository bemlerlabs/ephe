"""Ephe – the cell's receipt text: one block for model, audit log and panel.

The rendering half of the cell seam. ``core.cpython_cell`` decides which runtime
carries a turn and runs the program; this module turns the returned report into
the ``[execute_code] ...`` block that the model reads, that
``core.tools.registry`` caps into the audit log, and that the status panel parses
back through ``runtime_of_report_text``. Both renderers sit together so the header
a reader sees and the runtime a badge shows stay one wording.

The runtime names stay with the decision half (``core.cpython_cell``) and are read
at call time inside ``format_report``: a module-level import would close a cycle,
because that module re-exports these two functions.
"""
from __future__ import annotations

from typing import Any

from core.cell_output import loss_lines, work_lines


def format_report(report: dict[str, Any]) -> str:
    """Observability receipt: runtime, caps, status — ahead of the output.

    The same line lands in the audit log (core.tools.registry caps detail at 300
    characters) and in the chat's tool result: report == enforced.
    """
    from core.cpython_cell import ENV_EXEC, RUNTIME_CELL

    runtime = report.get("runtime") or RUNTIME_CELL
    if report.get("status") == "GUEST_UNVERIFIED":
        return (
            f"[execute_code] runtime={runtime} status=GUEST_UNVERIFIED\n"
            f"{report.get('reason', '')}\n"
            "The in-process kernel is the explicit opt-out: "
            f"{ENV_EXEC}=kernel — it names its own consequence (full host access)."
        )
    head = (
        f"[execute_code] runtime={runtime}/{report.get('guest_version', '')} "
        f"status={report.get('status')} exit={report.get('exit_code')} "
        f"fuel={report.get('fuel_consumed')}/{report.get('fuel_budget')} "
        f"elapsed={float(report.get('elapsed_ms') or 0.0):.0f}ms "
        f"mem<={report.get('memory_mb')}MB "
        f"work={report.get('work_bytes', 0)}B/{report.get('work_quota_bytes', 0)}B "
        f"preopens=/work net=none"
    )
    lines = [head]
    lines.extend(work_lines(report))
    stdout = str(report.get("stdout") or "")
    if stdout.strip():
        lines.append("stdout:")
        lines.append(stdout.rstrip())
    stderr = str(report.get("stderr") or "")
    if stderr.strip():
        lines.append("stderr:")
        lines.append(stderr.rstrip())
    lines.extend(loss_lines(report))
    names = report.get("names") or []
    dropped = report.get("dropped") or []
    if names:
        lines.append("Variables: " + ", ".join(str(n) for n in names))
    if dropped:
        lines.append(
            "not persisted (not picklable, e.g. modules, files, lambdas): "
            + ", ".join(str(d) for d in dropped)
        )
    if len(lines) == 1:
        lines.append("[execute_code] ran (no output)")
    return "\n".join(lines)


def runtime_of_report_text(text: str) -> str:
    """The runtime out of a result text (panel/badge — not a second state)."""
    marker = "[execute_code] runtime="
    start = str(text).find(marker)
    if start < 0:
        return ""
    rest = str(text)[start + len(marker):]
    return rest.split()[0].split("/")[0]
