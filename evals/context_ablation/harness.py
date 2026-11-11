"""Context ablation — what a repository's AGENTS.md does to correctness, duration and tokens.

One task runs twice in two copies of the same fixture repository. The ``with_agents``
arm keeps the repository's rule file at the workspace root, where the product's context
montage reads it; the ``no_agents`` arm starts from the same tree with that one file
removed. Both arms are verified by the task's own test command against tests restored
from the fixture, so an agent that rewrites its checks gains nothing. Duration and
tokens are recorded next to the verdict.

    python evals/context_ablation/harness.py                     # dry run, no engine
    python evals/context_ablation/harness.py --real --model TAG    # engine turns
    python evals/context_ablation/harness.py --compare a.json b.json

The default is the dry run. A stub applies the fixture solution a task declares, and
the verifier then really runs; that exercises the arms, the verifier and the JSON
without a network or a model, and the file marks itself ``"evidence": "stub"``. Real
runs take ``--real`` and the engine the user configured with ``ephe configure``: the
run preflights ``ephe run --dry-run`` first, so a missing engine stops the ablation
before a turn is spent.

See ``README.md`` for the fields, the paired comparison, and what a number from either
mode can support.
"""
from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for _extra in (str(REPO), str(HERE.parent)):
    if _extra not in sys.path:
        sys.path.insert(0, _extra)

from noise_floor import mcnemar_exact  # noqa: E402  (the exact sign test, one copy)

from core.usage import estimate_tokens, tokenizer_backend  # noqa: E402
from core.workspace_rules import RULES_NAME  # noqa: E402

SCHEMA = 1
ARMS = ("with_agents", "no_agents")
DEFAULT_TASKS = HERE / "tasks.jsonl"
STUB_ANSWER = "stub: fixture solution applied"
ALPHA = 0.05
POWER = 0.80
#: One-sided quantile TOST spends on each side of the margin, and the power target.
Z_ONE_SIDED = NormalDist().inv_cdf(1 - ALPHA)
Z_POWER = NormalDist().inv_cdf(POWER)


@dataclass(frozen=True)
class Task:
    id: str
    prompt: str
    fixture: Path
    verify: tuple[str, ...]
    guard: tuple[str, ...] = ("tests",)
    stub: dict[str, str] = field(default_factory=dict)

    @property
    def repo(self) -> Path:
        return self.fixture / "repo"

    @property
    def solution(self) -> Path:
        return self.fixture / "solution"


def load_tasks(path: Path | str) -> list[Task]:
    """Read ``tasks.jsonl``; a row that cannot run here stops the ablation with its line."""
    source = Path(path)
    tasks: list[Task] = []
    seen: set[str] = set()
    for number, raw in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"{source}:{number}: not JSON ({exc})") from exc
        task = Task(
            id=str(row.get("id") or ""),
            prompt=str(row.get("prompt") or ""),
            fixture=HERE / "fixtures" / str(row.get("fixture") or ""),
            verify=tuple(row.get("verify") or ()),
            guard=tuple(row.get("guard") or ("tests",)),
            stub=dict(row.get("stub") or {}),
        )
        where = f"{source}:{number}"
        if not task.id or not task.prompt:
            raise SystemExit(f"{where}: a task needs an id and a prompt")
        if task.id in seen:
            raise SystemExit(f"{where}: duplicate task id {task.id!r}")
        if not task.repo.is_dir():
            raise SystemExit(f"{where}: no fixture repository at {task.repo}")
        if not task.verify:
            raise SystemExit(f"{where}: a task needs a verify command")
        missing = [arm for arm in ARMS if task.stub.get(arm) not in ("pass", "fail")]
        if missing:
            raise SystemExit(f"{where}: stub outcome missing for {', '.join(missing)}")
        seen.add(task.id)
        tasks.append(task)
    if not tasks:
        raise SystemExit(f"{source}: no tasks")
    return tasks


def prepare_arm(task: Task, arm: str, root: Path) -> Path:
    """A fresh copy of the fixture for one arm; only the no-agents copy loses the file."""
    workspace = Path(root) / task.id / arm
    if workspace.exists():
        shutil.rmtree(workspace)
    shutil.copytree(task.repo, workspace,
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    if arm == "no_agents":
        (workspace / RULES_NAME).unlink(missing_ok=True)
    return workspace


def context_text(workspace: Path) -> str:
    """What the context montage would read out of this workspace (root rule file only)."""
    rules = workspace / RULES_NAME
    return rules.read_text(encoding="utf-8") if rules.is_file() else ""


def context_block(workspace: Path) -> dict:
    """The arm's context as a record, measured before the turn can change the tree."""
    text = context_text(workspace)
    return {
        "files": [RULES_NAME] if (workspace / RULES_NAME).is_file() else [],
        "chars": len(text),
        "tokens": estimate_tokens(text) if text else 0,
    }


def restore_guards(task: Task, workspace: Path) -> list[str]:
    """Put the fixture's verifier paths back, so the checks that score the arm are ours."""
    restored = []
    for rel in task.guard:
        source = task.repo / rel
        if not source.exists():
            continue
        target = workspace / rel
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        if source.is_dir():
            shutil.copytree(source, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        restored.append(rel)
    return restored


def verify_argv(task: Task) -> list[str]:
    return [part.replace("{python}", sys.executable) for part in task.verify]


def verify_command(task: Task) -> str:
    return " ".join(shlex.quote(part) for part in verify_argv(task))


def run_verify(task: Task, workspace: Path, timeout: int = 300) -> dict:
    started = time.perf_counter()
    try:
        done = subprocess.run(verify_argv(task), cwd=str(workspace), text=True,
                              capture_output=True, timeout=timeout, check=False)
        code, timed_out = done.returncode, False
        output = (done.stdout or "") + (done.stderr or "")
    except subprocess.TimeoutExpired:
        code, timed_out, output = None, True, f"verifier exceeded {timeout}s"
    return {
        "passed": code == 0,
        "exit_code": code,
        "timed_out": timed_out,
        "duration_s": round(time.perf_counter() - started, 3),
        "tail": output[-600:],
    }


def apply_solution(task: Task, workspace: Path) -> None:
    if task.solution.is_dir():
        shutil.copytree(task.solution, workspace, dirs_exist_ok=True)


def _cell(context: dict, verify: dict, *, duration: float, source: str,
          tokens: dict, record: str | None, record_solved: bool | None,
          notes: list[str]) -> dict:
    return {
        "context": context,
        "passed": bool(verify["passed"]),
        "exit_code": verify["exit_code"],
        "timed_out": bool(verify.get("timed_out")),
        "duration_s": round(duration, 3),
        "duration_source": source,
        "tokens": tokens,
        "record": record,
        "record_solved": record_solved,
        "verify_tail": verify["tail"] if not verify["passed"] else "",
        "notes": notes,
    }


def _token_block(prompt: int, context: int, output: int, source: str) -> dict:
    return {"prompt": prompt, "context": context, "output": output,
            "total": prompt + context + output, "source": source,
            "tokenizer": tokenizer_backend() if source == "estimated" else None}


def stub_arm(task: Task, arm: str, workspace: Path, timeout: int, context: dict) -> dict:
    """Play one arm without an engine: the task's fixture decides whether the fix lands."""
    notes = []
    if task.stub[arm] == "pass":
        apply_solution(task, workspace)
        notes.append("stub applied the fixture solution")
    else:
        notes.append("stub skipped the fixture solution, so the verifier has to fail")
    restore_guards(task, workspace)
    started = time.perf_counter()
    verify = run_verify(task, workspace, timeout)
    tokens = _token_block(estimate_tokens(task.prompt), context["tokens"],
                          estimate_tokens(STUB_ANSWER), "estimated")
    return _cell(context, verify, duration=time.perf_counter() - started,
                 source="verifier", tokens=tokens, record=None, record_solved=None, notes=notes)


def _read_record(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _record_tokens(record: dict | None, context_tokens: int) -> dict | None:
    """The record's own token block. ``context`` stays a label for the rule-file size.

    A measured prompt count already contains those tokens, so the field is descriptive
    here; ``total`` is the record's total and is not recomputed from the parts.
    """
    try:
        raw = record["effort"]["tokens"]
        return {"prompt": int(raw["in"]), "output": int(raw["out"]),
                "total": int(raw["total"]), "source": str(raw["source"]),
                "tokenizer": raw.get("tokenizer"), "context": context_tokens}
    except (KeyError, TypeError, ValueError):
        return None


def _git_ready(workspace: Path) -> None:
    """`ephe run` records its change set against a git worktree; give the arm one."""
    env = dict(os.environ)
    env["HOME"] = str(workspace.parent)
    for args in (["init", "-q"], ["add", "-A"],
                 ["-c", "user.name=context-ablation", "-c", "user.email=ablation@invalid",
                  "commit", "-q", "-m", "fixture"]):
        subprocess.run(["git", *args], cwd=str(workspace), env=env, check=True,
                       capture_output=True)


def real_arm(task: Task, arm: str, workspace: Path, result_path: Path, *, context: dict,
             model: str | None, timeout: int, verify_timeout: int) -> dict:
    """One engine turn through `ephe run`, then our own verifier on restored tests."""
    record_path = result_path.parent / "records" / task.id / f"{arm}.json"
    record_path.parent.mkdir(parents=True, exist_ok=True)
    _git_ready(workspace)
    argv = [sys.executable, str(REPO / "ephe_cli.py"), "run", task.prompt,
            "--workspace", str(workspace), "--verify", verify_command(task),
            "--json", "--no-stream", "--run-record", str(record_path)]
    if model:
        argv += ["--model", model]
    env = dict(os.environ)
    env["EPHE_WORKSPACE"] = str(workspace)
    env.setdefault("EPHE_WORKSPACES_DIR", str(result_path.parent / "workspaces"))
    notes: list[str] = []
    started = time.perf_counter()
    try:
        turn = subprocess.run(argv, cwd=str(workspace), env=env, text=True,
                              capture_output=True, timeout=timeout, check=False)
        turn_duration = time.perf_counter() - started
        if turn.returncode != 0:
            notes.append(f"ephe run exited {turn.returncode}: {turn.stderr.strip()[-300:]}")
    except subprocess.TimeoutExpired:
        turn_duration = time.perf_counter() - started
        notes.append(f"engine turn exceeded {timeout}s")
    except OSError as exc:
        turn_duration = time.perf_counter() - started
        notes.append(f"ephe run could not start: {exc}")
    record = _read_record(record_path)
    record_solved = None
    if record is not None:
        record_solved = record.get("outcome", {}).get("solved")
        wall = record.get("effort", {}).get("wall_seconds")
        if isinstance(wall, (int, float)):
            turn_duration = float(wall)
    restore_guards(task, workspace)
    verify = run_verify(task, workspace, verify_timeout)
    if record_solved is not None and bool(record_solved) != bool(verify["passed"]):
        notes.append("the record's verifier and the restored-test verifier disagree")
    tokens = _record_tokens(record, context["tokens"])
    if tokens is None:
        tokens = _token_block(estimate_tokens(task.prompt), context["tokens"], 0, "estimated")
    return _cell(context, verify, duration=turn_duration,
                 source="record" if record is not None else "measured",
                 tokens=tokens, record=str(record_path) if record is not None else None,
                 record_solved=record_solved, notes=notes)


def preflight(result_path: Path, model: str | None, timeout: int = 120) -> str | None:
    """Resolve the engine with `ephe run --dry-run`, which spends no turn."""
    workspace = result_path.parent / "preflight"
    workspace.mkdir(parents=True, exist_ok=True)
    argv = [sys.executable, str(REPO / "ephe_cli.py"), "run", "context ablation preflight",
            "--dry-run", "--workspace", str(workspace)]
    if model:
        argv += ["--model", model]
    done = subprocess.run(argv, cwd=str(REPO), text=True, capture_output=True,
                          timeout=timeout, check=False)
    if done.returncode == 0:
        return None
    return ((done.stdout or "") + (done.stderr or "")).strip() or f"ephe run exited {done.returncode}"


def summarize(rows: list[dict]) -> dict:
    n = len(rows)
    arms: dict[str, dict] = {}
    for arm in ARMS:
        cells = [row["arms"][arm] for row in rows]
        solved = sum(cell["passed"] for cell in cells)
        arms[arm] = {
            "passed": solved,
            "rate": round(solved / n, 4) if n else 0.0,
            "duration_s": round(sum(cell["duration_s"] for cell in cells), 3),
            "tokens_total": sum(cell["tokens"]["total"] for cell in cells),
            "tokens_context": sum(cell["tokens"]["context"] for cell in cells),
        }
    return {
        "n_tasks": n,
        "arms": arms,
        "delta": {
            "rate_pp": round(100 * (arms["with_agents"]["rate"] - arms["no_agents"]["rate"]), 2),
            "passed": arms["with_agents"]["passed"] - arms["no_agents"]["passed"],
            "duration_s": round(arms["with_agents"]["duration_s"]
                                - arms["no_agents"]["duration_s"], 3),
            "tokens_total": arms["with_agents"]["tokens_total"]
            - arms["no_agents"]["tokens_total"],
        },
    }


def run_ablation(tasks: list[Task], out: Path, workdir: Path, *, real: bool,
                 model: str | None, timeout: int, verify_timeout: int) -> dict:
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    if real:
        failure = preflight(out, model)
        if failure is not None:
            raise SystemExit(f"[context-ablation] no engine for a real run:\n{failure}")
    started_at = _iso_now()
    rows: list[dict] = []
    engine = None
    for task in tasks:
        row = {"id": task.id, "prompt": task.prompt, "fixture": str(task.fixture),
               "verify": verify_argv(task), "guard": list(task.guard), "arms": {}}
        for arm in ARMS:
            workspace = prepare_arm(task, arm, workdir)
            context = context_block(workspace)
            if real:
                row["arms"][arm] = real_arm(task, arm, workspace, out, context=context,
                                            model=model, timeout=timeout,
                                            verify_timeout=verify_timeout)
                record = _read_record(Path(row["arms"][arm]["record"])) if row["arms"][arm]["record"] else None
                if engine is None and record is not None:
                    engine = record.get("identity", {}).get("engine")
            else:
                row["arms"][arm] = stub_arm(task, arm, workspace, verify_timeout, context)
        rows.append(row)
    document = {
        "schema": SCHEMA,
        "mode": "real" if real else "dry-run",
        "evidence": "engine" if real else "stub",
        "started_at": started_at,
        "finished_at": _iso_now(),
        "counter": tokenizer_backend(),
        "engine": engine,
        "arms": list(ARMS),
        "tasks": rows,
        "summary": summarize(rows),
    }
    out.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    return document


def _iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_result(path: Path | str) -> dict:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("schema") != SCHEMA:
        raise SystemExit(f"{path}: schema {document.get('schema')!r}, this harness reads {SCHEMA}")
    return document


def print_report(document: dict, out: Path) -> None:
    rows = document["tasks"]
    print(f"{'task':<26}{'arm':<14}{'solved':<8}{'exit':<6}{'seconds':>9}{'tokens':>9}{'context':>9}")
    for row in rows:
        for arm in ARMS:
            cell = row["arms"][arm]
            print(f"{row['id']:<26}{arm:<14}{'pass' if cell['passed'] else 'fail':<8}"
                  f"{str(cell['exit_code']):<6}{cell['duration_s']:>9.2f}"
                  f"{cell['tokens']['total']:>9}{cell['context']['tokens']:>9}")
    summary = document["summary"]
    a, b = summary["arms"]["with_agents"], summary["arms"]["no_agents"]
    print()
    print(f"tasks: {summary['n_tasks']}  "
          f"with_agents {a['passed']}/{summary['n_tasks']} vs "
          f"no_agents {b['passed']}/{summary['n_tasks']} solved "
          f"({summary['delta']['rate_pp']:+.1f} pp)")
    print(f"tokens: {a['tokens_total']} vs {b['tokens_total']} "
          f"(context {a['tokens_context']} vs {b['tokens_context']})   "
          f"seconds: {a['duration_s']:.2f} vs {b['duration_s']:.2f}")
    if document["mode"] == "dry-run":
        print("mode: dry-run — the arms were played by fixture stubs; the verifier ran for real.")
        print("      These numbers test the harness. A context claim needs --real and an engine.")
    else:
        print(f"mode: real — engine {json.dumps(document.get('engine'))}, "
              f"counter {document.get('counter')}")
    print(f"result: {out}")


def _paired_diffs(doc_a: dict, doc_b: dict, arm: str) -> tuple[list[int], list[str]]:
    a = {row["id"]: row for row in doc_a["tasks"]}
    b = {row["id"]: row for row in doc_b["tasks"]}
    common = [task_id for task_id in a if task_id in b]
    if len(common) < 2:
        raise SystemExit(f"the two results share {len(common)} task(s); a paired test needs 2")
    diffs = []
    for task_id in common:
        pa = bool(a[task_id]["arms"][arm]["passed"])
        pb = bool(b[task_id]["arms"][arm]["passed"])
        diffs.append(int(pa) - int(pb))
    return diffs, common


def discordance_bound(n: int) -> float:
    """One-sided 95% upper bound on the discordance rate when no pair disagrees.

    ``|p_a - p_b|`` cannot exceed the share of pairs that disagree, so this bound also
    bounds the difference. Zero variance in a small sample is not a zero interval: ten
    concordant pairs leave a 26 pp window, which is why a stub pair is never called
    equivalent on its own.
    """
    return 1 - 0.05 ** (1 / n)


def tost(diffs: list[int], margin: float) -> dict:
    """Two one-sided tests against a margin, normal approximation on the paired differences."""
    n = len(diffs)
    mean = sum(diffs) / n
    if n > 1:
        var = sum((d - mean) ** 2 for d in diffs) / (n - 1)
    else:
        var = 0.0
    se = (var / n) ** 0.5
    if se == 0:
        half = discordance_bound(n)
        low, high = max(-1.0, mean - half), min(1.0, mean + half)
        inside = low > -margin and high < margin
        return {"mean": mean, "se": 0.0, "p": 0.0 if inside else 1.0,
                "ci90": [low, high], "bound": half}
    p_lower = 1 - NormalDist().cdf((mean + margin) / se)
    p_upper = 1 - NormalDist().cdf((margin - mean) / se)
    return {"mean": mean, "se": se, "p": max(p_lower, p_upper),
            "ci90": [mean - Z_ONE_SIDED * se, mean + Z_ONE_SIDED * se]}


def compare(path_a: Path | str, path_b: Path | str, arm: str, margin: float) -> str:
    """Paired read of two results: sign test for a difference, TOST for equivalence."""
    doc_a, doc_b = read_result(path_a), read_result(path_b)
    if arm not in doc_a.get("arms", []) or arm not in doc_b.get("arms", []):
        raise SystemExit(f"arm {arm!r} is not in both results")
    diffs, common = _paired_diffs(doc_a, doc_b, arm)
    n = len(common)
    lost = sum(1 for d in diffs if d > 0)
    gained = sum(1 for d in diffs if d < 0)
    sign_p = mcnemar_exact(lost, gained)
    test = tost(diffs, margin)
    rate_a = sum(1 for row in doc_a["tasks"] if row["id"] in common
                 and row["arms"][arm]["passed"]) / n
    rate_b = sum(1 for row in doc_b["tasks"] if row["id"] in common
                 and row["arms"][arm]["passed"]) / n
    if sign_p < ALPHA:
        verdict = f"a difference is detectable (exact sign test p={sign_p:.4f})"
    elif test["p"] < ALPHA:
        verdict = (f"equivalent within +/-{margin * 100:.1f} pp "
                   f"(TOST p={test['p']:.4f}, 90% CI "
                   f"[{test['ci90'][0] * 100:+.1f}, {test['ci90'][1] * 100:+.1f}] pp)")
    else:
        worst = ((Z_ONE_SIDED + Z_POWER) / margin) ** 2
        verdict = (f"inconclusive: TOST p={test['p']:.4f} at +/-{margin * 100:.1f} pp; "
                   f"n={n} pairs cannot place the difference inside that margin "
                   f"(about {worst:.0f} pairs are needed at 80% power for a binary outcome)")
    evidence = "engine" if doc_a.get("evidence") == doc_b.get("evidence") == "engine" else "stub"
    lines = [
        f"paired tasks: {n}  arm: {arm}  evidence: {evidence}",
        f"pass rate: {rate_a:.4f} vs {rate_b:.4f} ({test['mean'] * 100:+.1f} pp mean difference)",
        f"discordant: {lost} passing only in A, {gained} passing only in B, "
        f"{n - lost - gained} unchanged",
        f"exact sign test: p={sign_p:.4f}",
        f"TOST at +/-{margin * 100:.1f} pp: p={test['p']:.4f}, "
        f"90% CI [{test['ci90'][0] * 100:+.1f}, {test['ci90'][1] * 100:+.1f}] pp"
        + (" (every pair agrees; the window is the exact discordance bound)"
           if test["se"] == 0 else ""),
        f"verdict: {verdict}",
    ]
    if evidence == "stub":
        lines.append("note: at least one side is a dry run; its stub outcomes fix the rates.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tasks", default=str(DEFAULT_TASKS), help="task list (JSONL)")
    parser.add_argument("--out", default=None, help="result JSON path")
    parser.add_argument("--workdir", default=None, help="arm workspaces (default: beside the result)")
    parser.add_argument("--dry-run", action="store_true",
                        help="the default: fixture stubs play the arms and no engine is asked")
    parser.add_argument("--real", action="store_true",
                        help="run engine turns; needs the engine from `ephe configure`")
    parser.add_argument("--model", default=None, help="model tag passed through to ephe run")
    parser.add_argument("--timeout", type=int, default=900, help="seconds per engine turn")
    parser.add_argument("--verify-timeout", type=int, default=300, help="seconds per verifier run")
    parser.add_argument("--compare", nargs=2, metavar=("A", "B"),
                        help="paired read of two result files")
    parser.add_argument("--arm", choices=ARMS, default=ARMS[0], help="arm to pair in --compare")
    parser.add_argument("--margin", type=float, default=0.10,
                        help="equivalence margin as a proportion (default 0.10)")
    args = parser.parse_args(argv)

    if args.compare:
        print(compare(args.compare[0], args.compare[1], args.arm, args.margin))
        return 0
    if args.dry_run and args.real:
        raise SystemExit("--dry-run and --real are exclusive; the dry run is the default")

    stamp = _iso_now().replace(":", "").replace("-", "")
    out = Path(args.out) if args.out else (
        Path(tempfile.gettempdir()) / "ephe-context-ablation" / stamp / "result.json")
    workdir = Path(args.workdir) if args.workdir else out.parent / "work"
    tasks = load_tasks(args.tasks)
    document = run_ablation(tasks, out, workdir, real=args.real, model=args.model,
                            timeout=args.timeout, verify_timeout=args.verify_timeout)
    print_report(document, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
