#!/usr/bin/env python3
"""W3-73 - Judge eval: the rubric judge against human labels.

The **rubric judge** is ``core.react.reflect()``: the reflexion reviewer whose
system prompt is a quality rubric ("judge whether a given answer is correct and
complete", "I don't know is ALWAYS bad when tools are available"). It returns a
binary verdict - ``needs_revision`` (the answer is defective) or not.

This harness runs that judge, unchanged, over a human-labelled gold set
(``evals/judge/labels.jsonl``) and reports precision / recall of the judge's
"defective" verdict against the labels.

    positive class   "defective"  - the answer needs revision
    judge predicts + when reflect() returns needs_revision=True
    precision = TP / (TP + FP)     recall = TP / (TP + FN)

Each case is judged ``--reps`` times (default 3, as the product bench uses three
reps); the headline number is the majority vote per case, and the per-rep spread
and any flip are kept so the number's stability is visible. A transient engine
failure (``provider_error``) is retried and never counted as a vote.

The live number is a measurement of one engine, named in the receipt. It runs
against the persisted engine resolved from ``~/.ephe/engine.json`` (the DGX
Spark endpoint ``openai_compatible/qwen3.8-flash-next`` at the time of writing);
the API key, if the endpoint needs one, is read from the environment / OS store
and never written to a file. ``--selftest`` exercises the metric math and the
verdict parser without a model, so the harness is provable offline.

Usage:
    python evals/judge_eval.py                 # live run (3 reps), writes the receipt
    python evals/judge_eval.py --reps 1        # single rep
    python evals/judge_eval.py --selftest      # no model: schema + math + parser
    python evals/judge_eval.py --labels PATH --out PATH
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # evals/judge_eval.py -> repo root
sys.path.insert(0, str(ROOT))  # invoked by path, so core.* is not importable otherwise
DEFAULT_LABELS = ROOT / "evals" / "judge" / "labels.jsonl"
DEFAULT_OUT = ROOT / "evals" / "judge-eval-receipt.json"

#: The label that means "this answer needs revision" - the judge's positive class.
POSITIVE = "defective"
NEGATIVE = "ok"

REQUIRED_FIELDS = ("id", "category", "label", "question", "answer", "rationale")
DEFAULT_REPS = 3


# --------------------------------------------------------------------------- #
# Labels
# --------------------------------------------------------------------------- #

def load_labels(path: Path) -> list[dict]:
    """Parse the human-labelled gold set and validate every row.

    Every row must carry the required fields and a label in {defective, ok};
    a malformed row is a hard error, because a silently dropped case would move
    the precision/recall denominators without anyone seeing it.
    """
    rows: list[dict] = []
    seen: set[str] = set()
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno}: not JSON: {exc}") from exc
        missing = [f for f in REQUIRED_FIELDS if not str(row.get(f, "")).strip()]
        if missing:
            raise ValueError(f"{path}:{lineno}: missing fields {missing}")
        if row["label"] not in (POSITIVE, NEGATIVE):
            raise ValueError(
                f"{path}:{lineno}: label must be {POSITIVE!r} or {NEGATIVE!r}, "
                f"got {row['label']!r}"
            )
        if row["id"] in seen:
            raise ValueError(f"{path}:{lineno}: duplicate id {row['id']!r}")
        seen.add(row["id"])
        rows.append(row)
    if not rows:
        raise ValueError(f"{path}: no cases")
    return rows


def label_distribution(rows: list[dict]) -> dict:
    pos = sum(1 for r in rows if r["label"] == POSITIVE)
    neg = len(rows) - pos
    return {"total": len(rows), "defective": pos, "ok": neg, "prevalence": _ratio(pos, len(rows))}


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #

def _ratio(num: int, den: int) -> float:
    return round(num / den, 4) if den else 0.0


def confusion(pairs: list[tuple[str, str]]) -> dict:
    """Confusion matrix + derived metrics from (human_label, judge_pred) pairs.

    Both labels use the POSITIVE/NEGATIVE vocabulary. Raises on an unknown label
    so a typo can never quietly land in the wrong cell.
    """
    tp = fp = fn = tn = 0
    for human, pred in pairs:
        if human not in (POSITIVE, NEGATIVE) or pred not in (POSITIVE, NEGATIVE):
            raise ValueError(f"bad pair: {(human, pred)!r}")
        if human == POSITIVE and pred == POSITIVE:
            tp += 1
        elif human == NEGATIVE and pred == POSITIVE:
            fp += 1
        elif human == POSITIVE and pred == NEGATIVE:
            fn += 1
        else:
            tn += 1
    precision = _ratio(tp, tp + fp)
    recall = _ratio(tp, tp + fn)
    f1 = round(2 * precision * recall / (precision + recall), 4) if (precision + recall) else 0.0
    accuracy = _ratio(tp + tn, len(pairs))
    specificity = _ratio(tn, tn + fp)
    return {
        "n": len(pairs),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "accuracy": accuracy,
        "specificity": specificity,
        "precision_ci95": wilson_ci(tp, tp + fp),
        "recall_ci95": wilson_ci(tp, tp + fn),
    }


def wilson_ci(k: int, n: int, z: float = 1.959963984540054) -> list:
    """Wilson score 95% interval for k successes in n trials (0..1, 4 dp)."""
    if n == 0:
        return [0.0, 0.0]
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def per_category(rows: list[dict], pairs: list[tuple[str, str]]) -> dict:
    """Confusion metrics grouped by the human category of each case."""
    by_cat: dict[str, list[tuple[str, str]]] = {}
    for row, pair in zip(rows, pairs):
        by_cat.setdefault(row["category"], []).append(pair)
    return {cat: confusion(ps) for cat, ps in sorted(by_cat.items())}


def _majority(votes: list[str]) -> str:
    """Majority label over a case's rep votes; ties resolve to the negative."""
    return POSITIVE if votes.count(POSITIVE) * 2 > len(votes) else NEGATIVE


# --------------------------------------------------------------------------- #
# The judge (live)
# --------------------------------------------------------------------------- #

def judge_verdict_from_result(result) -> str:
    """Map a ReflexionResult to the judge's predicted label.

    A provider_error is recorded as a NEGATIVE prediction (that is what the
    parser returns by default), but its status is kept so a failure is never
    mistaken for a confident 'the answer is fine'.
    """
    return POSITIVE if getattr(result, "needs_revision", False) else NEGATIVE


def resolve_engine():
    """Resolve the persisted engine and apply it to the process env (idempotent)."""
    from core.engine_config import resolve_engine_choice

    choice = resolve_engine_choice()
    if hasattr(choice, "apply_env"):
        choice.apply_env()
    return choice


async def _judge_once(row: dict, model: str, retries: int) -> tuple[str | None, str, str]:
    """One judge observation, retrying transient engine failures.

    Returns ``(label, status, reason)`` where *label* is ``None`` when the engine
    never answered - an unanswered observation is not a vote and must not be
    folded into the majority as a default negative.
    """
    from core.react import reflect

    verdict = None
    status = "provider_error"
    for _ in range(retries + 1):
        verdict = await reflect(response=row["answer"], question=row["question"], model=model)
        status = getattr(verdict, "status", "ok")
        if status != "provider_error":
            return judge_verdict_from_result(verdict), status, getattr(verdict, "reason", "")
    return None, status, getattr(verdict, "reason", "")


async def run_live(rows: list[dict], model: str, *, reps: int = DEFAULT_REPS,
                   retries: int = 2) -> list[dict]:
    """Run the rubric judge ``reps`` times per case; one record per case.

    A transient engine failure (``provider_error``) is retried up to ``retries``
    times, and an observation that never answers is dropped rather than counted
    as a negative vote. Each case keeps its per-rep votes, the winner, and how
    many reps answered - so an unanswered case is visible, never laundered.
    """
    results: list[dict] = []
    for row in rows:
        votes: list[str] = []
        statuses: list[str] = []
        reasons: list[str] = []
        for _ in range(reps):
            label, status, reason = await _judge_once(row, model, retries)
            statuses.append(status)
            if label is not None:
                votes.append(label)
            if reason:
                reasons.append(reason)
        results.append(
            {
                "id": row["id"],
                "category": row["category"],
                "human_label": row["label"],
                "judge_label": _majority(votes) if votes else NEGATIVE,
                "votes": votes,
                "judge_statuses": statuses,
                "answered_reps": len(votes),
                "judge_reason": next((r for r in reasons if r), ""),
            }
        )
    return results


# --------------------------------------------------------------------------- #
# Receipt
# --------------------------------------------------------------------------- #

def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except (subprocess.SubprocessError, OSError):
        return ""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_receipt(rows: list[dict], records: list[dict], engine: dict, labels_path: Path,
                  reps: int) -> dict:
    pairs = [(r["human_label"], r["judge_label"]) for r in records]
    cm = confusion(pairs)

    # Per-rep metrics: transpose the votes so rep i is scored on its own column.
    # A case that dropped an observation contributes only to the reps it answered.
    per_rep = []
    for i in range(reps):
        rep_pairs = [(r["human_label"], r["votes"][i]) for r in records if len(r["votes"]) > i]
        per_rep.append(confusion(rep_pairs) if rep_pairs else None)

    statuses: dict[str, int] = {}
    for r in records:
        for s in r["judge_statuses"]:
            statuses[s] = statuses.get(s, 0) + 1

    flips = [
        {"id": r["id"], "human_label": r["human_label"], "votes": r["votes"],
         "majority": r["judge_label"], "answered_reps": r["answered_reps"]}
        for r in records
        if len(set(r["votes"])) > 1
    ]
    misses = [
        {"id": r["id"], "category": r["category"], "human_label": r["human_label"],
         "judge_label": r["judge_label"], "votes": r["votes"],
         "judge_reason": r["judge_reason"]}
        for r in records if r["human_label"] != r["judge_label"]
    ]
    unanswered = [r["id"] for r in records if r["answered_reps"] == 0]

    return {
        "kind": "judge-eval-receipt",
        "task": "W3-73",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": str(ROOT),
        "git_head": _git_head(),
        "engine": engine,
        "judge": {
            "what": "core.react.reflect - the reflexion quality reviewer (rubric judge)",
            "verdict": "binary: needs_revision True/False from the REVISION: YES/NO rubric",
            "positive_class": POSITIVE,
            "prompt_source": "core/react.py:REFLEXION_SYSTEM_PROMPT",
            "reps_per_case": reps,
            "retries_per_rep": 2,
            "aggregation": "majority vote over reps; ties resolve to the negative",
        },
        "labels": {**_label_meta(rows, labels_path), **label_distribution(rows)},
        "metrics": cm,
        "metrics_per_rep": per_rep,
        "by_category": per_category(rows, pairs),
        "judge_status_distribution": statuses,
        "flips": flips,
        "unanswered_cases": unanswered,
        "misses": misses,
    }


def _label_meta(rows: list[dict], labels_path: Path) -> dict:
    return {
        "path": str(labels_path.relative_to(ROOT)),
        "sha256": _sha256(labels_path),
        "authored_by": "engineer (human) - each row carries the human rationale that fixes its label",
        "categories": sorted({r["category"] for r in rows}),
    }


# --------------------------------------------------------------------------- #
# Self-test (no model)
# --------------------------------------------------------------------------- #

def selftest() -> int:
    """Prove the schema, the metric math and the verdict parser without a model."""
    failures: list[str] = []

    rows = load_labels(DEFAULT_LABELS)
    dist = label_distribution(rows)
    if dist["defective"] < 5 or dist["ok"] < 5:
        failures.append(f"label set too thin for precision+recall: {dist}")
    if dist["total"] != len(rows):
        failures.append("distribution total mismatch")

    # Hand-computed fixture: tp=3 fp=1 fn=2 tn=4
    pairs = [(POSITIVE, POSITIVE)] * 3 + [(NEGATIVE, POSITIVE)] + \
            [(POSITIVE, NEGATIVE)] * 2 + [(NEGATIVE, NEGATIVE)] * 4
    cm = confusion(pairs)
    if (cm["tp"], cm["fp"], cm["fn"], cm["tn"]) != (3, 1, 2, 4):
        failures.append(f"confusion cells wrong: {cm}")
    if cm["precision"] != 0.75 or cm["recall"] != 0.6:
        failures.append(f"precision/recall wrong: {cm['precision']}/{cm['recall']}")

    # Majority vote: 2 of 3 wins, a 1-1-1 tie resolves negative.
    if _majority([POSITIVE, POSITIVE, NEGATIVE]) != POSITIVE:
        failures.append("majority: 2/3 positive not positive")
    if _majority([POSITIVE, NEGATIVE, NEGATIVE]) != NEGATIVE:
        failures.append("majority: 1/3 positive not negative")
    if _majority([POSITIVE, NEGATIVE]) != NEGATIVE:
        failures.append("majority: tie not resolved to negative")

    # Verdict mapping
    class _R:
        def __init__(self, needs_revision: bool) -> None:
            self.needs_revision = needs_revision
    if judge_verdict_from_result(_R(True)) != POSITIVE:
        failures.append("verdict mapping: NEEDS_REVISION -> not positive")
    if judge_verdict_from_result(_R(False)) != NEGATIVE:
        failures.append("verdict mapping: no-revision -> not negative")

    # The parser the judge relies on (YES/NO/empty), from the product itself.
    from core.react import _parse_reflexion
    if not _parse_reflexion("blah\nREVISION: YES\nReason: wrong fact").needs_revision:
        failures.append("parser: REVISION: YES not detected")
    if _parse_reflexion("looks good\nREVISION: NO").needs_revision:
        failures.append("parser: REVISION: NO wrongly flagged")
    if _parse_reflexion("").status != "provider_error":
        failures.append("parser: empty content not marked provider_error")

    if failures:
        for f in failures:
            print("SELFTEST FAIL:", f)
        return 1
    print(f"SELFTEST OK: {dist['total']} cases "
          f"({dist['defective']} defective / {dist['ok']} ok); "
          f"metric math + majority vote + verdict parser verified without a model")
    return 0


def _engine_identity(choice) -> dict:
    return {
        "provider": getattr(choice, "provider", "?"),
        "model": getattr(choice, "model", "?"),
        "api_url": getattr(choice, "api_url", "?"),
        "source": "~/.ephe/engine.json (resolved via core.engine_config.resolve_engine_choice)",
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="W3-73 judge eval: rubric judge vs human labels")
    ap.add_argument("--labels", type=Path, default=DEFAULT_LABELS)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--reps", type=int, default=DEFAULT_REPS)
    ap.add_argument("--selftest", action="store_true", help="no model: schema, math, parser")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    rows = load_labels(args.labels)
    choice = resolve_engine()
    engine = _engine_identity(choice)
    print(f"engine: {engine['provider']}/{engine['model']} @ {engine['api_url']}")
    print(f"cases:  {len(rows)} ({label_distribution(rows)['defective']} defective), reps={args.reps}")

    records = asyncio.run(run_live(rows, model=engine["model"], reps=args.reps))
    receipt = build_receipt(rows, records, engine, args.labels, args.reps)

    # Fail loudly if the engine never answered: a provider_error storm is not a measurement.
    statuses = receipt["judge_status_distribution"]
    answered = statuses.get("ok", 0) + statuses.get("no_revision", 0)
    if answered == 0:
        print("ERROR: the judge never answered (all provider_error) - no number recorded")
        return 2

    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    m = receipt["metrics"]
    print(f"precision {m['precision']}  recall {m['recall']}  "
          f"f1 {m['f1']}  accuracy {m['accuracy']}  (n={m['n']})")
    print(f"tp={m['tp']} fp={m['fp']} fn={m['fn']} tn={m['tn']}  "
          f"flips={len(receipt['flips'])}  statuses={statuses}")
    print(f"receipt -> {args.out.relative_to(ROOT)}  misses={len(receipt['misses'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
