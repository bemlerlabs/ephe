"""The release cut refuses to start while the changelog names addresses the trunk does not carry.

A rebase merge rewrites the commits it lands, so a bullet written on a branch can name an sha that
exists only there. `scripts/changelog_remap.py` proves each move by patch id; these tests hold the
cut to three things: the gate runs, it runs read-only (`--check`, so a cut never rewrites a file it
is about to tag), and it judges the release remote's branch rather than a literal `origin` — the
same trap the provenance gate fell into on 2026-11-01, when a working clone's tag refs held another
lineage's commits.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_cut.sh"


def text() -> str:
    return SCRIPT.read_text(encoding="utf-8")


def gate_line(label: str) -> str:
    hits = [l for l in text().splitlines() if f'run_gate "{label}"' in l]
    assert len(hits) == 1, (label, hits)
    return hits[0]


class TestTheGateIsWired:
    def test_the_cut_runs_a_changelog_addresses_gate(self):
        assert 'run_gate "changelog addresses"' in text()

    def test_it_runs_read_only(self):
        """A cut must not rewrite CHANGELOG.md on its way to tagging a commit: a write here would
        leave the tree dirty against the very sha it is about to tag."""
        assert "--check" in gate_line("changelog addresses")
        assert not re.search(r'run_gate "changelog addresses"[^\n]*(--write|> *CHANGELOG)', text())

    def test_it_judges_the_release_remote_not_a_literal_origin(self):
        line = gate_line("changelog addresses")
        assert '--base "$REMOTE/$BRANCH"' in line, line
        assert '"origin/' not in line, line

    def test_it_runs_before_the_unreleased_check(self):
        order = [l for l in text().splitlines() if "run_gate \"changelog" in l]
        assert "addresses" in order[0] and "Unreleased" in order[1], order


class TestTheToolIsTheOneThatJudges:
    def test_the_gate_delegates_the_whole_decision_to_the_tool(self):
        """The cut does not re-implement address matching: it runs the tool and obeys its exit
        code. The tool's own behaviour (a proven move, a pending one, a refused guess) is pinned
        in tests/test_changelog_remap.py against a repository it builds itself."""
        line = gate_line("changelog addresses")
        assert "changelog_remap.py" in line, line
        # The gate's own line matches nothing: no git, no sed, no awk. Reading the trunk's
        # version out of the changelog is a different job, done elsewhere in the script.
        assert not re.search(r"\b(git|sed|awk)\b", line), line
