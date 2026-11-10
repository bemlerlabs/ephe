"""Seatbelt wrapper for an opted-in shell command.

The switch is security.json `sandbox_enabled`. When it is on, the command
runs under sandbox-exec on macOS or bwrap on Linux. Writes land in the
canonical workspace, the system temp directory and the device nodes a
toolchain needs. The rest of the home directory stays closed. Network is
denied. Reads stay open on macOS. A missing boundary returns None so the
caller can refuse the command.

On Linux the home is replaced by an empty tmpfs, and that hide reaches more than
the secrets: a project venv, or rustup's shims under `~/.cargo`, live under the
home as well, and `/bin/sh` then answers `not found` for an interpreter that
exists on the host. The mount list therefore re-opens the install root of the
program the command names — and of this process's own interpreter — after the
hides, the same measured exception `core.mcp_sandbox` makes for an MCP child.
"""
from __future__ import annotations

import os
import shlex
import shutil
import sys
import tempfile

#: Directory names a toolchain installs its executables into; the prefix is their parent.
_BIN_DIRS = frozenset({"bin", "sbin", "Scripts"})


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


def _hidden_roots() -> list[str]:
    """The directories the bubblewrap rail replaces with an empty tmpfs.

    One list feeds both the hides and the filter that decides which prefix needs
    its own ro-bind, so a new hide cannot be added without the re-open rule
    seeing it.
    """
    roots: list[str] = []
    for raw in (os.path.expanduser("~"), tempfile.gettempdir(), "/tmp", "/var/tmp"):
        real = os.path.realpath(raw)
        if real and os.path.isdir(real) and real not in roots:
            roots.append(real)
    return roots


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


def _install_prefix(program: str) -> str:
    """`<prefix>/bin/python` -> `<prefix>`; a program outside a bin dir keeps its own dir."""
    parent = os.path.dirname(os.path.abspath(program))
    return os.path.dirname(parent) if os.path.basename(parent) in _BIN_DIRS else parent


def _runtime_prefixes(program: str | None, hidden: list[str]) -> list[str]:
    """Install roots to re-open over the tmpfs hides — never the bare home.

    Measured on the public CI (Ubuntu, bubblewrap installed): the pull-request leg
    builds its venv under `$RUNNER_TEMP`
    (`/home/runner/work/_temp/ephe-leg/bin/python`) and rustup installs its shims
    under `~/.cargo`. Both are under the home the rail replaces with a tmpfs, so a
    sandbox check of a `.py` or `.rs` file came back as `/bin/sh: 1: <path>: not
    found` — the boundary had removed the interpreter, not just the secrets it is
    there to remove. The interpreter is resolved through its symlink and again
    after resolution (a venv's `bin/python` points at the base install, and both
    spellings are read on the way to exec). A rustup shim is re-opened together
    with `RUSTUP_HOME`, because the shim reads the toolchain from there.

    The widening is named here: re-opening `~/.cargo` (the directory the shim lives
    in) exposes the files beside it, `credentials.toml` among them, because a mount
    cannot split one directory. The rail denies the network and limits writes to the
    workspace; without the mount the compiler cannot start at all.
    """
    candidates: list[str] = []
    for executable in (program, sys.executable):
        if not executable:
            continue
        for spelling in (os.path.abspath(executable), os.path.realpath(executable)):
            candidates.append(_install_prefix(spelling))
    for prefix in (sys.prefix, sys.base_prefix):
        if prefix:
            candidates.append(prefix)
    if program and os.path.basename(os.path.realpath(program)) == "rustup":
        rustup_home = os.environ.get("RUSTUP_HOME") or os.path.expanduser("~/.rustup")
        candidates.append(os.path.realpath(rustup_home))

    prefixes: list[str] = []
    for candidate in candidates:
        real = os.path.realpath(candidate)
        if not real or real in prefixes or not os.path.isdir(real):
            continue
        # A prefix outside the hides is already readable under `--ro-bind / /`.
        if not any(_under(real, root) and real != root for root in hidden):
            continue
        # A prefix above a hide would put back exactly what the hide removed.
        if any(_under(root, real) for root in hidden):
            continue
        prefixes.append(real)
    return prefixes


def _named_program(command: str) -> str | None:
    """The program the line names first, resolved the way the shell resolves it.

    A checker line is one argv joined by `shlex.join`, so its first word is the
    interpreter or the compiler. Only that word is resolved, and by the shell's own
    rule: a word carrying a separator is a path (checked for exec, never searched for
    on PATH), anything else is a name. What follows are arguments, and this module
    deliberately holds no shell parser.
    """
    try:
        words = shlex.split(command)
    except ValueError:
        return None
    if not words:
        return None
    first = words[0]
    if os.sep in first:
        return first if os.access(first, os.X_OK) else None
    return _which(first)


def _bwrap_argv(workspace: str, sh_cmd: str, program: str | None = None) -> list[str]:
    # Hide home, re-open the program's install root, then bind the workspace so a
    # project under home stays writable.
    ws = os.path.realpath(workspace) if workspace else os.getcwd()
    argv = [
        "bwrap",
        "--die-with-parent",
        "--unshare-net",
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
    ]
    hidden = _hidden_roots()
    for root in hidden:
        argv += ["--tmpfs", root]
    for prefix in _runtime_prefixes(program, hidden):
        argv += ["--ro-bind", prefix, prefix]
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
        return _bwrap_argv(workspace, sh_cmd, _named_program(command))
    # Neither binary is on PATH. The seatbelt argv is the line the resolver pin names.
    return ["sandbox-exec", "-p", build_profile(workspace), "/bin/sh", "-c", sh_cmd]
