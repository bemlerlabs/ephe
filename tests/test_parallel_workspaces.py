"""tests/test_parallel_workspaces.py — fifty trees at once: measured, not argued.

``core/workspace_lifecycle.create`` states its own gap: its 50-agent guarantee is "argued
from the register design" and has never been measured. The argument is sound — every
register read-modify-write sits inside ``_locked()``, an exclusive ``fcntl.flock`` on a
file beside the register — but an argument is not a measurement, so this file measures.

What the measurement found, in the order it appeared:

* The register holds. Fifty concurrent ``create`` calls write exactly fifty rows carrying
  fifty distinct ids, ``list_live()`` never disagrees with ``git worktree list``, and the
  main checkout's file tree, ``git status`` and its own entry in that list all come back
  untouched. The lock does what the design says it does.
* ``git worktree add`` itself is not safe here, and ``create`` calls it *outside* the lock
  that ``remove`` already holds across its own git calls. Measured against git 2.54.0
  (Apple Git-157) in a one-file repository, concurrent adds were refused 0 to 3 times per
  run at widths 16, 32 and 50 with ``fatal: failed to read
  .git/worktrees/<sibling>/commondir: Undefined error: 0``. It is not width-monotonic — the
  window is a sibling's registration — so 16 is not a safe width either, and ``--detach``
  refuses too, so it is not the new ref that races. Serialising that one call behind the
  register lock took the refusals to 0 in 150 attempts at width 50, for ~12 % more wall
  time on that repository.
* A refusal is fail-safe rather than corrupting: the row is marked ``discarded`` before the
  exception leaves ``create``, so ``reap_orphans`` collects it with the branch it left.

So the wave case asserts the invariants that hold whatever git does, and reports the
refusal rate instead of hoping for zero: "no corruption" is the promise this file can
measure and it survives a refused add, while "fifty at once" is one it can only report on.

Every case runs against a one-file repository under ``tmp_path``. The checkout at the root
of this worktree carries ~3 400 tracked files and fifty worktrees of it would fill a disk
three sibling strands share, which is why the module's own tests throw one away too.
"""
from __future__ import annotations

import json
import os
import resource
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from core import agent_limits, load_bar, workspace_lifecycle as wl
from core.agent_limits import admit, check, defaults
from tests import timing_segment

CHECKOUT_FILE = "readme.txt"

#: The widths one wave case runs at. 16 is what a bounded run can afford on a box three
#: strands share; 50 is the width the sprint promises. Both go through `_check_wave`, so the
#: narrow run is decided by the same checks and hides nothing they cover.
WAVE_WIDTHS = (16, 50)

#: Widest wave the teardown case takes down, because serialised removal is the costly half.
TEARDOWN_WIDTH = 50

#: What each wave cost, written by the wave cases and read back by the report at the end.
COST: dict[int, dict] = {}

def _git(root: Path, *args: str) -> str:
    """stdout of one git call in `root`, which raises when git refuses it."""
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    assert done.returncode == 0, f"git {' '.join(args)} in {root}: {done.stderr.strip()}"
    return done.stdout

def _worktrees(root: Path) -> list[str]:
    """Every worktree git reports, resolved and in git's order: the checkout first."""
    out = _git(root, "worktree", "list", "--porcelain")
    named = (line.split(" ", 1)[1] for line in out.splitlines() if line.startswith("worktree "))
    return [str(Path(name).resolve()) for name in named]

def _checkout_entry(root: Path) -> str:
    """The main checkout's own porcelain entry, its path line dropped.

    `git worktree list` names the main checkout first and separates entries with a blank
    line, so a wave appends below that block rather than through it.
    """
    block = _git(root, "worktree", "list", "--porcelain").split("\n\n", 1)[0]
    return "\n".join(line for line in block.splitlines() if not line.startswith("worktree "))

def _tree(root: Path) -> set[str]:
    """Every path the checkout carries outside its own git directory."""
    return {str(path.relative_to(root)) for path in root.rglob("*") if ".git" not in path.parts}

def _branches(root: Path) -> set[str]:
    """Every local branch name, without the marker git draws beside the current one."""
    out = _git(root, "branch", "--format=%(refname:short)")
    return {line.strip() for line in out.splitlines() if line.strip()}

def _state(root: Path) -> dict:
    """The four witnesses a wave must leave exactly as it found them."""
    return {
        "entry": _checkout_entry(root),
        "status": _git(root, "status", "--porcelain"),
        "tree": _tree(root),
        "branches": _branches(root),
    }

def _rows() -> list[dict]:
    """The register as it stands, whatever the last writer left in it."""
    return json.loads(wl.register_file().read_text(encoding="utf-8"))["workspaces"]

def _child_cpu() -> float:
    """CPU seconds this process' reaped children burned: the cost load average cannot show.

    One-minute load average barely moves across a wave two seconds long, so the child CPU
    booked by `wait` is the number that describes the cost without any warm-up.
    """
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return usage.ru_utime + usage.ru_stime

def _exited_pid() -> int:
    """A pid that is certainly gone: a child that has been started and reaped."""
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    return child.pid

def _claim_owner(tree_id: str, pid: int) -> None:
    """Hand a row to another pid, the way a crashed owner leaves it behind."""
    rows = _rows()
    for row in rows:
        if row["id"] == tree_id:
            row["pid"] = pid
    wl.register_file().write_text(json.dumps({"workspaces": rows}), encoding="utf-8")

def _attempt(rank: int):
    """One agent's create, with a refusal kept as a value rather than raised into the pool."""
    try:
        return wl.create(f"agent-{rank:02d}"), None
    except wl.WorkspaceError as exc:
        return None, str(exc)

def _check_wave(trees: list, root: Path, before: dict, width: int) -> list[str]:
    """Every invariant one wave must hold, each named as it is decided.

    The names come back so the report can show that the narrow wave and the fifty-wide one
    were decided by the same checks rather than by two different standards.
    """
    done: list[str] = []

    rows = _rows()
    ids = [row["id"] for row in rows]
    assert len(rows) == width
    assert len(set(ids)) == width
    done.append("one-row-per-create-and-no-id-twice")

    accepted = {tree.id for tree in trees}
    on_git = set(_worktrees(root))
    assert on_git == {str(Path(tree.path).resolve()) for tree in trees} | {str(root.resolve())}
    done.append("git-names-every-accepted-tree-and-nothing-else")

    live = wl.list_live()
    assert {row.id for row in live} == accepted
    assert {str(Path(row.path).resolve()) for row in live} == on_git - {str(root.resolve())}
    done.append("list-live-equals-what-git-reports")

    for tree in trees:
        assert tree.state == "ready"
        assert Path(tree.path).is_dir()
    assert {row["id"] for row in rows if row.get("state") != "ready"} == set(ids) - accepted
    done.append("accepted-trees-are-ready-and-refusals-are-not-live")

    assert set(wl.reap_orphans(0)) == set(ids) - accepted
    done.append("the-reaper-collects-every-refused-row")

    assert set(_worktrees(root)) == on_git
    assert {row.id for row in wl.list_live()} == accepted
    assert _branches(root) - before["branches"] == {tree.branch for tree in trees}
    done.append("no-refusal-leaves-a-branch-or-a-registration-behind")

    assert _tree(root) == before["tree"]
    assert _git(root, "status", "--porcelain") == before["status"] == ""
    assert _checkout_entry(root) == before["entry"]
    done.append("the-checkout-is-as-it-was")
    return done


class _Reader(threading.Thread):
    """A live owner reading the register while the reaper works.

    `list_live()` every pass and `get()` on one rotating tree, because `get` refreshes a
    state through `git status` — the work a real agent does, and a register lock taken on
    the way. The pass is paced through an `Event`, so the case measures the reaper rather
    than this file's appetite for processes.
    """

    def __init__(self, ids: list[str]) -> None:
        super().__init__(daemon=True)
        self._ids = list(ids)
        # Not `_stop`: threading.Thread owns that name as a method and join() calls it.
        self._done = threading.Event()
        self.first = threading.Event()
        self.reads = 0
        self.low: int | None = None
        self.errors: list[str] = []

    def run(self) -> None:
        while not self._done.is_set():
            try:
                live = wl.list_live()
                wl.get(self._ids[self.reads % len(self._ids)])
            except Exception as exc:  # the case exists to report what a reader saw
                self.errors.append(f"{type(exc).__name__}: {exc}")
                self.first.set()
                return
            self.low = len(live) if self.low is None else min(self.low, len(live))
            self.reads += 1
            self.first.set()
            self._done.wait(0.005)

    def halt(self) -> None:
        """Ask the loop to end, and wait for the pass it is in to finish."""
        self._done.set()
        self.join(5)


@pytest.fixture
def checkout(tmp_path, monkeypatch) -> Path:
    """A repository with one file and one commit, plus the managed directory beside it."""
    root = tmp_path / "checkout"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    (root / CHECKOUT_FILE).write_text("the checkout\n", encoding="utf-8")
    _git(root, "add", CHECKOUT_FILE)
    _git(root, "-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", "init")
    monkeypatch.setattr(wl, "REPO_ROOT", root)
    monkeypatch.setattr(wl, "WORKSPACES_DIR", tmp_path / "managed")
    return root


@pytest.mark.parametrize("width", WAVE_WIDTHS)
def test_a_concurrent_wave_keeps_its_register_and_leaves_the_checkout_alone(checkout, width):
    """GIVEN N agents creating at once WHEN the register is rewritten concurrently THEN no
    row is lost or duplicated, git's list and `list_live()` agree, and the checkout is as it
    was — whatever git does with the adds."""
    before = _state(checkout)
    cpu_before = _child_cpu()
    started = time.monotonic()

    with ThreadPoolExecutor(max_workers=width) as pool:
        outcomes = list(pool.map(_attempt, range(width)))

    span = time.monotonic() - started
    burned = _child_cpu() - cpu_before
    trees = [tree for tree, _ in outcomes if tree is not None]
    refused = [error for _, error in outcomes if error is not None]

    done = _check_wave(trees, checkout, before, width)
    COST[width] = {
        "span_s": span,
        "child_cpu_s": burned,
        "load_per_cpu": timing_segment.load_per_cpu(),
        "invariants": done,
        "accepted": len(trees),
        "refused": len(refused),
    }
    print(
        f"\nwave {width}: {len(trees)} accepted, {len(refused)} refused by git, "
        f"{span:.2f} s wall, {burned:.2f} s child CPU, {len(done)} invariants held"
    )
    for error in refused[:3]:
        print(f"    {error.splitlines()[0][:120]}")

    assert span > 0.0
    assert burned > 0.0


def test_a_wave_tears_down_concurrently_and_a_second_reap_finds_nothing(checkout):
    """GIVEN fifty trees WHEN they are removed at once THEN nothing is left behind and a
    second reap has nothing to collect."""
    before = _state(checkout)
    trees = [wl.create(f"agent-{rank:02d}") for rank in range(TEARDOWN_WIDTH)]
    assert len(wl.list_live()) == TEARDOWN_WIDTH

    cpu_before = _child_cpu()
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=TEARDOWN_WIDTH) as pool:
        list(pool.map(wl.remove, [tree.id for tree in trees]))
    span = time.monotonic() - started

    assert wl.list_live() == []
    assert wl.get(trees[0].id) is None
    for tree in trees:
        assert not Path(tree.path).exists()
    assert _worktrees(checkout) == [str(checkout.resolve())]
    assert _branches(checkout) == before["branches"]
    assert _git(checkout, "status", "--porcelain") == ""
    assert _tree(checkout) == before["tree"]

    # Nothing left in the managed directory but the register and the lock beside it, and
    # nothing left in git's own admin area for the fifty trees that stood there.
    assert {path.name for path in wl.WORKSPACES_DIR.iterdir()} <= {"register.json", "register.lock"}
    admin = checkout / ".git" / "worktrees"
    assert not admin.exists() or not list(admin.iterdir())

    assert wl.reap_orphans(0) == []
    assert wl.list_live() == []
    assert _worktrees(checkout) == [str(checkout.resolve())]
    print(
        f"\nteardown {TEARDOWN_WIDTH}: {span:.2f} s wall, "
        f"{_child_cpu() - cpu_before:.2f} s child CPU"
    )
    assert span > 0.0


def test_the_reaper_takes_a_dead_owner_while_the_living_keep_working(checkout):
    """GIVEN one tree whose owner is gone and four whose owners are not WHEN the reaper runs
    under their reads THEN only the dead one goes and no reader sees a torn register."""
    living = [wl.create(f"agent-{rank}") for rank in range(4)]
    orphan = wl.create("ghost")
    _claim_owner(orphan.id, _exited_pid())

    reader = _Reader([tree.id for tree in living])
    reader.start()
    assert reader.first.wait(5), "the reader never finished a pass"

    reaped = wl.reap_orphans(0)
    # The reader keeps looping, so it takes the passes either side of the reaper's write.
    time.sleep(0.1)
    reader.halt()

    assert reaped == [orphan.id]
    assert not Path(orphan.path).exists()
    assert orphan.branch not in _branches(checkout)
    assert {tree.id for tree in wl.list_live()} == {tree.id for tree in living}
    for tree in living:
        assert Path(tree.path).is_dir()
        assert str(Path(tree.path).resolve()) in _worktrees(checkout)

    # What the concurrent reader saw: no exception, and never fewer than the four trees
    # that were supposed to survive — an empty or half-written register would show here.
    assert reader.errors == []
    assert reader.reads >= 2
    assert reader.low == len(living)


def test_admit_refuses_the_fifty_first_agent_under_this_boxs_own_load(checkout):
    """GIVEN the shipped bounds WHEN the wave is full THEN fifty enter, the fifty-first is
    refused, and the load rule reads the one bar object the timing segment reads too."""
    # Real load rather than a literal: eight agents start first, so the reading below is
    # taken on a box that is doing the work before the same reading is handed to the rule.
    for rank in range(8):
        wl.create(f"load-{rank}")

    limits = defaults()
    assert limits.max_agents == 50
    assert admit(limits, {"agents": 49})  # the fiftieth agent enters
    assert not admit(limits, {"agents": 50})  # the fifty-first is refused
    assert check(limits, {"agents": 50}) == [
        f"{agent_limits.REASON_TAG}: 50 agents running, cap 50"
    ]

    # One object, so the two readers cannot drift apart.
    bar = load_bar.LOAD_BAR_PER_CPU
    assert agent_limits.LOAD_BAR_PER_CPU is bar
    assert timing_segment.LOAD_BAR_PER_CPU is bar
    assert agent_limits.LOAD_BAR_PER_CPU is timing_segment.LOAD_BAR_PER_CPU

    assert not admit(limits, {"load_per_cpu": bar})  # at the bar: refused
    assert admit(limits, {"load_per_cpu": bar - 0.001})  # just under it: admitted

    reading = timing_segment.load_per_cpu()
    if reading is None:
        pytest.skip("this platform reports no load average")
    assert reading is not None
    # `check` is pure, so the load this box is under cannot move the boundary — it can only
    # decide which side of it the box is on, and that verdict is asserted here.
    assert bool(check(limits, {"load_per_cpu": reading})) == (reading >= bar)
    print(f"\nload now: {reading:.2f} runnable tasks per CPU, bar {bar:.1f}")


def test_the_report_holds_the_narrow_and_the_wide_wave_to_one_standard():
    """GIVEN both waves ran WHEN their records are compared THEN the same checks decided
    both, so the bounded run hides nothing those checks cover."""
    missing = [width for width in WAVE_WIDTHS if width not in COST]
    if missing:
        pytest.skip(f"the wave cases for {missing} did not run in this session")

    narrow, wide = COST[WAVE_WIDTHS[0]], COST[WAVE_WIDTHS[-1]]
    assert narrow["invariants"] == wide["invariants"]
    assert len(narrow["invariants"]) >= 7
    # Every create ends accepted or refused, and the two add up to the width: that is
    # the whole promise, and a refused add must not be able to move it.
    assert narrow["accepted"] + narrow["refused"] == WAVE_WIDTHS[0]
    assert wide["accepted"] + wide["refused"] == WAVE_WIDTHS[-1]

    print("\nwhat the waves cost, against a one-file repository:")
    for width in sorted(COST):
        record = COST[width]
        print(
            f"  {width:>2} trees: {record['span_s']:.2f} s wall, "
            f"{record['child_cpu_s']:.2f} s child CPU, "
            f"{record['refused']} add(s) refused by git"
        )
    assert all(COST[width]["span_s"] > 0.0 for width in COST)
