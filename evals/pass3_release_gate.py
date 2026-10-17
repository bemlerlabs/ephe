"""The pass^3 release gate: a cohort whose outcome is flaky does not release.

`pass^3` asks every repetition of a task to reach the same verdict
(`evals/bench_option_b.py`). A task whose repetitions disagree is a flaky outcome: the same
task, the same engine, a different result, so there is no single verdict the release would
carry. This gate reads a cohort's rep manifests and returns one release decision:

  * 0 — the outcome reproduces; the release may proceed;
  * 1 — a task flipped between reps (the flaky block this file exists for);
  * 2 — the gate cannot see (no manifests), cannot compute pass^3 (a rep set is short), the
    engine behind the recorded number is a local runtime instead of the provider API, or the
    cohort's own record names an engine other than the one this machine would stamp.

The release number is named with its engine, and the engine is read from the cohort first:
the `engine`/`model` a rep manifest carries, the `engine_seen` the preflight stamp answered,
the `point.json` the cohort was scored into, then the `engine_expected` the run was asked for
(`evals/bench_preflight.py` writes the last three, and `evals/bench_trend.py` the point). A
cohort measured on a local model describes one machine, so the gate refuses it. When the
cohort's record and the configured `~/.ephe/engine.json` disagree, the gate refuses to stamp
the configured engine onto a cohort it did not produce:

    engine mismatch: the cohort was measured on <engine> (<source>) while this machine's
    engine is <engine> (<config>) — stamping it here would name an engine that did not
    produce the number; way out: run the gate where engine.json names the cohort's engine,
    or --allow-engine-mismatch REASON to carry it on purpose

A cohort that records no engine at all is still scored, and the receipt says the cohort
carries no provenance rather than naming the machine the gate happens to run on.

Usage:

    python evals/pass3_release_gate.py --runs /tmp/bench-option-b/runs
    python evals/pass3_release_gate.py --runs DIR --receipt out.json --task W3-59
    python evals/pass3_release_gate.py --runs DIR --no-engine-check   # flake check only
    python evals/pass3_release_gate.py --runs DIR --allow-engine-mismatch "scored on the Spark"
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bench_manifests import STAMP_NAME, manifest_paths  # noqa: E402

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_RUNS = Path("/tmp/bench-option-b/runs")
DEFAULT_ENGINE = Path.home() / ".ephe" / "engine.json"

#: The point `evals/bench_trend.py --out <cohort>/point.json` scores the cohort into.
COHORT_POINT = "point.json"

REPS_EXPECTED = 3
RELEASE_OK = 0
BLOCKED = 1
UNTRUSTED = 2
DECISION = {RELEASE_OK: "release-ok", BLOCKED: "blocked-flaky", UNTRUSTED: "untrusted"}

# A local runtime is a machine under the desk, not the provider whose number a release
# would publish; the release bar is the persisted API engine.
LOCAL_PROVIDERS = frozenset({"ollama", "llamacpp", "llama.cpp", "local", "mlx", "lmstudio"})
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal"})
LOCAL_MODEL_MARKERS = (".gguf", ":latest")


def load_manifests(runs_dir: Path) -> list[dict]:
    """Every readable rep manifest in `runs_dir`, the stamp and the strays left out."""
    runs: list[dict] = []
    for path in manifest_paths(Path(runs_dir)):
        try:
            row = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(row, dict) and row.get("task_id"):
            runs.append(row)
    return runs


def classify(runs: list[dict], reps: int = REPS_EXPECTED) -> dict[str, list[str]]:
    """Per-task verdicts: pass, fail, flaky, incomplete, blocked.

    A task with any `error_class: "engine"` rep is blocked and drops out of the denominator,
    because the engine never answered it (the rule `evals/bench_option_b.py` applies). A
    complete set with mixed verdicts is flaky; a complete set that never passed is a
    consistent fail. A short set is incomplete: pass^3 needs all `reps` to be stated.
    """
    by_task: dict[str, dict] = defaultdict(dict)
    for run in runs:
        by_task[str(run["task_id"])][run.get("rep")] = run

    out: dict[str, list[str]] = {"pass": [], "fail": [], "flaky": [], "incomplete": [], "blocked": []}
    for task_id in sorted(by_task):
        reps_seen = by_task[task_id]
        if any(str(r.get("error_class") or "") == "engine" for r in reps_seen.values()):
            out["blocked"].append(task_id)
        elif len(reps_seen) != reps:
            out["incomplete"].append(task_id)
        else:
            ok = [bool(r.get("ok")) for r in reps_seen.values()]
            if all(ok):
                out["pass"].append(task_id)
            elif not any(ok):
                out["fail"].append(task_id)
            else:
                out["flaky"].append(task_id)
    return out


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def engine_status(cfg: dict | None) -> tuple[str, str]:
    """Whether the engine cfg may carry the release number: "ok", "local" or "unknown"."""
    cfg = cfg or {}
    provider = str(cfg.get("provider") or "").strip().lower()
    model = str(cfg.get("model") or "").strip()
    url = str(cfg.get("api_url") or cfg.get("base_url") or "").strip()
    if not provider or provider in {"?", "unknown"}:
        return "unknown", "the persisted engine could not be read"
    if provider in LOCAL_PROVIDERS:
        return "local", f"provider {provider!r} is a local runtime"
    host = _host(url)
    if host in LOCAL_HOSTS or host.startswith("127."):
        return "local", f"api_url host {host!r} is loopback"
    if any(marker in model.lower() for marker in LOCAL_MODEL_MARKERS):
        return "local", f"model {model!r} is a local artifact"
    return "ok", f"{provider}/{model or '?'} at {host or 'the provider default'}"


def _text(value: object) -> str:
    return str(value or "").strip()


def _read_json(path: Path) -> object:
    """The JSON at `path`, or `None` when the file is missing or unreadable."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _engine_id(provider: object, model: object) -> str:
    """`provider/model`, the series key `evals/bench_trend.py` records — provider alone when
    the row names no model."""
    provider, model = _text(provider).lower(), _text(model).lower()
    if not provider and not model:
        return ""
    return f"{provider}/{model}" if model else provider


def _series_id(row: dict) -> str:
    """The engine one recorded row names: its `series`, or its `engine`/`model` pair."""
    return _text(row.get("series")).lower() or _engine_id(
        row.get("engine") or row.get("provider"), row.get("model"))


def _split(ident: str) -> tuple[str, str]:
    provider, _, model = ident.partition("/")
    return provider.strip().lower(), model.strip().lower()


def _same_engine(a: str, b: str) -> bool:
    """Two records name the same engine. A record without a model stands for any model of
    its provider, so it never turns a missing field into a disagreement."""
    provider_a, model_a = _split(a)
    provider_b, model_b = _split(b)
    if provider_a != provider_b:
        return False
    return not (model_a and model_b) or model_a == model_b


def cohort_provenance(runs_dir: Path, runs: list[dict]) -> dict:
    """The engine the cohort itself records, read from the files in `runs_dir`.

    The measuring engine is written in a few places, and they are read in the order the
    cohort trusts them: the `engine`/`model` a rep manifest carries, the `engine_seen` the
    backend answered at preflight, the `point.json` the cohort was scored into, then the
    `engine_expected` the run was only *asked* for. A cohort that records none of these
    carries no provenance, and the gate names that instead of guessing.
    """
    runs_dir = Path(runs_dir)
    records: list[tuple[str, str]] = []

    def add(source: str, ident: object) -> None:
        ident = _text(ident)
        if ident:
            records.append((source, ident))

    for row in runs:
        add("a rep manifest", _series_id(row))
    raw_stamp = _read_json(runs_dir / STAMP_NAME)
    stamp = raw_stamp if isinstance(raw_stamp, dict) else {}
    add(f"{STAMP_NAME}:engine_seen", stamp.get("engine_seen"))
    add(f"{STAMP_NAME}:engine_series", stamp.get("engine_series"))
    raw_point = _read_json(runs_dir / COHORT_POINT)
    points = raw_point if isinstance(raw_point, list) else ([raw_point] if isinstance(raw_point, dict) else [])
    for row in points:
        if isinstance(row, dict):
            add(COHORT_POINT, _series_id(row))
    add(f"{STAMP_NAME}:engine_expected", stamp.get("engine_expected"))
    health = stamp.get("health")
    if isinstance(health, dict):
        add(f"{STAMP_NAME}:health",
            _engine_id(health.get("active_provider"), health.get("active_model")))

    return {
        "engine": records[0][1] if records else "",
        "source": records[0][0] if records else "",
        "expected": _text(stamp.get("engine_expected")),
        "records": [{"source": source, "engine": engine} for source, engine in records],
    }


def cohort_agreement(cohort: dict, configured: str) -> str:
    """One word for how the cohort's own records relate to the configured engine:

    "two-engines" — the cohort names engines that cannot be one run;
    "absent" — the cohort records no engine at all;
    "not-compared" — the cohort records one, and no engine is configured to compare it with;
    "match" / "mismatch" — against the configured engine.
    """
    engines = [row["engine"] for row in cohort["records"]]
    if len(engines) > 1:
        for i, one in enumerate(engines):
            for other in engines[i + 1:]:
                if not _same_engine(one, other):
                    return "two-engines"
    if not engines:
        return "absent"
    if not configured:
        return "not-compared"
    return "match" if _same_engine(engines[0], configured) else "mismatch"


def engine_refusal(cohort: dict, agreement: str, configured: str, engine_source: str) -> str:
    """Why the cohort's engine and the configured one may not be written together, or `""`.

    A mismatch is a decision someone can take out loud (`--allow-engine-mismatch REASON`).
    A cohort that names two engines is not a number that needs permission — it is two runs
    wearing one label, and there is deliberately no flag for it.
    """
    if agreement == "two-engines":
        named = ", ".join(dict.fromkeys(row["engine"] for row in cohort["records"]))
        return (f"cohort engine: {named} are all named inside one cohort — one cohort measured "
                f"on two engines is two runs wearing one label; way out: split the cohort or "
                f"re-score it on one engine (no flag waives this)")
    if agreement != "mismatch":
        return ""
    return (f"engine mismatch: the cohort was measured on {cohort['engine']} ({cohort['source']}) "
            f"while this machine's engine is {configured} "
            f"({engine_source or 'the persisted engine'}) — stamping it here would name an "
            f"engine that did not produce the number; way out: run the gate where engine.json "
            f"names the cohort's engine, or --allow-engine-mismatch REASON to carry it on purpose")


def gate(runs_dir: Path, reps: int = REPS_EXPECTED, engine_cfg: dict | None = None,
         *, engine_source: str = "", allow_engine_mismatch: str | None = None) -> dict:
    """The release decision for one cohort: exit code, the reasons that produced it, the facts."""
    runs = load_manifests(runs_dir)
    facts = classify(runs, reps)
    evaluable = len(facts["pass"]) + len(facts["fail"]) + len(facts["flaky"])
    reasons: list[str] = []

    status, engine_note = engine_status(engine_cfg) if engine_cfg is not None else ("ok", "")
    if status == "unknown":
        reasons.append(f"engine unnamed: {engine_note}")
    elif status == "local":
        reasons.append(f"local engine: {engine_note} — the recorded number needs the provider API engine")

    cfg = engine_cfg or {}
    configured = _engine_id(cfg.get("provider"), cfg.get("model")) if engine_cfg is not None else ""
    cohort = cohort_provenance(runs_dir, runs)
    agreement = cohort_agreement(cohort, configured)
    refusal = engine_refusal(cohort, agreement, configured, engine_source)
    # Only a config-vs-cohort mismatch is a decision a reason can waive; two engines in one
    # cohort never is (see `engine_refusal`).
    waived = allow_engine_mismatch if refusal and agreement == "mismatch" else None
    if refusal and not waived:
        reasons.append(refusal)

    if not runs:
        reasons.append(f"no rep manifests under {runs_dir} — way out: --runs <a cohort's runs dir>")
    elif facts["flaky"]:
        names = ", ".join(facts["flaky"])
        reasons.append(f"flaky outcome: {names} flip between reps — way out: re-run the task, "
                       "or record the flake before the number is quoted")
    elif facts["incomplete"]:
        names = ", ".join(facts["incomplete"])
        reasons.append(f"pass^3 not computable: {names} have a short rep set — way out: re-run "
                       "the missing reps")

    if (engine_cfg is not None and status in {"local", "unknown"}) or not runs or (refusal and not waived):
        exit_code = UNTRUSTED
    elif facts["flaky"]:
        exit_code = BLOCKED
    elif facts["incomplete"]:
        exit_code = UNTRUSTED
    else:
        exit_code = RELEASE_OK

    return {
        "exit": exit_code,
        "decision": DECISION[exit_code],
        "reasons": reasons,
        "facts": facts,
        "runs": len(runs),
        "reps": reps,
        "pass3": f"{len(facts['pass'])}/{evaluable}",
        "engine_status": status,
        "engine_note": engine_note,
        "cohort_engine": cohort["engine"],
        "cohort_engine_source": cohort["source"],
        "cohort_engine_expected": cohort["expected"],
        "cohort_engine_records": cohort["records"],
        "engine_agreement": agreement,
        "engine_refusal": refusal,
        "engine_mismatch_waived": waived,
    }


def _git_head() -> str:
    try:
        done = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=False)
    except OSError:
        return "unknown"
    return done.stdout.strip() if done.returncode == 0 else "unknown"


def build_receipt(result: dict, engine_cfg: dict | None, engine_source: str, *, task: str) -> dict:
    """The decision as a receipt, the engine named so the number carries its producer.

    The configured engine is recorded beside what the cohort itself names, so a reader can
    see whether the number carries the engine that measured it or the one on this machine.
    """
    facts = result["facts"]
    cfg = engine_cfg or {}
    return {
        "kind": "pass3-release-gate-receipt",
        "task": task,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": str(REPO),
        "git_head": _git_head(),
        "gate": "pass^3",
        "reps_expected": result["reps"],
        "manifests": result["runs"],
        "decision": result["decision"],
        "exit": result["exit"],
        "pass3": result["pass3"],
        "flaky_tasks": facts["flaky"],
        "consistent_fail_tasks": facts["fail"],
        "incomplete_tasks": facts["incomplete"],
        "engine_blocked_tasks": facts["blocked"],
        "engine": {
            "provider": cfg.get("provider"),
            "model": cfg.get("model"),
            "api_url": cfg.get("api_url"),
            "host": _host(str(cfg.get("api_url") or "")),
            "source": engine_source,
            "status": result["engine_status"],
            "cohort": {
                "engine": result["cohort_engine"],
                "source": result["cohort_engine_source"],
                "expected": result["cohort_engine_expected"],
                "agreement": result["engine_agreement"],
                "refusal": result["engine_refusal"],
                "waived": result["engine_mismatch_waived"],
            },
        },
        "reasons": result["reasons"],
    }


def _render(result: dict) -> str:
    facts = result["facts"]
    engine = result["engine_note"] or "engine check skipped"
    agreement = result["engine_agreement"]
    if agreement == "two-engines":
        cohort = (f"two engines in one cohort "
                  f"({', '.join(dict.fromkeys(r['engine'] for r in result['cohort_engine_records']))})")
    elif result["cohort_engine"]:
        cohort = f"{result['cohort_engine']} ({result['cohort_engine_source']}, {agreement})"
    else:
        cohort = "no engine provenance in the cohort"
    return (f"[pass3-gate] {result['decision']}: pass^3 {result['pass3']}, "
            f"{len(facts['flaky'])} flaky, {len(facts['fail'])} consistent fail, "
            f"{len(facts['incomplete'])} short, {len(facts['blocked'])} engine-blocked "
            f"({result['runs']} manifests) — engine {engine}; cohort {cohort}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Block a release on a flaky pass^3 outcome.")
    ap.add_argument("--runs", default=str(DEFAULT_RUNS))
    ap.add_argument("--reps", type=int, default=REPS_EXPECTED)
    ap.add_argument("--receipt", default=None, help="write the decision as JSON here")
    ap.add_argument("--engine", default=str(DEFAULT_ENGINE),
                    help="engine config to name in the receipt (default ~/.ephe/engine.json)")
    ap.add_argument("--no-engine-check", action="store_true",
                    help="judge flakiness only; do not read or name an engine")
    ap.add_argument("--allow-engine-mismatch", metavar="REASON", default=None,
                    help="name the configured engine on a cohort measured on another one, with "
                         "the reason recorded (the number then carries an engine it did not "
                         "come from)")
    ap.add_argument("--task", default="W3-59")
    args = ap.parse_args(argv)

    if args.no_engine_check:
        engine_cfg: dict | None = None
        engine_source = "skipped (--no-engine-check)"
    else:
        engine_path = Path(args.engine)
        engine_source = str(engine_path)
        home = str(Path.home())
        if engine_source.startswith(home):  # the tree carries ~, never an absolute home path
            engine_source = "~" + engine_source[len(home):]
        try:
            loaded = json.loads(engine_path.read_text(encoding="utf-8"))
            engine_cfg = loaded if isinstance(loaded, dict) else {}
        except (OSError, json.JSONDecodeError):
            engine_cfg = {}

    result = gate(Path(args.runs), reps=args.reps, engine_cfg=engine_cfg,
                  engine_source=engine_source,
                  allow_engine_mismatch=args.allow_engine_mismatch)
    print(_render(result))
    for reason in result["reasons"]:
        print(f"[pass3-gate] {reason}", file=sys.stderr)
    if args.receipt:
        receipt = build_receipt(result, engine_cfg, engine_source, task=args.task)
        Path(args.receipt).write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                                      encoding="utf-8")
        print(f"[pass3-gate] receipt -> {args.receipt}")
    return result["exit"]


if __name__ == "__main__":
    sys.exit(main())
