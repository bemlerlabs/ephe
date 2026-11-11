#!/usr/bin/env python3
"""Breadth over capability classes (4c) and repeatability over three runs (4d).

The creation set (`evals/creation/cases.jsonl`) spreads 24 cases over six capability
classes. A single aggregate over those cases answers "how many passed" and hides the
question the set exists for: which classes pass, over how many cases, with what
uncertainty. This module turns a graded receipt into that answer.

Three rules make the number honest:

* a case is scored only when the instrument measured it. A turn that was not graded, or
  a check that did not run, is ``unusable`` and leaves the denominator; counting it as a
  failure reports an instrument defect as a capability defect;
* every rate names its denominator and carries a Wilson 95% interval. A class with four
  cases cannot show a rate finer than that interval;
* a number is ``quotable`` only when it comes from engine evidence, every case was
  scored, and every class clears the floor in `evals/creation_eval.py`.

The old 10/24 headline is reproduced as a regression fixture
(`evals/breadth/legacy-10-of-24.json`) and is printed with its raw denominator and a
label; it never stands as a breadth rate.

Repeatability runs the same set three times and classifies each case with the pass^3
rule the release gate already uses (`evals/pass3_release_gate.py`): a case that passes
in all three runs is a pass, one that fails in all three is a fail, and one that flips
is flaky. The report keeps the per-run rates, the flaky cases and the observed pass^3
rate; a flaky case is a result about the engine, so it does not make the run
unquotable by itself.

    python evals/breadth_eval.py                      # dry run, no engine turn
    python evals/breadth_eval.py --receipt run.json   # replay a graded receipt
    python evals/breadth_eval.py --real --key-file ~/.ephe/engine.key \
        --base-url https://... --model <tag>          # three paid rounds

The dry run reads `evals/breadth/stub-runs.json` and marks the evidence ``stub``. A
real run boots the creation harness once per round and grades each round with the same
receipt the creation runner prints, so there is one grader and one case set.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
for _extra in (str(REPO), str(HERE)):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from evals.creation_eval import (  # noqa: E402
    MIN_CASES,
    MIN_PER_CATEGORY,
    load_cases,
)
from evals.live_eval import wilson_interval  # noqa: E402

SCHEMA = 1
PASS = "pass"
FAIL = "fail"
UNUSABLE = "unusable"
STATUSES = (PASS, FAIL, UNUSABLE)
RUNS_EXPECTED = 3
DEFAULT_CASES = REPO / "evals" / "creation" / "cases.jsonl"
DEFAULT_FIXTURE = HERE / "breadth" / "stub-runs.json"
DEFAULT_ROUNDS_ROOT = Path(tempfile.gettempdir()) / "ephe-breadth-eval"


class ReceiptError(ValueError):
    """A receipt does not describe this case set, so it cannot carry this set's rate."""


@dataclass(frozen=True)
class CaseOutcome:
    """One case as the instrument left it: a verdict, or the reason there is none."""

    case_id: str
    category: str
    status: str
    detail: str = ""


@dataclass(frozen=True)
class Run:
    """One pass over the set, with the evidence label that says what produced it."""

    index: int
    evidence: str
    outcomes: tuple[CaseOutcome, ...]
    engine: dict | None = None
    declared: dict | None = None
    note: str = ""


def expected_cases(path: Path | None = None) -> dict[str, str]:
    """Case id to capability class, in file order, from the creation set's own loader."""
    cases = load_cases(Path(path) if path is not None else None)
    return {str(case["id"]): str(case["category"]) for case in cases}


def _status(value: object, where: str) -> str:
    status = str(value or "").strip().lower()
    if status not in STATUSES:
        raise ReceiptError(f"{where}: status {value!r} is not one of {', '.join(STATUSES)}")
    return status


def outcome_of_row(row: dict, category: str) -> CaseOutcome:
    """Classify one creation-runner case row into pass, fail or unusable.

    `creation_runner.Receipt.ok` treats a case with no turn and a case with checks that
    did not run as a pass when its remaining checks are green. That is the shape the old
    headline counted; here both are unusable, because neither says what the turn did.
    """
    case_id = str(row.get("case_id") or "")
    not_run = row.get("not_run") or []
    checks = row.get("checks") or []
    if not isinstance(not_run, list) or not isinstance(checks, list) or any(
        not isinstance(check, dict) for check in checks
    ):
        raise ReceiptError(f"{case_id or 'a case row'}: not_run and checks must be lists")
    not_run = [str(name) for name in not_run]
    failed = [str(check.get("check") or "check") for check in checks if not check.get("ok")]
    turn_ok = row.get("turn_ok")
    if turn_ok is False:
        detail = str(row.get("turn_detail") or "the turn did not satisfy its expect block")
        return CaseOutcome(case_id, category, FAIL, detail)
    if turn_ok is None:
        detail = str(row.get("detail") or row.get("turn_detail") or "the turn was not graded")
        return CaseOutcome(case_id, category, UNUSABLE, detail)
    if not_run:
        detail = f"{len(not_run)} check(s) did not run: {', '.join(not_run)}"
        return CaseOutcome(case_id, category, UNUSABLE, detail)
    if failed:
        detail = f"{len(failed)} check(s) failed: {', '.join(failed)}"
        return CaseOutcome(case_id, category, FAIL, detail)
    if not checks:
        return CaseOutcome(case_id, category, UNUSABLE, "no end-state check was graded")
    return CaseOutcome(case_id, category, PASS)


def runs_from_receipt(
    receipt: dict,
    expected: dict[str, str],
    *,
    index: int = 1,
    evidence: str | None = None,
    engine: dict | None = None,
) -> Run:
    """Read one `creation_runner --json` receipt, refusing any other case set.

    A missing or extra case moves the denominator, and a receipt that relabels a class
    moves it between rates, so both are refused with the counts that differ. A declared
    headline that disagrees with the rows is carried and named in the report instead,
    because that disagreement is the defect this harness exists to show.
    """
    if not isinstance(receipt, dict):
        raise ReceiptError("a receipt is a JSON object")
    rows = receipt.get("cases")
    if not isinstance(rows, list) or not rows:
        raise ReceiptError("the receipt carries no cases")
    seen: dict[str, dict] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ReceiptError("the receipt holds a case row that is not an object")
        case_id = str(row.get("case_id") or "")
        if not case_id:
            raise ReceiptError("the receipt holds a case row with no case_id")
        if case_id in seen:
            raise ReceiptError(f"the receipt holds case {case_id!r} twice")
        if case_id not in expected:
            raise ReceiptError(f"the receipt holds case {case_id!r}, which is not in this set")
        declared = str(row.get("category") or expected[case_id])
        if declared != expected[case_id]:
            raise ReceiptError(
                f"{case_id}: the receipt calls the case {declared!r}, the set calls it "
                f"{expected[case_id]!r}; a relabelled case would move between rates"
            )
        seen[case_id] = row
    missing = [case_id for case_id in expected if case_id not in seen]
    if missing:
        raise ReceiptError(
            f"the receipt holds {len(seen)} of {len(expected)} cases; missing "
            f"{', '.join(missing[:6])} — a rate over a different set is not this set's rate"
        )
    outcomes = tuple(outcome_of_row(seen[case_id], expected[case_id]) for case_id in expected)
    declared = None
    declared_passed, declared_total = receipt.get("passed"), receipt.get("total")
    if declared_passed is not None and declared_total is not None:
        try:
            declared_passed, declared_total = int(declared_passed), int(declared_total)
        except (TypeError, ValueError) as exc:
            raise ReceiptError("the receipt's passed/total fields are not numbers") from exc
        derived = sum(1 for outcome in outcomes if outcome.status == PASS)
        declared = {
            "pass": declared_passed,
            "total": declared_total,
            "rows_pass": derived,
            "rows_total": len(outcomes),
            "matches_rows": declared_total == len(outcomes) and declared_passed == derived,
        }
    return Run(
        index=index,
        evidence=str(evidence or receipt.get("evidence") or "unverified"),
        outcomes=outcomes,
        engine=engine if engine is not None else receipt.get("engine"),
        declared=declared,
        note=str(receipt.get("note") or ""),
    )


def fixture_runs(document: dict, expected: dict[str, str], *, evidence: str | None = None) -> list[Run]:
    """Expand the compact dry-run fixture into one Run per declared repetition.

    A fixture row names the status of one case in every run, so a missing run or a
    status outside the vocabulary is refused at load time instead of silently becoming
    a failure.
    """
    if not isinstance(document, dict):
        raise ReceiptError("a fixture is a JSON object")
    try:
        schema = int(document.get("schema") or 0)
        rounds = int(document.get("runs") or 0)
    except (TypeError, ValueError) as exc:
        raise ReceiptError("the fixture's schema and runs fields must be numbers") from exc
    if schema != SCHEMA:
        raise ReceiptError(f"the fixture is not schema {SCHEMA}")
    if rounds < 1:
        raise ReceiptError("the fixture declares no runs")
    rows = document.get("cases")
    if not isinstance(rows, list) or not rows:
        raise ReceiptError("the fixture carries no cases")
    by_id: dict[str, dict] = {}
    for row in rows:
        case_id = str(row.get("id") or "")
        if case_id not in expected:
            raise ReceiptError(f"the fixture holds case {case_id!r}, which is not in this set")
        if case_id in by_id:
            raise ReceiptError(f"the fixture holds case {case_id!r} twice")
        by_id[case_id] = row
    missing = [case_id for case_id in expected if case_id not in by_id]
    if missing:
        raise ReceiptError(f"the fixture misses {', '.join(missing[:6])}")
    label = str(evidence or document.get("evidence") or "stub")
    runs: list[Run] = []
    for offset in range(rounds):
        outcomes = []
        for case_id, category in expected.items():
            row = by_id[case_id]
            statuses = row.get("outcomes")
            if not isinstance(statuses, list) or len(statuses) != rounds:
                raise ReceiptError(
                    f"{case_id}: expected {rounds} outcome(s), got {statuses!r}"
                )
            details = row.get("details") or [""] * rounds
            if not isinstance(details, list) or len(details) != rounds:
                raise ReceiptError(f"{case_id}: details must name one run each")
            outcomes.append(
                CaseOutcome(
                    case_id,
                    category,
                    _status(statuses[offset], case_id),
                    str(details[offset] or ""),
                )
            )
        runs.append(Run(index=offset + 1, evidence=label, outcomes=tuple(outcomes),
                        engine=document.get("engine"),
                        note=str(document.get("note") or "")))
    return runs


def load_fixture(path: Path, expected: dict[str, str], *, evidence: str | None = None) -> list[Run]:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return fixture_runs(document, expected, evidence=evidence)


def rate_block(passed: int, total: int) -> dict:
    """A rate with the denominator and the Wilson interval it was measured at."""
    return {
        "pass": passed,
        "total": total,
        "rate": round(passed / total, 4) if total else 0.0,
        "ci95": list(wilson_interval(passed, total)),
    }


def _class_order(expected: dict[str, str]) -> list[str]:
    return list(dict.fromkeys(expected.values()))


def breadth_report(
    run: Run,
    expected: dict[str, str],
    *,
    min_cases: int = MIN_CASES,
    min_per_class: int = MIN_PER_CATEGORY,
) -> dict:
    """Per-class rates, the aggregate over scored cases, and whether the number may be quoted.

    `headline` is what a receipt-shaped summary prints when it divides passes by every
    row; `scored` drops the rows that hold no verdict. The two differ exactly when the
    instrument did not answer, and the report keeps both so neither is mistaken for the
    other.
    """
    buckets = {cls: {PASS: 0, FAIL: 0, UNUSABLE: 0} for cls in _class_order(expected)}
    for outcome in run.outcomes:
        buckets[outcome.category][outcome.status] += 1
    per_class: dict[str, dict] = {}
    for cls in _class_order(expected):
        bucket = buckets[cls]
        usable = bucket[PASS] + bucket[FAIL]
        per_class[cls] = {
            "cases": usable + bucket[UNUSABLE],
            "usable": usable,
            "pass": bucket[PASS],
            "fail": bucket[FAIL],
            "unusable": bucket[UNUSABLE],
            "rate": round(bucket[PASS] / usable, 4) if usable else 0.0,
            "ci95": list(wilson_interval(bucket[PASS], usable)),
            "rateable": usable >= min_per_class,
        }
    scored_total = sum(bucket[PASS] + bucket[FAIL] for bucket in buckets.values())
    scored_pass = sum(bucket[PASS] for bucket in buckets.values())
    unusable = [
        {"case_id": outcome.case_id, "category": outcome.category, "detail": outcome.detail}
        for outcome in run.outcomes if outcome.status == UNUSABLE
    ]
    defects: list[str] = []
    if unusable:
        names = ", ".join(row["case_id"] for row in unusable[:6])
        defects.append(f"{len(unusable)} case(s) hold no verdict: {names}")
    for cls, row in per_class.items():
        if not row["rateable"]:
            defects.append(
                f"class {cls!r} holds {row['usable']} scored case(s), below the "
                f"{min_per_class}-case floor"
            )
    if scored_total < min_cases:
        defects.append(
            f"{scored_total} scored case(s) is below the {min_cases}-case floor"
        )
    if run.declared and not run.declared["matches_rows"]:
        defects.append(
            f"the receipt declares {run.declared['pass']}/{run.declared['total']} passing, "
            f"its rows carry {run.declared['rows_pass']}/{run.declared['rows_total']}; "
            f"the rows are the number"
        )
    if run.evidence != "engine":
        defects.append(
            f"the run carries {run.evidence!r} evidence; a quotable rate needs 'engine'"
        )
    return {
        "evidence": run.evidence,
        "engine": run.engine,
        "declared": run.declared,
        "headline": rate_block(scored_pass, len(run.outcomes)),
        "scored": rate_block(scored_pass, scored_total),
        "per_class": per_class,
        "unusable": unusable,
        "defects": defects,
        "quotable": not defects,
    }


def repeatability_report(
    runs: list[Run],
    expected: dict[str, str],
    *,
    min_cases: int = MIN_CASES,
    min_per_class: int = MIN_PER_CATEGORY,
) -> dict:
    """Three runs of one set: per-run rates, pass^3, flaky cases and their classes.

    The classification is `pass3_release_gate.classify`, so a case that flips between
    runs is called flaky by the rule the release gate already applies. A run that left
    a case without a verdict omits that repetition, which `classify` reports as
    incomplete.
    """
    if len(runs) != RUNS_EXPECTED:
        raise ValueError(f"repeatability needs {RUNS_EXPECTED} runs, got {len(runs)}")
    breadth = [breadth_report(run, expected, min_cases=min_cases,
                              min_per_class=min_per_class) for run in runs]
    rows: list[dict] = []
    for run in runs:
        for outcome in run.outcomes:
            if outcome.status in (PASS, FAIL):
                rows.append({"task_id": outcome.case_id, "rep": run.index,
                             "ok": outcome.status == PASS})
    from evals.pass3_release_gate import classify

    groups = classify(rows, RUNS_EXPECTED)
    complete = set(groups[PASS]) | set(groups[FAIL]) | set(groups["flaky"])
    stable = set(groups[PASS]) | set(groups[FAIL])
    per_case = []
    for case_id, category in expected.items():
        statuses = [
            next(outcome.status for outcome in run.outcomes if outcome.case_id == case_id)
            for run in runs
        ]
        if case_id in groups[PASS]:
            verdict = "pass"
        elif case_id in groups[FAIL]:
            verdict = "fail"
        elif case_id in groups["flaky"]:
            verdict = "flaky"
        else:
            verdict = "incomplete"
        per_case.append({"case_id": case_id, "category": category,
                         "statuses": statuses, "verdict": verdict})
    per_class: dict[str, dict] = {}
    for cls in _class_order(expected):
        ids = [case_id for case_id, category in expected.items() if category == cls]
        rates = [entry["per_class"][cls]["rate"] for entry in breadth]
        per_class[cls] = {
            "cases": len(ids),
            "rates": rates,
            "mean_rate": round(sum(rates) / len(rates), 4),
            "min_rate": min(rates),
            "max_rate": max(rates),
            "spread_pp": round(100 * (max(rates) - min(rates)), 2),
            "pass^3": sum(1 for case_id in ids if case_id in groups[PASS]),
            "flaky": [case_id for case_id in ids if case_id in groups["flaky"]],
        }
    defects: list[str] = []
    for entry in breadth:
        for reason in entry["defects"]:
            if reason not in defects:
                defects.append(reason)
    incomplete = sorted(set(groups["incomplete"]) | set(groups["blocked"]))
    agreement = rate_block(len(stable), len(complete))
    return {
        "runs": [
            {"run": run.index, "evidence": run.evidence, "engine": run.engine,
             "scored": entry["scored"], "per_class": entry["per_class"]}
            for run, entry in zip(runs, breadth)
        ],
        "per_case": per_case,
        "per_class": per_class,
        "stable": sorted(stable),
        "flaky": sorted(groups["flaky"]),
        "incomplete": incomplete,
        "agreement": agreement,
        "pass^3": rate_block(len(groups[PASS]), len(expected)),
        "defects": defects,
        "quotable": not defects,
    }


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_document(source: str, expected: dict[str, str], runs: list[Run],
                   *, min_cases: int = MIN_CASES,
                   min_per_class: int = MIN_PER_CATEGORY) -> dict:
    breadth = breadth_report(runs[0], expected, min_cases=min_cases,
                             min_per_class=min_per_class)
    repeatability = (
        repeatability_report(runs, expected, min_cases=min_cases,
                             min_per_class=min_per_class)
        if len(runs) == RUNS_EXPECTED else None
    )
    return {
        "schema": SCHEMA,
        "generated_at": _iso_now(),
        "source": source,
        "note": runs[0].note if runs else "",
        "method": {
            "interval": "wilson",
            "level": 0.95,
            "denominator": "scored cases; unusable rows leave the denominator",
            "repeatability": "pass^3 over three runs",
        },
        "set": {
            "cases": len(expected),
            "classes": len(_class_order(expected)),
            "case_floor": min_cases,
            "class_floor": min_per_class,
            "runs": len(runs),
        },
        "breadth": breadth,
        "repeatability": repeatability,
    }


def _rate_line(label: str, block: dict, width: int = 12) -> str:
    low, high = block["ci95"]
    count = f"{block['pass']}/{block['total']}"
    return (
        f"  {label:<{width}}{count:>12}{block['rate']:>9.4f}"
        f"  [{low:.4f}, {high:.4f}]"
    )


def format_report(document: dict) -> str:
    breadth = document["breadth"]
    plan = document["set"]
    lines = []
    if document.get("note"):
        lines.append(f"note: {document['note']}")
    lines += [
        f"breadth 4c: {plan['cases']} cases in {plan['classes']} classes, "
        f"evidence {breadth['evidence']}",
        f"  {'class':<12}{'pass/usable':>12}{'unusable':>10}{'rate':>9}  95% CI (Wilson)",
    ]
    for cls, row in breadth["per_class"].items():
        low, high = row["ci95"]
        count = f"{row['pass']}/{row['usable']}"
        lines.append(
            f"  {cls:<12}{count:>12}{row['unusable']:>10}"
            f"{row['rate']:>9.4f}  [{low:.4f}, {high:.4f}]"
        )
    if breadth["headline"]["total"] != breadth["scored"]["total"]:
        low, high = breadth["headline"]["ci95"]
        count = f"{breadth['headline']['pass']}/{breadth['headline']['total']}"
        lines.append(
            f"  headline    {count:>12}{breadth['headline']['rate']:>9.4f}"
            f"  [{low:.4f}, {high:.4f}]"
            f"  (raw pass/all rows; {len(breadth['unusable'])} row(s) hold no verdict)"
        )
    lines.append(_rate_line("scored", breadth["scored"]))
    lines.append(f"  verdict     {'QUOTABLE' if breadth['quotable'] else 'NOT QUOTABLE'}")
    for reason in breadth["defects"]:
        lines.append(f"              - {reason}")

    repeat = document.get("repeatability")
    if repeat:
        lines.append("")
        lines.append(
            f"repeatability 4d: {plan['runs']} runs, {plan['cases']} cases, "
            f"evidence {repeat['runs'][0]['evidence']}"
        )
        for entry in repeat["runs"]:
            lines.append(_rate_line(f"run {entry['run']}", entry["scored"], width=8))
        lines.append(f"  {'class':<12}{'run rates':<30}{'spread':>9}{'pass^3':>9}")
        for cls, row in repeat["per_class"].items():
            rates = "/".join(f"{rate:.3f}" for rate in row["rates"])
            lines.append(
                f"  {cls:<12}{rates:<30}{row['spread_pp']:>8.1f}pp"
                f"{row['pass^3']:>7}/{row['cases']}"
            )
        lines.append(_rate_line("agreement", repeat["agreement"]))
        lines.append(_rate_line("pass^3", repeat["pass^3"]))
        if repeat["flaky"]:
            lines.append(f"  flaky       {len(repeat['flaky'])}: {', '.join(repeat['flaky'])}")
        if repeat["incomplete"]:
            lines.append(
                f"  incomplete  {len(repeat['incomplete'])}: "
                f"{', '.join(repeat['incomplete'])}"
            )
        lines.append(f"  verdict     {'QUOTABLE' if repeat['quotable'] else 'NOT QUOTABLE'}")
        for reason in repeat["defects"]:
            lines.append(f"              - {reason}")
    if breadth["evidence"] == "stub":
        lines.append("")
        lines.append(
            "numbers above test the harness; a breadth or repeatability claim needs "
            "--real and the engine the run names."
        )
    return "\n".join(lines)


def run_paid_round(
    out_dir: Path,
    *,
    cases_path: Path,
    key_file: Path,
    base_url: str,
    model: str,
    timeout: float = 10800.0,
) -> dict:
    """One paid round: the creation run spends the turns, the creation grader scores them."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    turn = [sys.executable, str(REPO / "evals" / "creation_run.py"),
            "--out", str(out_dir), "--cases", str(cases_path),
            "--key-file", str(key_file), "--base-url", base_url, "--model", model]
    turn_run = subprocess.run(turn, cwd=str(REPO), text=True, timeout=timeout)
    grade = [sys.executable, str(REPO / "evals" / "creation_runner.py"),
             "--cases", str(cases_path),
             "--staging", str(out_dir / "staging.json"),
             "--transcripts", str(out_dir / "transcripts.json"),
             "--config", str(out_dir / "config"), "--browser", "--json"]
    graded = subprocess.run(grade, cwd=str(REPO), text=True, capture_output=True,
                            timeout=timeout)
    if graded.returncode not in (0, 1):
        tail = (graded.stderr or "").strip()[-600:]
        raise RuntimeError(
            f"grading {out_dir} exited {graded.returncode} "
            f"(turns exited {turn_run.returncode}): {tail}"
        )
    try:
        return json.loads(graded.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"the grader printed no receipt: {exc}") from exc


def paid_runs(
    root: Path,
    expected: dict[str, str],
    *,
    cases_path: Path,
    key_file: Path,
    base_url: str,
    model: str,
    round_fn=None,
) -> list[Run]:
    """Three paid rounds of the set, each graded by the creation runner's own receipt."""
    round_fn = round_fn or run_paid_round
    runs: list[Run] = []
    for index in range(1, RUNS_EXPECTED + 1):
        receipt = round_fn(
            Path(root) / f"run-{index}",
            cases_path=cases_path,
            key_file=key_file,
            base_url=base_url,
            model=model,
        )
        runs.append(
            runs_from_receipt(
                receipt, expected, index=index, evidence="engine",
                engine={"provider": "openai_compatible", "model": model},
            )
        )
    return runs


def _load_receipt(path: Path, expected: dict[str, str], index: int,
                  evidence: str | None) -> Run:
    try:
        document = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReceiptError(f"{path}: {exc}") from exc
    return runs_from_receipt(document, expected, index=index, evidence=evidence)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES,
                        help="the JSONL case set (default: evals/creation/cases.jsonl)")
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE,
                        help="the dry-run fixture with three runs")
    parser.add_argument("--receipt", action="append", type=Path, default=[],
                        help="replay a graded receipt; repeat three times for repeatability")
    parser.add_argument("--evidence", default=None,
                        help="evidence label for --receipt files (default: the file's own)")
    parser.add_argument("--real", action="store_true",
                        help=f"spend engine turns: {RUNS_EXPECTED} rounds of the set")
    parser.add_argument("--key-file", type=Path, help="one-line engine key for --real")
    parser.add_argument("--base-url", help="engine base URL for --real")
    parser.add_argument("--model", help="model tag for --real")
    parser.add_argument("--out-dir", type=Path,
                        help="where real rounds write (default: a temp directory)")
    parser.add_argument("--json-out", type=Path, help="write the report as JSON")
    args = parser.parse_args(argv)

    if args.real and args.receipt:
        parser.error("--real and --receipt are exclusive")
    try:
        expected = expected_cases(args.cases)
    except (OSError, ValueError) as exc:
        print(f"breadth-eval: no run — {exc}", file=sys.stderr)
        return 2
    if args.real:
        if not args.key_file or not args.base_url or not args.model:
            parser.error("--real needs --key-file, --base-url and --model")
        if not args.key_file.is_file() or not args.key_file.stat().st_size:
            parser.error(f"--key-file {args.key_file} is missing or empty")
        root = args.out_dir or DEFAULT_ROUNDS_ROOT / _iso_now().replace(":", "")
        print(
            f"real run: {RUNS_EXPECTED} rounds x {len(expected)} turns = "
            f"{RUNS_EXPECTED * len(expected)} turns on {args.model} at {args.base_url}"
        )
        source = f"real:{root}"
        try:
            runs = paid_runs(root, expected, cases_path=args.cases, key_file=args.key_file,
                             base_url=args.base_url, model=args.model)
        except (ReceiptError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
            print(f"breadth-eval: no real run — {exc}", file=sys.stderr)
            return 2
    elif args.receipt:
        if len(args.receipt) not in (1, RUNS_EXPECTED):
            parser.error(
                f"--receipt needs one file for breadth or {RUNS_EXPECTED} for "
                f"repeatability, got {len(args.receipt)}"
            )
        try:
            runs = [_load_receipt(path, expected, index, args.evidence)
                    for index, path in enumerate(args.receipt, 1)]
        except ReceiptError as exc:
            print(f"breadth-eval: no run — {exc}", file=sys.stderr)
            return 2
        source = "receipt:" + ",".join(str(path) for path in args.receipt)
    else:
        try:
            runs = load_fixture(args.fixture, expected)
        except (ReceiptError, OSError, json.JSONDecodeError) as exc:
            print(f"breadth-eval: no run — {exc}", file=sys.stderr)
            return 2
        source = f"fixture:{args.fixture}"

    document = build_document(source, expected, runs)
    print(format_report(document))
    if args.json_out:
        args.json_out.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        print(f"breadth-eval: wrote {args.json_out}")
    if args.real and document["breadth"]["scored"]["total"] == 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
