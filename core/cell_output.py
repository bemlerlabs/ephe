"""Ephe – Output policy of the cell: what arrives from the stream and what stays secured (wave I1).

Third security layer (docs/SANDBOX_EXECUTION.md): the execution caps what a
model program writes. This seam answers the question about the *result*
of that capping — how much output the model, the audit log and the panel see, where the rest
lies and how long it stays reachable.

The trigger was measured, not invented: the cell's output sink is not a
cap but a wall. Up to ~10,000 bytes per stream the guest survives, from
~11,000 its own ``sys.stdout.write`` raises ``OSError: [Errno 29] I/O error``.
An agent printing a large JSON therefore crashed on its own print and, on top of
that, saw 8192 bytes from somewhere — the normal case, not the error case.

The answer sits in two halves: ``core.cell_boot`` (runs INSIDE the guest) tees the
full stream into ``/work`` and lets only a remainder below the wall through the
real fd. This module (host) reads the journal by byte ranges, cuts the
head *and* the body and names every loss — including the number that says
that /work does not write without limits either.
"""
from __future__ import annotations

from pathlib import Path

#: Wall of the engine (measured 2026-10-02), not Ephe's cap: the value the
#: forward budget below has to stay under. A cap without this number is half the truth.
SINK_CEILING_BYTES = 10_000
#: Bytes per stream allowed to reach the real fd — with both budgets and
#: their markers this stays under the wall (proved in
#: tests/test_cpython_cell_e1.py::test_forward_budget_can_never_reach_the_sink_wall).
GUEST_FORWARD_BYTES = 2_048
#: Largest write volume of the journal per run and stream.
GUEST_TEE_CAP_BYTES = 512 * 1024

#: Policy, not a hardware cap: how much output the model and the panel see. The
#: rest lies in the journal and is retrievable within the same session.
OUTPUT_CAP_BYTES = 10_000
#: The tail stays free: errors stand at the end, and cutting that away would be
#: the most expensive way to save.
OUTPUT_TAIL_BYTES = 2_000
#: Room for the loss marker including the byte range.
OUTPUT_MARKER_RESERVE = 256

STDOUT_LOG_NAME = "stdout.log"
STDERR_LOG_NAME = "stderr.log"

#: Ceiling of the journal per stream. The journal writes into the same /work that
#: the model program itself creates files in — a journal growing without
#: limits would squeeze the cap of the following runs shut from the inside.
#: Rotation is therefore not a space-saving trick but part of the promise.
JOURNAL_MAX_BYTES = 4 * 1024 * 1024


def rotate_journal(path: Path) -> bool:
    """Drop the journal when it becomes too heavy. True when it is gone.

    After that the journal starts at byte 0 — the ranges of the runs after it are correct,
    the ones before were a promise for this session, not for unlimited storage.
    """
    try:
        if path.is_file() and path.stat().st_size > JOURNAL_MAX_BYTES:
            path.unlink(missing_ok=True)
            return True
    except OSError:
        return False
    return False


def read_journal(path: Path, start: int, length: int) -> bytes | None:
    """The byte range of a run from the session journal — None if it does not exist.

    The file is read, not the channel: larger output was always there,
    it just lay behind a wall the guest was not allowed to break through.
    """
    if length <= 0 or not path.is_file():
        return None
    try:
        with path.open("rb") as fh:
            fh.seek(start)
            return fh.read(min(length, GUEST_TEE_CAP_BYTES))
    except OSError:
        return None


def span_text(log_name: str, start: int, secured: int) -> str:
    """The byte range of a run — it makes the journal retrievable without guessing."""
    return f"Byte {start}..{start + secured} in /work/{log_name}"


def excerpt(data: bytes, log_name: str, total: int, start: int) -> tuple[str, bool]:
    """Head + body up to OUTPUT_CAP_BYTES, with the loss spelled out.

    A head alone would cut off the error at the end — with tracebacks and with
    "last line = result" that is the line it was about. The promise in the
    marker only holds as far as the tee cap allows: /work does not write without limits either.
    """
    if len(data) <= OUTPUT_CAP_BYTES:
        return data.decode("utf-8", errors="replace"), False
    head_len = OUTPUT_CAP_BYTES - OUTPUT_TAIL_BYTES - OUTPUT_MARKER_RESERVE
    head = data[:head_len].decode("utf-8", errors="ignore")
    tail = data[-OUTPUT_TAIL_BYTES:].decode("utf-8", errors="ignore")
    lost = len(data) - head_len - OUTPUT_TAIL_BYTES
    span = span_text(log_name, start, len(data))
    if total > len(data):
        rest = f"die ersten {len(data)} Byte sind gesichert ({span}), " \
               f"{total - len(data)} sind verloren"
    else:
        rest = f"vollstaendig — {span}"
    marker = f"\n[… {lost} Byte nicht uebergeben — {rest}]\n"
    return head + marker + tail, True


def loss_lines(report: dict) -> list[str]:
    """The lines a shortened run has to speak: number, reason, place.

    Silence would be the old false claim in a new dress — and "complete in
    the file" too, as soon as the tee cap takes effect.
    """
    lines: list[str] = []
    for name, log in (("stdout", STDOUT_LOG_NAME), ("stderr", STDERR_LOG_NAME)):
        total = int(report.get(f"{name}_bytes") or 0)
        secured = int(report.get(f"{name}_log_bytes") or 0)
        start = int(report.get(f"{name}_log_start") or 0)
        delivered = len(str(report.get(name) or "").encode("utf-8"))
        if total <= delivered:
            continue
        span = span_text(log, start, secured)
        if secured >= total:
            rest = f"vollstaendig gesichert — {span}, in dieser Session abholbar"
        else:
            rest = f"{secured} Byte gesichert ({span}), {total - secured} Byte sind weg"
        lines.append(f"[{name}: {total} Byte erzeugt, {delivered} uebergeben — {rest}]")
    return lines


def work_lines(report: dict) -> list[str]:
    """The lines the workspace clean-up has to speak: number, reason, remainder.

    The bytecode buffer is the large, worthless part of the list: it counts in the
    sum, but it does not fill the model's context with thirty paths. What
    is regenerable is known by the session quota (`core.cpython_guest`), not here.
    """
    evicted = [str(name) for name in report.get("work_evicted") or []]
    lines: list[str] = []
    if evicted:
        data = [str(name) for name in report.get("work_evicted_data") or []]
        caches = len(evicted) - len(data)
        quota = int(report.get("work_quota_bytes") or 0)
        freed = int(report.get("work_freed_bytes") or 0)
        parts = [f"{freed} bytes removed, oldest first"]
        if caches > 0:
            parts.append(f"{caches} bytecode cache file(s)")
        if data:
            shown = ", ".join(data[:4])
            more = f" (+{len(data) - 4} more)" if len(data) > 4 else ""
            parts.append(f"{len(data)} oldest results: {shown}{more}")
        lines.append(f"[work: session quota {quota // 1048576} MiB reached — "
                     + "; ".join(parts) + "]")
    if report.get("work_over_quota"):
        lines.append(
            "[work: still over the session quota — only protected files "
            "(output journal, state); nothing was deleted]"
        )
    return lines


def dir_bytes(path: Path) -> int:
    """What the session really occupies — the engine counter does not see guest write paths."""
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total
