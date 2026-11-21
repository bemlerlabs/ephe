"""W3-73 - deterministic tests for the judge-eval harness (no model).

The harness scores the rubric judge (``core.react.reflect``) against a
human-labelled gold set. Its *live* number needs the engine; these tests prove
the parts that must be right for that number to mean anything, without a socket:

  * the label set parses, validates and holds both classes;
  * the confusion matrix and its precision/recall are arithmetically correct;
  * the Wilson interval is sane and bounds the point estimate;
  * the rep majority vote and the tie rule are correct;
  * a malformed label row is rejected (never silently dropped);
  * the verdict mapping and the product's own REVISION parser behave.

Run: `.venv/bin/python -m pytest evals/judge_test.py -q`
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evals import judge_eval as J

POS, NEG = J.POSITIVE, J.NEGATIVE


# --------------------------------------------------------------------------- #
# Label set
# --------------------------------------------------------------------------- #

def test_labels_parse_and_are_balanced():
    rows = J.load_labels(J.DEFAULT_LABELS)
    dist = J.label_distribution(rows)
    assert dist["total"] == len(rows) >= 20
    # Precision and recall both need positives AND negatives to be defined.
    assert dist["defective"] >= 5
    assert dist["ok"] >= 5
    for r in rows:
        assert set(J.REQUIRED_FIELDS) <= set(r)
        assert r["label"] in (POS, NEG)


def test_malformed_label_row_is_rejected(tmp_path):
    p = tmp_path / "labels.jsonl"
    p.write_text(
        '{"id":"x","category":"c","label":"defective","question":"q",'
        '"answer":"a"}\n',  # rationale missing
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        J.load_labels(p)


def test_unknown_label_is_rejected(tmp_path):
    p = tmp_path / "labels.jsonl"
    p.write_text(
        '{"id":"x","category":"c","label":"maybe","question":"q",'
        '"answer":"a","rationale":"r"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        J.load_labels(p)


def test_duplicate_id_is_rejected(tmp_path):
    row = ('{"id":"x","category":"c","label":"ok","question":"q",'
           '"answer":"a","rationale":"r"}\n')
    p = tmp_path / "labels.jsonl"
    p.write_text(row + row, encoding="utf-8")
    with pytest.raises(ValueError):
        J.load_labels(p)


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #

def test_confusion_and_precision_recall_are_correct():
    # tp=3 fp=1 fn=2 tn=4  -> precision 3/4, recall 3/5
    pairs = [(POS, POS)] * 3 + [(NEG, POS)] + [(POS, NEG)] * 2 + [(NEG, NEG)] * 4
    cm = J.confusion(pairs)
    assert (cm["tp"], cm["fp"], cm["fn"], cm["tn"]) == (3, 1, 2, 4)
    assert cm["precision"] == 0.75
    assert cm["recall"] == 0.6
    assert cm["accuracy"] == round(7 / 10, 4)


def test_confusion_rejects_bad_labels():
    with pytest.raises(ValueError):
        J.confusion([("maybe", POS)])


def test_wilson_bounds_the_point_estimate():
    lo, hi = J.wilson_ci(13, 15)
    assert 0.0 <= lo <= 13 / 15 <= hi <= 1.0
    assert J.wilson_ci(0, 0) == [0.0, 0.0]


def test_majority_vote_and_tie_rule():
    assert J._majority([POS, POS, NEG]) == POS
    assert J._majority([POS, NEG, NEG]) == NEG
    assert J._majority([POS, NEG]) == NEG  # tie -> negative


def test_per_category_groups_by_human_category():
    rows = [
        {"category": "a"}, {"category": "a"}, {"category": "b"},
    ]
    pairs = [(POS, POS), (NEG, NEG), (POS, NEG)]
    cats = J.per_category(rows, pairs)
    assert cats["a"]["n"] == 2 and cats["a"]["tp"] == 1 and cats["a"]["tn"] == 1
    assert cats["b"]["fn"] == 1


# --------------------------------------------------------------------------- #
# Judge interface
# --------------------------------------------------------------------------- #

class _R:
    def __init__(self, needs_revision, status="ok", reason=""):
        self.needs_revision = needs_revision
        self.status = status
        self.reason = reason


def test_verdict_mapping():
    assert J.judge_verdict_from_result(_R(True)) == POS
    assert J.judge_verdict_from_result(_R(False)) == NEG


def test_product_parser_roundtrip():
    from core.react import _parse_reflexion
    assert _parse_reflexion("x\nREVISION: YES\nReason: wrong fact").needs_revision is True
    assert _parse_reflexion("fine\nREVISION: NO").needs_revision is False
    assert _parse_reflexion("").status == "provider_error"


def test_build_receipt_shape():
    rows = [
        {"id": "1", "category": "c", "label": POS, "question": "q",
         "answer": "a", "rationale": "r"},
        {"id": "2", "category": "c", "label": NEG, "question": "q",
         "answer": "a", "rationale": "r"},
    ]
    records = [
        {"id": "1", "category": "c", "human_label": POS, "judge_label": POS,
         "votes": [POS, POS, POS], "judge_statuses": ["ok"] * 3,
         "answered_reps": 3, "judge_reason": "bad"},
        {"id": "2", "category": "c", "human_label": NEG, "judge_label": NEG,
         "votes": [NEG, NEG, NEG], "judge_statuses": ["no_revision"] * 3,
         "answered_reps": 3, "judge_reason": ""},
    ]
    labels_path = J.DEFAULT_LABELS
    r = J.build_receipt(rows, records, {"provider": "x", "model": "y", "api_url": "z"},
                        labels_path, reps=3)
    assert r["metrics"]["precision"] == 1.0 and r["metrics"]["recall"] == 1.0
    assert len(r["metrics_per_rep"]) == 3
    assert r["unanswered_cases"] == []
    assert r["engine"]["model"] == "y"
    # JSON-serialisable end to end
    json.dumps(r)
