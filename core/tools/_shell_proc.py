"""Ephe – run_shell / execute_confirmed_shell tools."""

from __future__ import annotations

import atexit
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from core.tools.base import (
    SHELL_TIMEOUT_SECONDS,
)
from core.secret_broker import child_env

# Issue #19 (Runs-anywhere): Execution-Backends — local (default) | docker
# Opt-in via EPHE_SHELL_BACKEND=docker; without the env, byte-identical locally.
# The workspace is mounted as /workspace into a per-workspace container,
# created lazily and cleaned up at process end. Fail-closed: if the
# Docker daemon is unusable, run_shell returns a clear configuration error
# — never a silent local fallback (no-silent-default philosophy).
_DOCKER_MANAGED: set[str] = set()


def _new_group_kwargs() -> dict:
    """W17 P0-1: child as group leader — killpg reaps the whole family."""
    if sys.version_info >= (3, 11):
        return {"start_new_session": True}
    return {"preexec_fn": os.setsid}


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def _reap(proc: "subprocess.Popen") -> None:
    """Collect the exit status after the group kill (no zombie left in Popen)."""
    for _ in range(20):
        if proc.poll() is not None:
            return
        time.sleep(0.01)


def _shell_backend() -> str:
    """Execution target at call time: 'local' (default) or 'docker'.

    Normalised ONCE and compared to the docker value: the previous
    `get(X) or get(X, "").strip().lower() == "docker"` let the un-normalised first
    operand win whenever the variable held anything non-empty, so
    `EPHE_SHELL_BACKEND=local` (and a blank "   ") silently ran every command inside
    the container. Only a genuine docker value opts in.
    """
    return "docker" if os.environ.get("EPHE_SHELL_BACKEND", "").strip().lower() == "docker" else "local"


# WB-16: one host-independent sandbox target decision. sandbox-exec is macOS-only, so a
# Linux host and a macOS with the binary removed have to read the SAME outcome; keeping
# the branch and its audit word in one function is what stops the surface from drifting
# apart between platforms.
SANDBOX_UNAVAILABLE = "sandbox-unavailable"


def resolve_sandbox(command: str, workspace: str) -> tuple[list[str] | None, str]:
    """Pick the OS sandbox wrapper for this host and name the outcome in one shot.

    Returns (argv, detail):
      (argv, "")                      wrapper active — run wrapped
      (None, "sandbox-unavailable")   configured, but this host has no wrapper
      (None, "")                      sandbox switched off
    """
    from core.security_config import load_security_config

    if not load_security_config().sandbox_enabled:
        return None, ""
    from core.shell_sandbox import wrap_command

    argv = wrap_command(command, workspace)
    if argv is None:
        return None, SANDBOX_UNAVAILABLE
    return argv, ""


def _docker_image() -> str:
    return os.environ.get("EPHE_DOCKER_IMAGE", "python:3.12-slim")


def _docker_run(args: list[str], timeout: float = 60.0) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, env=child_env()
    )


def _docker_container_name(workspace: Path) -> str:
    digest = hashlib.sha1(str(workspace).encode("utf-8")).hexdigest()[:10]
    return f"ephe-shell-{digest}"


# WS2-12: a container is trusted only when it still carries the labels this backend
# wrote. The name is a guessable hash of the workspace path and survives a SIGKILL
# (atexit never ran), so a name match alone cannot vouch for what runs the command.
_MANAGED_LABEL = "com.ephe.shell.managed"
_WORKSPACE_LABEL = "com.ephe.shell.workspace"
_IMAGE_LABEL = "com.ephe.shell.image"


def _created_labels(workspace: Path, image: str) -> list[str]:
    return [
        "--label", f"{_MANAGED_LABEL}=1",
        "--label", f"{_WORKSPACE_LABEL}={workspace}",
        "--label", f"{_IMAGE_LABEL}={image}",
    ]


def _inspect_container(name: str) -> dict | None:
    raw = _docker_run(["docker", "inspect", name], timeout=20)
    if raw.returncode != 0:
        return None
    try:
        return json.loads(raw.stdout)[0]
    except (ValueError, IndexError, KeyError, TypeError):
        # Exists but unreadable: {} fails every label check, so it stays unverified.
        return {}


def _is_managed(info: dict, workspace: Path, image: str) -> bool:
    """True only for a container this backend created for this workspace and image."""
    labels = (info.get("Config") or {}).get("Labels") or {}
    return (
        labels.get(_MANAGED_LABEL) == "1"
        and labels.get(_WORKSPACE_LABEL) == str(workspace)
        and labels.get(_IMAGE_LABEL) == image
    )


def _ensure_docker_container(workspace: Path) -> str:
    """Create-or-reuse the per-workspace container, verifying a reuse by label.

    Raises RuntimeError with a fix hint when the daemon is unusable (no silent
    fallback) or when a container already holds the managed name without the
    labels this backend wrote — a stale or foreign container is never exec'd into.
    """
    name = _docker_container_name(workspace)
    image = _docker_image()
    probe = _docker_run(["docker", "info"], timeout=20)
    if probe.returncode != 0:
        raise RuntimeError(
            "EPHE_SHELL_BACKEND=docker, but the docker daemon is not usable — "
            "start Docker (or the daemon) or unset EPHE_SHELL_BACKEND. "
            f"(docker info: {(probe.stderr or probe.stdout).strip()[:160]})"
        )

    info = _inspect_container(name)
    if info is None:
        run = _docker_run(
            [
                "docker", "run", "-d", "--name", name,
                *_created_labels(workspace, image),
                "--security-opt", "no-new-privileges",
                "-v", f"{workspace}:/workspace",
                "-w", "/workspace",
                image, "sleep", "infinity",
            ],
            timeout=180,
        )
        if run.returncode != 0:
            raise RuntimeError(f"docker run failed: {(run.stderr or run.stdout).strip()[:200]}")
        _DOCKER_MANAGED.add(name)
        return name

    if not _is_managed(info, workspace, image):
        raise RuntimeError(
            f"EPHE_SHELL_BACKEND=docker: a container named '{name}' already exists but is not "
            f"the Ephe container for {workspace} on {image} — refusing to run commands inside it. "
            f"Inspect it (`docker inspect {name}`) and drop it with `docker rm -f {name}`, or point "
            "EPHE_DOCKER_IMAGE at the image it was created from."
        )

    if (info.get("State") or {}).get("Running"):
        return name
    start = _docker_run(["docker", "start", name], timeout=60)
    if start.returncode != 0:
        raise RuntimeError(f"docker start {name} failed: {start.stderr.strip()[:160]}")
    return name


def _docker_teardown() -> None:
    """Remove the containers this process created (best effort)."""
    for name in list(_DOCKER_MANAGED):
        try:
            _docker_run(["docker", "rm", "-f", name], timeout=60)
        except Exception:
            pass
        _DOCKER_MANAGED.discard(name)


atexit.register(_docker_teardown)


def _docker_exec(command: str, workspace: Path) -> "subprocess.CompletedProcess[str]":
    """Run command in the container (workspace mounted as /workspace)."""
    name = _ensure_docker_container(workspace)
    argv = ["docker", "exec", "-w", "/workspace", name, "sh", "-c", command]
    return _exec_sync(argv, None, False)


def _exec_sync(command, cwd: "str | None", use_shell: bool):
    """P0-1: Popen instead of run — on timeout the process group is reaped."""
    from core.tools.cancel_scope import register_group, unregister_group

    proc = subprocess.Popen(
        command,
        shell=use_shell,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=cwd,
        env=child_env(),
        **_new_group_kwargs(),
    )
    register_group(proc.pid)
    try:
        out, err = proc.communicate(timeout=SHELL_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        _kill_group(proc.pid)
        _reap(proc)
        raise
    finally:
        unregister_group(proc.pid)
    return subprocess.CompletedProcess(
        args=command, returncode=proc.returncode, stdout=out, stderr=err
    )
