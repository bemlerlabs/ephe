#!/usr/bin/env python3
"""Runner timings, read from the Actions API and reduced to the numbers a queue decision needs.

`docs/CI_HYBRID_CAPACITY_2026-10-11.md` section 1.5 lists figures no run in this repository has ever
printed: the serial timing segment's p90 while several listeners work at once, a cold install inside a
leg, the Playwright lane's first wall, the runner cost of the two Wave I legs. `GET
/repos/{owner}/{repo}/actions/runs/{run_id}/jobs` already answers all of it -- one call per run, and
each job entry carries `started_at`, `completed_at`, `runner_name` and a `steps` array with its own
timings. The unit that matters is the step: measured on run 38095759973, `pytest-linux (py3.12)` has an
81 s job wall whose `Run tracked pytest suite` step is 47 s, and the difference is checkout, install and
`Set up job`, which belong to no timing budget.

Two things the instrument treats as findings rather than blanks:

* Absence. A leg named in `required_legs` that appears in none of the runs read is reported, because
  fifteen hours of green runs with zero collected tests looked exactly like this from the outside.
* Overlap. The number of self-hosted jobs running at the same instant is what decides whether a fourth
  listener is a gain, so it is computed per run instead of assumed from the listener count.

The p90 is nearest-rank: the value at index `ceil(0.9 * n) - 1` of the sorted sample. A sample of one
therefore reports its own number and never interpolates a leg that did not run.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUDGETS_DEFAULT = ROOT / "scripts" / "timing-budgets.json"
API_ROOT = "https://api.github.com"
#: The steps a timing decision is made of. Everything else in a job is overhead, and overhead belongs
#: in its own column rather than averaged into a gate.
MEASURED_STEPS = (
    "Run tracked pytest suite",
    "Run tracked pytest suite (macOS)",
    "Run timing gates (serial)",
    "Run timing gates (serial, macOS)",
    "Install package (with dev tools)",
    "Move a pull request's install out of the shared interpreter",
)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def seconds_between(start: str | None, end: str | None) -> int | None:
    first, last = parse_time(start), parse_time(end)
    if first is None or last is None:
        return None
    return int((last - first).total_seconds())


def nearest_rank(sample: list[int], rank: float) -> int | None:
    if not sample:
        return None
    ordered = sorted(sample)
    return ordered[max(0, math.ceil(rank * len(ordered)) - 1)]


def gh_token() -> str:
    for name in ("ACTIONS_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(name):
            return os.environ[name]
    done = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=False)
    return done.stdout.strip() if done.returncode == 0 else ""


class ApiUnavailable(RuntimeError):
    """The Actions API did not answer, after the retries."""


def api_get(path: str, token: str, attempts: int = 3) -> dict:
    """One read of the Actions API, retried while the answer is transient.

    A 502 from the API is not a statement about our timings, and it used to end
    the whole report before a single file was written: the nightly went red, the
    artifact step found nothing, and the reason lived only in the log.
    """
    request = urllib.request.Request(
        f"{API_ROOT}/{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code not in {429, 500, 502, 503, 504}:
                raise ApiUnavailable(f"HTTP {exc.code} from {path}") from exc
            last = exc
        except urllib.error.URLError as exc:
            last = exc
        if attempt + 1 < attempts:
            time.sleep(2 * (attempt + 1))
    raise ApiUnavailable(f"the Actions API stayed unreachable for {path}: {last}")


def shape(job: dict, run: dict) -> dict:
    """One API job entry, kept as the fields the report reads.

    A step skipped by its own `if:` arrives as `status: completed` with `conclusion: skipped` and
    equal start and completion stamps, so its arithmetic is 0 s. Reading that as a measurement would
    hand a budget a sample no run ever produced, so only steps that actually ran are timed.
    """
    return {
        "run_id": run.get("id", job.get("run_id", 0)),
        "head_sha": run.get("head_sha", job.get("head_sha", "")),
        "created_at": run.get("created_at", ""),
        "event": run.get("event", job.get("event", "push")),
        "runner": job.get("runner_name") or "",
        "labels": job.get("labels", []),
        "job": job["name"],
        "conclusion": job.get("conclusion"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "job_seconds": seconds_between(job.get("started_at"), job.get("completed_at")),
        "steps": {
            step["name"]: seconds_between(step.get("started_at"), step.get("completed_at"))
            for step in job.get("steps", [])
            if step["name"] in MEASURED_STEPS
            and step.get("status") == "completed"
            and step.get("conclusion") not in (None, "skipped")
        },
    }


def collect_runs(workflow: str, events: tuple[str, ...], limit: int, token: str) -> list[dict]:
    """The last `limit` completed push runs of one workflow, flattened to job records."""
    repository = os.environ["REPOSITORY"]
    out: list[dict] = []
    runs_read = 0
    for event in events:
        page = api_get(f"repos/{repository}/actions/runs?per_page=100&event={event}", token)
        for run in page.get("workflow_runs", []):
            if runs_read >= limit:
                return out
            if run.get("name") != workflow or run.get("status") != "completed":
                continue
            if run.get("run_attempt", 1) != 1:
                # A rerun measures the rerun. The queue's history is about the commit that shipped.
                continue
            runs_read += 1
            jobs = api_get(f"repos/{repository}/actions/runs/{run['id']}/jobs?per_page=100", token)
            out.extend(shape(job, run) for job in jobs.get("jobs", []))
    return out


def load_fixture(path: Path) -> list[dict]:
    """A saved API payload, so the instrument runs offline in a test and against a plant."""
    raw = json.loads(path.read_text(encoding="utf-8"))
    runs = raw.get("runs")
    if runs:
        return [shape(job, run) for run in runs for job in run.get("jobs", [])]
    return [shape(job, {}) for job in raw.get("jobs", [])]


def ran(job: dict) -> bool:
    """Whether this job actually executed work.

    A cancelled job is the shape of the queue, not the shape of a gate: `cancel-in-progress: true`
    leaves it with no `runner_name` and a start-to-completion span that is the queue wait plus a
    teardown. Counting those intervals reported seven jobs in the air at once on a box with three
    listeners, and counting their steps would put a cancellation in a p90.
    """
    return job["conclusion"] in ("success", "failure") and bool(job["runner"])


def distributions(jobs: list[dict]) -> dict[str, dict]:
    samples: dict[str, list[int]] = defaultdict(list)
    for job in jobs:
        if not ran(job):
            continue
        for step, seconds in job["steps"].items():
            if seconds is not None:
                samples[f"{job['job']} :: {step}"].append(seconds)
    return {
        key: {
            "n": len(values),
            "min": min(values),
            "median": round(statistics.median(values), 1),
            "p90": nearest_rank(values, 0.90),
            "p95": nearest_rank(values, 0.95),
            "max": max(values),
        }
        for key, values in sorted(samples.items())
    }


def max_overlap(intervals: list[tuple[datetime, datetime]]) -> int:
    events: list[tuple[datetime, int]] = []
    for start, end in intervals:
        events.append((start, 1))
        events.append((end, -1))
    # A job ending at the same second another starts is not concurrency, so closes sort after opens.
    events.sort(key=lambda item: (item[0], -item[1]))
    live = best = 0
    for _, delta in events:
        live += delta
        best = max(best, live)
    return best


def overlap_by_host(jobs: list[dict]) -> dict[str, dict]:
    """Concurrency per host per run, because three listeners on one box are not three hosts.

    The group key is the routing label, never the runner name: `lab-runner`, `lab-runner-2` and
    `lab-runner-3` are three listeners on one DGX Spark, and grouping by name reports max overlap 1
    on a machine that is measurably running three jobs at once. The fourth-listener question in
    section 1.3 is about that box.
    """
    groups: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for job in jobs:
        host = job["labels"][0] if job["labels"] else job["runner"]
        if host and ran(job):
            groups[(job["run_id"], host)].append(job)
    out: dict[str, dict] = {}
    for (run_id, host), records in sorted(groups.items()):
        intervals = []
        for job in records:
            start = parse_time(job.get("started_at"))
            wall = job["job_seconds"]
            if start is None or wall is None:
                continue
            intervals.append((start, start + timedelta(seconds=wall)))
        out[f"run {run_id} on {host}"] = {
            "jobs": len(records),
            "runners": sorted({job["runner"] for job in records if job["runner"]}),
            "max_overlap": max_overlap(intervals),
            "runner_seconds": sum(job["job_seconds"] or 0 for job in records),
        }
    return out


def check_budgets(report: dict, data: dict) -> list[str]:
    failures = []
    samples = report["distributions"]
    for entry in data.get("entries", []):
        key = entry["measured_as"]
        ceiling = entry["budget_seconds"]
        sample = samples.get(key)
        if sample is None:
            failures.append(f"{key}: a {ceiling} s budget is declared and no run measured it")
            continue
        if sample["p90"] is not None and sample["p90"] > ceiling:
            failures.append(
                f"{key}: p90 {sample['p90']} s over its {ceiling} s budget at n={sample['n']}"
            )
    present = set(report["legs_present"])
    for leg in data.get("required_legs", []):
        if leg not in present:
            failures.append(f"{leg}: required leg absent from every run read")
    floor = data.get("minimum_runs", 1)
    if report["runs"] < floor:
        failures.append(
            f"only {report['runs']} completed run(s) of {report['workflow']} read, "
            f"{floor} is the minimum for a distribution to mean anything"
        )
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workflow", default="Tests")
    parser.add_argument("--events", default="push", help="comma separated")
    parser.add_argument("--runs", type=int, default=10, help="completed runs to read")
    parser.add_argument("--repository", default=os.environ.get("REPOSITORY", ""))
    parser.add_argument("--fixture", type=Path, help="a saved API payload, for offline runs")
    parser.add_argument("--budgets", type=Path, default=BUDGETS_DEFAULT)
    parser.add_argument("--check", action="store_true", help="exit 1 on a breached budget or absent leg")
    parser.add_argument("--json", type=Path, help="write the report here")
    args = parser.parse_args(argv)

    if args.repository:
        os.environ["REPOSITORY"] = args.repository
    elif "REPOSITORY" not in os.environ:
        parser.error("name the repository with --repository or REPOSITORY")

    if args.fixture:
        jobs = load_fixture(args.fixture)
    else:
        token = gh_token()
        if not token:
            print("timing: no token in the environment and `gh auth token` answered nothing")
            return 2
        try:
            jobs = collect_runs(
                args.workflow, tuple(e.strip() for e in args.events.split(",")), args.runs, token
            )
        except ApiUnavailable as exc:
            # The artifact records the reason: a run whose file is missing says
            # less than one that says why it could not be written.
            print(f"timing: {exc}")
            if args.json:
                args.json.parent.mkdir(parents=True, exist_ok=True)
                args.json.write_text(
                    json.dumps(
                        {"workflow": args.workflow, "source_error": str(exc)},
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )
            return 2

    if not jobs:
        print(f"timing: no completed `{args.workflow}` runs in the pages read")
        return 1 if args.check else 0

    report = {
        "workflow": args.workflow,
        "runs": len({job["run_id"] for job in jobs}),
        "jobs": len(jobs),
        "jobs_ran": sum(1 for job in jobs if ran(job)),
        "jobs_cancelled": sum(1 for job in jobs if job["conclusion"] == "cancelled"),
        "jobs_skipped": sum(1 for job in jobs if job["conclusion"] == "skipped"),
        "distributions": distributions(jobs),
        "overlap": overlap_by_host(jobs),
        "legs_present": sorted({job["job"] for job in jobs}),
    }

    print(f"timing: {report['runs']} run(s), {report['jobs']} job(s), workflow {args.workflow}")
    print(
        f"  {report['jobs_ran']} ran, {report['jobs_cancelled']} cancelled, "
        f"{report['jobs_skipped']} skipped -- only the ones that ran are sampled"
    )
    for key, sample in report["distributions"].items():
        print(
            f"  {key}: n={sample['n']} median={sample['median']}s p90={sample['p90']}s "
            f"p95={sample['p95']}s max={sample['max']}s"
        )
    for key, facts in report["overlap"].items():
        print(
            f"  {key}: {facts['jobs']} job(s) on {', '.join(facts['runners']) or 'unknown runner'}, "
            f"max overlap {facts['max_overlap']}, runner-seconds {facts['runner_seconds']}"
        )
    per_host: dict[str, list[int]] = {}
    for key, facts in report["overlap"].items():
        per_host.setdefault(key.split(" on ", 1)[1], []).append(facts["max_overlap"])
    for host, overlaps in sorted(per_host.items()):
        seconds = [
            facts["runner_seconds"] for key, facts in report["overlap"].items()
            if key.endswith(f" on {host}")
        ]
        print(
            f"  {host}: max overlap {max(overlaps)} of {len(overlaps)} run(s), "
            f"median runner-seconds {round(statistics.median(seconds), 1)}"
        )
    totals = [facts["runner_seconds"] for facts in report["overlap"].values()]
    if totals:
        print(f"timing: {sum(totals)} runner-seconds across the runs read")

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"timing: wrote {args.json}")

    if not args.check:
        return 0
    if not args.budgets.exists():
        print(f"timing: --check has no budget file at {args.budgets}")
        return 1
    failures = check_budgets(report, json.loads(args.budgets.read_text(encoding="utf-8")))
    for failure in failures:
        print(f"timing: FAIL {failure}")
    if failures:
        return 1
    print("timing: every declared budget holds at its p90, and every required leg appeared")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
