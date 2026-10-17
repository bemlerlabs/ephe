"""The serial timing segment, and when its gates must stand down.

`.github/workflows/tests.yml` runs four whole timing files plus six budget node ids in
"Run timing gates (serial)" and keeps them out of the `-n auto` leg; that split is held by
`tests/test_timing_assertion_guard.py`. This module carries the runtime half of the same
rule: a local `pytest tests -n 8` excludes nothing, so those units reach every worker, and
a wall clock read there describes the machine. `tests/conftest.py` hands each serial-segment
item the skip below whenever the clock cannot be trusted; the guard fails when one reaches a
worker without it.

Two conditions make the reading untrustworthy, both measured on this project:

* xdist workers share the cores. On the owner's 10-CPU Mac `pytest -n auto` took the load
  from 3.2 to ~20 and pushed `test_startup_budget` past its 150 ms budget while the same
  file passed in 5.6 s on its own; run 37974211156 read a 200 ms search budget as 324.7 ms
  with 3536 green tests beside it.
* A loaded machine does the same to a serial run. The bar is 2.0 runnable tasks per CPU
  (`core/load_bar.py`, shared with the agent admission rule), the state that Mac reached
  under `-n auto` (load ~20 on 10 CPUs). The Spark's full CI run
  peaked at 27.9 on 20 cores (1.4 per CPU), and its serial segment is documented to hold
  there — so CI keeps measuring while an ad-hoc run on a busy box stands down instead of
  going red over the queue.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from core.load_bar import LOAD_BAR_PER_CPU

REPO = Path(__file__).resolve().parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "tests.yml"
SERIAL_STEP = "Run timing gates (serial)"
PARALLEL_STEP = "Run tracked pytest suite"
TARGET = re.compile(r"tests/[^\s]+\.py(?:::[^\s]+)?")

#: every reason this module produces starts with it, so the rule stays greppable
SKIP_TAG = "serial timing segment"


def step_command(name: str) -> str:
    """The shell text of one workflow step, folded across its continuation lines."""
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip() == f"- name: {name}")
    except StopIteration:
        raise AssertionError(f"step {name!r} is not in {WORKFLOW.relative_to(REPO)}")
    body: list[str] = []
    for line in lines[start + 1 :]:
        stripped = line.strip()
        # A blank line, the next step, or a comment ends the command. The comment rule matters:
        # the block above this segment names test files, and reading them as arguments would put
        # them in the serial set.
        if not stripped or stripped.startswith(("- name:", "- uses:", "#", "run: |")):
            break
        body.append(stripped)
    text = " ".join(body)
    assert "pytest" in text, f"step {name!r} does not run pytest: {text}"
    return text


def serial_targets(command: str) -> tuple[set[str], set[str]]:
    """Files and test ids the serial segment runs. A bare file is a whole timing file."""
    files: set[str] = set()
    nodes: set[str] = set()
    for token in TARGET.findall(command):
        if "::" in token:
            nodes.add(token)
        else:
            files.add(token)
    return files, nodes


def parallel_excludes(command: str) -> tuple[set[str], set[str]]:
    ignored = set(re.findall(r"--ignore=(\S+)", command))
    deselected = set(re.findall(r"--deselect=(\S+)", command))
    return ignored, deselected


def segment_items(items):
    """The collected items the serial segment owns: whole files plus single node ids."""
    files, nodes = serial_targets(step_command(SERIAL_STEP))
    prefixes = tuple(node + "::" for node in files)
    return [item for item in items if item.nodeid in nodes or item.nodeid.startswith(prefixes)]


def load_per_cpu() -> float | None:
    """One-minute load average per CPU, or None where the platform does not report one."""
    try:
        load1 = os.getloadavg()[0]
    except (OSError, AttributeError):
        return None
    return load1 / max(1, os.cpu_count() or 1)


def _hosted_runner() -> bool:
    """True on a GitHub-hosted runner: a machine whose host, and so whose speed, varies."""
    return (
        os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
    )


def unmeasurable_reason() -> str | None:
    """Why a wall-clock reading taken now would describe the machine, or None when it would not.

    A pure function of the load and the worker: `core/agent_limits.py` reads the same bar and the
    two must stand down at the same reading (`tests/test_agent_limits.py`). A condition that has
    nothing to do with the run queue belongs in `stand_down_reason()` beside this one.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker:
        return f"xdist worker {worker} shares these cores, so a budget read here measures the machine"
    load = load_per_cpu()
    if load is not None and load >= LOAD_BAR_PER_CPU:
        return (
            f"load {load:.1f} runnable tasks per CPU (bar {LOAD_BAR_PER_CPU:.1f}), so a "
            f"budget read here measures the machine"
        )
    return None


def uncalibrated_machine_reason() -> str | None:
    """Why this machine's speed is unknown, so a budget read here describes the host.

    Separate from `unmeasurable_reason()` on purpose: this is not a statement about the run
    queue, and `core/agent_limits.py` (which reads the queue) must not inherit it. The bar can
    only decide whether a reading describes the queue; it says nothing about whether the machine
    behind it was ever measured. A GitHub-hosted runner is a fresh host each run, and the
    project's budgets were frozen on characterised machines (the owner's Mac, the self-hosted
    Spark), so the clock gates stand down here instead of going red over the host.
    """
    if _hosted_runner():
        return (
            "a GitHub-hosted runner is not a characterised machine (the host, and with it the "
            "CPU speed and the disk, changes per run), so a budget read here measures the host"
        )
    return None


def stand_down_reason() -> str | None:
    """The first reason a wall-clock reading here would describe the machine rather than the code."""
    return unmeasurable_reason() or uncalibrated_machine_reason()


def skips_in_this_session(item) -> bool:
    """True when an active marker makes pytest skip `item`, so running it reads no clock."""
    for mark in item.iter_markers():
        if mark.name == "skip":
            return True
        if mark.name == "skipif" and mark.args and mark.args[0] is True:
            return True
    return False
