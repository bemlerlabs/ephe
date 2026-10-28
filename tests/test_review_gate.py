"""The review gate refuses what it cannot read and what it must not allow.

A gate that can only agree is not a gate. These tests hold the two refusals that make the
change set safe to merge: a verdict arrives with a reason a reviewer can act on, and the
agent that wrote a change set is not the agent that approves it. Both are asserted as
nothing-recorded, so a refused submission leaves ``decide`` exactly where it was.

The self-approval proof has two halves on purpose. ``submit`` refuses a self-approval, and
``may_publish`` refuses one already lying in the ledger, so an approval written straight
into the file by hand is refused too.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from core import review_gate
from core.review_gate import (
    APPROVE,
    REJECT,
    REQUEST_CHANGES,
    ChangeSet,
    Reason,
    ReviewGateError,
    ReviewLedger,
    ReviewVerdict,
)

AUTHOR = "wt/w1-review"
REVIEWER = "wt/reviewer-2"

#: A change set with a file list, so a reason can be held to the files it names.
CHANGE_SET = ChangeSet(change_set_id="cs-1", author=AUTHOR, paths=("core/review_gate.py",))
GOOD = [{"path": "core/review_gate.py", "line": 42, "why": "line 42 re-reads the ledger per call"}]


@pytest.fixture()
def ledger(tmp_path: Path) -> ReviewLedger:
    return ReviewLedger(tmp_path / "reviews.jsonl")


def decided(ledger: ReviewLedger, change_set: ChangeSet | str) -> ReviewVerdict:
    """``decide`` with the None an empty ledger answers taken out of the way."""
    verdict = ledger.decide(change_set)
    assert verdict is not None
    return verdict


def test_approve_is_recorded_and_may_publish(ledger: ReviewLedger) -> None:
    verdict = ledger.submit(CHANGE_SET, APPROVE, REVIEWER, GOOD)
    assert verdict.verdict == APPROVE
    assert verdict.change_set_id == "cs-1"
    assert verdict.reviewer == REVIEWER
    assert ledger.decide(CHANGE_SET) == verdict
    assert ledger.may_publish(CHANGE_SET) is True


def test_request_changes_and_reject_hold_the_change_set_back(ledger: ReviewLedger) -> None:
    for decision in (REQUEST_CHANGES, REJECT):
        fresh = ReviewLedger(None)
        fresh.submit(CHANGE_SET, decision, REVIEWER, GOOD)
        assert decided(fresh, CHANGE_SET).verdict == decision
        assert fresh.may_publish(CHANGE_SET) is False


def test_nothing_publishes_before_a_verdict_exists(ledger: ReviewLedger) -> None:
    assert ledger.decide(CHANGE_SET) is None
    assert ledger.may_publish(CHANGE_SET) is False


@pytest.mark.parametrize("decision", [APPROVE, REQUEST_CHANGES, REJECT])
def test_a_verdict_without_reasons_is_refused(ledger: ReviewLedger, decision: str) -> None:
    empty_values: tuple[object, ...] = (None, [], ())
    for empty in empty_values:
        with pytest.raises(ReviewGateError, match="at least one reason"):
            ledger.submit(CHANGE_SET, decision, REVIEWER, empty)  # type: ignore[arg-type]
    assert ledger.decide(CHANGE_SET) is None
    assert ledger.may_publish(CHANGE_SET) is False


@pytest.mark.parametrize(
    "reason",
    [
        {"line": 7, "why": "no path"},
        {"path": "core/review_gate.py", "why": "no line"},
        {"path": "core/review_gate.py", "line": 7},
        {"path": "", "line": 7, "why": "blank path"},
        {"path": "core/review_gate.py", "line": 0, "why": "line zero is not a line"},
        {"path": "core/review_gate.py", "line": -3, "why": "negative line"},
        {"path": "core/review_gate.py", "line": "12", "why": "a line is a number"},
        {"path": "core/review_gate.py", "line": True, "why": "bool is not a line"},
        {"path": "core/review_gate.py", "line": 7, "why": "   "},
        {"path": "core/review_gate.py", "line": 7, "why": "x", "severity": "blocker"},
    ],
)
def test_a_reason_must_name_a_file_and_a_line(ledger: ReviewLedger, reason: dict) -> None:
    with pytest.raises(ReviewGateError):
        ledger.submit(CHANGE_SET, REJECT, REVIEWER, [reason])
    assert ledger.decide(CHANGE_SET) is None


def test_a_reason_is_stored_with_exactly_path_line_why(ledger: ReviewLedger) -> None:
    verdict = ledger.submit(CHANGE_SET, APPROVE, REVIEWER, GOOD)
    assert verdict.to_dict()["reasons"] == [
        {"path": "core/review_gate.py", "line": 42, "why": "line 42 re-reads the ledger per call"}
    ]
    assert decided(ledger, CHANGE_SET).to_dict() == verdict.to_dict()


def test_a_reason_may_be_a_reason_object(ledger: ReviewLedger) -> None:
    verdict = ledger.submit(
        CHANGE_SET, APPROVE, REVIEWER, [Reason("core/review_gate.py", 1, "the header lies")]
    )
    assert verdict.reasons[0].where() == "core/review_gate.py:1"


def test_an_author_cannot_approve_its_own_change_set(ledger: ReviewLedger) -> None:
    with pytest.raises(ReviewGateError, match="authored cs-1 and cannot approve"):
        ledger.submit(CHANGE_SET, APPROVE, AUTHOR, GOOD)
    assert ledger.decide(CHANGE_SET) is None
    assert ledger.may_publish(CHANGE_SET) is False


def test_an_author_may_still_block_its_own_change_set(ledger: ReviewLedger) -> None:
    for decision in (REQUEST_CHANGES, REJECT):
        fresh = ReviewLedger(None)
        fresh.submit(CHANGE_SET, decision, AUTHOR, GOOD)
        assert decided(fresh, CHANGE_SET).verdict == decision
        assert fresh.may_publish(CHANGE_SET) is False


def test_a_self_approval_written_into_the_ledger_still_cannot_publish(tmp_path: Path) -> None:
    path = tmp_path / "reviews.jsonl"
    line = {
        "schema": 1,
        "change_set_id": "cs-1",
        "author": AUTHOR,
        "verdict": APPROVE,
        "reviewer": AUTHOR,
        "reasons": GOOD,
    }
    path.write_text(json.dumps(line) + "\n", encoding="utf-8")
    ledger = ReviewLedger(path)
    # The line is readable as a verdict, and the gate still answers no.
    assert decided(ledger, CHANGE_SET).reviewer == AUTHOR
    assert ledger.may_publish(CHANGE_SET) is False


def test_a_change_set_presented_under_another_author_does_not_publish(ledger: ReviewLedger) -> None:
    ledger.submit(CHANGE_SET, APPROVE, REVIEWER, GOOD)
    impostor = ChangeSet(change_set_id="cs-1", author="someone/else", paths=("core/review_gate.py",))
    assert ledger.may_publish(impostor) is False


def test_the_latest_verdict_wins(ledger: ReviewLedger) -> None:
    ledger.submit(CHANGE_SET, REJECT, REVIEWER, GOOD)
    ledger.submit(CHANGE_SET, APPROVE, REVIEWER, GOOD)
    assert decided(ledger, CHANGE_SET).verdict == APPROVE
    assert ledger.may_publish(CHANGE_SET) is True

    ledger.submit(CHANGE_SET, REQUEST_CHANGES, REVIEWER, GOOD)
    assert decided(ledger, CHANGE_SET).verdict == REQUEST_CHANGES
    assert ledger.may_publish(CHANGE_SET) is False


def test_a_verdict_for_another_change_set_does_not_leak(ledger: ReviewLedger) -> None:
    other = ChangeSet(change_set_id="cs-2", author=AUTHOR, paths=("core/review_gate.py",))
    ledger.submit(other, APPROVE, REVIEWER, GOOD)
    assert ledger.decide(CHANGE_SET) is None
    assert ledger.may_publish(CHANGE_SET) is False
    assert ledger.may_publish(other) is True


def test_a_reason_outside_the_change_set_is_refused(ledger: ReviewLedger) -> None:
    stray = [{"path": "core/audit_log.py", "line": 5, "why": "not in this change set"}]
    with pytest.raises(ReviewGateError, match="does not touch core/audit_log.py:5"):
        ledger.submit(CHANGE_SET, REJECT, REVIEWER, stray)
    assert ledger.decide(CHANGE_SET) is None


def test_an_unknown_verdict_is_refused(ledger: ReviewLedger) -> None:
    for decision in ("lgtm", "", "Approve-ish", "APPROVED"):
        with pytest.raises(ReviewGateError, match="unknown verdict"):
            ledger.submit(CHANGE_SET, decision, REVIEWER, GOOD)
    assert ledger.decide(CHANGE_SET) is None


def test_a_verdict_needs_a_reviewer(ledger: ReviewLedger) -> None:
    reviewers: tuple[object, ...] = ("", "   ", None)
    for reviewer in reviewers:
        with pytest.raises(ReviewGateError, match="needs the reviewer"):
            ledger.submit(CHANGE_SET, APPROVE, reviewer, GOOD)  # type: ignore[arg-type]
    assert ledger.decide(CHANGE_SET) is None


def test_a_latest_line_that_will_not_parse_publishes_nothing(ledger: ReviewLedger) -> None:
    ledger.submit(CHANGE_SET, APPROVE, REVIEWER, GOOD)
    assert ledger.may_publish(CHANGE_SET) is True
    path = ledger.path
    assert path is not None
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"change_set_id": "cs-1", "verdict": "approve"}) + "\n")
    assert ledger.decide(CHANGE_SET) is None
    assert ledger.may_publish(CHANGE_SET) is False


def test_a_verdict_survives_a_new_reader(tmp_path: Path) -> None:
    path = tmp_path / "reviews.jsonl"
    ReviewLedger(path).submit(CHANGE_SET, APPROVE, REVIEWER, GOOD)
    reopened = ReviewLedger(path)
    assert decided(reopened, CHANGE_SET).reviewer == REVIEWER
    assert reopened.may_publish(CHANGE_SET) is True


def test_a_path_the_ledger_cannot_write_to_refuses_the_submission(tmp_path: Path) -> None:
    blocked = tmp_path / "reviews.jsonl"
    blocked.mkdir()
    with pytest.raises(ReviewGateError, match="was not recorded"):
        ReviewLedger(blocked).submit(CHANGE_SET, APPROVE, REVIEWER, GOOD)
    assert ReviewLedger(blocked).decide(CHANGE_SET) is None


def test_the_module_interface_is_the_documented_one() -> None:
    submit_params = list(inspect.signature(review_gate.submit).parameters)
    assert submit_params == ["change_set", "verdict", "reviewer", "reasons"]
    assert list(inspect.signature(review_gate.decide).parameters) == ["change_set"]
    assert list(inspect.signature(review_gate.may_publish).parameters) == ["change_set"]


def test_the_module_level_submit_decide_and_may_publish_run_through_one_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(review_gate, "_default_ledger", ReviewLedger(tmp_path / "reviews.jsonl"))
    assert review_gate.may_publish("cs-1") is False
    verdict = review_gate.submit(CHANGE_SET, APPROVE, REVIEWER, GOOD)
    assert isinstance(verdict, ReviewVerdict)
    latest = review_gate.decide("cs-1")
    assert latest is not None and latest.verdict == APPROVE
    assert review_gate.may_publish("cs-1") is True


def test_self_signature_carries_its_own_code():
    """J2: an author approving its own work answers a stable code, not prose."""
    import pytest

    from core.review_gate import ChangeSet, Reason, ReviewGateError, ReviewLedger

    ledger = ReviewLedger(path=None)
    target = ChangeSet(change_set_id="cs-9", author="agent-a", paths=("src/a.py",))
    with pytest.raises(ReviewGateError) as caught:
        ledger.submit(
            target,
            "approve",
            "agent-a",
            [Reason(path="src/a.py", line=12, why="looks fine")],
        )
    assert caught.value.code == "self_sign_forbidden"


def test_another_refusal_keeps_the_generic_code():
    import pytest

    from core.review_gate import ChangeSet, Reason, ReviewGateError, ReviewLedger

    ledger = ReviewLedger(path=None)
    target = ChangeSet(change_set_id="cs-10", author="agent-a", paths=("src/a.py",))
    with pytest.raises(ReviewGateError) as caught:
        ledger.submit(
            target,
            "approve",
            "agent-b",
            [Reason(path="src/other.py", line=3, why="outside the set")],
        )
    assert caught.value.code == "review_refused"
