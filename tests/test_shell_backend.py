"""Issue #19 — Runs-anywhere: Docker execution backend for run_shell.

Opt-in via EPHE_SHELL_BACKEND=docker: the workspace is mounted as /workspace
into a per-workspace container. Without the env, run_shell stays byte-identically local
(existing pins cover that). Fail-closed: an unusable daemon yields a clear configuration
error, never a silent local fallback.
Command validation (whitelist/blocked patterns) applies BEFORE the backend.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from core.tools import shell_tools
from core.tools import _shell_exec
from core.tools import _shell_proc
from core.tools.shell_tools import run_shell, _shell_backend

docker_ready = shutil.which("docker") is not None
if docker_ready:
    probe = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=30)
    docker_ready = probe.returncode == 0

# Deliberately not a module-level `pytestmark`: the env -> backend decision is pure and
# has to be pinned on every machine. As a module marker the whole file skipped without a
# docker daemon, so even the one existing local-backend pin never ran off a docker runner.
docker_required = pytest.mark.skipif(not docker_ready, reason="docker daemon not available")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "hello.txt").write_text("mount-check", encoding="utf-8")
    monkeypatch.setenv("EPHE_SHELL_BACKEND", "docker")
    # Set the workspace through an isolated engine.json (single source) —
    # the resolver reads get_workspace_dir(), never an env.
    import json

    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "engine.json").write_text(
        json.dumps({"provider": "local_ollama", "model": "test-model", "workspace_dir": str(ws)}),
        encoding="utf-8",
    )
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))
    import core.engine_config as ec

    monkeypatch.setattr(ec, "CONFIG_DIR", cfg)
    yield ws
    shell_tools._docker_teardown()


@docker_required
@pytest.mark.asyncio
async def test_given_docker_backend_when_echo_then_stdout_flows(workspace):
    out = await run_shell("echo docker-hello")
    assert "docker-hello" in out


@docker_required
@pytest.mark.asyncio
async def test_given_docker_backend_when_ls_workspace_then_host_files_visible(workspace):
    """The end-state proof: the container sees the HOST workspace files
    (bind mount) — ls inside the container lists hello.txt from the host."""
    out = await run_shell("ls /workspace")
    assert "hello.txt" in out


@docker_required
@pytest.mark.asyncio
async def test_given_docker_backend_when_cat_mounted_file_then_content_matches(workspace):
    out = await run_shell("cat /workspace/hello.txt")
    assert "mount-check" in out


@docker_required
@pytest.mark.asyncio
async def test_given_blocked_command_when_docker_backend_then_rejected_identically(workspace):
    """Validation runs BEFORE the backend — the gate text is identical locally."""
    out = await run_shell("rm -rf /")
    assert "not allowed" in out.lower() or "blocked" in out.lower() or "nicht erlaubt" in out.lower()


@docker_required
@pytest.mark.asyncio
async def test_given_unusable_daemon_when_docker_backend_then_fail_closed(monkeypatch, workspace):
    """No silent local fallback: an unusable daemon → a clear error with a fix hint.
    (the workspace fixture = CONFIG_DIR isolation: without it the macOS Seatbelt
    sandbox is auto-active and conservatively wins against the backend env.)"""
    monkeypatch.setenv("EPHE_SHELL_BACKEND", "docker")

    def broken(*_a, **_kw):
        return subprocess.CompletedProcess(args=["docker"], returncode=1, stdout="", stderr="Cannot connect to the Docker daemon")

    # _docker_exec is defined inside _shell_proc and resolves _docker_run there from
    # the module globals — the patch has to target _shell_proc, otherwise
    # the mock never fires (shell_tools only re-exports the names, lines 20-33).
    monkeypatch.setattr(_shell_proc, "_docker_run", broken)
    monkeypatch.setattr(shell_tools, "_docker_run", broken)
    out = await run_shell("echo hello")
    assert "[docker backend error]" in out
    assert "EPHE_SHELL_BACKEND" in out


def test_given_no_env_when_backend_resolved_then_local(monkeypatch):
    """GIVEN the variable is absent
    THEN local — the docker backend is opt-in only (no silent default)."""
    monkeypatch.delenv("EPHE_SHELL_BACKEND", raising=False)
    assert _shell_backend() == "local"


# The env -> backend decision (pure: no daemon and no container needed)
# Why these pins exist: the read was `get(X) or get(X, "").strip().lower() == "docker"`,
# where the FIRST operand is the un-normalised string and wins whenever it is non-empty.
# So the mere PRESENCE of the variable selected the container — `EPHE_SHELL_BACKEND=local`
# measured "docker", and a whitespace-only value measured "docker" too. Normalising once
# is the whole fix; nothing else in this file would notice a regression.


@pytest.mark.parametrize("value", ["local", "LOCAL", "Local", "podman", ""])
def test_given_non_docker_value_when_backend_resolved_then_local(monkeypatch, value):
    """GIVEN EPHE_SHELL_BACKEND set to any value that is not docker (including empty)
    THEN the command still runs on the host — "local" has to mean local."""
    monkeypatch.setenv("EPHE_SHELL_BACKEND", value)
    assert _shell_backend() == "local"


def test_given_blank_value_when_backend_resolved_then_local(monkeypatch):
    """GIVEN EPHE_SHELL_BACKEND="   " (whitespace only)
    THEN local — a blank variable reads as unset, never as a container opt-in."""
    monkeypatch.setenv("EPHE_SHELL_BACKEND", "   ")
    assert _shell_backend() == "local"


@pytest.mark.parametrize("value", ["docker", "DOCKER", "Docker", " docker ", "docker\n"])
def test_given_docker_value_when_backend_resolved_then_docker(monkeypatch, value):
    """GIVEN a genuine docker value, however cased or padded
    THEN docker — the normalisation that makes the pins above safe must not get lost."""
    monkeypatch.setenv("EPHE_SHELL_BACKEND", value)
    assert _shell_backend() == "docker"


# The branch, not just the string
# A wrong resolution is not cosmetic: _shell_exec.execute_confirmed_shell() reads the
# backend at line 206 and routes EVERY command of that run into the per-workspace
# container. Under the double read `EPHE_SHELL_BACKEND=local` resolved to "docker", so a
# user who wrote down "stay on the host" got off-host execution with the workspace
# bind-mounted and the Seatbelt wrapper out of the picture.
# These pins stub the container entry itself, so they need no daemon. The docker case is
# not decoration: it is the control proving the branch is reachable here — an active
# Seatbelt sandbox takes the local path BEFORE the backend is consulted, which would turn
# the "never reached the container" assertions into a vacuous green.


def _stub_container(monkeypatch) -> list[str]:
    """Replace the docker entry in both namespaces that resolved it (see the
    `_docker_run` note above in the fail-closed test)."""
    calls: list[str] = []

    def fake_exec(command: str, _workspace: Path) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(args=["docker"], returncode=0, stdout="ran-in-container", stderr="")

    monkeypatch.setattr(_shell_proc, "_docker_exec", fake_exec)
    monkeypatch.setattr(_shell_exec, "_docker_exec", fake_exec)
    return calls


async def test_given_docker_value_when_run_shell_then_container_branch_is_reached(workspace, monkeypatch):
    """GIVEN EPHE_SHELL_BACKEND=docker and a stubbed container call
    THEN the branch fires — the control for the pin below (no daemon needed: the
    container entry itself is stubbed, so this runs on a daemon-less machine too)."""
    calls = _stub_container(monkeypatch)
    out = await run_shell("echo hi")

    assert calls == ["echo hi"], "the backend branch has to be reachable on this machine"
    assert "ran-in-container" in out


@pytest.mark.parametrize("value", ["local", "   ", "podman", ""])
async def test_given_non_docker_value_when_run_shell_then_never_reaches_the_container(
    workspace, monkeypatch, value
):
    """GIVEN EPHE_SHELL_BACKEND naming anything but docker
    THEN the command runs on the host and the container entry is never called.

    The `workspace` fixture keeps the config dir isolated: without it the auto-active
    Seatbelt sandbox would win against the backend env and this assertion would hold for
    the wrong reason (that is what the control test above rules out)."""
    calls = _stub_container(monkeypatch)
    monkeypatch.setenv("EPHE_SHELL_BACKEND", value)
    out = await run_shell("echo host-only")

    assert calls == [], f"EPHE_SHELL_BACKEND={value!r} must not route through the docker branch"
    assert "host-only" in out

