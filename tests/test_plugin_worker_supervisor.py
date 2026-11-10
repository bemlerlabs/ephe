"""Task #47: the plugin worker supervisor — crash, timeout, OOM, exit classification.

Two layers, and the difference is the point of `tests/support/capabilities.py`. The
classification tests spawn a plainly forked child, so `crashed`, `oom`, `nonzero` and the
timeout translation are provable on any host; the tests marked `requires_boundary` drive a
really confined child and prove what the boundary itself delivers, skipping (with the
probe's reason) where the host has none.

One measured difference is named rather than smoothed over: `bwrap --unshare-pid` reports a
child killed by SIGTERM as exit 143 (128+15), so on Linux the confined rail reads `nonzero`
where Seatbelt's exec'd child reports `crashed`. The classifier is therefore proven on the
plain child, and the confined test claims only what survives both boundaries.
"""
from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

import pytest

from core import mcp_sandbox
from core.sandbox import (
    STATUSES,
    Refusal,
    RestartBudget,
    WorkerSpec,
    build_spec,
    confined_argv,
    policy_snapshot,
    run_worker,
)
from tests.support import capabilities

PLUGIN_ID = "w47demo"


@pytest.fixture
def plain_child(tmp_path, monkeypatch):
    """The supervisor's child with no boundary; the subject is the classifier."""
    with capabilities.spawn_without_boundary(monkeypatch, tmp_path / "plain-home"):
        yield


def _plugin(tmp_path: Path, body: str, name: str = "tool.py") -> Path:
    root = tmp_path / "plugin"
    root.mkdir(exist_ok=True)
    (root / name).write_text(body)
    return root


def _spec(root: Path, **kw) -> WorkerSpec:
    base = {"plugin_id": PLUGIN_ID, "plugin_dir": root, "entry": "tool.py"}
    spec, error = build_spec(**{**base, **kw})
    assert error == "", error
    return spec


@capabilities.requires_boundary
def test_ok_child_exit_and_output(tmp_path):
    spec = _spec(_plugin(tmp_path, "print('hello worker')"), timeout_seconds=30.0)
    outcome = run_worker(spec)
    assert outcome.status == "ok", outcome.note + outcome.stderr
    assert "hello worker" in outcome.stdout
    assert outcome.exit_code == 0


def test_nonzero_exit_is_classified_not_raised(tmp_path, plain_child):
    """The exit status is read after the spawn, so the classifier needs no boundary."""
    spec = _spec(_plugin(tmp_path, "import sys; sys.exit(3)"), timeout_seconds=30.0)
    outcome = run_worker(spec)
    assert outcome.status == "nonzero"
    assert outcome.exit_code == 3


def test_signal_death_is_crashed(tmp_path, plain_child):
    """A signal death is `crashed` and carries the number, proven on a plain child.

    The confined rail is not used here because bubblewrap does not forward the signal:
    measured in a Linux container, `bwrap` exits 143 for a child that took SIGTERM, and
    the confined test below states the part of the classification both boundaries keep.
    """
    body = "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"
    spec = _spec(_plugin(tmp_path, body), timeout_seconds=30.0)
    outcome = run_worker(spec)
    assert outcome.status == "crashed"
    assert outcome.signal_number == int(signal.SIGTERM)


@capabilities.requires_boundary
def test_timeout_kills_the_whole_process_group(tmp_path):
    body = (
        "import subprocess, time\n"
        "subprocess.Popen(['sleep', '30'])\n"
        "time.sleep(30)\n"
    )
    spec = _spec(_plugin(tmp_path, body), timeout_seconds=1.0)
    started = time.monotonic()
    outcome = run_worker(spec)
    assert outcome.status == "timeout"
    assert outcome.timed_out and outcome.duration_seconds < 10
    assert outcome.group_gone is True
    # The proof, not the promise: the group id is dead and reaped.
    with pytest.raises(ProcessLookupError):
        os.killpg(outcome.pgid, 0)


@capabilities.requires_boundary
def test_output_cap_keeps_the_tail_and_states_itself(tmp_path):
    body = "import sys\nfor i in range(20000):\n    sys.stdout.write('x')\nsys.stdout.write('\\nDONE\\n')\n"
    spec = _spec(_plugin(tmp_path, body), timeout_seconds=30.0, output_cap_bytes=600)
    outcome = run_worker(spec)
    assert outcome.status == "ok"
    assert outcome.stdout_dropped > 19000
    assert f"cap {spec.output_cap_bytes}" in outcome.stdout
    assert "tail preserved" in outcome.stdout
    assert outcome.stdout.rstrip().endswith("DONE")
    assert len(outcome.stdout) < 20000


def test_oom_path_classified_from_exit_status(tmp_path, plain_child):
    # An unasked-for SIGKILL is the kernel OOM-killer's signature on Linux. The
    # kernel path itself is unmeasured on this machine (macOS has no such kill);
    # the classification is provoked through the exit status, exactly as the
    # task demands, and `policy_snapshot` says the same in words.
    body = "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"
    spec = _spec(_plugin(tmp_path, body), timeout_seconds=30.0)
    outcome = run_worker(spec)
    assert outcome.status == "oom"
    assert outcome.signal_number == int(signal.SIGKILL)


@capabilities.requires_boundary
def test_a_confined_signal_death_reads_as_the_boundary_reports_it(tmp_path):
    """The difference the classification tests above stand aside for, measured.

    Seatbelt execs the child, so the supervisor sees `-15` and says `crashed`. bubblewrap
    keeps a supervisor process, so the same death arrives as exit 143 (128+15) and the
    status is `nonzero`. Pinning both here keeps the platform's answer a measurement and
    keeps a future edit from asserting one boundary's shape on the other.
    """
    body = "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"
    spec = _spec(_plugin(tmp_path, body), timeout_seconds=30.0)
    outcome = run_worker(spec)
    if outcome.boundary == "bubblewrap":
        assert outcome.exit_code == 128 + int(signal.SIGTERM) and outcome.signal_number is None
        assert outcome.status == "nonzero"
    else:
        assert outcome.signal_number == int(signal.SIGTERM) and outcome.status == "crashed"


@capabilities.requires_boundary
def test_a_confined_child_exit_status_reaches_the_classifier(tmp_path):
    """Through the real boundary, the child's own exit code arrives and classifies.

    A signal death is left out on purpose: bubblewrap reports 128+N for one, so the same
    run reads `nonzero` on Linux and `crashed` on macOS. That difference is the platform's,
    and the two classification tests above pin the vocabulary on a child neither boundary
    wraps.
    """
    spec = _spec(_plugin(tmp_path, "import sys; sys.exit(9)"), timeout_seconds=30.0)
    outcome = run_worker(spec)
    assert outcome.boundary in ("seatbelt", "bubblewrap")
    assert outcome.status == "nonzero" and outcome.exit_code == 9
    assert outcome.pgid is not None


def test_no_confinement_means_no_execution(tmp_path, monkeypatch):
    marker = tmp_path / "plugin" / "RAN"
    body = f"import pathlib; pathlib.Path({str(marker)!r}).write_text('ran')"
    root = _plugin(tmp_path, body)
    spec = _spec(root, timeout_seconds=30.0)
    monkeypatch.setattr(mcp_sandbox, "platform_boundary", lambda: "unavailable")
    outcome = run_worker(spec)
    assert outcome.status == "sandbox_unavailable"
    assert not marker.exists(), "the child ran even though the boundary was unavailable"
    assert outcome.pgid is None


@capabilities.requires_boundary
def test_protocol_error_when_stdout_fails_framing(tmp_path):
    spec = _spec(_plugin(tmp_path, "print('not a framed reply')"), timeout_seconds=30.0)
    outcome = run_worker(spec, protocol_check=lambda text: text.startswith("{"))
    assert outcome.status == "protocol_error"


def test_restart_budget_turns_a_crash_loop_into_a_visible_refusal():
    budget = RestartBudget(max_restarts=3, backoff_seconds=(0.5, 2.0, 8.0), clock=lambda: 0.0)
    assert budget.record_failure() == 0.5
    assert budget.record_failure() == 2.0
    refusal = budget.record_failure()
    assert isinstance(refusal, Refusal) and budget.spent
    assert refusal.code == "plugin_worker_restart_exhausted"
    assert "refused" in refusal.message
    assert isinstance(budget.record_failure(), Refusal)
    budget.record_success()
    assert not budget.spent


def test_descriptor_refuses_paths_outside_the_plugin_dir(tmp_path):
    root = _plugin(tmp_path, "print(1)")
    spec, error = build_spec(plugin_id="ok", plugin_dir=root, entry="../evil.py")
    assert spec is None and "outside" in error
    spec, error = build_spec(plugin_id="ok", plugin_dir=root, entry="tool.py", allowed_roots=("/etc",))
    assert spec is None and "absolute" in error
    spec, error = build_spec(plugin_id="ok", plugin_dir=root, entry="tool.py", timeout_seconds=0)
    assert spec is None and "timeout" in error
    spec, error = build_spec(plugin_id="ok", plugin_dir=root, entry="missing.py")
    assert spec is None and "not a file" in error


def test_confined_argv_uses_the_reused_builders(tmp_path):
    root = _plugin(tmp_path, "print(1)")
    spec = _spec(root, timeout_seconds=30.0)
    home = mcp_sandbox.home_for(f"plugin_{PLUGIN_ID}")
    argv = confined_argv(
        spec.child_argv()[0], spec.child_argv()[1:], str(home), spec.read_roots()
    )
    boundary = mcp_sandbox.platform_boundary()
    if boundary == "unavailable":
        assert argv is None
    else:
        assert argv is not None and argv[0] in ("sandbox-exec", "bwrap")
        assert str(spec.entry_path()) in argv


def test_policy_snapshot_states_every_ceiling_in_the_fixed_words():
    snapshot = policy_snapshot()
    assert snapshot["boundary_here"] in ("seatbelt", "bubblewrap", "unavailable")
    for name, statement in snapshot["ceilings"].items():
        assert statement.split(" ", 1)[0].rstrip("—- ") in (
            "enforced", "not_enforced", "bounded",
        ), name
    assert snapshot["ceilings"]["filesystem_capacity"].startswith("not_enforced")
    assert snapshot["ceilings"]["cpu_seconds"].startswith("not_enforced")
    assert "windows" in snapshot["platform_notes"]
    assert "no confinement rung" in snapshot["platform_notes"]["windows"]
    assert set(snapshot["statuses"]) == set(STATUSES)


@capabilities.requires_boundary
def test_a_declared_memory_ceiling_runs_the_tool_and_says_what_the_os_allowed(tmp_path):
    """Measured here: macOS refuses every finite RLIMIT_AS, so a declared cap cannot kill a run.

    The bootstrap let that `ValueError` escape and the child died at exit code 1 before it
    loaded the plugin, which made every tool that declared a ceiling fail on this machine.
    What a ceiling buys now is the child's own verdict, carried on the outcome.
    """
    spec = _spec(
        _plugin(tmp_path, "print('capped worker ran')"),
        timeout_seconds=30.0, memory_cap_mb=256,
    )
    outcome = run_worker(spec)
    assert outcome.status == "ok", outcome.note + outcome.stderr
    assert outcome.memory_ceiling in ("applied", "refused")
    if sys.platform == "darwin":
        assert outcome.memory_ceiling == "refused", outcome.stderr


@capabilities.requires_boundary
def test_a_run_that_declared_no_ceiling_reports_no_verdict(tmp_path):
    spec = _spec(_plugin(tmp_path, "print(1)"), timeout_seconds=30.0)
    outcome = run_worker(spec)
    assert outcome.status == "ok"
    assert outcome.memory_ceiling == ""
