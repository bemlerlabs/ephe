"""The opted-in shell profile writes the workspace and closes the rest.

Network is denied, including a listener on loopback. A write inside the
canonical workspace succeeds. A write under the home directory, outside that
workspace, fails and leaves no file. The product switch stays off.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from core import shell_sandbox
from core.security_config import SecurityConfig


def test_the_profile_denies_network_and_the_rest_of_home():
    profile = shell_sandbox.build_profile("/tmp/ws")
    home = os.path.realpath(os.path.expanduser("~"))
    assert "(deny network*)" in profile
    assert "network-bind" not in profile
    assert '(subpath "/tmp/ws")' in profile or '(subpath "/private/tmp/ws")' in profile
    assert f'(subpath "{home}")' not in profile
    assert '(literal "/dev/null")' in profile


def test_the_sandbox_switch_defaults_off():
    assert SecurityConfig().sandbox_enabled is False


def test_bwrap_hides_home_and_binds_the_workspace(monkeypatch, tmp_path):
    def _which(name: str) -> str | None:
        return "/usr/bin/bwrap" if name == "bwrap" else None

    monkeypatch.setattr(shell_sandbox, "_which", _which)
    argv = shell_sandbox.wrap_command("echo hi", str(tmp_path))
    assert argv is not None and argv[0] == "bwrap"
    assert "--unshare-net" in argv
    home = os.path.realpath(os.path.expanduser("~"))
    workspace = os.path.realpath(tmp_path)
    assert argv.index(home) < argv.index("--bind")
    bind = argv.index("--bind")
    assert argv[bind + 1] == workspace and argv[bind + 2] == workspace


pytestmark_sandbox = pytest.mark.skipif(
    not shell_sandbox.is_available(), reason="sandbox-exec exists on macOS only"
)


def _run_in_sandbox(workspace, script: str) -> subprocess.CompletedProcess[str]:
    argv = shell_sandbox.wrap_command(f"{sys.executable} {script}", str(workspace))
    assert argv is not None
    return subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)


@pytestmark_sandbox
def test_a_bind_on_loopback_stays_refused(tmp_path):
    script = tmp_path / "bind.py"
    script.write_text(
        "import socket\n"
        "s = socket.socket()\n"
        "s.bind(('127.0.0.1', 0))\n"
        "s.listen(1)\n"
        "print('bound', s.getsockname()[1])\n",
        encoding="utf-8",
    )
    done = _run_in_sandbox(tmp_path, script)
    assert done.returncode != 0, done.stderr
    assert "bound" not in done.stdout


@pytestmark_sandbox
def test_an_outbound_connection_stays_refused(tmp_path):
    script = tmp_path / "connect.py"
    script.write_text(
        "import socket\n"
        "socket.create_connection(('1.1.1.1', 80), timeout=3)\n"
        "print('connected')\n",
        encoding="utf-8",
    )
    done = _run_in_sandbox(tmp_path, script)
    assert done.returncode != 0
    assert "connected" not in done.stdout


@pytestmark_sandbox
def test_a_write_inside_the_workspace_succeeds(tmp_path):
    argv = shell_sandbox.wrap_command("echo ok > inside.txt", str(tmp_path))
    assert argv is not None and argv[0] in {"sandbox-exec", "bwrap"}
    done = subprocess.run(
        argv, capture_output=True, text=True, timeout=30, check=False, cwd=tmp_path,
    )
    assert done.returncode == 0, done.stderr
    assert (tmp_path / "inside.txt").read_text(encoding="utf-8") == "ok\n"


@pytestmark_sandbox
def test_a_write_under_home_outside_the_workspace_fails(tmp_path):
    probe = Path.home() / f".ephe-sandbox-probe-{os.getpid()}"
    probe.unlink(missing_ok=True)
    try:
        argv = shell_sandbox.wrap_command(
            f"echo leaked > {shlex.quote(str(probe))}", str(tmp_path),
        )
        assert argv is not None
        done = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
        assert done.returncode != 0, done.stdout
        assert not probe.exists()
    finally:
        probe.unlink(missing_ok=True)
