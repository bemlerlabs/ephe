"""Filesystem boundary for an MCP stdio child (SC-02).

The environment scrub in `core.secret_broker.child_env` keeps credentials out of
a child's process environment, and a sanitized HOME keeps the *derived* paths
away from the user's `~/.ssh` and `~/.ephe`. Neither stops an absolute
`open()` on the engine key. This module adds the OS boundary:

- macOS: a Seatbelt profile that denies reads of the user's whole home, allows
  writes only in the child's own home plus temp, and re-opens only the child
  home for reading.
- Linux: bubblewrap, with the user's home (and a config root outside it, and
  `/run/user/<uid>`) replaced by empty tmpfs mounts; the command's runtime
  prefixes and the child home are bound back in after the tmpfs, and the shared
  `/tmp` stays readable (writes go to the child's own `tmp/`, which `TMPDIR`
  names). Every dotdir under the home is gone, not just the listed ones.
- Neither available: `wrap()` returns None and the caller refuses the spawn
  with a coded error and an `os_boundary=unavailable` line. There is no
  unsandboxed fallback for an untrusted server.

Honest limits, pinned by the tests: `sandbox-exec` is deprecated by Apple but
still works on the macOS versions this ships to. bubblewrap must be installed
and user namespaces permitted; where it is not, the Linux boundary is
unavailable, and the receipt says so instead of calling SC-02 closed.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

#: The enumeration the first macOS profile used. The profile now denies the
#: whole home and keeps this list as the record of what it used to name.
DENY_READ_SUBPATHS = (
    ".ssh",
    ".gnupg",
    ".aws",
    ".ephe",
    ".config",
    ".kube",
    ".docker",
    ".npmrc",
    ".netrc",
    ".git-credentials",
    "Library/Application Support/Google",
    "Library/Application Support/Chromium",
    "Library/Application Support/Firefox",
    "Library/Application Support/Safari",
    "Library/Safari",
    "Library/Cookies",
    "Library/Mail",
    "Library/Messages",
    "Library/Keychains",
    ".zsh_history",
    ".gitconfig",
)


def platform_boundary() -> str:
    """`seatbelt`, `bubblewrap` or `unavailable` — what the OS can enforce here."""
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return "seatbelt"
    if sys.platform.startswith("linux") and shutil.which("bwrap"):
        return "bubblewrap"
    return "unavailable"


def is_available() -> bool:
    return platform_boundary() != "unavailable"


def home_for(server: str) -> Path:
    """A per-server HOME under the config root, created 0700."""
    base = os.environ.get("EPHE_CONFIG_DIR")
    root = (Path(base) if base else Path.home() / ".ephe") / "mcp" / "homes"
    slug = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in server)[:60] or "server"
    home = root / slug
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    (home / "tmp").mkdir(exist_ok=True, mode=0o700)
    return home


def _under(path: str, root: str) -> bool:
    return path == root or path.startswith(root + os.sep)


def _looks_like_runtime(prefix: str) -> bool:
    """An install prefix with a python or node entry, or a venv root."""
    if os.path.basename(prefix) in {".venv", "venv", "env"}:
        return True
    if any(
        os.path.exists(os.path.join(prefix, rel))
        for rel in ("bin/python", "bin/python3", "bin/node")
    ):
        return True
    try:
        entries = os.listdir(os.path.join(prefix, "bin"))
    except OSError:
        return False
    # A uv-installed CPython ships `bin/python3.<minor>` and, on the macOS runner,
    # no bare `python` or `python3` beside it.
    return any(name.startswith("python3.") and name[8:].isdigit() for name in entries)


def _runtime_prefixes(command: str | None, real_home: str) -> list[str]:
    """Install prefixes the command needs to read; never a secret subtree.

    A whole-home deny also hides the interpreter and its libraries, so the
    measured runtime roots are re-opened. A command that names a secret
    directory contributes nothing: its prefix is not a runtime.
    """
    roots: set[str] = set()

    def consider(prefix: str) -> None:
        # Resolve the parent but keep the final name: the final component may be a
        # symlink whose own read must be allowed, and `/tmp` may stand for `/private/tmp`.
        parent, name = os.path.split(os.path.abspath(prefix))
        literal = os.path.join(os.path.realpath(parent), name)
        # A symlinked prefix is read at its literal path and again after resolution;
        # only the resolved tree is not enough. uv's `cpython-3.12-…` alias is one.
        for candidate in (literal, os.path.realpath(literal)):
            if not _under(candidate, real_home) or candidate == real_home:
                continue
            if any(_under(candidate, os.path.join(real_home, rel)) for rel in DENY_READ_SUBPATHS):
                continue
            if not _looks_like_runtime(candidate):
                continue
            roots.add(candidate)

    if command:
        for candidate in (os.path.abspath(command), os.path.realpath(command)):
            consider(os.path.dirname(os.path.dirname(candidate)))
        # The executable can be a symlink to a path that is itself a symlink: `uv venv`
        # names its unversioned alias, while `realpath` reports the versioned tree. The
        # kernel reads the alias on the way, so its literal prefix needs its own allow.
        try:
            target = os.readlink(command)
        except OSError:
            target = ""
        if target:
            if not os.path.isabs(target):
                target = os.path.join(os.path.dirname(command), target)
            consider(os.path.dirname(os.path.dirname(target)))
    # The interpreter itself, through its symlink and its target: a venv's `bin/python`
    # points at the base installation, and the child has to execute both.
    for executable in (sys.executable, os.path.realpath(sys.executable or "")):
        if executable:
            consider(os.path.dirname(os.path.dirname(executable)))
    for prefix in (sys.prefix, sys.base_prefix):
        consider(prefix)
    return sorted(roots)


def build_profile(home: str, command: str | None = None) -> str:
    """Deny the user's whole home, allow writes only in the child's home/tmp.

    The per-server home lives under the config root, which is itself inside the
    denied home; the final read rule re-opens exactly that subtree (measured on
    this macOS: an allow after the deny wins for the child home while
    `~/.ephe/engine.key` stays refused). A config root outside HOME is denied
    as well. Runtime prefixes are measured exceptions: without them the whole-
    home deny also refuses the interpreter that runs the child.
    """
    real_home = os.path.realpath(os.path.expanduser("~"))
    child_home = os.path.realpath(home)
    config_root = os.path.realpath(
        os.environ.get("EPHE_CONFIG_DIR") or os.path.join(real_home, ".ephe")
    )
    tmp = os.path.realpath(tempfile.gettempdir())
    runtime = "".join(
        f'(allow file-read* (subpath "{prefix}"))\n'
        for prefix in _runtime_prefixes(command, real_home)
    )
    outside_config = ""
    if config_root != real_home and not config_root.startswith(real_home + os.sep):
        outside_config = f'(deny file-read* (subpath "{config_root}"))\n'
    return (
        "(version 1)\n"
        "(allow default)\n"
        "(deny file-read*\n"
        f'  (subpath "{real_home}")\n'
        ")\n"
        f"{outside_config}"
        "(deny file-write*)\n"
        "(allow file-write*\n"
        f'  (subpath "{child_home}")\n'
        f'  (subpath "{tmp}")\n'
        '  (regex #"^/private/var/folders/.*")\n'
        '  (literal "/dev/null")\n'
        '  (literal "/dev/stdout")\n'
        '  (literal "/dev/stderr")\n'
        ")\n"
        f"{runtime}"
        # Last rule wins for this subtree; it must stay after the denies.
        f'(allow file-read* (subpath "{child_home}"))\n'
    )


def build_bwrap(home: str, command: str | None = None) -> list[str]:
    """bubblewrap mounts: read-only root, empty home, runtime and child home bound back.

    `--tmpfs <real home>` after `--ro-bind / /` hides every dotdir the user has,
    including the ones this repository does not enumerate; the per-server home
    is bound on top of it. A config root outside the home (`EPHE_CONFIG_DIR`)
    and the session bus/keyring under `/run/user/<uid>` are hidden the same
    way, because a read-only root would otherwise expose them.

    Two things are re-opened after the hides: the command's runtime prefixes, as
    the macOS profile does (an interpreter installed under the home, such as the
    CI leg's venv, is otherwise unreadable), and the child home. The shared
    `/tmp` stays readable from the read-only root — a server script may live
    there, and `TMPDIR` already points at the child's own `tmp/` for writes.
    Without `--unshare-net`: the boundary is the filesystem, and an MCP server
    may legitimately be a network client.
    """
    real_home = os.path.realpath(os.path.expanduser("~"))
    child_home = os.path.realpath(home)
    config_root = os.path.realpath(
        os.environ.get("EPHE_CONFIG_DIR") or os.path.join(real_home, ".ephe")
    )
    argv = [
        "bwrap",
        "--die-with-parent",
        "--unshare-pid",
        "--ro-bind", "/", "/",
        "--dev", "/dev",
        "--proc", "/proc",
    ]
    run_user = f"/run/user/{os.getuid()}"
    if os.path.isdir(run_user):
        argv += ["--tmpfs", run_user]
    hidden = [real_home]
    if config_root != real_home and not config_root.startswith(real_home + os.sep):
        hidden.append(config_root)
    for path in hidden:
        argv += ["--tmpfs", path]
    for prefix in _runtime_prefixes(command, real_home):
        argv += ["--ro-bind", prefix, prefix]
    argv += ["--bind", child_home, child_home]
    return argv


def wrap(command: str, args: list[str], home: str) -> list[str] | None:
    """The command under the platform boundary, or None where none exists."""
    boundary = platform_boundary()
    if boundary == "seatbelt":
        return ["sandbox-exec", "-p", build_profile(home, command), command, *args]
    if boundary == "bubblewrap":
        return [*build_bwrap(home, command), "--chdir", os.path.realpath(home), command, *args]
    return None
