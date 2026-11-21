"""The picker's 500 ms ceiling lives in a serial perf lane, not in the parallel suite.

On `v0.1.1` the same assertion read 553.7 ms in Frontend Build and 811.2 ms in Verify
while the picker itself was unchanged: a wall clock read under a ten-worker vitest run
measures the host, so the parallel suite cannot own a ceiling. This contract keeps the
functional open/filter test free of timing, and confines the number to a one-worker lane
that warms up, takes a median and distinguishes an overloaded host from a regression.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app"
PICKER_PERF = ROOT / ".github" / "workflows" / "picker-perf.yml"
TIMING = ROOT / ".github" / "workflows" / "timing.yml"
FUNCTIONAL = APP / "src" / "components" / "model" / "ModelPicker.test.tsx"
PERF = APP / "src" / "components" / "model" / "ModelPicker.perf.test.tsx"
PERF_CONFIG = APP / "vitest.perf.config.ts"
VITE_CONFIG = APP / "vite.config.ts"
PACKAGE = APP / "package.json"
BUDGET = APP / "src" / "components" / "model" / "pickerBudget.ts"


def test_the_parallel_suite_does_not_read_a_wall_clock_for_the_picker():
    """GIVEN a ten-worker run THEN the functional test may assert what the picker shows
    and nothing about how long the host took to show it. `performance.now` and a literal
    500 in this file are the two shapes the red runs carried.
    """
    text = FUNCTIONAL.read_text(encoding="utf-8")
    assert "performance.now" not in text, (
        "ModelPicker.test.tsx reads a wall clock; move the measurement to the serial lane"
    )
    assert "toBeLessThan(500)" not in text, (
        "ModelPicker.test.tsx still carries the absolute 500 ms assertion"
    )
    assert "budgetReport" not in text, "the parallel test still imports the budget report"


def test_the_functional_test_still_covers_the_320_row_list():
    """GIVEN the timing assertion is gone THEN the case it guarded must remain: 320 rows
    open and the search narrows them. A deleted perf case is not a split.
    """
    text = FUNCTIONAL.read_text(encoding="utf-8")
    assert "length: 320" in text, "the 320-row fixture is gone"
    assert "model-7" in text, "the search term the perf case used is gone"
    assert "optionRows()" in text, "the test no longer inspects the rendered rows"


def test_the_perf_lane_exists_and_is_serial():
    """GIVEN the ceiling THEN its lane names one worker, no file parallelism and no
    concurrent test sequence. Two workers is the shape that made the number describe the
    runner instead of the picker.
    """
    assert PERF_CONFIG.is_file(), "app/vitest.perf.config.ts is missing"
    config = PERF_CONFIG.read_text(encoding="utf-8")
    assert re.search(r"maxWorkers:\s*1\b", config), "the perf lane does not pin maxWorkers: 1"
    assert re.search(r"fileParallelism:\s*false", config), "the perf lane parallelises files"
    assert re.search(r"concurrent:\s*false", config), "the perf lane runs tests concurrently"
    assert "*.perf.test." in config, "the perf config does not select the perf test"
    assert PERF.is_file(), "the picker perf test is missing"


def test_the_default_suite_excludes_the_perf_file():
    """GIVEN the default `vitest run` THEN it must not collect the lane's file, or the
    wall clock is back in the parallel suite under a different name.
    """
    config = VITE_CONFIG.read_text(encoding="utf-8")
    assert "*.perf.test." in config, "vite.config.ts does not exclude the perf test"
    package = json.loads(PACKAGE.read_text(encoding="utf-8"))
    scripts = package.get("scripts") or {}
    assert "test:perf" in scripts, "app/package.json has no test:perf script"
    assert "vitest.perf.config.ts" in scripts["test:perf"], (
        "the test:perf script does not use the serial config"
    )


def test_the_perf_lane_warms_up_and_uses_a_median():
    """GIVEN a JIT and a first-render cost THEN one cold sample is not a measurement.
    The lane warms up, takes several samples, and reports the middle one.
    """
    text = PERF.read_text(encoding="utf-8")
    assert "warm" in text.lower(), "the perf lane has no warm-up"
    assert "median" in text, "the perf lane reads a single sample instead of a median"
    assert "performance.now" in text, "the perf lane does not measure anything"
    assert "PICKER_BUDGET_MS" in text or "500" in text, "the ceiling is not named in the lane"


def test_the_control_is_a_load_diagnostic_not_a_widened_budget():
    """GIVEN the control render THEN it can mark the host overloaded and can never move
    the ceiling. A control that 'explains' a slow reading by raising the budget is the
    defect this split exists to remove.
    """
    budget = BUDGET.read_text(encoding="utf-8")
    assert "PICKER_BUDGET_MS = 500" in budget, "the ceiling moved"
    assert "overloaded" in budget, "the budget report cannot mark an overloaded host"
    perf = PERF.read_text(encoding="utf-8")
    assert "overloaded" in perf, "the perf lane ignores the load diagnostic"
    assert "CONTROL_LOAD_MS" in perf or "overload" in perf.lower(), (
        "the perf lane does not name the load condition"
    )
    assert "budgetReport" in perf, "the perf lane does not use the shared budget report"


def test_the_lane_runs_in_its_own_nightly_workflow():
    """GIVEN the timing workflow has been red on stale pytest budgets since 2026-10-17 THEN the
    picker reading gets its own workflow. A green measurement inside a permanently red run is
    invisible, and the lane has to be schedule-triggered to stay serial.
    """
    document = yaml.safe_load(PICKER_PERF.read_text(encoding="utf-8")) or {}
    triggers = document.get("on") or document.get(True) or {}
    assert "schedule" in triggers, "picker-perf.yml is not scheduled"
    assert "workflow_dispatch" in triggers, "picker-perf.yml cannot be run by hand"
    jobs = document.get("jobs") or {}
    lane = jobs.get("picker-perf")
    assert lane is not None, "picker-perf.yml has no picker-perf job"
    assert lane.get("runs-on") == "${{ vars.CI_LINUX_RUNNER || 'ubuntu-latest' }}", (
        "the perf lane does not use the shared measurement runner label"
    )
    runs = "\n".join(str(step.get("run", "")) for step in lane.get("steps") or [])
    assert "pnpm run test:perf" in runs, "the scheduled lane does not run the serial config"
    assert "pnpm install --frozen-lockfile" in runs, "the scheduled lane installs outside the lockfile"

    timing = yaml.safe_load(TIMING.read_text(encoding="utf-8")) or {}
    assert "picker-perf" not in (timing.get("jobs") or {}), (
        "picker-perf moved back into the long timing workflow, where its green status is hidden"
    )
