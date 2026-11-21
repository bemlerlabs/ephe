"""The research ledger's two caps, pinned at the seam that sets them.

`MAX_RUNS` and `MAX_SOURCES` are read by nothing outside this module, and before these cases no
test had ever constructed an `EvidenceLedger` with a bound: the class promised "bounded and newest
first" and either cap could break in either direction unnoticed. The cases drive the constructor,
because the product's own producer caps one run at `policy.MAX_PAGES` sources — the source bound
binds a caller that builds a tighter ledger than the defaults, and the last case pins the relation
between the two numbers.
"""

from __future__ import annotations

import hashlib

from core.web_intake.evidence import EvidenceSource
from core.web_intake.ledger import MAX_RUNS, EvidenceLedger


def _source(index: int) -> EvidenceSource:
    body = f"page {index}"
    return EvidenceSource(
        source_id=f"s{index}",
        url=f"https://example.test/{index}",
        title=f"Page {index}",
        fetched_at="2026-11-18T00:00:00Z",
        content_type="text/html",
        sha256=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        extract=body,
    )


def _sources(count: int) -> list[EvidenceSource]:
    return [_source(i) for i in range(count)]


def _record(ledger: EvidenceLedger, name: str, *, sources: int = 0):
    return ledger.record(query=name, sources=_sources(sources))


class TestLedgerCaps:
    def test_the_newest_runs_stay_and_the_oldest_leaves(self):
        ledger = EvidenceLedger(max_runs=3)
        for name in ("a", "b", "c", "d", "e"):
            _record(ledger, name)

        assert [run.query for run in ledger.runs()] == ["e", "d", "c"]

    def test_a_run_over_the_source_cap_takes_the_oldest_run_with_it(self):
        ledger = EvidenceLedger(max_runs=10, max_sources=5)
        _record(ledger, "old", sources=3)
        _record(ledger, "new", sources=3)

        runs = ledger.runs()
        assert [run.query for run in runs] == ["new"]
        assert sum(len(run.sources) for run in runs) == 3

    def test_the_source_cap_never_leaves_the_ledger_empty(self):
        """One run over an impossible cap stays whole: the alternative is an empty answer."""
        ledger = EvidenceLedger(max_runs=10, max_sources=1)
        _record(ledger, "alone", sources=4)

        runs = ledger.runs()
        assert [run.query for run in runs] == ["alone"]
        assert len(runs[0].sources) == 4

    def test_the_default_caps_hold_every_run_the_product_can_produce(self):
        """`MAX_PAGES` sources per run (policy's own bound) must never cost a run at the defaults."""
        from core.web_intake.policy import MAX_PAGES

        ledger = EvidenceLedger()
        for index in range(MAX_RUNS):
            _record(ledger, f"q{index}", sources=MAX_PAGES)

        runs = ledger.runs()
        assert len(runs) == MAX_RUNS
        assert sum(len(run.sources) for run in runs) == MAX_RUNS * MAX_PAGES
