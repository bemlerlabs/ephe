"""The cut runs the release checklist, and a skipped gate set leaves a receipt.

The cut, the checklist and the release workflow used to judge three disjoint sets: the cut
checked the changelog, language and provenance; the checklist checked pass^3, signing and the
tag; the workflow checked pytest and the frontend. No command ran their union, so `--skip-gates`
could bypass the remaining checks with no record. The cut now runs the checklist itself, and
`--skip-gates` needs a reason that is written beside the tag it protected.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml

from tests.test_release_cut_semver import FOLDED, _fixture

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_cut.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


def _cut(root: Path, *args: str, receipt: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(root / "scripts" / "release_cut.sh"), "--dry-run", "--local", *args],
        capture_output=True,
        text=True,
        cwd=root,
        env={**os.environ, "EPHE_RELEASE_RECEIPT": str(receipt)},
    )


def test_the_gate_set_runs_the_release_checklist():
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'run_gate "release checklist"' in text
    assert "scripts/release_checklist.py" in text
    assert '--version "$V"' in text


def test_skip_gates_without_a_reason_is_refused(tmp_path):
    root = _fixture(tmp_path, "1.2.3", FOLDED.format(top="1.2.3"))
    receipt = tmp_path / "receipts.jsonl"
    out = _cut(root, "--skip-gates", receipt=receipt)
    assert out.returncode == 1, out.stdout + out.stderr
    assert "needs a reason" in out.stdout + out.stderr
    assert not receipt.exists()


def test_skip_gates_with_a_reason_writes_a_receipt(tmp_path):
    root = _fixture(tmp_path, "1.2.3", FOLDED.format(top="1.2.3"))
    receipt = tmp_path / "receipts.jsonl"
    out = _cut(
        root, "--skip-gates", "--skip-reason", "the mirrors are down", receipt=receipt
    )
    assert out.returncode == 0, out.stdout + out.stderr
    records = [json.loads(line) for line in receipt.read_text(encoding="utf-8").splitlines()]
    assert records and records[-1]["reason"] == "the mirrors are down"
    assert records[-1]["tag"] == "v1.2.3"
    assert len(records[-1]["head"]) == 40
    assert "receipt" in out.stdout


def test_the_reason_can_arrive_from_the_environment(tmp_path):
    root = _fixture(tmp_path, "1.2.3", FOLDED.format(top="1.2.3"))
    receipt = tmp_path / "receipts.jsonl"
    done = subprocess.run(
        ["bash", str(root / "scripts" / "release_cut.sh"), "--dry-run", "--local", "--skip-gates"],
        capture_output=True,
        text=True,
        cwd=root,
        env={
            **os.environ,
            "EPHE_RELEASE_RECEIPT": str(receipt),
            "EPHE_RELEASE_SKIP_REASON": "documented exception",
        },
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert json.loads(receipt.read_text(encoding="utf-8"))["reason"] == "documented exception"


def test_the_release_workflow_runs_the_same_checklist():
    doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")) or {}
    job = (doc.get("jobs") or {})["test-gate"]
    runs = [str(step.get("run", "")) for step in job.get("steps") or []]
    checklist = [text for text in runs if "release_checklist.py" in text]
    assert len(checklist) == 1, "release.yml does not run the checklist exactly once"
    text = checklist[0]
    assert "--skip-pass3" in text, "the workflow already ran the pass^3 gate"
    assert "--skip-signing" in text, "the build job's guard owns the key"
    assert "--tagged" in text, "the tag already exists at a tag-push event"
