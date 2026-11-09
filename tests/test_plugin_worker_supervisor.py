"""Task #47: the plugin worker supervisor — crash, timeout, OOM, exit classification.

Every test drives a real confined child through `core.sandbox.run_worker` on this
machine's boundary (Seatbelt on macOS; the same rail the MCP children already
run under). The vocabulary asserted here is the vocabulary tasks #9 and #38
consume: a fixed status, never an exception string.
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
    Refusal,
    RestartBudget,
    STATUSES,
    WorkerSpec,
    build_spec,
    confined_argv,
    policy_snapshot,
    run_worker,
)

PLUGIN_ID = "w47demo"


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


def test_ok_child_exit_and_output(tmp_path):
    spec = _spec(_plugin(tmp_path, "print('hello worker')"), timeout_seconds=30.0)
    outcome = run_worker(spec)
    assert outcome.status == "ok", outcome.note + outcome.stderr
    assert "hello worker" in outcome.stdout
    assert outcome.exit_code == 0


def test_nonzero_exit_is_classified_not_raised(tmp_path):
    spec = _spec(_plugin(tmp_path, "import sys; sys.exit(3)"), timeout_seconds=30.0)
    outcome = run_worker(spec)
    assert outcome.status == "nonzero"
    assert outcome.exit_code == 3


def test_signal_death_is_crashed(tmp_path):
    body = "import os, signal; os.kill(os.getpid(), signal.SIGTERM)"
    spec = _spec(_plugin(tmp_path, body), timeout_seconds=30.0)
    outcome = run_worker(spec)
    assert outcome.status == "crashed"
    assert outcome.signal_number == int(signal.SIGTERM)


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


def test_oom_path_classified_from_exit_status(tmp_path):
    # An unasked-for SIGKILL is the kernel OOM-killer's signature on Linux. The
    # kernel path itself is unmeasured on this machine (macOS has no such kill);
    # the classification is provoked through the exit status, exactly as the
    # task demands, and `policy_snapshot` says the same in words.
    body = "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"
    spec = _spec(_plugin(tmp_path, body), timeout_seconds=30.0)
    outcome = run_worker(spec)
    assert outcome.status == "oom"
    assert outcome.signal_number == int(signal.SIGKILL)


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


def test_a_run_that_declared_no_ceiling_reports_no_verdict(tmp_path):
    spec = _spec(_plugin(tmp_path, "print(1)"), timeout_seconds=30.0)
    outcome = run_worker(spec)
    assert outcome.status == "ok"
    assert outcome.memory_ceiling == ""
