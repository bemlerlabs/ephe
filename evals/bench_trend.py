"""N4 — Benchmark trendline: pass^3 over several runs as a JSON manifest.

Reads the run manifests of ``evals/bench_option_b.py`` (one JSON per rep under
``<runs>/*.json``), computes the pass^3 metrics with the same semantics as
``bench_option_b.score`` (a task counts as reliable when every rep that exists
is ok AND the rep count is complete), and appends a data point to the trend
manifest. Append-only stat: nothing gets overwritten, the history grows.

A rep whose failure class is `engine` never reached the model, so it is left out
of the rep sets and of every timing/token/cost axis. Its task loses through the
incomplete-set rule above instead of counting as an agent failure. Such a point
names its own denominator (`n_tasks_effective`) plus `blocked_task_ids` and a
`comparability` note, because it describes a smaller matrix than a clean run of
the same tasks.

One data point:
    {
      "ts": "<ISO>",                # time of the score
      "commit": "<short>",          # short git HEAD (or "unknown")
      "engine": "<provider>",       # the measurement env first, then ~/.ephe/engine.json
      "model": "<model>",
      "series": "<provider>/<model>",  # the trend is per engine: another engine is its own series
      "pass3_total": "7/10",        # n/len, only tasks with a full rep set
      "pass3_rate": 0.7,            # float, rounded 4
      "by_family": {"tau": "2/4", "gaia": "3/4", "web": "2/2"},
      "wall_median_s": 12.3,        # median over all reps
      "reps_total": 30,
      "n_reps_blocked": 0,          # reps that never reached the engine
      "blocked_task_ids": []        # tasks left out of the denominator
    }

Usage:
    python evals/bench_trend.py            # append + last 8 points as a table
    python evals/bench_trend.py --show     # table only, no write
    python evals/bench_trend.py --runs DIR --out FILE   # explicit paths
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from bench_code_address import cohort_state as _cohort_state  # noqa: E402
from bench_manifests import manifest_paths as _manifest_paths  # noqa: E402

DEFAULT_RUNS = Path("/tmp/bench-option-b/runs")
DEFAULT_OUT = HERE / "bench-trend.json"
BENCH_SOURCE = HERE / "bench_option_b.py"
REPS_EXPECTED = 3
FAMILIES = ("tau", "gaia", "endstate")


def _matrix_size() -> int:
    """How many tasks the registry defines.

    Parsed, never imported: importing `bench_option_b` probes the product server for
    its model, and a scorer must not open a socket. The count is what lets a partial
    run say so — a 26-task point otherwise lands next to the 60-task series with
    nothing on it but a smaller number.
    """
    try:
        text = BENCH_SOURCE.read_text(encoding="utf-8")
    except OSError:
        return 0
    return len(re.findall(r'Task\(\s*"[A-Z]+\d+"', text))


def _read_manifests(runs_dir: Path) -> list[dict]:
    if not runs_dir.is_dir():
        return []
    out: list[dict] = []
    for f in _manifest_paths(runs_dir):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return out


def _median(vals: list[float]) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    n = len(s)
    mid = n // 2
    if n % 2:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2.0


def _percentile(vals: list[float], p: float) -> float:
    """Nearest-rank percentile (consistent with _median for odd n)."""
    if not vals:
        return 0.0
    import math
    s = sorted(vals)
    idx = max(1, math.ceil(p / 100.0 * len(s))) - 1
    return s[idx]


def _wilson95(k: int, n: int) -> dict:
    """95% Wilson interval for a binomial rate (z=1.959963984549679)."""
    if n <= 0:
        return {"lo": 0.0, "hi": 0.0, "width": 0.0, "n": 0}
    z = 1.959963984549679
    p = k / n
    den = 1.0 + z * z / n
    c = z * ((p * (1.0 - p) / n + z * z / (4.0 * n * n)) ** 0.5)
    centre = p + z * z / (2.0 * n)
    lo = (centre - c) / den
    hi = (centre + c) / den
    lo = max(0.0, lo)
    hi = min(1.0, hi)
    return {"lo": round(lo, 4), "hi": round(hi, 4),
            "width": round(hi - lo, 4), "n": n}


def _dist(vals: list[float]) -> dict:
    """Median/p90/p95/max/mean/sd/cv — tail regression visible at CV>0.3."""
    if not vals:
        return {}
    n = len(vals)
    mean = sum(vals) / n
    var = sum((x - mean) ** 2 for x in vals) / (n - 1) if n > 1 else 0.0
    sd = var ** 0.5
    return {
        "median": round(_median(vals), 2),
        "p90": round(_percentile(vals, 90), 2),
        "p95": round(_percentile(vals, 95), 2),
        "max": round(max(vals), 2),
        "mean": round(mean, 2),
        "sd": round(sd, 2),
        "cv": round(sd / mean, 4) if mean else 0.0,
    }


def _engine_rep(rep: dict) -> bool:
    """A rep that never reached the model: plumbing, so it is not a measurement.

    Same rule as `bench_option_b._engine_rep`, read here rather than imported —
    importing that module probes the product server for its model, and a scorer
    must not open a socket.
    """
    return str(rep.get("error_class") or "") == "engine"


def _display(k: int, n: int) -> str:
    """`52/60 = 86.7% ± 8.6` — the interval where a reader cannot miss it.

    The point always had `pass3_wilson95`, and it was still quoted as a bare
    `52/60` in prose, because a count is what catches the eye and an object is what
    holds the width. This puts both in one string.
    """
    if not n:
        return f"{k}/0"
    return f"{k}/{n} = {100.0 * k / n:.1f}% ± {_wilson95(k, n)['width'] * 50:.1f}"


def compute_point(runs: list[dict], *, ts: str, commit: str,
                  engine: str, model: str) -> dict:
    """pass^3 with the same semantics as bench_option_b.score()."""
    # A blocked rep never reached the engine. It is left out of every measurement
    # below, so its task falls out through the incomplete-rep-set rule instead of
    # counting as an agent loss. The rep itself stays in `error_histogram`: the
    # run did happen, and hiding which engine failed would lose the diagnosis.
    blocked = [r for r in runs if _engine_rep(r)]
    blocked_ids = sorted({str(r.get("task_id")) for r in blocked})
    live = [r for r in runs if not _engine_rep(r)]

    # task_id -> {rep: ok}
    by_task: dict[str, dict[int, bool]] = {}
    fam_of: dict[str, str] = {}
    walls: list[float] = []
    for r in live:
        tid = r.get("task_id")
        if not tid:
            continue
        by_task.setdefault(tid, {})[int(r.get("rep", 0))] = bool(r.get("ok"))
        if r.get("family"):
            fam_of[tid] = r["family"]
        if isinstance(r.get("wall_ms"), (int, float)):
            walls.append(float(r["wall_ms"]) / 1000.0)

    def p3_for(task_ids: list[str]) -> tuple[int, int]:
        passed = 0
        counted = 0
        for tid in task_ids:
            reps = by_task.get(tid, {})
            if len(reps) != REPS_EXPECTED:
                continue  # incomplete set -> not counted
            counted += 1
            if all(reps[k] for k in range(1, REPS_EXPECTED + 1)):
                passed += 1
        return passed, counted

    all_ids = sorted(by_task)
    tot_pass, tot_cnt = p3_for(all_ids)

    # Per-task verdicts, next to the counts. A point that stores only "52/60" cannot be
    # compared with another point by the test the design calls for: the same 60 tasks
    # measured twice is a paired experiment, and McNemar needs to know *which* tasks
    # flipped, not how many did. `noise_floor.py` reads this to give one p, not a range.
    task_verdicts: dict[str, str] = {}
    for tid in all_ids:
        reps = by_task[tid]
        if tid in blocked_ids:
            task_verdicts[tid] = "blocked"
        elif len(reps) != REPS_EXPECTED:
            task_verdicts[tid] = "incomplete"
        else:
            task_verdicts[tid] = "pass" if all(reps[k] for k in range(1, REPS_EXPECTED + 1)) else "fail"

    by_family: dict[str, str] = {}
    by_family_display: dict[str, str] = {}
    fam_ci: dict[str, dict] = {}
    fam_stats: dict[str, dict] = {}
    for fam in FAMILIES:
        fam_ids = [t for t in all_ids if fam_of.get(t) == fam]
        if not fam_ids:
            continue
        fp, fc = p3_for(fam_ids)
        by_family[fam] = f"{fp}/{fc}"
        by_family_display[fam] = _display(fp, fc)
        fam_ci[fam] = _wilson95(fp, fc)
        fam_walls = [float(r["wall_ms"]) / 1000.0 for r in live
                     if r.get("family") == fam and isinstance(r.get("wall_ms"), (int, float))]
        fam_tcs = [len(r["tool_calls"]) for r in live
                   if r.get("family") == fam and isinstance(r.get("tool_calls"), list)]
        fam_ttfts = [float(r["ttft_first_event_ms"]) for r in live
                    if r.get("family") == fam and isinstance(r.get("ttft_first_event_ms"), (int, float))]
        fam_stats[fam] = {
            "wall_s": _dist(fam_walls),
            "tool_calls": _dist([float(x) for x in fam_tcs]),
            "ttft_ms": _dist(fam_ttfts),
        }

    rate = round(tot_pass / tot_cnt, 4) if tot_cnt else 0.0

    # ── v2/v3 axes: only when the manifests supply them (schema-backwards-compatible)
    tcs = [float(len(r["tool_calls"])) for r in live if isinstance(r.get("tool_calls"), list)]
    ttfts = [float(r["ttft_first_event_ms"]) for r in live
             if isinstance(r.get("ttft_first_event_ms"), (int, float))]
    # v3: real tokens_out_proxy in the manifest; v2 fallback: chars/4 heuristic
    tokens_proxy = [float(r["tokens_out_proxy"]) for r in live
                    if isinstance(r.get("tokens_out_proxy"), (int, float))]
    if not tokens_proxy:
        tokens_proxy = [float(r["answer_chars"]) / 4.0 for r in live
                        if isinstance(r.get("answer_chars"), (int, float))]
    tool_hist: dict[str, int] = {}
    for r in live:
        for name in r.get("tool_calls") or []:
            tool_hist[str(name)] = tool_hist.get(str(name), 0) + 1

    # v3: error taxonomy + level band + fixture hash (v3 manifests only)
    err_hist: dict[str, int] = {}
    for r in runs:
        if not r.get("ok"):
            ec = str(r.get("error_class") or "assertion")
            err_hist[ec] = err_hist.get(ec, 0) + 1
    levels: dict[str, list[str]] = {}
    for r in live:
        if r.get("level"):
            levels.setdefault(str(r["level"]), []).append(str(r["task_id"]))
    fixture_hashes = {r.get("fixture_hash") for r in runs if r.get("fixture_hash")}
    # Which code answered, counted per measured surface rather than per commit: tooling
    # commits between reps are one number, a second surface digest is two.
    code = _cohort_state(runs)

    # v4: real token/cost axis from the usage frame (only when manifests have it)
    pin = [float(r["prompt_tokens"]) for r in live
           if isinstance(r.get("prompt_tokens"), (int, float))]
    pout = [float(r["completion_tokens"]) for r in live
            if isinstance(r.get("completion_tokens"), (int, float))]
    ptot = [float(r["total_tokens"]) for r in live
            if isinstance(r.get("total_tokens"), (int, float))]
    costs = [float(r["cost_usd"]) for r in live
             if isinstance(r.get("cost_usd"), (int, float))]
    est_flags = [bool(r["usage_estimated"]) for r in live
                 if isinstance(r.get("usage_estimated"), bool)]

    # Rep agreement: tasks whose ok is identical over all reps (temp=0 => 1.0 expected)
    agree = sum(1 for tid in all_ids
                if len(set(by_task[tid].values())) == 1 and len(by_task[tid]) == REPS_EXPECTED)

    # Single-trial axis: the published agent tables report one resolution rate with a
    # ± and a cost per task, not a pass^3. Both numbers describe the same run, so a
    # point that wants to sit next to theirs has to carry theirs as well.
    live_ok = sum(1 for r in live if r.get("ok"))
    pass1_rate = round(live_ok / len(live), 4) if live else 0.0
    pricing_sources = {str(r.get("pricing_source")) for r in live if r.get("pricing_source")}
    point = {
        "schema_version": 4 if ptot else (3 if err_hist or levels else 2),
        "ts": ts,
        "commit": commit,
        "code_address": code,
        "engine": engine,
        "model": model,
        # The trend is per engine: a point measured on another engine is its own series, and
        # this key is what says so on the row and blocks a mixed append (see
        # `engine_series_block`).
        "series": f"{engine}/{model}",
        "pass3_total": f"{tot_pass}/{tot_cnt}",
        "pass3_display": _display(tot_pass, tot_cnt),
        "pass3_rate": rate,
        "pass3_wilson95": _wilson95(tot_pass, tot_cnt),
        "trials": REPS_EXPECTED,
        "pass1_rate": pass1_rate,
        "pass1_display": _display(live_ok, len(live)),
        "pass1_wilson95": _wilson95(live_ok, len(live)),
        "n_tasks_effective": tot_cnt,  # reps at temp=0 are not independent observations
        "matrix_tasks": _matrix_size() or None,
        "rep_agreement_rate": round(agree / len(all_ids), 4) if all_ids else 0.0,
        "by_family": by_family,
        "by_family_display": by_family_display,
        "by_family_wilson95": fam_ci,
        "by_family_stats": fam_stats,
        "wall_median_s": round(_median(walls), 1),
        "wall_s": _dist(walls),
        "ttft_ms": _dist(ttfts),
        "tool_calls": _dist(tcs),
        "tool_calls_histogram": tool_hist,
        "tokens_out_proxy": _dist(tokens_proxy),
        "reps_total": len(live),
        "n_reps_blocked": len(blocked),
        "blocked_task_ids": blocked_ids,
        "task_verdicts": task_verdicts,
        "trend_gate": {
            "min_delta_significant": round(_wilson95(tot_pass, tot_cnt).get("width", 0.0), 4),
            "note": "movement is only significant when |delta pass_rate| >= CI width",
        },
    }
    reasons = []
    if blocked_ids:
        reasons.append(f"{len(blocked_ids)} task(s) lost reps to the engine, not to Ephe, and "
                       f"are out of the {tot_cnt}-task denominator")
    matrix = _matrix_size()
    if matrix and tot_cnt < matrix:
        reasons.append(f"partial matrix: {tot_cnt} of {matrix} tasks scored"
                       + (f", {matrix - tot_cnt} absent from these manifests" if matrix - tot_cnt else ""))
    if reasons:
        point["comparability"] = ("; ".join(reasons)
                                  + " — not comparable with full-matrix points")
    if err_hist:
        point["error_histogram"] = err_hist
    if levels:
        point["by_level"] = {lv: len(sorted(set(ids))) for lv, ids in sorted(levels.items())}
    if len(fixture_hashes) == 1:
        point["fixture_hash"] = next(iter(fixture_hashes))
    # v4: real token/cost axis (tau-bench parity: tokens+cost per rep)
    if ptot:
        point["tokens"] = {
            "prompt": _dist(pin),
            "completion": _dist(pout),
            "total": _dist(ptot),
            "sum_total": int(sum(ptot)),
            "usage_estimated_share": (
                round(sum(1 for f in est_flags if f) / len(est_flags), 4) if est_flags else None
            ),
        }
    if costs:
        total_cost = round(sum(costs), 6)
        point["cost_usd"] = {
            "per_run": _dist(costs),
            "sum_total": total_cost,
            "per_task_attempted": round(total_cost / tot_cnt, 6) if tot_cnt else None,
            "per_task_solved": round(total_cost / tot_pass, 6) if tot_pass else None,
        }
    if len(pricing_sources) == 1:
        point["pricing_source"] = next(iter(pricing_sources))
    return point


def _git_short() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                           cwd=HERE, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _engine_meta() -> tuple[str, str, str]:
    """(provider, model, source) of the *measurement* engine.

    The env override is the measurement engine (2026-10-12 DeepSeek decision): a run booted
    with `EPHE_MODEL_PROVIDER=openai_compatible` / `EPHE_OPENAI_COMPAT_MODEL=deepseek-v4-pro`
    answers with a different engine than the persisted `~/.ephe/engine.json`, which stays the
    owner's chat engine. The trend must name the engine that measured, so the env wins; the
    persisted config is the fallback for cohorts measured before the override existed. This
    closes the runbook's item 5 ("the engine label can be a lie") for the switched-engine case.
    """
    provider = (os.environ.get("EPHE_MODEL_PROVIDER") or "").strip()
    model_env = {"local_ollama": "EPHE_MODEL", "custom_ollama": "EPHE_MODEL",
                 "openai_compatible": "EPHE_OPENAI_COMPAT_MODEL"}.get(provider)
    model = (os.environ.get(model_env) or "").strip() if model_env else ""
    if provider and model:
        return provider, model, "env"
    p = Path.home() / ".ephe" / "engine.json"
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return str(d.get("provider", "?")), str(d.get("model", "?")), str(p)
    except Exception:
        return "unknown", "unknown", "unknown"


def _series_of(point: dict) -> str:
    """The series a point belongs to: one series per engine.

    Read from the recorded `series` field, or derived for the points written before it
    existed. A missing engine derives `"/"`, which never equals a named series.
    """
    stored = str(point.get("series") or "").strip()
    if stored:
        return stored
    return f"{point.get('engine','')}/{point.get('model','')}"


def _read_history(out: Path) -> list[dict]:
    if not out.exists():
        return []
    try:
        raw = json.loads(out.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return raw if isinstance(raw, list) else []


def _append(out: Path, point: dict) -> int:
    history: list[dict] = []
    if out.exists():
        try:
            raw = json.loads(out.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                history = raw
        except (json.JSONDecodeError, OSError):
            history = []
    # idempotent: the same ts replaces the last point (no double append)
    if history and history[-1].get("ts") == point["ts"]:
        history[-1] = point
    else:
        history.append(point)
    out.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    return len(history)


def _render(points: list[dict], n: int = 8) -> str:
    """The series table. Every rate arrives with its interval and its trial count.

    The first ten points were scored before the display fields existed, so the width is
    derived here rather than read: a row that could not carry its scatter would be the
    one row someone quotes.

    The engine cell marks where the series breaks: a point measured on another engine is a
    different series, and the row says so instead of letting the line read as one that fell.
    """
    start = max(0, len(points) - n)
    rows = points[start:]
    lines = ["| ts | commit | engine | pass^3 ± CI | pass^1 ± CI | trials | tasks | tau | gaia | endstate | wall_med |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for i, p in enumerate(rows, start=start):
        bf = p.get("by_family", {})
        k, total = _count_pair(p.get("pass3_total"))
        prev = points[i - 1] if i else None
        marker = ""
        if prev is not None and _series_of(prev) and _series_of(p) != _series_of(prev):
            marker = f" ⟵ new series ({_series_of(p)})"
        lines.append(
            f"| {p.get('ts','')} | {p.get('commit','')} | {p.get('engine','')}{marker} | "
            f"{p.get('pass3_display') or _display(k, total)} | {_pass1_display(p)} | "
            f"{_trials_of(p)} | "
            f"{p.get('n_tasks_effective') or total or '-'} | "
            f"{bf.get('tau','-')} | {bf.get('gaia','-')} | {bf.get('endstate','-')} | "
            f"{p.get('wall_median_s','')}s |"
        )
    return "\n".join(lines)


def _count_pair(raw: object) -> tuple[int, int]:
    parts = str(raw or "").split("/")
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return int(parts[0]), int(parts[1])
    return 0, 0


def _pass1_from_point(p: dict) -> tuple[float | None, float | None]:
    """Single-trial rate of a point scored before the field was written.

    `reps_total` and `error_histogram` carry it: the histogram counts the reps that did
    not pass, and blocked reps are absent from `reps_total` but present in the
    histogram, so they are subtracted back out.
    """
    rate, ci = p.get("pass1_rate"), p.get("pass1_wilson95")
    if isinstance(rate, float) and isinstance(ci, dict):
        return rate, ci.get("width")
    total = p.get("reps_total")
    if not isinstance(total, int) or total <= 0:
        return None, None
    failed = sum((p.get("error_histogram") or {}).values()) - int(p.get("n_reps_blocked") or 0)
    ok = max(total - failed, 0)
    return round(ok / total, 4), _wilson95(ok, total)["width"]


def _trials_of(p: dict) -> object:
    """Trial count: recorded, or derived from a rep-bearing point, never invented."""
    return p.get("trials") or (REPS_EXPECTED if p.get("reps_total") else "-")


def _pass1_display(p: dict) -> str:
    """`164/180 = 91.1% ± 4.2`, read from the point or derived from its counts."""
    stored = p.get("pass1_display")
    if stored:
        return str(stored)
    rate, width = _pass1_from_point(p)
    if not isinstance(rate, float) or not isinstance(width, (int, float)):
        return "-"
    total = p.get("reps_total")
    if isinstance(total, int) and total > 0:
        return _display(int(round(rate * total)), total)
    return f"{rate * 100:.1f}% ± {width * 50:.1f}"


def _render_public(points: list[dict], n: int = 4) -> str:
    """The last points in the format the published agent tables use.

    Single-trial resolution rate with its interval, trials, and USD per solved task —
    the axes Terminal-Bench and peers print, so a number here is readable next to
    theirs instead of being compared to the wrong column.
    """
    lines = ["| agent | model | resolution ± 95% CI | trials | tasks | USD / solved task |",
             "|---|---|---|---|---|---|"]
    for p in points[-n:]:
        solved = (p.get("cost_usd") or {}).get("per_task_solved")
        lines.append(
            f"| {p.get('engine','')} | {p.get('model','')} | {_pass1_display(p)} | "
            f"{_trials_of(p)} | {p.get('n_tasks_effective','-')} | "
            f"{solved if solved is not None else '-'} |"
        )
    return "\n".join(lines)


def partial_block(point: dict) -> str:
    """Why this point must not join the series, or `""` when it may.

    A family-only run scores 26 tasks and used to land beside the 60-task points
    carrying nothing but a smaller number, where the interval around it is already
    twice as wide. The full matrix is what the trend line means; a sub-matrix belongs
    in a report, or in the line only as a labelled exception a human asked for.
    """
    matrix = int(point.get("matrix_tasks") or 0)
    got = int(point.get("n_tasks_effective") or 0)
    if not matrix:
        return "the registry task count could not be read, so no matrix check ran"
    if got < matrix:
        shown = point.get("pass3_display") or point.get("pass3_total") or f"{got} tasks"
        return (f"partial matrix: {got} of {matrix} tasks carry a complete rep set "
                f"({shown}) — a {got}-task figure cannot sit beside a full-matrix point")
    return ""


def engine_series_block(point: dict, history: list[dict]) -> str:
    """Why this point may not join the series, or `""` when it may.

    The trend is per engine (2026-10-12 DeepSeek decision): a point measured on engine A and
    a point measured on engine B are two experiments, and appending the second next to the
    first would read as one line that fell. A DeepSeek run starts its *own* series — its own
    file — instead of quietly continuing the Spark series, and the point itself names it via
    the `series` field. Only the mixing is refused, never a new series.
    """
    if not history:
        return ""
    new = _series_of(point)
    if not new or "/" not in new:
        return ""
    in_file = {_series_of(p) for p in history}
    if new in in_file:
        return ""
    prev = _series_of(history[-1])
    return (f"engine series: this point is {new}, the series here is {prev} — the trend is "
            f"per engine and a point measured on another engine is its own series; way out: "
            f"score it into its own --out file, or --allow-engine-series REASON to carry two "
            f"engines in one file on purpose")


def address_block(point: dict) -> tuple[str, bool]:
    """(why this cohort may not join the series, whether a recorded reason can waive it).

    An old cohort is a decision someone can take out loud. A cohort measured across two
    surfaces is not a number that needs permission — it is two runs wearing one label,
    and there is deliberately no flag for it.
    """
    code = point.get("code_address") or {}
    status = code.get("status", "legacy")
    if status in ("legacy", "partly-unaddressed"):
        total = code.get("manifests", 0)
        missing = code.get("unaddressed", 0)
        return (f"no code address: {missing} of {total} manifest(s) name neither a commit nor "
                f"the measured surface, so the rate cannot be tied back to a tree — way out: "
                f"re-score a cohort written after `code_address` landed, or --allow-legacy "
                f"REASON to carry an old one over on purpose", True)
    if status == "moved-mid-run":
        per = code.get("reps_per_stand") or {}
        shown = ", ".join(f"{key[:8]}: {count} reps" for key, count in sorted(per.items()))
        return (f"the tree moved mid-run: {code.get('stands')} measured stands in one cohort "
                f"({shown}) — way out: score each stand as its own point or discard the "
                f"cohort; no flag waives this one", False)
    return "", False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", default=str(DEFAULT_RUNS))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--show", action="store_true", help="table only, no write")
    ap.add_argument("--public", action="store_true",
                    help="last points as resolution ± CI and USD per solved task")
    ap.add_argument("--allow-legacy", metavar="REASON", default=None,
                    help="append a cohort whose manifests carry no code address, with the reason")
    ap.add_argument("--allow-partial", metavar="REASON", default=None,
                    help="append a sub-matrix point anyway, with the reason recorded")
    ap.add_argument("--allow-engine-series", metavar="REASON", default=None,
                    help="append a point from another engine next to the series here, with "
                         "the reason recorded (the trend is per engine)")
    ap.add_argument("--ts", default=None, help="ISO timestamp (default: now)")
    args = ap.parse_args()

    if args.public:
        history = _read_history(Path(args.out))
        print(_render_public(history))
        return

    runs = _read_manifests(Path(args.runs))
    if not runs:
        print(f"[bench-trend] no manifests under {args.runs} — nothing to log.")
        return

    ts = args.ts or __import__("datetime").datetime.now().isoformat(timespec="seconds")
    commit = _git_short()
    engine, model, engine_source = _engine_meta()
    point = compute_point(runs, ts=ts, commit=commit, engine=engine, model=model)
    # Where the engine label came from: `env` is the measurement override (first-class since
    # 2026-10-12), a path is the persisted engine.json a legacy cohort ran under.
    point["engine_source"] = engine_source

    out = Path(args.out)
    if args.show:
        existing = _read_history(out)
        print(_render(existing or [point]))
        return

    unaddressed, waivable = address_block(point)
    if unaddressed and not (waivable and args.allow_legacy):
        print(f"[bench-trend] not appended: {unaddressed}", file=sys.stderr)
        if waivable:
            print("[bench-trend] this is a judgement about an old cohort, so it is yours to "
                  "record: pass --allow-legacy <reason>", file=sys.stderr)
        raise SystemExit(2)
    if unaddressed:
        point["legacy_reason"] = args.allow_legacy
        point["comparability"] = (f"{point.get('comparability', '')} — appended under "
                                  f"--allow-legacy: {args.allow_legacy}").lstrip(" —")

    blocked = partial_block(point)
    if blocked and not args.allow_partial:
        print(f"[bench-trend] not appended: {blocked}", file=sys.stderr)
        print("[bench-trend] a family run is a report, not a trend point; if this is "
              "meant to be a labelled sub-matrix, pass --allow-partial <reason>",
              file=sys.stderr)
        raise SystemExit(2)
    if blocked:
        point["submatrix_reason"] = args.allow_partial
        point["comparability"] = (f"{point.get('comparability', '')} — appended under "
                                  f"--allow-partial: {args.allow_partial}").lstrip(" —")

    mixed_engine = engine_series_block(point, _read_history(out))
    if mixed_engine and not args.allow_engine_series:
        print(f"[bench-trend] not appended: {mixed_engine}", file=sys.stderr)
        print("[bench-trend] a DeepSeek run starts its own series: score it with its own "
              "--out (e.g. evals/bench-trend-deepseek.json)", file=sys.stderr)
        raise SystemExit(2)
    if mixed_engine:
        point["engine_series_reason"] = args.allow_engine_series
        point["comparability"] = (f"{point.get('comparability', '')} — appended under "
                                  f"--allow-engine-series: {args.allow_engine_series}").lstrip(" —")
    n = _append(out, point)
    print(f"[bench-trend] point appended -> {out} ({n} points)")
    print(json.dumps(point, ensure_ascii=False, indent=2))
    history = _read_history(out)
    print()
    print(_render(history))


if __name__ == "__main__":
    main()
