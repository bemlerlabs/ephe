"""The timing report, measured against a saved API payload rather than against the live queue.

`scripts/ci_timing_report.py` reads the Actions API, and a unit test cannot make that call. The
payloads below are the shape the API returns for `runs/{id}/jobs`, and they carry the two defects this
instrument exists to catch: a step that only ever ran as `skipped` arrives with equal start and
completion stamps, which reads as 0 s unless the status is checked, and a leg that stopped existing
leaves no absence in any log.

The p90 is nearest-rank on purpose, so a distribution can be asserted from a hand-counted sample:
ten values 1..10 put p90 at 9 and p95 at 10.
"""
from __future__ import annotations

import json
import subprocess
import sys

import yaml
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci_timing_report.py"

SERIAL = "Run timing gates (serial)"
SUITE = "Run tracked pytest suite"
LEG = "pytest-linux (py3.10)"


BASE = datetime(2026, 10, 11, 0, 0, 0, tzinfo=timezone.utc)


def stamp(hour: int, minute: int, second: int) -> str:
    return f"2026-10-11T{hour:02d}:{minute:02d}:{second:02d}Z"


def offset(seconds: int) -> str:
    """A timestamp `seconds` after BASE, so a step longer than a minute stays a valid stamp."""
    return (BASE + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def job(name: str, steps: list[dict[str, Any]], *, runner: str = "lab-runner",
        started: str = stamp(0, 0, 0), completed: str = stamp(0, 1, 0),
        conclusion: str = "success", labels: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "conclusion": conclusion,
        "status": "completed",
        "runner_name": runner,
        # A cancelled job still carries its requested labels; that is what makes the routing table
        # the right group key and the runner name the wrong one.
        "labels": labels or (["lab-runner"] if runner.startswith("lab-runner") else [runner]),
        "started_at": started,
        "completed_at": completed,
        "steps": steps,
    }


def step(name: str, seconds: int, *, at: int = 10, status: str = "completed",
         conclusion: str = "success") -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "started_at": offset(at),
        "completed_at": offset(at + seconds),
    }


def payload(runs: list[dict[str, Any]]) -> str:
    return json.dumps({"runs": runs}, indent=2)


def one_run(jobs: list[dict[str, Any]], run_id: int = 1) -> dict[str, Any]:
    return {"id": run_id, "head_sha": "a" * 40, "created_at": stamp(0, 0, 0), "event": "push",
            "name": "Tests", "status": "completed", "run_attempt": 1, "jobs": jobs}


def budgets(entries: list[dict[str, Any]], required: list[str], minimum: int = 1) -> str:
    return json.dumps({
        "policy": "runner-timing-budget", "version": 1, "instrument": "scripts/ci_timing_report.py",
        "minimum_runs": minimum, "required_legs": required, "entries": entries,
    }, indent=2)


def run_report(tmp_path: Path, fixture: str, budgets_text: str) -> subprocess.CompletedProcess[str]:
    """The report under --check, against a payload and a budget file in a temp directory.

    The committed `scripts/timing-budgets.json` is never the input here: a unit test that read it
    would turn every budget edit into a red test for an unrelated reason.
    """
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(fixture, encoding="utf-8")
    budgets_path = tmp_path / "budgets.json"
    budgets_path.write_text(budgets_text, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--repository", "octo/ephe", "--fixture", str(payload_path),
         "--check", "--budgets", str(budgets_path)],
        text=True, capture_output=True, check=False, cwd=ROOT,
    )


class TestDistribution:
    def test_p90_is_the_nearest_rank_value(self, tmp_path):
        runs = [
            one_run([job(LEG, [step(SUITE, seconds)])], run_id=100 + minute)
            for minute, seconds in enumerate([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        ]
        fixture = payload(runs)
        text = budgets([{"measured_as": f"{LEG} :: {SUITE}", "budget_seconds": 90}], [LEG], minimum=10)
        done = run_report(tmp_path, fixture, text)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "p90=9s" in done.stdout and "p95=10s" in done.stdout, done.stdout

    def test_a_step_that_only_skipped_is_never_reported_as_zero_seconds(self, tmp_path):
        """The pull-request-only install step is skipped on every push.

        Its API record carries equal start and completion stamps, so a report that trusted the
        arithmetic would budget-check a 0 s sample that no run ever produced.
        """
        skipped = step("Move a pull request's install out of the shared interpreter", 0,
                       status="completed", conclusion="skipped")
        fixture = payload([one_run([job(LEG, [skipped, step(SUITE, 40)])])])
        text = budgets(
            [{"measured_as": f"{LEG} :: Run tracked pytest suite", "budget_seconds": 90}],
            [LEG],
        )
        done = run_report(tmp_path, fixture, text)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "Move a pull request" not in done.stdout, done.stdout


class TestBudgetBreaches:
    def test_a_step_over_its_budget_fails_naming_the_leg_and_the_measured_p90(self, tmp_path):
        breaches = [job(LEG, [step(SERIAL, seconds)]) for seconds in (18, 20, 22)]
        fixture = payload([one_run([leg], run_id=100 + index) for index, leg in enumerate(breaches)])
        text = budgets(
            [{"measured_as": f"{LEG} :: {SERIAL}", "budget_seconds": 12}],
            [LEG],
            minimum=3,
        )
        done = run_report(tmp_path, fixture, text)
        assert done.returncode == 1, done.stdout
        assert "p90 22 s over its 12 s budget at n=3" in done.stdout, done.stdout

    def test_a_declared_budget_that_no_run_measured_is_a_failure_of_its_own(self, tmp_path):
        """A renamed step is invisible to a budget check that only looks at samples it found."""
        fixture = payload([one_run([job(LEG, [step(SUITE, 40)])])])
        text = budgets([{"measured_as": f"{LEG} :: {SERIAL}", "budget_seconds": 12}], [LEG])
        done = run_report(tmp_path, fixture, text)
        assert done.returncode == 1, done.stdout
        assert "declared and no run measured it" in done.stdout, done.stdout

    def test_a_missing_required_leg_is_reported_as_absence(self, tmp_path):
        fixture = payload([one_run([
            job(LEG, [step(SUITE, 40)]),
            job("pytest-linux (py3.11)", [step(SUITE, 40)]),
        ]), one_run([
            job(LEG, [step(SUITE, 42)]),
            job("pytest-linux (py3.11)", [step(SUITE, 41)]),
        ], run_id=2)])
        text = budgets(
            [{"measured_as": f"{LEG} :: {SUITE}", "budget_seconds": 90}],
            [LEG, "pytest-linux (py3.11)", "pytest-linux (py3.13)"],
            minimum=2,
        )
        done = run_report(tmp_path, fixture, text)
        assert done.returncode == 1, done.stdout
        assert "pytest-linux (py3.13): required leg absent" in done.stdout, done.stdout

    def test_too_few_runs_is_a_failure_because_a_distribution_of_two_says_nothing(self, tmp_path):
        fixture = payload([one_run([job(LEG, [step(SUITE, 40)])])])
        text = budgets(
            [{"measured_as": f"{LEG} :: {SUITE}", "budget_seconds": 90}], [LEG], minimum=5,
        )
        done = run_report(tmp_path, fixture, text)
        assert done.returncode == 1, done.stdout
        assert "minimum for a distribution" in done.stdout, done.stdout


class TestConcurrencyAccounting:
    def test_three_listeners_on_one_box_count_as_one_host_with_three_slots(self, tmp_path):
        """Grouping by runner *name* would report max overlap 1 and argue for a fourth listener."""
        legs = [
            job(LEG, [step(SUITE, 60)], runner="lab-runner", started=offset(0),
                completed=offset(60)),
            job("pytest-linux (py3.11)", [step(SUITE, 60)], runner="lab-runner-2",
                started=offset(10), completed=offset(70)),
            job("pytest-linux (py3.12)", [step(SUITE, 60)], runner="lab-runner-3",
                started=offset(20), completed=offset(80)),
        ]
        fixture = payload([one_run(legs)])
        done = run_report(tmp_path, fixture, budgets([], [LEG]))
        assert done.returncode == 0, done.stdout + done.stderr
        assert "max overlap 3" in done.stdout, done.stdout
        assert "lab-runner, lab-runner-2, lab-runner-3" in done.stdout, done.stdout

    def test_a_cancelled_job_is_queue_shape_and_not_a_slot(self, tmp_path):
        """Run 38083434368 is the witness: five of its jobs were cancelled with `runner_name: null`
        and a span that covers the queue wait, so counting them reported seven jobs in the air at
        once on a box with three listeners.
        """
        legs = [
            job(LEG, [step(SUITE, 60)], runner="lab-runner", started=offset(0), completed=offset(60)),
            job("pytest-linux (py3.11)", [step(SUITE, 59)], runner="", labels=["lab-runner"],
                started=offset(0), completed=offset(59), conclusion="cancelled"),
            job("pytest-linux (py3.12)", [step(SUITE, 59)], runner="", labels=["lab-runner"],
                started=offset(1), completed=offset(60), conclusion="cancelled"),
        ]
        fixture = payload([one_run(legs)])
        done = run_report(tmp_path, fixture, budgets([], [LEG]))
        assert done.returncode == 0, done.stdout + done.stderr
        assert "max overlap 1" in done.stdout, done.stdout
        assert "2 cancelled" in done.stdout, done.stdout
        assert f"{LEG} :: {SUITE}: n=1" in done.stdout, done.stdout


class TestBudgetFileAgreesWithTheWorkflows:
    """The committed budget names steps and legs that exist in `.github/workflows/`.

    A renamed step is this leg's silent failure: the budget check would report "declared and no run
    measured it" at 02:30, one night after the merge that renamed it. The same keys are checkable
    offline against the YAML, so the commit that renames the step is the one that goes red.
    """

    def setup_method(self):
        self.data = json.loads((ROOT / "scripts" / "timing-budgets.json").read_text(encoding="utf-8"))
        loaded = (ROOT / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        self.tests_yml = yaml.safe_load(loaded)

    def step_names(self) -> set[str]:
        return {
            step["name"]
            for job in self.tests_yml["jobs"].values()
            for step in job.get("steps", [])
            if isinstance(step, dict) and "name" in step
        }

    def job_name_prefixes(self) -> list[str]:
        """The static part of each job display name, with any matrix expression cut off."""
        return [
            job.get("name", "").split("${{", 1)[0].strip()
            for job in self.tests_yml["jobs"].values()
        ]

    def test_the_file_is_a_versioned_ratchet_like_the_other_baselines(self):
        assert self.data["policy"] == "runner-timing-budget"
        assert self.data["version"] == 1
        assert self.data["instrument"] == "scripts/ci_timing_report.py"
        assert self.data["minimum_runs"] >= 2, "a distribution of one is a single sample"

    def test_every_budgeted_step_still_exists_in_the_workflow(self):
        known = self.step_names()
        missing = [
            entry["measured_as"].split(" :: ", 1)[1]
            for entry in self.data["entries"]
            if entry["measured_as"].split(" :: ", 1)[1] not in known
        ]
        assert not missing, f"budgeted steps absent from tests.yml: {sorted(set(missing))}"

    def test_every_required_leg_matches_a_job_name_in_the_workflow(self):
        prefixes = [p for p in self.job_name_prefixes() if p]
        unmatched = [
            leg for leg in self.data["required_legs"]
            if not any(leg.startswith(prefix) or prefix.startswith(leg) for prefix in prefixes)
        ]
        assert not unmatched, f"required legs no workflow declares: {unmatched}"

    def test_a_budget_sits_above_its_own_measured_p90(self):
        """A budget below the number it was written from is a red the moment it lands."""
        for entry in self.data["entries"]:
            assert entry["budget_seconds"] > entry["measured_p90_seconds"], entry["measured_as"]
