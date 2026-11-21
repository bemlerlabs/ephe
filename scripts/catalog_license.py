"""Licence evidence for catalogue entries.

Hierarchy: a LICENSE/COPYING text inside the artifact outranks the manifest
metadata, which outranks an index claim. Approval needs the artifact file and a
hash; metadata alone is unproven. Allowed identifiers are permissive only.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ALLOWED = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC"}
COPYLEFT = ("AGPL", "LGPL", "GPL", "MPL", "EUPL", "CDDL")

_PATTERNS = (
    ("Apache-2.0", r"Apache License,?\s+Version 2\.0"),
    ("MIT", r"\bMIT License\b|Permission is hereby granted, free of charge"),
    ("BSD-3-Clause", r"BSD 3-Clause|Neither the name"),
    ("BSD-2-Clause", r"BSD 2-Clause|Redistribution and use in source and binary forms"),
    ("ISC", r"\bISC License\b|Permission to use, copy, modify, and/or distribute"),
)
_ALIASES = {
    "MIT".lower(): "MIT", "MIT License".lower(): "MIT",
    "apache-2.0": "Apache-2.0", "apache 2.0": "Apache-2.0", "apache license 2.0": "Apache-2.0",
    "bsd-2-clause": "BSD-2-Clause", "bsd 2-clause": "BSD-2-Clause",
    "bsd-3-clause": "BSD-3-Clause", "bsd 3-clause": "BSD-3-Clause",
    "isc": "ISC", "isc license": "ISC",
}


@dataclass(frozen=True)
class LicenseResult:
    spdx: str
    status: str
    evidence: str


def detect(text: str) -> str:
    for spdx, pattern in _PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return spdx
    if re.search(
        r"GNU (?:AFFERO )?GENERAL PUBLIC LICENSE|\b(?:A?GPL|LGPL|MPL|EUPL|CDDL)\b",
        text,
        re.IGNORECASE,
    ):
        return "copyleft"
    return ""


def normalize(value: str) -> str:
    return _ALIASES.get(value.strip().lower(), "")


def classify(
    *, artifact_text: str | None = None, metadata: str | None = None, index_claim: str | None = None
) -> LicenseResult:
    artifact = detect(artifact_text or "")
    meta = normalize(metadata or "")
    claim = normalize(index_claim or "")
    declared = [value for value in (meta, claim) if value]
    if artifact:
        conflict = [value for value in declared if value != artifact]
        if conflict:
            return LicenseResult("", "conflict", f"artifact={artifact} conflicts with {conflict}")
        if artifact in ALLOWED:
            return LicenseResult(artifact, "allowed", "LICENSE/COPYING in the artifact")
        if artifact == "copyleft":
            return LicenseResult("", "copyleft", "copyleft licence in the artifact")
        return LicenseResult("", "denied", f"unrecognised licence text ({artifact})")
    if len(set(declared)) > 1:
        return LicenseResult("", "conflict", f"metadata={meta} conflicts with index={claim}")
    if declared and declared[0] in ALLOWED:
        return LicenseResult(declared[0], "unproven", "metadata or index only; no artifact licence file")
    if declared and declared[0] == "copyleft":
        return LicenseResult("", "copyleft", "copyleft declared without an artifact licence file")
    if declared:
        return LicenseResult("", "denied", "unrecognised declared licence")
    return LicenseResult("", "missing", "no licence text, metadata or index claim")
