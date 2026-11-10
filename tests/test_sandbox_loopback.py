"""The opted-in shell profile writes the workspace and closes the rest.

Network is denied. A write inside the canonical workspace succeeds. A write under the
home directory, outside that workspace, never reaches the host. The product switch stays
off.

Two claims only mean something under the right boundary, so they say which one they are
under instead of being skipped quietly: `--unshare-net` gives the child a loopback of its
own, where a bind is allowed and proves nothing, so the portable proof is that the host's
listener never accepts, and the bind refusal is marked `requires_seatbelt`.
"""
from __future__ import annotations

import os
import shlex
import socket
import subprocess
import sys
import threading
from pathlib import Path

from core import shell_sandbox
from core.security_config import SecurityConfig
from tests.support import capabilities


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


def _run_in_sandbox(workspace, script: Path) -> subprocess.CompletedProcess[str]:
    argv = shell_sandbox.wrap_command(f"{sys.executable} {script}", str(workspace))
    assert argv is not None, "the capability marker promised a boundary, so this is a bug"
    return subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)


@capabilities.requires_boundary
def test_a_host_listener_on_loopback_stays_unreachable(tmp_path):
    """The child may keep a loopback of its own; it must not reach the host's.

    Seatbelt denies the connect call. bubblewrap gives the child a network namespace with
    its own loopback interface, so the reach that matters is the one measured here: a
    socket the host is listening on never accepts, on either boundary.
    """
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    reached = threading.Event()

    def accept_once() -> None:
        server.settimeout(10.0)
        try:
            connection, _address = server.accept()
        except OSError:
            return
        connection.close()
        reached.set()

    thread = threading.Thread(target=accept_once, daemon=True)
    thread.start()
    script = tmp_path / "connect_host.py"
    script.write_text(
        "import socket\n"
        f"socket.create_connection(('127.0.0.1', {port}), timeout=3)\n"
        "print('connected')\n",
        encoding="utf-8",
    )
    try:
        done = _run_in_sandbox(tmp_path, script)
    finally:
        thread.join(timeout=12)
        server.close()
    assert "connected" not in done.stdout, done.stdout
    assert not reached.is_set(), "the host accepted the sandboxed child's connection"


@capabilities.requires_seatbelt
def test_a_bind_on_loopback_is_refused_under_seatbelt(tmp_path):
    """Seatbelt denies the bind itself; under bubblewrap this is a private interface."""
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


@capabilities.requires_boundary
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


@capabilities.requires_boundary
def test_a_write_inside_the_workspace_succeeds(tmp_path):
    argv = shell_sandbox.wrap_command("echo ok > inside.txt", str(tmp_path))
    assert argv is not None and argv[0] in {"sandbox-exec", "bwrap"}
    done = subprocess.run(
        argv, capture_output=True, text=True, timeout=30, check=False, cwd=tmp_path,
    )
    assert done.returncode == 0, done.stderr
    assert (tmp_path / "inside.txt").read_text(encoding="utf-8") == "ok\n"


@capabilities.requires_boundary
def test_a_write_under_home_outside_the_workspace_never_reaches_the_host(tmp_path):
    """The host-side file is the promise; Seatbelt refuses the call before that question.

    bubblewrap answers with an empty tmpfs over the home instead of an error, so the shell
    can exit 0 while the bytes land in a directory that exists only inside the sandbox.
    """
    probe = Path.home() / f".ephe-sandbox-probe-{os.getpid()}"
    probe.unlink(missing_ok=True)
    try:
        argv = shell_sandbox.wrap_command(
            f"echo leaked > {shlex.quote(str(probe))}", str(tmp_path),
        )
        assert argv is not None
        done = subprocess.run(argv, capture_output=True, text=True, timeout=30, check=False)
        assert not probe.exists(), "the write under the real home reached the host"
        if capabilities.boundary() == "seatbelt":
            assert done.returncode != 0, done.stdout
    finally:
        probe.unlink(missing_ok=True)
