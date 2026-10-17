"""WS2-12 — what a run_shell command executes in, and what a missing sandbox records.

`core/tools/_shell_validate.py` bounds the command text; these pins bound the target
behind that guard: which container the docker backend may reuse, which surface the PTY
route reaches, and what the audit says when a configured sandbox has no wrapper on the
host. The backend runs against a stubbed `_docker_run`, so nothing here needs a daemon.

docs/HOST_EXEC_BOUNDARY_REVIEW_2026-10-11.md names the findings; G1 and G2 carry
receipt tests below so a later change to either boundary has to face them.
"""
from __future__ import annotations

import asyncio
import json
import subprocess

import pytest

from core.tools import _shell_exec, _shell_proc


def _result(args, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args=args, returncode=returncode, stdout=stdout, stderr=stderr)


def _labels(image, workspace=None, managed=True):
    labels = {}
    if managed:
        labels[_shell_proc._MANAGED_LABEL] = "1"
        labels[_shell_proc._WORKSPACE_LABEL] = str(workspace)
        labels[_shell_proc._IMAGE_LABEL] = image
    return labels


def _container(image, workspace, *, running=True, managed=True):
    return json.dumps([{
        "Config": {"Image": image, "Labels": _labels(image, workspace, managed)},
        "State": {"Running": running},
    }])


class _FakeDocker:
    """Answers by the subcommand in argv[1] and records every call."""

    def __init__(self, inspect_stdout=None, info_rc=0, run_rc=0):
        self.calls: list[list[str]] = []
        self.inspect_stdout = inspect_stdout
        self.info_rc = info_rc
        self.run_rc = run_rc

    def __call__(self, args, timeout=60.0):
        self.calls.append(list(args))
        sub = args[1] if len(args) > 1 else ""
        if sub == "info":
            return _result(args, self.info_rc, "Server Version: 27.0", "cannot connect")
        if sub == "inspect":
            if self.inspect_stdout is None:
                return _result(args, 1, "", "Error: No such object")
            return _result(args, 0, self.inspect_stdout, "")
        if sub == "run":
            return _result(args, self.run_rc, "container-id", "run refused")
        if sub == "start":
            return _result(args, 0)
        raise AssertionError(f"unexpected docker call: {args}")

    def argv_of(self, sub):
        return [c for c in self.calls if len(c) > 1 and c[1] == sub]


def test_given_no_container_when_ensured_then_created_labelled_and_mounted(tmp_path, monkeypatch):
    docker = _FakeDocker(inspect_stdout=None)
    monkeypatch.setattr(_shell_proc, "_docker_run", docker)
    ws = tmp_path / "ws"
    ws.mkdir()

    name = _shell_proc._ensure_docker_container(ws)

    assert name == _shell_proc._docker_container_name(ws)
    run = docker.argv_of("run")[0]
    assert f"{_shell_proc._MANAGED_LABEL}=1" in run
    assert f"{_shell_proc._WORKSPACE_LABEL}={ws}" in run
    assert f"{_shell_proc._IMAGE_LABEL}={_shell_proc._docker_image()}" in run
    assert run[run.index("--security-opt") + 1] == "no-new-privileges"
    mounts = [run[i + 1] for i, token in enumerate(run) if token == "-v"]
    assert mounts == [f"{ws}:/workspace"], "the workspace is the only host path offered"


def test_given_foreign_container_on_the_managed_name_when_ensured_then_refused(tmp_path, monkeypatch):
    """A name match is not provenance: a container without our labels is never used."""
    docker = _FakeDocker(inspect_stdout=_container("attacker/img:latest", None, managed=False))
    monkeypatch.setattr(_shell_proc, "_docker_run", docker)
    ws = tmp_path / "ws"
    ws.mkdir()
    name = _shell_proc._docker_container_name(ws)

    with pytest.raises(RuntimeError) as excinfo:
        _shell_proc._ensure_docker_container(ws)

    message = str(excinfo.value)
    assert name in message
    assert f"docker rm -f {name}" in message
    assert not docker.argv_of("run") and not docker.argv_of("exec")


def test_given_managed_container_on_another_image_when_ensured_then_refused(tmp_path, monkeypatch):
    """EPHE_DOCKER_IMAGE moved on while the old container still runs: refuse it."""
    ws = tmp_path / "ws"
    ws.mkdir()
    stale = _container("python:3.9-slim", ws, running=True)
    docker = _FakeDocker(inspect_stdout=stale)
    monkeypatch.setattr(_shell_proc, "_docker_run", docker)

    with pytest.raises(RuntimeError, match="refusing"):
        _shell_proc._ensure_docker_container(ws)
    assert not docker.argv_of("run")


def test_given_verified_running_container_when_ensured_then_reused_without_run(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    image = _shell_proc._docker_image()
    docker = _FakeDocker(inspect_stdout=_container(image, ws, running=True))
    monkeypatch.setattr(_shell_proc, "_docker_run", docker)

    name = _shell_proc._ensure_docker_container(ws)

    assert name == _shell_proc._docker_container_name(ws)
    assert not docker.argv_of("run") and not docker.argv_of("start")


def test_given_verified_stopped_container_when_ensured_then_started(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    docker = _FakeDocker(inspect_stdout=_container(_shell_proc._docker_image(), ws, running=False))
    monkeypatch.setattr(_shell_proc, "_docker_run", docker)

    _shell_proc._ensure_docker_container(ws)

    assert docker.argv_of("start") and not docker.argv_of("run")


@pytest.mark.parametrize("answer", ["not json at all", "{}"])
def test_given_unreadable_inspect_answer_when_ensured_then_refused(tmp_path, monkeypatch, answer):
    """An inspect answer that is not the container array leaves the container unverified."""
    docker = _FakeDocker(inspect_stdout=answer)
    monkeypatch.setattr(_shell_proc, "_docker_run", docker)
    ws = tmp_path / "ws"
    ws.mkdir()

    with pytest.raises(RuntimeError):
        _shell_proc._ensure_docker_container(ws)
    assert not docker.argv_of("run")


def test_given_unusable_daemon_when_ensured_then_fail_closed_before_any_inspect(tmp_path, monkeypatch):
    docker = _FakeDocker(info_rc=1)
    monkeypatch.setattr(_shell_proc, "_docker_run", docker)
    ws = tmp_path / "ws"
    ws.mkdir()

    with pytest.raises(RuntimeError, match="EPHE_SHELL_BACKEND"):
        _shell_proc._ensure_docker_container(ws)
    assert not docker.argv_of("inspect")


def test_closed_a_docker_segment_cannot_reach_the_host_root():
    """CLOSED (G1, WB-13) — `docker`/`docker-compose` stay in ALLOWED_COMMANDS, but the
    segment now carries its own read-only subcommand allowlist (WB-13): the head check is
    binding again. `run`/`exec`/`create`/`build`/… and the host-handing flags
    (`-v /:/host`, `--privileged`, `--mount`, …) are refused, so the container command and
    its mounts no longer slip past the whitelist. The receipt flipped the day the head
    gained its own subcommand allowlist.
    """
    from core.tools.shell_tools import validate_shell_command

    escape = "docker run --privileged -v /:/host alpine sh -c 'cat /host/etc/shadow'"
    refusal = validate_shell_command(escape)
    assert refusal is not None and "⚠" in refusal


def test_recorded_the_container_keeps_the_daemon_default_network_and_user(tmp_path, monkeypatch):
    """RECORDED ACCEPTED (G2) — pip/npm installs need egress and most images assume root,
    so this backend is a runs-anywhere exec target and its isolation stops at the
    workspace bind mount. The Seatbelt profile denies network; the container does not,
    and the review states the difference.
    """
    docker = _FakeDocker(inspect_stdout=None)
    monkeypatch.setattr(_shell_proc, "_docker_run", docker)
    ws = tmp_path / "ws"
    ws.mkdir()

    _shell_proc._ensure_docker_container(ws)

    run = docker.argv_of("run")[0]
    assert "--network" not in run
    assert "--net" not in run
    assert "--user" not in run


def test_recorded_the_pty_route_stays_on_the_host(tmp_path, monkeypatch):
    """RECORDED ACCEPTED (G3) — `run_shell_pty` executes shell=True locally and consults
    neither the backend nor the sandbox: an interactive terminal cannot be rebuilt through
    `docker exec` without a TTY. With EPHE_SHELL_BACKEND=docker the command still runs on
    the host, which is the surface the review names.
    """
    monkeypatch.setenv("EPHE_SHELL_BACKEND", "docker")

    def refuse(*_args, **_kwargs):
        raise AssertionError("the PTY route must not touch the container backend")

    monkeypatch.setattr(_shell_proc, "_docker_exec", refuse)
    monkeypatch.setattr(_shell_exec, "_docker_exec", refuse)
    monkeypatch.setattr(_shell_exec, "_resolve_cwd", lambda _cwd: str(tmp_path))

    from core.tools.shell_tools import run_shell_pty

    out = run_shell_pty("echo pty-on-host")

    assert "pty-on-host" in out


def test_given_sandbox_configured_without_a_wrapper_then_the_audit_records_it(tmp_path, monkeypatch):
    """GIVEN sandbox_enabled and a host without the OS wrapper (sandbox-exec is macOS-only)
    WHEN a command runs THEN it executes unsandboxed and the audit detail carries
    'sandbox-unavailable'. That detail is the close of finding G4: the fallback is visible
    in the shell audit line instead of disappearing.
    """
    from types import SimpleNamespace

    import core.audit_log as audit_log
    import core.security_config as security_config
    import core.shell_sandbox as shell_sandbox

    monkeypatch.setattr(security_config, "load_security_config",
                        lambda: SimpleNamespace(sandbox_enabled=True))
    monkeypatch.setattr(shell_sandbox, "wrap_command", lambda *_a, **_k: None)
    monkeypatch.setattr(_shell_exec, "_resolve_cwd", lambda _cwd: str(tmp_path))
    events: list[dict] = []
    monkeypatch.setattr(audit_log, "audit_event",
                        lambda kind, **kw: events.append({"kind": kind, **kw}))

    out = asyncio.run(_shell_exec.execute_confirmed_shell("echo still-here", True))

    assert "still-here" in out
    shell = [e for e in events if e["kind"] == "shell"]
    assert shell and shell[-1]["status"] == "executed"
    assert "sandbox-unavailable" in shell[-1]["detail"]


# WB-16: the sandbox target decision is one host-independent resolver. A host that
# lacks the OS wrapper (Linux; or macOS with the binary removed) and a host that has it
# (macOS) have to read the SAME audit surface, so the branch and its word live in
# _shell_proc.resolve_sandbox and every host drives that one function. The unit pins
# call it directly; the execution pins read the audit line back.


def _capture_shell_audit(monkeypatch):
    """Collect audit_event calls so a pin can read the shell line back."""
    import core.audit_log as audit_log

    events: list[dict] = []
    monkeypatch.setattr(audit_log, "audit_event",
                        lambda kind, **kw: events.append({"kind": kind, **kw}))
    return events


def _last_shell_line(events):
    shell = [e for e in events if e["kind"] == "shell"]
    assert shell, "no shell audit line was written"
    return shell[-1]


def _set_sandbox(monkeypatch, *, enabled: bool, wrapper: bool):
    """Drive the real decision: the config flag plus whether sandbox-exec is on PATH.

    `wrapper=False` is the Linux host and the macOS with the binary removed: the real
    `shell_sandbox.wrap_command` answers None because `is_available()` is False, so the
    resolver branch under test is the production one rather than a stubbed return.
    """
    from types import SimpleNamespace

    import core.security_config as security_config
    import core.shell_sandbox as shell_sandbox

    monkeypatch.setattr(security_config, "load_security_config",
                        lambda: SimpleNamespace(sandbox_enabled=enabled))
    monkeypatch.setattr(shell_sandbox, "is_available", lambda: wrapper)


def test_resolve_sandbox_off_returns_no_wrapper_and_no_detail(monkeypatch):
    _set_sandbox(monkeypatch, enabled=False, wrapper=True)
    assert _shell_proc.resolve_sandbox("echo hi", "/tmp") == (None, "")


def test_resolve_sandbox_on_without_a_wrapper_reads_unavailable_on_any_host(monkeypatch):
    """Linux without sandbox-exec and macOS with the binary removed read the same word."""
    _set_sandbox(monkeypatch, enabled=True, wrapper=False)
    argv, detail = _shell_proc.resolve_sandbox("echo hi", "/tmp")
    assert argv is None
    assert detail == _shell_proc.SANDBOX_UNAVAILABLE == "sandbox-unavailable"


def test_resolve_sandbox_on_with_a_wrapper_returns_argv_and_no_detail(monkeypatch):
    _set_sandbox(monkeypatch, enabled=True, wrapper=True)
    argv, detail = _shell_proc.resolve_sandbox("echo hi", "/tmp")
    assert argv is not None and argv[0] == "sandbox-exec"
    assert detail == ""


def test_sandbox_off_runs_locally_with_a_clean_audit_detail(tmp_path, monkeypatch):
    events = _capture_shell_audit(monkeypatch)
    _set_sandbox(monkeypatch, enabled=False, wrapper=True)
    monkeypatch.setattr(_shell_exec, "_resolve_cwd", lambda _cwd: str(tmp_path))

    out = asyncio.run(_shell_exec.execute_confirmed_shell("echo plain", True))

    assert "plain" in out
    line = _last_shell_line(events)
    assert line["status"] == "executed"
    assert "sandbox-unavailable" not in line["detail"]


def test_sandbox_active_runs_wrapped_and_records_sandboxed(tmp_path, monkeypatch):
    events = _capture_shell_audit(monkeypatch)
    _set_sandbox(monkeypatch, enabled=True, wrapper=True)
    monkeypatch.setattr(_shell_exec, "_resolve_cwd", lambda _cwd: str(tmp_path))
    # The Seatbelt wrapper runs `sandbox-exec` for real; stub the process edge so the
    # pin asserts the branch and the audit word, not a host toolchain.
    monkeypatch.setattr(_shell_exec, "_exec_sync", lambda *_a, **_k: _result([], 0, "wrapped-ok"))

    out = asyncio.run(_shell_exec.execute_confirmed_shell("echo wrapped", True))

    assert "wrapped-ok" in out
    line = _last_shell_line(events)
    assert line["status"] == "sandboxed"
    assert line["detail"] == ""


def test_local_fallback_without_a_wrapper_records_sandbox_unavailable(tmp_path, monkeypatch):
    """The G4 surface again, this time through the real wrap_command rather than a stub."""
    events = _capture_shell_audit(monkeypatch)
    _set_sandbox(monkeypatch, enabled=True, wrapper=False)
    monkeypatch.setattr(_shell_exec, "_resolve_cwd", lambda _cwd: str(tmp_path))

    out = asyncio.run(_shell_exec.execute_confirmed_shell("echo still-here", True))

    assert "still-here" in out
    line = _last_shell_line(events)
    assert line["status"] == "executed"
    assert line["detail"] == "sandbox-unavailable"


def test_docker_backend_without_a_wrapper_records_the_missing_sandbox(tmp_path, monkeypatch):
    events = _capture_shell_audit(monkeypatch)
    _set_sandbox(monkeypatch, enabled=True, wrapper=False)
    monkeypatch.setattr(_shell_exec, "_resolve_cwd", lambda _cwd: str(tmp_path))
    monkeypatch.setattr(_shell_exec, "_shell_backend", lambda: "docker")
    monkeypatch.setattr(_shell_exec, "_docker_exec", lambda *_a, **_k: _result([], 0, "in-container"))

    out = asyncio.run(_shell_exec.execute_confirmed_shell("echo container", True))

    assert "in-container" in out
    line = _last_shell_line(events)
    assert line["status"] == "executed"
    assert line["detail"] == "backend=docker sandbox-unavailable"


def test_docker_backend_without_a_sandbox_configured_has_no_missing_marker(tmp_path, monkeypatch):
    events = _capture_shell_audit(monkeypatch)
    _set_sandbox(monkeypatch, enabled=False, wrapper=False)
    monkeypatch.setattr(_shell_exec, "_resolve_cwd", lambda _cwd: str(tmp_path))
    monkeypatch.setattr(_shell_exec, "_shell_backend", lambda: "docker")
    monkeypatch.setattr(_shell_exec, "_docker_exec", lambda *_a, **_k: _result([], 0, "in-container"))

    asyncio.run(_shell_exec.execute_confirmed_shell("echo container", True))

    assert _last_shell_line(events)["detail"] == "backend=docker"
