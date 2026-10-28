"""O2: the certificate is reproducible, order-free, and refuses to lie."""
from __future__ import annotations

import hashlib
import json

import pytest

from core.proof_tree import (
    CertificateError,
    build_certificate,
    leaf,
    merkle_root,
    verify_certificate,
    write_certificate,
)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


PARTS = {
    "task_spec_hash": "spec-abc",
    "tool_outputs": ["first output", "second output"],
    "envelope": '{"status":"ok","summary":"two steps"}',
    "custody_signature": "sig-123",
}


def test_the_root_is_the_same_whatever_order_the_parts_arrived_in() -> None:
    forward = build_certificate(PARTS)
    backward = build_certificate({**PARTS, "tool_outputs": list(reversed(PARTS["tool_outputs"]))})
    # The leaves carry arrival indexes, so the labels differ; the tree sorts by digest.
    assert merkle_root(item["sha256"] for item in forward["leaves"]) == merkle_root(
        item["sha256"] for item in backward["leaves"]
    )


def test_a_certificate_verifies_and_a_tampered_one_does_not() -> None:
    cert = build_certificate(PARTS)
    assert verify_certificate(cert) is True

    broken = json.loads(json.dumps(cert))
    broken["leaves"][0]["sha256"] = _digest("another spec")
    assert verify_certificate(broken) is False


def test_a_missing_part_is_a_refusal_and_an_absent_signature_is_recorded() -> None:
    for name in ("task_spec_hash", "tool_outputs", "envelope"):
        with pytest.raises(CertificateError):
            build_certificate({**PARTS, name: "" if name != "tool_outputs" else []})

    without_custody = build_certificate({k: v for k, v in PARTS.items() if k != "custody_signature"})
    assert [item for item in without_custody["leaves"] if item["kind"] == "custody_signature"] == [
        {"kind": "custody_signature", "sha256": "absent"}
    ]
    assert verify_certificate(without_custody) is True


def test_the_written_file_verifies_from_disk(tmp_path) -> None:
    cert = build_certificate(PARTS)
    path = write_certificate(tmp_path / ".ephe-proof.json", cert)
    reread = json.loads(path.read_text(encoding="utf-8"))
    assert reread["root"] == cert["root"]
    assert verify_certificate(reread) is True
    assert path.name == ".ephe-proof.json"


def test_an_empty_tree_has_the_empty_digest_and_leaf_needs_a_value() -> None:
    assert merkle_root([]) == _digest("")
    with pytest.raises(CertificateError):
        leaf("tool_output_0", "")


def test_a_refused_certificate_is_never_written(tmp_path) -> None:
    cert = build_certificate(PARTS)
    cert["root"] = _digest("not the root")
    with pytest.raises(CertificateError):
        write_certificate(tmp_path / ".ephe-proof.json", cert)
    assert not (tmp_path / ".ephe-proof.json").exists()
