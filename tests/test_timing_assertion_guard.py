"""No wall-clock budget is asserted inside the `-n auto` leg of the pytest job.

`a8c8d35f` split the timing gates out of the parallel leg for a measured reason: on the
owner's 10-CPU Mac `pytest -n auto` took the load from 3.2 to ~20 and `test_startup_budget`
lost its 150 ms budget, while the same file passed in 5.6 s on its own. CI run 37974211156
(2026-10-09) proved the class is wider than that one file — a search-route budget fell at
324.7 ms against 200 ms while every non-timing assertion in the same test stayed green.

Owner rule for this class: a budget that only fails under load gets its own serial
segment, and the budget is never widened to absorb contention, because a widened budget
measures nothing. This guard holds the line so the next timing assertion is placed on
purpose.

What it checks, in order:

* the two pytest steps of `.github/workflows/tests.yml` still describe one serial segment
  and one `-n` leg, and everything the serial segment runs is kept out of the parallel one;
* an `assert` in the parallel set that bounds a measured wall time from above is either
  listed as serial or carries an English reason in `REASONS` proving no clock is read;
* a reason whose assertion no longer exists is itself a failure, so the table cannot rot;
* the collection-time half of the same rule: every collected serial-segment item in a
  worker session carries the load-aware skip that `tests/conftest.py` hands out from
  `tests/timing_segment.py`, because a local `pytest tests -n 8` excludes nothing and a
  budget read there measures the queue.

Only upper bounds count. `assert duration_ms >= 0` gets larger under load, so it is a
presence check; the family that breaks is the one that promises a ceiling. A ceiling on a
value no test named after time is beyond any static scan, so the suite's naming of
`elapsed_ms`, `p95` and `_ms` is part of what this guard holds.
"""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path
from typing import NamedTuple

import pytest

from tests import timing_segment as segment
from tests.timing_segment import PARALLEL_STEP, SERIAL_STEP

REPO = Path(__file__).resolve().parent.parent
TESTS = REPO / "tests"

# The names a measured duration arrives under in this suite (surveyed 2026-10-09 over
# every test file that reads a clock or asserts a time-shaped response field).
TIME_SHAPE = re.compile(
    r"elapsed|duration|latenc|perf_counter|monotonic|time\.time|\bp\d{2}\b|_ms\b|\bms\b|"
    r"millis|seconds?|_secs?\b|wall|took|runtime|uptime",
    re.I,
)
# `assert p90 < STARTUP_BUDGET_S` is the same shape as a literal ceiling.
BUDGET_NAME = re.compile(r"^[A-Z_]*(?:BUDGET|CEILING|TOLERANCE|LIMIT|DEADLINE)[A-Z_]*$")

# (file, test id) -> why the ceiling in it does not come from a clock.
REASONS: tuple[tuple[str, str, str], ...] = (
    (
        "tests/test_browser_url_policy.py",
        "test_the_budget_is_clamped_into_a_sane_range",
        "budget_seconds is arithmetic on the URL count and no clock is read",
    ),
    (
        "tests/test_finding_03_websearch_returntype.py",
        "test_web_search_has_hard_timeout",
        "WEB_SEARCH_TIMEOUT_SECONDS is a configured constant, its value is the subject",
    ),
    (
        "tests/test_chat_stream_errors.py",
        "test_a_long_4xx_body_is_held_to_one_bounded_line",
        "the bounds count occurrences of the word wall in a refusal text; no clock is read",
    ),
)

GERMAN = re.compile(r"\b(?:nicht|und|der|die|das|mit|wegen|f[uü]r|[uü]ber|gr[oö][ßs]er)\b", re.I)  # language-gate: ignore (the German markers this check detects, held as data)


class Hit(NamedTuple):
    path: str
    node: str
    text: str
    line: int


def _step_command(name: str) -> str:
    """The workflow step's shell text; `tests/timing_segment.py` owns the parse."""
    return segment.step_command(name)


def _serial_targets(command: str) -> tuple[set[str], set[str]]:
    return segment.serial_targets(command)


def _parallel_excludes(command: str) -> tuple[set[str], set[str]]:
    return segment.parallel_excludes(command)


def _test_files() -> list[Path]:
    return sorted(TESTS.rglob("test_*.py"))


def _parallel_files(command: str) -> list[Path]:
    """Test modules the parallel leg collects: under tests/, outside every --ignore path."""
    ignored = _parallel_excludes(command)[0]
    return [
        path
        for path in _test_files()
        if (rel := path.relative_to(REPO).as_posix()) not in ignored
        and not any(rel.startswith(f"{item}/") for item in ignored)
    ]


def _is_ceiling(node: ast.Compare) -> bool:
    if not any(isinstance(op, (ast.Lt, ast.LtE)) for op in node.ops):
        return False
    text = ast.unparse(node)
    if not TIME_SHAPE.search(text):
        return False
    operands = [node.left, *node.comparators]
    for operand in operands:
        if isinstance(operand, ast.Constant) and isinstance(operand.value, (int, float)):
            return True
        if BUDGET_NAME.match(ast.unparse(operand)):
            return True
    return False


def _enclosing(rel: str, assert_node: ast.Assert, parents: dict[ast.AST, ast.AST]) -> str:
    trail: list[str] = []
    seen_test = False
    node: ast.AST | None = assert_node
    while node is not None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            trail.insert(0, node.name)
            seen_test = True
        elif isinstance(node, ast.ClassDef) and seen_test:
            trail.insert(0, node.name)
        node = parents.get(node)
    return f"{rel}::{'::'.join(trail)}" if trail else rel


def _hits(rel: str, source: str) -> list[Hit]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    found: list[Hit] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        ceilings = [sub for sub in ast.walk(node.test) if isinstance(sub, ast.Compare) and _is_ceiling(sub)]
        if ceilings:
            found.append(
                Hit(rel, _enclosing(rel, node, parents), ast.unparse(ceilings[0]), node.lineno)
            )
    return found


def _serial_side() -> tuple[str, set[str], set[str]]:
    command = _step_command(SERIAL_STEP)
    files, nodes = _serial_targets(command)
    return command, files, nodes


def _parallel_side() -> tuple[str, set[str], set[str]]:
    command = _step_command(PARALLEL_STEP)
    ignored, deselected = _parallel_excludes(command)
    return command, ignored, deselected


def _parallel_hits() -> list[tuple[str, Hit]]:
    out: list[tuple[str, Hit]] = []
    for path in _parallel_files(_step_command(PARALLEL_STEP)):
        rel = path.relative_to(REPO).as_posix()
        out.extend((rel, hit) for hit in _hits(rel, path.read_text(encoding="utf-8")))
    return out


def offenders() -> list[Hit]:
    """Every ceiling on a measured duration that the parallel leg still collects.

    `_parallel_files` already drops what the parallel command ignores, so a whole timing file
    is not scanned here.
    """
    _, _, not_collected = _parallel_side()
    return [
        hit
        for rel, hit in _parallel_hits()
        if hit.node not in not_collected and not reason_for(rel, hit.node)
    ]


def reason_for(rel: str, node: str) -> str:
    """The recorded reason for a ceiling in `node`, matched on the test function name."""
    tail = node.rsplit("::", 1)[-1]
    for path, listed, reason in REASONS:
        if (path, listed) == (rel, tail):
            return reason
    return ""


def test_the_serial_segment_and_the_parallel_leg_are_split():
    command, serial_files, serial_nodes = _serial_side()
    parallel, ignored, deselected = _parallel_side()
    assert not any(tok.startswith("-n") for tok in command.split()), (
        f"{SERIAL_STEP} must not spread workers: {command}"
    )
    assert any(tok.startswith("-n") for tok in parallel.split()), (
        f"{PARALLEL_STEP} is no longer the parallel leg: {parallel}"
    )
    # Equal in both directions: a budget the serial segment runs must leave the `-n auto` leg, and
    # a test the `-n auto` leg drops must be run by the serial segment, or it disappears from CI.
    on_disk = {path.relative_to(REPO).as_posix() for path in _test_files()}
    assert serial_files == ignored & on_disk, (
        f"serial files and --ignore differ: {sorted(serial_files ^ (ignored & on_disk))}"
    )
    assert serial_nodes == deselected, (
        f"serial test ids and --deselect differ: {sorted(serial_nodes ^ deselected)}"
    )


def test_no_wall_clock_ceiling_sits_in_the_parallel_leg():
    bad = offenders()
    assert not bad, "wall-clock budgets in the parallel leg: " + ", ".join(
        f"{hit.path}:{hit.line} ({hit.node}) {hit.text}" for hit in bad
    )


MACOS_SERIAL_STEP = "Run timing gates (serial, macOS)"
MACOS_PARALLEL_STEP = "Run tracked pytest suite (macOS)"


def test_the_macos_leg_splits_the_same_way_as_the_linux_leg():
    """`.github/workflows/tests.yml` carries the segment twice, by the owner's decision of
    2026-10-10: two jobs with a literal matrix instead of one job with a `fromJSON` matrix,
    because the literal form is the one GitHub is measured to expand. Nothing here read the
    copy, so the two lists moved by hand and no test said when they stopped agreeing.

    Both halves are asserted: the macOS pair must keep its own serial segment free of workers
    and its parallel leg free of ceilings, and the two legs' segment lists must be equal,
    which is the drift the duplication actually risks.
    """
    mac_serial = _step_command(MACOS_SERIAL_STEP)
    assert not any(tok.startswith("-n") for tok in mac_serial.split()), (
        f"{MACOS_SERIAL_STEP} must not spread workers: {mac_serial}"
    )
    mac_parallel = _step_command(MACOS_PARALLEL_STEP)
    assert any(tok.startswith("-n") for tok in mac_parallel.split()), (
        f"{MACOS_PARALLEL_STEP} is no longer the parallel leg: {mac_parallel}"
    )

    mac_files, mac_nodes = _serial_targets(mac_serial)
    mac_ignored, mac_deselected = _parallel_excludes(mac_parallel)
    _, linux_files, linux_nodes = _serial_side()

    assert mac_files == linux_files, (
        f"the two serial segments disagree on files: macOS {sorted(mac_files)} vs Linux "
        f"{sorted(linux_files)}"
    )
    assert mac_nodes == linux_nodes, (
        f"the two serial segments disagree on node ids: macOS {sorted(mac_nodes)} vs Linux "
        f"{sorted(linux_nodes)}"
    )
    assert mac_files <= mac_ignored, (
        f"the macOS parallel leg collects a serial file: {mac_parallel}"
    )
    assert mac_nodes <= mac_deselected, (
        f"the macOS parallel leg keeps a serial node: {mac_parallel}"
    )


def test_no_ceiling_is_measured_inside_a_parallel_worker(request):
    """The static half of this file cannot see a local ``pytest tests/ -n 8``.

    Nothing is excluded there, so the 15 units the serial segment owns reach every worker
    session: run 37974211156 measured 324.7 ms against a 200 ms budget with 3536 green
    tests beside it. The wiring that answers this is ``tests/conftest.py`` handing each
    collected serial-segment item the load-aware skip from ``tests/timing_segment.py``, and
    this test verifies the items arrive skipped — a unit that reads a clock can no longer
    be measured through workers, and a broken skip blows up here instead of on a budget.

    It lives here and not in ``tests/conftest.py`` because of where the information is.
    Measured on this machine with ``-n 2``: the xdist controller runs ``pytest_configure``,
    ``pytest_sessionstart`` and the terminal summary, and no collection hook at all — the
    only process that can see the collected node ids is the worker.
    """
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if not worker:
        return  # a serial run reads these budgets the way the segment means it
    measured = sorted(
        item.nodeid
        for item in segment.segment_items(request.session.items)
        if not segment.skips_in_this_session(item)
    )
    assert not measured, (
        f"{len(measured)} clock-reading test(s) reach xdist worker {worker} without the "
        f"load-aware skip: {', '.join(measured[:4])}. A budget read while workers share the "
        "machine measures the machine, so the number is not a budget. tests/conftest.py "
        "hands every serial-segment item that skip (tests/timing_segment.py); if this list "
        "is non-empty, that wiring is gone."
    )


def test_the_stand_down_reason_speaks_of_the_worker_or_of_the_load(monkeypatch):
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    monkeypatch.setattr(segment, "load_per_cpu", lambda: 0.3)
    assert segment.unmeasurable_reason() is None
    monkeypatch.setattr(segment, "load_per_cpu", lambda: segment.LOAD_BAR_PER_CPU)
    busy = segment.unmeasurable_reason()
    assert busy and "load" in busy, busy
    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw7")
    on_worker = segment.unmeasurable_reason()
    assert on_worker and "gw7" in on_worker, on_worker


def test_an_uncalibrated_machine_stands_down_without_touching_the_run_queue(monkeypatch):
    """GIVEN a GitHub-hosted runner WHEN either reader is asked THEN only the timing one stands down.

    The load bar answers a question about the run queue, and `core/agent_limits.py` refuses an
    agent on that answer alone — so a hosted runner must not make that reader stand down. The
    clock gate, whose budgets were frozen on characterised machines, must.
    """
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    monkeypatch.setattr(segment, "load_per_cpu", lambda: 0.3)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "github-hosted")

    hosted = segment.uncalibrated_machine_reason()

    assert hosted and "host" in hosted, hosted
    assert segment.unmeasurable_reason() is None  # the queue is calm and the worker is not xdist
    assert segment.stand_down_reason() == hosted

    monkeypatch.setenv("RUNNER_ENVIRONMENT", "self-hosted")

    assert segment.uncalibrated_machine_reason() is None  # a characterised machine keeps measuring
    assert segment.stand_down_reason() is None


def test_an_item_with_an_active_skip_marker_is_left_alone():
    class Item:
        # iter_markers is the only attribute the session predicate reads.
        def __init__(self, marks):
            self._marks = list(marks)

        def iter_markers(self):
            return iter(self._marks)

    assert not segment.skips_in_this_session(Item([]))
    assert not segment.skips_in_this_session(Item([pytest.mark.skipif(False, reason="inactive")]))
    assert segment.skips_in_this_session(Item([pytest.mark.skipif(True, reason="active")]))
    assert segment.skips_in_this_session(Item([pytest.mark.skip(reason="plain")]))


def test_a_ceiling_on_a_measured_duration_is_found():
    source = "def test_x():\n    import time\n    t0 = time.perf_counter()\n    assert elapsed_ms < 200\n"
    hits = _hits("tests/test_scratch.py", source)
    assert [hit.node for hit in hits] == ["tests/test_scratch.py::test_x"]
    named = _hits("tests/test_scratch.py", "def test_x():\n    assert p95 < STARTUP_BUDGET_S\n")
    assert len(named) == 1


def test_a_presence_check_or_a_plain_count_is_not_a_ceiling():
    for source in (
        "def test_x():\n    assert rec['duration_ms'] >= 0\n",
        "def test_x():\n    assert len(results) < 5\n",
        "def test_x():\n    assert timeout.connect <= 30.0\n",
    ):
        assert not _hits("tests/test_scratch.py", source), source


def test_every_reason_is_english_and_still_buys_an_exemption():
    surveyed = _parallel_hits()
    for rel, node, reason in REASONS:
        assert reason.isascii() and len(reason.split()) >= 4, f"weak reason for {rel}::{node}"
        assert not GERMAN.search(reason), f"reason must be English: {rel}::{node}"
        assert any(path == rel and hit.node.endswith(f"::{node}") for path, hit in surveyed), (
            f"reason for {rel}::{node} no longer matches an assertion in the parallel leg"
        )
