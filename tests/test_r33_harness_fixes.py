"""
Ephe — R33 / stress triage P3-2: harness honesty fixes.

The 1000-message campaign report (docs/STRESS_1000_2026-09-06.md, P3-2)
recorded four harness limitations, fixed here as pure, unit-testable helpers
inside scripts/stress_1000_messages.py:

  1. retry transparency  — the first-attempt failure was silently overwritten
     whenever a retry succeeded (9 rows said attempts:2 with no reason);
  2. resume idempotence  — an external kill lost the last progress flush, so
     resumed runs re-executed up to ~24 items (1013 lines for 1000 ids);
     completed rows in the results JSONL must seed the skip set;
  3. RSS samples survive — a resumed run overwrote rss_samples.json, losing
     the earlier 30s curve; samples are now merged, never clobbered;
  4. emoji tolerance     — 62 ultra-short (emoji / one-word) replies were
     flagged lang_unclassifiable although hard mismatches were 0; the
     heuristic's blind spot must not count as a validation failure.

Given / When / Then — strikt. Tests BEFORE implementation (WGT).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "stress_1000_messages.py"


@pytest.fixture(scope="session")
def stress_mod():
    spec = importlib.util.spec_from_file_location("ephe_stress_harness", str(SCRIPT))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[spec.name] = module
    return module


class TestRetryTransparency:
    def test_first_attempt_failure_is_preserved(self, stress_mod):
        """GIVEN a failed first attempt + successful retry WHEN bookkeeping THEN reason survives."""
        res = {"ok": True, "valid": True, "attempts": 2}
        first = {"ok": False, "failure": "stream_error", "status": 200}
        out = stress_mod.apply_first_attempt_bookkeeping(res, first)
        assert out["first_attempt_failure"] == "stream_error"
        assert out["first_attempt_status"] == 200

    def test_successful_first_attempt_records_nothing(self, stress_mod):
        """GIVEN success on attempt one WHEN bookkeeping THEN no failure fields."""
        res = {"ok": True, "attempts": 1}
        out = stress_mod.apply_first_attempt_bookkeeping(res, {"ok": True, "status": 200})
        assert "first_attempt_failure" not in out


class TestResumeIdempotence:
    def test_done_indices_are_seeded_from_results_jsonl(self, stress_mod, tmp_path):
        """GIVEN a results JSONL from a killed run WHEN seeding THEN its ids count as done."""
        rows = [
            {"idx": 0, "ok": True, "valid": True},
            {"idx": 1, "ok": False, "valid": False, "failure": "http_503"},
            {"idx": 2, "ok": True, "valid": True},
        ]
        path = tmp_path / "results_full.jsonl"
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
        done = stress_mod.load_done_indices(path)
        assert set(done) == {0, 1, 2}  # every written id is skipped on resume

    def test_torn_last_line_is_tolerated(self, stress_mod, tmp_path):
        """GIVEN a half-written final line (kill during append) WHEN seeding THEN no crash."""
        path = tmp_path / "results_full.jsonl"
        path.write_text('{"idx": 5, "ok": true}\n{"idx": 6", "ok"', encoding="utf-8")
        done = stress_mod.load_done_indices(path)
        assert set(done) == {5}

    def test_missing_file_yields_empty(self, stress_mod, tmp_path):
        """GIVEN no results file WHEN seeding THEN empty done set."""
        assert stress_mod.load_done_indices(tmp_path / "nope.jsonl") == {}


class TestRssMerge:
    def test_samples_merge_without_clobber(self, stress_mod):
        """GIVEN old samples from a previous run WHEN merging THEN both survive, ordered."""
        old = [{"ts": 1.0, "pid": 7, "rss_mb": 100.0}, {"ts": 2.0, "pid": 7, "rss_mb": 101.0}]
        new = [{"ts": 3.0, "pid": 7, "rss_mb": 102.0}]
        merged = stress_mod.merge_rss_samples(old, new)
        assert [s["ts"] for s in merged] == [1.0, 2.0, 3.0]

    def test_duplicate_timestamps_dedupe(self, stress_mod):
        """GIVEN re-sampled identical points WHEN merging THEN each point appears once."""
        same = {"ts": 1.0, "pid": 7, "rss_mb": 100.0}
        merged = stress_mod.merge_rss_samples([same], [same, {"ts": 4.0, "pid": 7}])
        assert len(merged) == 2


class TestEmojiTolerance:
    def test_substantive_german_reply_classifies(self, stress_mod):
        """GIVEN a normal DE answer with emoji bullets WHEN checking THEN pass, no violation."""
        status, note = stress_mod.tolerant_language_check(
            "de", "✅ Gerne! Und ich helfe dir dabei, das ist schnell erledigt. 🌲"
        )
        assert status == "pass"
        assert note == ""

    def test_emoji_only_reply_is_tolerated_not_flagged(self, stress_mod):
        """GIVEN an ultra-short emoji acknowledgment WHEN checking THEN tolerated, not a violation."""
        status, _ = stress_mod.tolerant_language_check("de", "👍🎉")
        assert status == "tolerated"

    def test_hard_mismatch_still_fires(self, stress_mod):
        """GIVEN a DE probe answered in solid English WHEN checking THEN mismatch still reports."""
        status, _ = stress_mod.tolerant_language_check(
            "de",
            "The reason why you would never do that is because the system files "
            "would be deleted and there is no way to recover this.",
        )
        assert status == "mismatch"

    def test_long_unclassifiable_text_still_violates(self, stress_mod):
        """GIVEN a long reply with no DE/EN stopword evidence WHEN checking THEN violation kept."""
        status, _ = stress_mod.tolerant_language_check(
            "de",
            "Bonjour, comment allez-vous aujourd'hui? Il fait tres beau temps, "
            "nous allons au marche au parc ensemble.",
        )
        assert status == "unclassifiable"
