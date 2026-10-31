"""The public trunk carries product documentation and no workshop state.

The workshop is the private repository: orders, plans, boards, decision records,
competitive readings and the working-backwards drafts live there and stay there.
This gate names the two ways they used to reach this tree — a dated filename and
a document whose own words say it is an order — so a later wave cannot publish
one again by naming it after its subject.
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

#: A workshop document names its own class: the order it answers, the plan it
#: carries, the decision it records. None of those classes is a product page.
WORKSHOP_NAME = re.compile(
    r"(^|_)(ORDER|DIRECTIVE|DECISION|PLAN|BOARD|CHECKLIST|DOSSIER|STRATEGY|ROADMAP"
    r"|BRAINSTORM|PROPOSAL|COMPETITIVE|MASTER|WORKING_BACKWARDS|AT_A_GLANCE|SPEC)(\.|_|$)",
    re.IGNORECASE,
)
#: A document can carry the class in its first line instead of its name.
WORKSHOP_TEXT = re.compile(
    r"owner order|order:\s*s\d|playbook rule|working-backwards",
    re.IGNORECASE,
)
#: The comparison names live in the workshop. A public page cites prior art by
#: what it does, never by whose product it is.
COMPETITORS = re.compile(r"\b(Qoder|Hermes|Cursor|pi coding agent)\b")
PUBLIC_MARKDOWN = ("docs/", "README", "CONTRIBUTING", "SECURITY", "COMMERCIAL")


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


def test_no_workshop_document_published_under_docs():
    offenders = [
        rel for rel in tracked()
        if rel.startswith("docs/")
        and rel.endswith(".md")
        and WORKSHOP_NAME.search(Path(rel).name)
    ]
    assert offenders == [], f"workshop documents in the public docs tree: {offenders}"


def test_no_document_announces_itself_as_an_order():
    offenders: list[str] = []
    for rel in tracked():
        if not rel.endswith(".md"):
            continue
        if not (rel.startswith(PUBLIC_MARKDOWN) or Path(rel).name in {
            "README.md", "CONTRIBUTING.md", "SECURITY.md", "COMMERCIAL.md",
        }):
            continue
        text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        match = WORKSHOP_TEXT.search(text)
        if match:
            offenders.append(f"{rel}: {match.group(0)!r}")
    assert offenders == [], "workshop prose in a public document: " + ", ".join(offenders)


def test_no_competitor_product_is_named_in_the_public_documents():
    offenders: list[str] = []
    for rel in tracked():
        if not rel.endswith(".md") or rel.startswith("app/"):
            continue
        text = (ROOT / rel).read_text(encoding="utf-8", errors="ignore")
        found = {m.group(0).lower() for m in COMPETITORS.finditer(text)}
        if found:
            offenders.append(f"{rel}: {sorted(found)}")
    assert offenders == [], "competitor names in the public tree: " + ", ".join(offenders)
