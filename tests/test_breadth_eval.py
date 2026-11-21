"""The breadth (4c) and repeatability (4d) arithmetic, with no engine in the loop.

Every test here builds its runs from the fixture helpers or replays the reconstructed
legacy receipt, so the suite pins the denominators, the intervals and the quotability
rule while an engine stays out of it.
"""
import json
from pathlib import Path

import pytest

import evals.breadth_eval as breadth
from evals.breadth_eval import (
    DEFAULT_FIXTURE,
    FAIL,
    PASS,
    UNUSABLE,
    ReceiptError,
    breadth_report,
    expected_cases,
    fixture_runs,
    load_fixture,
    main,
    outcome_of_row,
    paid_runs,
    repeatability_report,
    runs_from_receipt,
)

REPO = Path(__file__).resolve().parents[1]
LEGACY = REPO / "evals" / "breadth" / "legacy-10-of-24.json"


def _row(case_id: str, category: str, status: str) -> dict:
    if status == PASS:
        return {"case_id": case_id, "category": category, "turn_ok": True,
                "checks": [{"check": "manifest_valid", "ok": True}], "not_run": []}
    if status == FAIL:
        return {"case_id": case_id, "category": category, "turn_ok": True,
                "checks": [{"check": "manifest_valid", "ok": False,
                            "detail": "no declared entry"}], "not_run": []}
    return {"case_id": case_id, "category": category, "turn_ok": None,
            "turn_detail": "the turn was not graded", "checks": [], "not_run": []}


def _receipt(expected: dict[str, str], statuses: dict[str, str], **meta) -> dict:
    rows = [_row(case_id, category, statuses[case_id])
            for case_id, category in expected.items()]
    return {
        "total": len(rows),
        "passed": sum(1 for status in statuses.values() if status == PASS),
        "cases": rows,
        **meta,
    }


def _small_expected() -> dict[str, str]:
    return {"a": "x", "b": "x", "c": "y", "d": "y"}


def _fixture(expected: dict[str, str], runs: dict[str, list[str]]) -> list:
    document = {
        "schema": 1,
        "evidence": "engine",
        "engine": {"provider": "openai_compatible", "model": "fixture-model"},
        "runs": len(next(iter(runs.values()))),
        "cases": [{"id": case_id, "outcomes": outcomes}
                  for case_id, outcomes in runs.items()],
    }
    return fixture_runs(document, expected)


def test_a_check_that_did_not_run_leaves_the_denominator_instead_of_counting_as_a_failure():
    outcome = outcome_of_row(
        {"case_id": "c1", "turn_ok": True,
         "checks": [{"check": "manifest_valid", "ok": True}],
         "not_run": ["offer_matches_grant"]},
        "widget",
    )

    assert outcome.status == UNUSABLE
    assert "offer_matches_grant" in outcome.detail


def test_a_turn_with_no_end_state_check_is_unusable_because_nothing_measured_the_bundle():
    outcome = outcome_of_row(
        {"case_id": "c1", "turn_ok": True, "checks": [], "not_run": []}, "widget"
    )

    assert outcome.status == UNUSABLE
    assert "no end-state check" in outcome.detail


def test_a_malformed_receipt_returns_two_instead_of_tracebacking(tmp_path, capsys):
    receipt = tmp_path / "bad.json"
    receipt.write_text('{"cases": []}', encoding="utf-8")

    code = main(["--receipt", str(receipt)])

    assert code == 2
    assert "no run" in capsys.readouterr().err


def test_a_turn_that_was_never_graded_is_unusable_and_a_failed_check_is_a_failure():
    ungraded = outcome_of_row({"case_id": "c1", "turn_ok": None, "checks": []}, "widget")
    failed = outcome_of_row(
        {"case_id": "c2", "turn_ok": True,
         "checks": [{"check": "manifest_valid", "ok": False}], "not_run": []},
        "widget",
    )

    assert ungraded.status == UNUSABLE
    assert failed.status == FAIL
    assert "manifest_valid" in failed.detail


def test_a_receipt_that_holds_fewer_cases_than_the_set_is_refused_with_its_denominator():
    expected = {"a": "x", "b": "y"}
    receipt = {"cases": [_row("a", "x", PASS)]}

    with pytest.raises(ReceiptError, match="1 of 2"):
        runs_from_receipt(receipt, expected)


def test_a_receipt_that_relabels_a_class_is_refused():
    expected = {"a": "x"}
    receipt = {"cases": [_row("a", "y", PASS)]}

    with pytest.raises(ReceiptError, match="relabelled"):
        runs_from_receipt(receipt, expected)


def test_a_receipt_whose_headline_disagrees_with_its_rows_is_unquotable():
    expected = {"a": "x"}
    receipt = {"total": 1, "passed": 0, "cases": [_row("a", "x", PASS)]}

    run = runs_from_receipt(receipt, expected, evidence="engine")
    report = breadth_report(run, expected, min_cases=1, min_per_class=1)

    assert run.declared["matches_rows"] is False
    assert report["quotable"] is False
    assert any("declares 0/1" in reason for reason in report["defects"])


def test_a_complete_engine_receipt_with_full_classes_is_quotable():
    expected = _small_expected()
    run = runs_from_receipt(
        _receipt(expected, {case_id: PASS for case_id in expected}),
        expected, evidence="engine",
        engine={"provider": "openai_compatible", "model": "fixture-model"},
    )

    report = breadth_report(run, expected, min_cases=4, min_per_class=2)

    assert report["quotable"] is True
    assert report["defects"] == []
    assert report["scored"] == {"pass": 4, "total": 4, "rate": 1.0,
                                "ci95": [0.5101, 1.0]}


def test_the_legacy_10_of_24_is_reproduced_and_the_scored_rate_drops_the_four_unscored_rows():
    expected = expected_cases()
    run = breadth._load_receipt(LEGACY, expected, 1, None)
    report = breadth_report(run, expected)

    assert report["headline"] == {"pass": 10, "total": 24, "rate": 0.4167,
                                  "ci95": [0.2447, 0.6117]}
    assert report["scored"]["pass"] == 10
    assert report["scored"]["total"] == 20
    assert report["scored"]["rate"] == 0.5
    assert [row["case_id"] for row in report["unusable"]] == [
        "creation-04", "creation-15", "creation-20", "creation-24",
    ]
    assert report["quotable"] is False
    assert any("hold no verdict" in reason for reason in report["defects"])
    assert any("needs 'engine'" in reason for reason in report["defects"])


def test_the_legacy_report_prints_the_old_number_with_its_denominator_and_labels_it():
    expected = expected_cases()
    run = breadth._load_receipt(LEGACY, expected, 1, None)
    text = breadth.format_report(
        breadth.build_document("receipt:legacy", expected, [run])
    )

    assert "headline" in text
    assert "10/24" in text
    assert "0.4167" in text
    assert "scored" in text
    assert "10/20" in text
    assert "row(s) hold no verdict" in text
    assert "NOT QUOTABLE" in text


def test_a_class_below_the_floor_makes_the_rate_unquotable():
    expected = _small_expected()
    statuses = {"a": PASS, "b": FAIL, "c": PASS, "d": PASS}
    run = runs_from_receipt(
        _receipt(expected, statuses), expected, evidence="engine",
        engine={"provider": "openai_compatible", "model": "fixture-model"},
    )

    report = breadth_report(run, expected, min_cases=4, min_per_class=3)

    assert report["per_class"]["x"]["rateable"] is False
    assert report["quotable"] is False
    assert any("below the 3-case floor" in reason for reason in report["defects"])


def test_every_rate_in_the_report_names_its_denominator_and_its_interval():
    expected = expected_cases()
    document = breadth.build_document(
        "fixture:default", expected, load_fixture(DEFAULT_FIXTURE, expected)
    )
    blocks = [
        document["breadth"]["headline"],
        document["breadth"]["scored"],
        document["repeatability"]["agreement"],
        document["repeatability"]["pass^3"],
    ]

    for block in blocks:
        assert {"pass", "total", "rate", "ci95"} <= set(block)
    for row in document["breadth"]["per_class"].values():
        assert {"pass", "usable", "rate", "ci95"} <= set(row)
    assert document["method"]["interval"] == "wilson"
    assert document["method"]["level"] == 0.95


def test_the_dry_run_fixture_covers_the_set_with_three_runs():
    expected = expected_cases()

    runs = load_fixture(DEFAULT_FIXTURE, expected)

    assert len(runs) == 3
    assert [run.index for run in runs] == [1, 2, 3]
    assert all(run.evidence == "stub" for run in runs)
    for run in runs:
        assert [outcome.case_id for outcome in run.outcomes] == list(expected)


def test_three_runs_with_one_flip_name_the_flaky_case_and_keep_pass_cubed_separate():
    expected = _small_expected()
    runs = _fixture(expected, {
        "a": [PASS, PASS, PASS],
        "b": [PASS, FAIL, PASS],
        "c": [FAIL, FAIL, FAIL],
        "d": [PASS, PASS, PASS],
    })

    report = repeatability_report(runs, expected, min_cases=4, min_per_class=2)

    assert report["flaky"] == ["b"]
    assert report["stable"] == ["a", "c", "d"]
    assert report["agreement"] == {"pass": 3, "total": 4, "rate": 0.75,
                                   "ci95": [0.3006, 0.9544]}
    assert report["pass^3"] == {"pass": 2, "total": 4, "rate": 0.5,
                                "ci95": [0.15, 0.85]}
    assert report["per_class"]["x"] == {
        "cases": 2, "rates": [1.0, 0.5, 1.0], "mean_rate": 0.8333,
        "min_rate": 0.5, "max_rate": 1.0, "spread_pp": 50.0,
        "pass^3": 1, "flaky": ["b"],
    }
    assert report["quotable"] is True


def test_a_case_with_one_ungraded_run_is_incomplete_and_the_set_is_not_quotable():
    expected = _small_expected()
    runs = _fixture(expected, {
        "a": [PASS, PASS, PASS],
        "b": [PASS, PASS, PASS],
        "c": [FAIL, FAIL, FAIL],
        "d": [PASS, UNUSABLE, PASS],
    })

    report = repeatability_report(runs, expected, min_cases=4, min_per_class=2)

    assert report["incomplete"] == ["d"]
    assert report["pass^3"]["pass"] == 2
    assert report["quotable"] is False
    assert any("hold no verdict" in reason for reason in report["defects"])


def test_repeatability_refuses_a_set_of_two_runs():
    expected = _small_expected()
    runs = _fixture(expected, {
        "a": [PASS, PASS], "b": [PASS, PASS], "c": [FAIL, FAIL], "d": [PASS, PASS],
    })

    with pytest.raises(ValueError, match="needs 3 runs"):
        repeatability_report(runs, expected)


def test_three_identical_paid_rounds_are_read_as_engine_evidence(tmp_path):
    expected = _small_expected()
    statuses = {case_id: PASS for case_id in expected}
    calls: list[Path] = []

    def fake_round(out_dir, **kwargs):
        calls.append(Path(out_dir))
        assert kwargs["model"] == "pinned-model"
        return _receipt(expected, statuses)

    runs = paid_runs(
        tmp_path, expected, cases_path=REPO / "evals" / "creation" / "cases.jsonl",
        key_file=tmp_path / "key", base_url="https://engine.invalid", model="pinned-model",
        round_fn=fake_round,
    )

    assert len(calls) == 3
    assert all(run.evidence == "engine" for run in runs)
    assert all(run.engine == {"provider": "openai_compatible", "model": "pinned-model"}
               for run in runs)
    document = breadth.build_document("real:test", expected, runs, min_cases=4,
                                      min_per_class=2)
    assert document["breadth"]["quotable"] is True
    assert document["repeatability"]["quotable"] is True


def test_the_default_run_is_a_dry_run_and_writes_its_evidence(tmp_path, capsys):
    out = tmp_path / "breadth.json"

    code = main(["--json-out", str(out)])

    assert code == 0
    document = json.loads(out.read_text(encoding="utf-8"))
    assert document["breadth"]["evidence"] == "stub"
    assert document["repeatability"]["runs"][0]["evidence"] == "stub"
    assert document["set"] == {"cases": 24, "classes": 6, "case_floor": 20,
                               "class_floor": 3, "runs": 3}
    printed = capsys.readouterr().out
    assert "numbers above test the harness" in printed


def test_real_mode_without_an_engine_refuses_before_a_turn_is_spent():
    with pytest.raises(SystemExit) as raised:
        main(["--real"])

    assert raised.value.code == 2


def test_a_missing_receipt_is_refused_with_its_path(tmp_path, capsys):
    """A path that holds no receipt is a named refusal, not an empty run."""
    path = tmp_path / "absent.json"

    code = main(["--receipt", str(path)])

    assert code == 2
    err = capsys.readouterr().err
    assert str(path) in err
    assert "no receipt" in err


def test_an_empty_receipt_is_refused_with_its_path(tmp_path, capsys):
    """A crashed grader leaves 0 bytes, and the operator has to see which file."""
    path = tmp_path / "receipt.json"
    path.write_bytes(b"")

    code = main(["--receipt", str(path)])

    assert code == 2
    err = capsys.readouterr().err
    assert str(path) in err
    assert "the receipt is empty" in err


def test_an_empty_receipt_is_cleared_before_a_round_and_the_new_one_written_atomically(
    tmp_path, monkeypatch
):
    """A 0-byte file is not a finished receipt, and it may not survive into the round.

    `run_paid_round` reuses a graded receipt so a crash does not cost the same turns twice.
    A crash used to leave 0 bytes behind; reading that as "not finished yet" left the
    round waiting on a file nothing would ever write again. The empty file is cleared
    before the turns are spent, and the graded receipt lands in one atomic write.
    """
    import subprocess

    out = tmp_path / "run-1"
    out.mkdir()
    stale = out / "receipt.json"
    stale.write_bytes(b"")
    expected = _small_expected()
    fresh = _receipt(expected, {case_id: PASS for case_id in expected})
    seen: list[tuple[str, bool]] = []

    def fake_run(argv, **kwargs):
        command = " ".join(str(part) for part in argv)
        seen.append((command, stale.exists()))
        if "creation_runner.py" in command:
            return subprocess.CompletedProcess(argv, 0, stdout=json.dumps(fresh), stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(breadth.subprocess, "run", fake_run)

    receipt = breadth.run_paid_round(
        out,
        cases_path=REPO / "evals" / "creation" / "cases.jsonl",
        key_file=tmp_path / "key",
        base_url="https://engine.invalid",
        model="pinned-model",
    )

    assert len(seen) == 2
    assert seen[0][1] is False, "the stale 0-byte receipt was still there when turns were spent"
    assert seen[1][1] is False
    assert receipt == fresh
    assert json.loads(stale.read_text(encoding="utf-8")) == fresh
    assert [path.name for path in out.iterdir()] == ["receipt.json"]


def test_a_round_whose_grading_printed_no_receipt_names_the_path(tmp_path, monkeypatch):
    """Grading that prints nothing is a failed round, and the error says where to look."""
    import subprocess

    out = tmp_path / "run-1"

    def fake_run(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(breadth.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="receipt.json"):
        breadth.run_paid_round(
            out,
            cases_path=REPO / "evals" / "creation" / "cases.jsonl",
            key_file=tmp_path / "key",
            base_url="https://engine.invalid",
            model="pinned-model",
        )


def test_a_receipt_replay_can_name_the_engine_and_then_be_quotable(tmp_path):
    from evals.breadth_eval import expected_cases

    expected = expected_cases()
    receipt = _receipt(expected, {case_id: PASS for case_id in expected})
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")

    code = breadth.main(["--receipt", str(path), "--evidence", "engine",
                         "--engine-model", "fixture-model",
                         "--json-out", str(tmp_path / "r.json")])
    assert code == 0
    report = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))
    assert report["breadth"]["quotable"] is True
    assert report["breadth"]["engine"]["model"] == "fixture-model"
