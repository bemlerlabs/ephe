"""O2: the Merkle certificate for one release or pull request.

Four facts are supposed to stand behind a claim that Ephe did the work: the hash
of the task spec, the digest of every tool output, the swarm envelope, and the
custody signature of the approver. Three of them exist today; the fourth has no
producer yet (`core/custody.py`, named by the order, is not in the tree), so a
certificate records an absent part as absent instead of quietly dropping it.

The root is a plain binary Merkle tree over sorted leaves: two leaves hash into
their parent, an odd leaf is carried up unchanged, and the last hash standing is
the root. Sortedness makes the root independent of the order the caller happened
to collect leaves in, which is what lets a verifier rebuild it from a JSON file
alone.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

VERSION = 1

#: The parts a certificate is built from. `custody` may be absent; the others may not,
#: because a certificate that omits the task it certifies says nothing.
REQUIRED_PARTS = ("task_spec_hash", "tool_outputs", "envelope")


class CertificateError(ValueError):
    """A certificate that cannot be built or does not verify."""


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()


def leaf(kind: str, value: str) -> dict[str, str]:
    """One fact as a leaf: its kind and the digest of its value."""
    if not kind or not value:
        raise CertificateError("a leaf needs a kind and a value")
    return {"kind": kind, "sha256": _digest(value)}


def merkle_root(hashes: Iterable[str]) -> str:
    """The root of the binary tree over these digests; sha256("") for none."""
    level = sorted(h for h in hashes if h)
    if not level:
        return _digest("")
    while len(level) > 1:
        nxt: list[str] = []
        for i in range(0, len(level), 2):
            if i + 1 == len(level):
                nxt.append(level[i])
            else:
                nxt.append(_digest(level[i] + level[i + 1]))
        level = nxt
    return level[0]


def build_certificate(parts: Mapping[str, Any]) -> dict[str, Any]:
    """Assemble the certificate from the four named parts.

    ``tool_outputs`` is a sequence of digests or raw texts; each becomes its own leaf
    in arrival order, then the tree sorts them, so a caller may append freely.
    """
    missing = [name for name in REQUIRED_PARTS if not parts.get(name)]
    if missing:
        raise CertificateError(f"certificate without {', '.join(missing)}")

    leaves = [leaf("task_spec_hash", str(parts["task_spec_hash"]))]
    leaves.append(leaf("envelope", str(parts["envelope"])))
    for index, output in enumerate(parts["tool_outputs"]):
        text = str(output)
        leaves.append(leaf(f"tool_output_{index}", text))

    custody = str(parts.get("custody_signature") or "")
    leaves.append(leaf("custody_signature", custody) if custody else {"kind": "custody_signature", "sha256": "absent"})

    return {
        "version": VERSION,
        "leaves": leaves,
        "root": merkle_root(item["sha256"] for item in leaves),
    }


def verify_certificate(certificate: Mapping[str, Any]) -> bool:
    """Rebuild the root from the recorded leaves; raise when the file is malformed."""
    if certificate.get("version") != VERSION:
        raise CertificateError(f"unknown certificate version: {certificate.get('version')}")
    leaves = certificate.get("leaves")
    if not isinstance(leaves, list) or not leaves:
        raise CertificateError("a certificate needs leaves")
    hashes = []
    for item in leaves:
        if not isinstance(item, Mapping) or "sha256" not in item:
            raise CertificateError("every leaf carries its digest")
        hashes.append(str(item["sha256"]))
    return merkle_root(hashes) == certificate.get("root")


def write_certificate(path: Path | str, certificate: Mapping[str, Any]) -> Path:
    target = Path(path)
    if not verify_certificate(certificate):
        raise CertificateError("refusing to write a certificate that does not verify")
    target.write_text(json.dumps(certificate, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
