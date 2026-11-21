"""Noise floor — what a pass^3 delta on this matrix can mean at all.

Read-only over `evals/bench-trend.json`: it never writes a point, and it lives apart
from `bench_trend.py` because that is the module a running matrix scores with. The
unit of `pass^3` is a task, so the sample size is the number of tasks, not the number
of reps; the arithmetic below is what that costs.

    python evals/noise_floor.py                 # the floor from the recorded points
    python evals/noise_floor.py --power          # required tasks per arm, per delta
    python evals/noise_floor.py --verdict 0.9667 0.8667 60
    python evals/noise_floor.py --compare 4f2778c 29d47732

The recipe for a before/after that is worth something: score both arms with
`evals/bench_trend.py` (each point carries `task_verdicts` from 2026-10-10 on), then
`--compare` them. Six tasks flipping in one direction is already p=0.0312, seven is
0.0156, nine is 0.0039. Two independent points of the same size need 16-22 pp of
movement to say anything at all, so an A/B is worth running only as a pair.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from statistics import NormalDist

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from bench_trend import _wilson95  # noqa: E402 — one copy of the interval, not two

TREND = HERE / "bench-trend.json"
ALPHA = 0.05
POWER = 0.80
Z_ALPHA = NormalDist().inv_cdf(1 - ALPHA / 2)
Z_BETA = NormalDist().inv_cdf(POWER)
DELTAS = (0.05, 0.10, 0.15)


def se_single(rate: float, n: int) -> float:
    """Standard error of a pass^3 rate over n tasks."""
    if n <= 0:
        return 0.0
    return (max(rate, 0.0) * (1 - max(rate, 0.0)) / n) ** 0.5


def two_prop_z(p1: float, p2: float, n: int) -> tuple[float, float]:
    """Unpaired two-proportion test: z and its two-sided normal p-value."""
    pooled = (p1 + p2) / 2.0
    se = (2 * pooled * (1 - pooled) / n) ** 0.5
    if se == 0:
        return 0.0, 1.0
    z = abs(p1 - p2) / se
    return z, 2 * (1 - NormalDist().cdf(z))


def power_at(p1: float, delta: float, n: int, power: float = POWER) -> float:
    """Power of the unpaired test for a shift of `delta` away from `p1`."""
    p2 = min(max(p1 - delta, 0.0), 1.0)
    pbar = (p1 + p2) / 2.0
    se0 = (2 * pbar * (1 - pbar) / n) ** 0.5
    se1 = ((p1 * (1 - p1) + p2 * (1 - p2)) / n) ** 0.5
    if se1 == 0:
        return 0.0
    crit = Z_ALPHA * se0
    return 1 - NormalDist().cdf((crit - delta) / se1) + NormalDist().cdf((-crit - delta) / se1)


def required_n(p1: float, delta: float) -> int:
    n = 2
    while n < 200000 and power_at(p1, delta, n) < POWER:
        n += 1 if n < 200 else 10
    return n


def mdd(p1: float, n: int) -> float:
    """Smallest delta detectable at 80% power with n tasks per arm."""
    lo, hi = 0.0005, max(p1, 1 - p1)
    for _ in range(60):
        mid = (lo + hi) / 2
        if power_at(p1, mid, n) >= POWER:
            hi = mid
        else:
            lo = mid
    return hi


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact sign test on discordant task pairs (paired design)."""
    n = b + c
    if n == 0:
        return 1.0
    k = max(b, c)
    tail = sum(_binom(n, i) for i in range(k, n + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def _binom(n: int, k: int) -> int:
    out = 1
    for i in range(k):
        out = out * (n - i) // (i + 1)
    return out


def _points(path: Path) -> list[dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return raw if isinstance(raw, list) else []


def _split_total(raw: object) -> tuple[int, int]:
    parts = str(raw or "").split("/")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return int(parts[0]), int(parts[1])
    return 0, 0


def table(points: list[dict]) -> str:
    # Four of the ten recorded points were scored before the Wilson bug was fixed in
    # `02c7ce44`, so their stored interval is not the interval of their own counts.
    # Recomputing from `pass3_total` is the only way to put one number on the axis.
    lines = ["| ts | commit | tasks | pass^3 | rate | width recorded | width recomputed | implied per-rep p |",
             "|---|---|---|---|---|---|---|---|"]
    for p in points:
        k, n = _split_total(p.get("pass3_total"))
        rate = float(p.get("pass3_rate") or 0.0)
        if not n:
            lines.append(f"| {p.get('ts','')} | {p.get('commit','')} | - | "
                         f"{p.get('pass3_total','')} | {rate:.4f} | - | - | - |")
            continue
        recorded = (p.get("pass3_wilson95") or {}).get("width")
        now = _wilson95(k, n)["width"]
        stale = " *(stale)*" if recorded is not None and abs(recorded - now) > 5e-4 else ""
        lines.append(
            f"| {p.get('ts','')} | {p.get('commit','')} | {n} | {k}/{n} | {rate:.4f} | "
            f"{round(recorded, 4) if recorded is not None else '-'} | {round(now, 4)}{stale} | "
            f"{(k / n) ** (1 / 3):.4f} |"
        )
    return "\n".join(lines)


def pass_k(p: float, k: int) -> float:
    """Reliability of a task that answers each rep with probability p, over k reps."""
    return p ** k


def power_report(baselines: list[float]) -> str:
    lines = ["## Required tasks per arm, two-sided alpha=0.05, power=0.80 (unpaired)",
             "",
             f"z(alpha/2)={Z_ALPHA:.6f}  z(power)={Z_BETA:.6f}",
             "",
             "| baseline pass^3 | delta 5pp | delta 10pp | delta 15pp |",
             "|---|---|---|---|"]
    for b in baselines:
        row = [f"{b:.4f}"] + [f"{required_n(b, d)}" for d in DELTAS]
        lines.append("| " + " | ".join(row) + " |")
    lines += ["",
              "## What the matrix we have can already resolve",
              "",
              "Both columns are computed at a baseline pass^3 of 0.90.",
              "",
              "| tasks per arm | smallest delta at 80% power | delta significant at 5% |",
              "|---|---|---|"]
    for n in (30, 50, 60, 100, 150, 260, 500):
        detect = mdd(0.9, n)
        sig = Z_ALPHA * (2 * 0.9 * 0.1 / n) ** 0.5
        lines.append(f"| {n} | {detect * 100:.1f} pp | {sig * 100:.1f} pp |")
    lines += ["",
              "## Reps do not buy resolution, they change the quantity",
              "",
              "The observed pass^3 rate is a mean of n task-level Bernoulli indicators, so its",
              "standard error is sqrt(R(1-R)/n) and holds for any reps-per-task k. What k moves is",
              "the mapping from per-rep reliability p to the reported number:",
              "",
              "| per-rep p | pass^1 | pass^3 | pass^5 | pass^10 |",
              "|---|---|---|---|---|"]
    for p in (0.99, 0.95, 0.9, 0.85, 0.8):
        lines.append(f"| {p:.2f} | {pass_k(p, 1):.3f} | {pass_k(p, 3):.3f} | "
                     f"{pass_k(p, 5):.3f} | {pass_k(p, 10):.3f} |")
    return "\n".join(lines)


def paired_range(k1: int, k2: int, n: int) -> list[tuple[int, int, int, float]]:
    """McNemar over every overlap the two counts allow: (overlap, b, c, p).

    The trend file stores only how many tasks passed in each point, not which, so the
    number of tasks that flipped is not one value but a range — and that range is the
    honest statement about what the record can prove.
    """
    fail1, fail2 = n - k1, n - k2
    out = []
    for overlap in range(0, min(fail1, fail2) + 1):
        b, c = fail2 - overlap, fail1 - overlap
        if b + c == 0:
            continue
        out.append((overlap, b, c, mcnemar_exact(b, c)))
    return out


def verdict(p1: float, p2: float, n: int, overlap: int | None = None) -> str:
    k1, k2 = round(p1 * n), round(p2 * n)
    z, pval = two_prop_z(p1, p2, n)
    width = _wilson95(k1, n)["width"]
    delta = abs(p1 - p2)
    lines = [
        f"unpaired two-proportion: z={z:.3f} p={pval:.4f} -> "
        f"{'significant' if pval < ALPHA else 'not significant'} at alpha=0.05",
        f"single-point Wilson width at n={n}: {width:.4f} — the recorded trend_gate rule "
        f"demands delta >= width, so it {'passes' if delta >= width else 'fails'}",
        f"80% power needs {mdd(p1, n) * 100:.1f} pp at n={n} per arm",
        f"paired (same {n} tasks) McNemar sign test, k1={k1} k2={k2}:",
    ]
    rows = paired_range(k1, k2, n)
    shown = [r for r in rows if r[0] == overlap] if overlap is not None else rows
    for _, b, c, pm in shown:
        lines.append(f"  b={b} c={c}: p={pm:.4f} -> "
                     f"{'significant' if pm < ALPHA else 'not significant'}")
    if len(rows) > 1 and overlap is None:
        lo = min(r[3] for r in rows)
        hi = max(r[3] for r in rows)
        lines.append(f"  the record cannot settle it: p ranges {lo:.4f} to {hi:.4f} "
                     f"over the {len(rows)} possible overlaps — store per-task verdicts "
                     "in the point and the paired test becomes exact")
    return "\n".join(lines)


def _find(points: list[dict], label: str) -> dict | None:
    for p in points:
        if str(p.get("commit", "")) == label or str(p.get("ts", "")) == label:
            return p
        if str(p.get("ts", "")).startswith(label) or str(p.get("commit", "")).startswith(label):
            return p
    return None


def compare(points: list[dict], a: str, b: str) -> str:
    """The paired test on two points: which tasks flipped, and the exact p it implies.

    Counts alone cannot be paired — `paired_range` shows what that costs. With
    `task_verdicts` recorded in both points, the discordant pairs are a fact instead of
    a range, and the tasks are named so no one can average the finding away.
    """
    pa, pb = _find(points, a), _find(points, b)
    if not pa or not pb:
        return f"[noise-floor] point not found: {a if not pa else b}"
    va, vb = pa.get("task_verdicts") or {}, pb.get("task_verdicts") or {}
    if not va or not vb:
        k1, n1 = _split_total(pa.get("pass3_total"))
        k2, n2 = _split_total(pb.get("pass3_total"))
        rows = paired_range(k1, k2, n1) if n1 == n2 else []
        head = ("one of the two points carries no `task_verdicts`, so the paired test "
                "stays a range:")
        body = "\n".join(f"  overlap={o} b={b_} c={c}: p={p:.4f}" for o, b_, c, p in rows)
        return f"{head}\n{body or '  (different task counts, not pairable)'}"
    both = [t for t in sorted(set(va) & set(vb)) if va[t] in ("pass", "fail") and vb[t] in ("pass", "fail")]
    union = sorted(set(va) | set(vb))
    b_out = [t for t in both if va[t] == "pass" and vb[t] == "fail"]
    c_in = [t for t in both if va[t] == "fail" and vb[t] == "pass"]
    p = mcnemar_exact(len(b_out), len(c_in))
    rate_a = sum(va[t] == "pass" for t in both) / len(both) if both else 0.0
    rate_b = sum(vb[t] == "pass" for t in both) / len(both) if both else 0.0
    verdict_word = "significant" if p < ALPHA else "not significant"
    lines = [
        f"pairable tasks: {len(both)} of {len(union)} named across the two points",
        f"rate over the pair: {rate_a:.4f} -> {rate_b:.4f}",
        f"newly failing ({len(b_out)}): {', '.join(b_out) or '-'}",
        f"newly passing ({len(c_in)}): {', '.join(c_in) or '-'}",
        f"McNemar exact two-sided: p={p:.4f} -> {verdict_word} at alpha={ALPHA}",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trend", default=str(TREND))
    ap.add_argument("--power", action="store_true")
    ap.add_argument("--verdict", nargs=3, type=float, metavar=("P1", "P2", "N"))
    ap.add_argument("--compare", nargs=2, metavar=("A", "B"),
                    help="pair two recorded points by commit or ts and run the paired test")
    ap.add_argument("--overlap", type=int, default=None,
                    help="tasks failing in both points, for the paired test")
    args = ap.parse_args()

    points = _points(Path(args.trend))
    if args.compare:
        print(compare(points, args.compare[0], args.compare[1]))
        return
    if args.verdict:
        p1, p2, n = args.verdict
        print(verdict(p1, p2, int(n), args.overlap))
        return
    if not points:
        print(f"[noise-floor] no points in {args.trend}")
        return
    print(table(points))
    rates = [float(p.get("pass3_rate") or 0) for p in points if p.get("n_tasks_effective")]
    baselines = sorted({round(r, 4) for r in rates if 0 < r < 1}) or [0.87, 0.97]
    if args.power:
        print()
        print(power_report(baselines))
    print()
    last = points[-1]
    k, n = _split_total(last.get("pass3_total"))
    rate = k / n if n else 0.0
    print("Rule: a pass^3 claim is only a claim with its interval. The standard error of")
    print(f"this point alone is {se_single(rate, n) * 100:.1f} pp at n={n} tasks, and the floor for")
    print(f"an unpaired before/after comparison at 80% power is "
          f"{mdd(rate, n) * 100:.1f} pp. Below that, print both numbers or print nothing.")


if __name__ == "__main__":
    main()
