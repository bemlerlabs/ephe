"""Seatbelt wrapper for an opted-in shell command.

The switch is security.json `sandbox_enabled`. When it is on, the command
runs under sandbox-exec on macOS or bwrap on Linux. Writes land in the
canonical workspace, the system temp directory and the device nodes a
toolchain needs. The rest of the home directory stays closed. Network is
denied. Reads stay open on macOS. A missing boundary returns None so the
caller can refuse the command.
"""
from __future__ import annotations

import os
import shutil
import tempfile


def _which(name: str) -> str | None:
    return shutil.which(name)


def is_available() -> bool:
    return _which("sandbox-exec") is not None or _which("bwrap") is not None


def build_profile(workspace: str) -> str:
    """SBPL profile: workspace, temp and device nodes, the rest of home closed."""
    tmp = tempfile.gettempdir()
    darwin_tmp = "/private" + tmp if not tmp.startswith("/private") else tmp
    ws = os.path.realpath(workspace) if workspace else os.getcwd()
    return (
        "(version 1)\n"
        "(allow default)\n"
        "(deny network*)\n"
        "(deny file-write*)\n"
        "(allow file-write*\n"
        f'  (subpath "{ws}")\n'
        f'  (subpath "{tmp}")\n'
        f'  (subpath "{darwin_tmp}")\n'
        '  (regex #"^/private/var/folders/.*")\n'
        '  (literal "/dev/null")\n'
        '  (literal "/dev/tty")\n'
        '  (subpath "/dev/fd")\n'
        ")\n"
    )


def _bwrap_argv(workspace: str, sh_cmd: str) -> list[str]:
    # Hide home, then bind the workspace so a project under home stays writable.
    ws = os.path.realpath(workspace) if workspace else os.getcwd()
    home = os.path.realpath(os.path.expanduser("~"))
    argv = [
        "bwrap",
        "--die-with-parent",
        "--unshare-net",
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", home,
        "--tmpfs", "/tmp",
    ]
    if os.path.isdir("/var/tmp"):
        argv += ["--tmpfs", "/var/tmp"]
    argv += ["--bind", ws, ws, "--chdir", ws, "/bin/sh", "-c", sh_cmd]
    return argv


def wrap_command(command: str, workspace: str) -> list[str] | None:
    """The sandbox command line, or None when this host has no boundary."""
    if not is_available():
        return None
    # GIT_PAGER is forced off. Git's /dev/null probe is covered by the device nodes.
    sh_cmd = f"export GIT_PAGER=cat GIT_PAGER_NO_COLOR=1; {command}"
    if _which("sandbox-exec"):
        return ["sandbox-exec", "-p", build_profile(workspace), "/bin/sh", "-c", sh_cmd]
    if _which("bwrap"):
        return _bwrap_argv(workspace, sh_cmd)
    # Neither binary is on PATH. The seatbelt argv is the line the resolver pin names.
    return ["sandbox-exec", "-p", build_profile(workspace), "/bin/sh", "-c", sh_cmd]
