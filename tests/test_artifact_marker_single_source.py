"""One artifact-marker set, imported, not three that drift (W10, wave 10).

Three modules used to keep their own marker list and two fell behind, so a produced
file reached neither the evidence stamp nor the workbench. The set lives once in
``core/artifact_markers`` now; this module fails the moment a consumer grows a copy
again or a view drifts from the shared rows.
"""
from __future__ import annotations

import re
from pathlib import Path

from core.artifact_markers import (
    ARTIFACT_MARKER_PREFIXES,
    ARTIFACT_MARKERS,
    MARKER_BY_KIND,
)

ROOT = Path(__file__).resolve().parents[1]

# A quoted "..._FILE:" literal, the shape a restated marker list takes.
_MARKER_LITERAL = re.compile(r'"[A-Z][A-Z0-9_]*_FILE:"')

# The three sites this unification touched. Each reads core/artifact_markers; none
# may name a marker literal of its own.
_CALLERS = (
    "server/routes/chat.py",
    "core/tools/registry.py",
    "core/quality.py",
)
_SSOT = "core/artifact_markers.py"


def test_no_caller_restates_a_marker_literal():
    offenders: dict[str, list[str]] = {}
    for rel in _CALLERS:
        src = (ROOT / rel).read_text(encoding="utf-8")
        found = sorted(set(_MARKER_LITERAL.findall(src)))
        if found:
            offenders[rel] = found
    assert not offenders, (
        f"these callers restate marker literals instead of importing {_SSOT}: {offenders}"
    )


def test_server_registration_table_is_the_shared_rows():
    from server.routes.chat import _FILE_RESULT_PREFIXES

    assert tuple(_FILE_RESULT_PREFIXES) == ARTIFACT_MARKERS


def test_evidence_gate_scans_the_shared_prefixes():
    from core.tools import registry

    assert tuple(registry._ARTIFACT_MARKERS) == ARTIFACT_MARKER_PREFIXES


def test_quality_resolves_every_marker_it_reads_through_the_shared_rows():
    from core import quality

    missing = [kind for kind in quality._VALIDATED_KINDS if kind not in MARKER_BY_KIND]
    assert not missing, f"quality validates kinds the shared table lacks: {missing}"

    # Each validated kind maps to exactly one marker and back to its own type name.
    raw = "\n".join(f"{MARKER_BY_KIND[kind]}/out/{kind}" for kind in quality._VALIDATED_KINDS)
    types = [artifact["type"] for artifact in quality._artifacts_from_raw(raw)]
    expected = [quality._QUALITY_TYPE.get(kind, kind) for kind in quality._VALIDATED_KINDS]
    assert types == expected


def test_shared_rows_carry_no_duplicate_marker():
    markers = [row[0] for row in ARTIFACT_MARKERS]
    assert len(markers) == len(set(markers))
