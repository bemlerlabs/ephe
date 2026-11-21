"""`ephe context`: the workspace context files as the resolver read them.

The reading, the caps and the status words belong to ``core.workspace_rules``; this module
renders that one report, so the terminal and the prompt cannot disagree about a file. A tree
that carries ``explain_workspace_context()`` answers with the structured report; one that
does not answers with ``read_workspace_rules()``, the same read one step below.
"""
from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core import workspace_rules

#: The structured report lands with the context contract. Without it the resolver's own
#: report is the answer, so the verb is usable in both states of that change.
try:
    _explain_workspace_context = workspace_rules.explain_workspace_context
except AttributeError:
    _explain_workspace_context = None

CONTRACT_SOURCE = "explain_workspace_context"
RESOLVER_SOURCE = "read_workspace_rules"


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _layer_name(file: str) -> str:
    """The layer a rule file belongs to, read from where it sits under the root."""
    path = Path(file)
    if path.name == workspace_rules.RULES_NAME:
        return "agents"
    if path.parent == workspace_rules.RULES_DIR:
        return "rules"
    return "workspace"


def _counts(layers: list[dict]) -> dict[str, int]:
    """How many files each status word covers."""
    counted: dict[str, int] = {}
    for row in layers:
        counted[row["status"]] = counted.get(row["status"], 0) + 1
    return counted


def _fallback_report() -> dict:
    """One row per file, exactly as ``read_workspace_rules()`` reported it."""
    read = workspace_rules.read_workspace_rules()
    return {
        "layers": [
            {
                "layer": _layer_name(entry.name),
                "file": entry.name,
                "chars": entry.chars,
                "status": entry.status,
                "reason": entry.reason,
                "scope": "workspace",
            }
            for entry in read.files
        ],
        "caps": {
            "total": workspace_rules.WORKSPACE_RULES_MAX,
            "per_file": workspace_rules.RULE_FILE_MAX,
        },
        "total_chars": sum(entry.chars for entry in read.files),
        "source": RESOLVER_SOURCE,
    }


def _normalize(raw: Any) -> dict | None:
    """The documented report shape, or None when ``raw`` is something else.

    The shape is ``{layers: [{name, file, chars, status, reason, scope}],
    caps: {total, per_file}, total_chars}``. A report that does not carry it is not guessed
    at: the resolver's own ``read_workspace_rules()`` answers instead.
    """
    if not isinstance(raw, Mapping):
        return None
    rows = raw.get("layers")
    if not isinstance(rows, list):
        return None
    layers: list[dict] = []
    for row in rows:
        if not isinstance(row, Mapping) or not row.get("file") or not row.get("status"):
            return None
        try:
            chars = int(row.get("chars") or 0)
        except (TypeError, ValueError):
            return None
        layers.append(
            {
                "layer": str(row.get("name") or "workspace"),
                "file": str(row["file"]),
                "chars": chars,
                "status": str(row["status"]),
                "reason": str(row.get("reason") or ""),
                "scope": str(row.get("scope") or ""),
            }
        )
    caps = raw.get("caps")
    caps = caps if isinstance(caps, Mapping) else {}
    return {
        "layers": layers,
        "caps": {
            "total": _int(caps.get("total"), workspace_rules.WORKSPACE_RULES_MAX),
            "per_file": _int(caps.get("per_file"), workspace_rules.RULE_FILE_MAX),
        },
        "total_chars": _int(raw.get("total_chars"), sum(row["chars"] for row in layers)),
        "source": CONTRACT_SOURCE,
    }


def _contract_report() -> Any:
    """The structured explanation, or None when this tree carries none or it broke.

    A broken explanation is no reason to fail the command: the resolver's own read answers
    with the same files.
    """
    if _explain_workspace_context is None:
        return None
    try:
        return _explain_workspace_context()
    except Exception:  # noqa: BLE001 — the fallback below is the answer then
        return None


def report() -> dict:
    """The context layers this run carries, normalized for the terminal and for ``--json``."""
    payload = _normalize(_contract_report())
    if payload is None:
        payload = _fallback_report()
    return {
        "workspace": workspace_rules.resolve_workspace_dir(),
        "layers": payload["layers"],
        "caps": payload["caps"],
        "total_chars": payload["total_chars"],
        "counts": _counts(payload["layers"]),
        "source": payload["source"],
    }


def _status_cell(row: dict) -> str:
    """The status word, with the reason a file stayed out when the reader gave one."""
    return f"{row['status']} ({row['reason']})" if row["reason"] else row["status"]


def render(payload: dict) -> list[str]:
    """The report as a person reads it: the workspace, the caps, one row per file."""
    caps = payload["caps"]
    lines = [
        f"Workspace  {payload['workspace']}",
        f"Caps       {caps['total']} chars total, {caps['per_file']} per file",
    ]
    rows = payload["layers"]
    if not rows:
        lines.append(f"No context files under {payload['workspace']}.")
        return lines
    noun = "file" if len(rows) == 1 else "files"
    lines.append(f"Total      {payload['total_chars']} chars from {len(rows)} {noun}")
    table = [("LAYER", "FILE", "CHARS", "STATUS")]
    table += [
        (row["layer"], row["file"], str(row["chars"]), _status_cell(row)) for row in rows
    ]
    widths = [max(len(row[col]) for row in table) for col in range(3)]
    lines.append("")
    for row in table:
        lines.append(
            f"{row[0]:<{widths[0]}}  {row[1]:<{widths[1]}}  "
            f"{row[2]:>{widths[2]}}  {row[3]}"
        )
    return lines


def doctor_row() -> str:
    """The doctor's one-line version: how many files loaded, capped and stayed out."""
    payload = report()
    counts = payload["counts"]
    if not payload["layers"]:
        return f"none in {payload['workspace']} — inspect: ephe context"
    named = (
        workspace_rules.INCLUDED,
        workspace_rules.TRUNCATED,
        workspace_rules.DENIED,
    )
    parts = [f"{counts.get(word, 0)} {word}" for word in named]
    parts += [
        f"{counts[status]} {status}"
        for status in sorted(counts)
        if counts[status] and status not in named
    ]
    return f"{', '.join(parts)}, {payload['total_chars']} chars — inspect: ephe context"


def run(*, as_json: bool = False) -> int:
    """Print the report. The exit code is 0 for every workspace, an empty one included."""
    payload = report()
    if as_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for line in render(payload):
            print(line)
    return 0
