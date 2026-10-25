"""The public trunk carries product documentation and no workshop state.

The workshop is the private repository. A dated workshop document under docs/
and a reference to the retired export pipeline are the two shapes that would
drag it back into this tree.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = "tests/test_public_docs_policy.py"
DATED = re.compile(r"\d{4}-\d{2}-\d{2}")
FORBIDDEN = ("public_export", ".publish-exclude", "public-release.json")
TEXT_SUFFIXES = {
    ".md", ".py", ".yml", ".yaml", ".json", ".sh", ".toml",
    ".mjs", ".js", ".ts", ".tsx", ".ps1",
}
RECEIPT = re.compile(r"docs/RELEASE_RECEIPT_\d+\.\d+\.\d+\.md")


def tracked() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return out.stdout.splitlines()


def test_no_dated_document_under_docs():
    dated = [
        rel for rel in tracked()
        if rel.startswith("docs/") and DATED.search(Path(rel).name)
    ]
    assert dated == [], f"dated workshop documents in the public docs tree: {dated}"


def test_no_reference_to_the_retired_export_pipeline():
    hits: list[str] = []
    for rel in tracked():
        if rel == SELF or Path(rel).suffix not in TEXT_SUFFIXES:
            continue
        text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        hits.extend(f"{rel}: {token}" for token in FORBIDDEN if token in text)
    assert hits == [], "retired export pipeline referenced: " + ", ".join(hits)


def test_a_release_receipt_is_version_named():
    for rel in tracked():
        if rel.startswith("docs/") and "RECEIPT" in Path(rel).name.upper():
            assert RECEIPT.fullmatch(rel), rel
