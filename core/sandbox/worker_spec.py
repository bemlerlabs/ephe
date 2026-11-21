"""The descriptor handed to the supervisor: paths, argv form, declared ceilings.
Callables do not cross this line.

Task #6 froze the registry rule: a dynamic tool entry carries a transport, not plugin
code the backend could import. This spec is what the `plugin_` transport resolves to:
one plugin tool invocation described from the outside. Host paths enter only through
the plugin directory the manifest declared, and entry and allowed roots are re-checked
against it here with the same rule `core.plugin_manifest._under` enforces — a `..` or
a symlink that steps out is refused at build time, so the supervisor never sees it.

No field of `WorkerSpec` is executable, and none names a mechanism outside the plugin
directory.
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

#: The fixed outcome vocabulary of the supervisor (#47, surfaced by #9 and #38).
#: A status is the whole classification; free text rides in `WorkerOutcome.note`.
STATUSES = (
    "ok",
    "timeout",
    "crashed",
    "nonzero",
    "oom",
    "sandbox_unavailable",
    "protocol_error",
)

DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_OUTPUT_CAP_BYTES = 64 * 1024
#: 0 declares no child memory ceiling. `policy_snapshot` then reports memory
#: not-enforced for the call — an unstated default would be a ceiling nobody wrote.
DEFAULT_MEMORY_CAP_MB = 0


#: The child applies its own memory ceiling before it loads the entry: a
#: `preexec_fn` is unsafe from a threaded supervisor, so the limit rides as
#: bootstrap code in the argv; a fork-time hook would be unsafe with the
#: supervisor's reader threads. The descriptor still carries only the number.
#:
#: The child reports whether the ceiling took. `resource.setrlimit(RLIMIT_AS, …)` refuses
#: every finite value on macOS — measured here at 256 MB, 512 MB, 1 GB, 2 GB and 4 GB with
#: both limits unbounded — and a bootstrap that let that error escape killed every tool that
#: declared a cap. The verdict rides on stderr in one fixed line, and `run_worker` lifts it
#: onto the outcome, so a ceiling the OS declined is a stated fact rather than a silence.

#: The marker the bootstrap writes, and the word `run_worker` looks for in the child's stderr.
#: One name for both halves, so the verdict cannot be written where nobody reads it.
MEMORY_CEILING_MARKER = "EPHE-MEMORY-CAP"

_MEMORY_BOOTSTRAP = (
    "import os, resource, runpy, sys\n"
    "cap = int(sys.argv[1]) * 1024 * 1024\n"
    "if cap:\n"
    "    try:\n"
    "        resource.setrlimit(resource.RLIMIT_AS, (cap, cap))\n"
    "        verdict = 'applied'\n"
    "    except (ValueError, OSError) as exc:\n"
    "        verdict = 'refused ' + type(exc).__name__\n"
    f"    sys.stderr.write('{MEMORY_CEILING_MARKER} ' + verdict + '\\n')\n"
    "    sys.stderr.flush()\n"
    "sys.argv = sys.argv[2:]\n"
    "# `python script.py` puts the script's own directory on sys.path; `python -c` does not, so\n"
    "# the capped form has to add it or a module that lives beside the launcher — `bridge_client`\n"
    "# for #23 — cannot be found, and the two forms would mean different things.\n"
    "sys.path.insert(0, os.path.dirname(os.path.realpath(sys.argv[0])))\n"
    "runpy.run_path(sys.argv[0], run_name='__main__')\n"
)


@dataclass(frozen=True)
class WorkerSpec:
    """One confined worker invocation, described by data alone."""

    plugin_id: str
    plugin_dir: Path          # the manifest's own directory — the only host path in
    entry: str                # relative to plugin_dir, validated at build
    interpreter: str          # absolute; default is this process's interpreter
    args: tuple[str, ...] = ()
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    memory_cap_mb: int = DEFAULT_MEMORY_CAP_MB
    output_cap_bytes: int = DEFAULT_OUTPUT_CAP_BYTES
    allowed_roots: tuple[str, ...] = ()  # extra read roots, relative to plugin_dir
    host_roots: tuple[str, ...] = ()     # declared data roots, absolute, existing dirs
    launcher: str = ""        # path to the trusted repo launcher; empty runs `entry`

    def entry_path(self) -> Path:
        root = os.path.realpath(self.plugin_dir)
        return Path(os.path.join(root, *self.entry.split("/")))

    def _script(self) -> str:
        """What the interpreter loads: the trusted launcher, else the plugin entry."""
        return self.launcher or str(self.entry_path())

    def child_argv(self) -> list[str]:
        script = self._script()
        if self.memory_cap_mb:
            return [
                self.interpreter,
                "-c",
                _MEMORY_BOOTSTRAP,
                str(self.memory_cap_mb),
                script,
                *self.args,
            ]
        return [self.interpreter, script, *self.args]

    def read_roots(self) -> list[str]:
        root = os.path.realpath(self.plugin_dir)
        roots = [root] + [
            os.path.join(root, *rel.split("/")) for rel in self.allowed_roots
        ]
        if self.launcher:
            roots.append(os.path.dirname(os.path.realpath(self.launcher)))
        roots += [os.path.realpath(root) for root in self.host_roots]
        return roots


def build_spec(
    *,
    plugin_id: str,
    plugin_dir: Path | str,
    entry: str,
    interpreter: str | None = None,
    args: tuple[str, ...] = (),
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    memory_cap_mb: int = DEFAULT_MEMORY_CAP_MB,
    output_cap_bytes: int = DEFAULT_OUTPUT_CAP_BYTES,
    allowed_roots: tuple[str, ...] = (),
    launcher: str | None = None,
    host_roots: tuple[str, ...] = (),
) -> tuple[WorkerSpec | None, str]:
    """Validate a descriptor or say plainly why it is refused. Nothing is executed here."""
    if not plugin_id or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for ch in plugin_id):
        return None, f"plugin id {plugin_id!r} is not a plain slug"
    root = Path(plugin_dir)
    if not root.is_dir():
        return None, f"plugin directory {root} does not exist"
    real_root = os.path.realpath(root)

    def inside(rel: str) -> str | None:
        """The `_under` rule, applied to a manifest-relative path."""
        if os.path.isabs(rel):
            return f"{rel!r} is absolute; only paths under the plugin directory qualify"
        target = os.path.realpath(os.path.join(real_root, *rel.split("/")))
        if target != real_root and not target.startswith(real_root + os.sep):
            return f"{rel!r} resolves outside the plugin directory"
        return None

    error = inside(entry)
    if error:
        return None, error
    if not Path(os.path.join(real_root, *entry.split("/"))).is_file():
        return None, f"entry {entry!r} is not a file inside the plugin directory"
    for rel in allowed_roots:
        error = inside(rel)
        if error:
            return None, f"allowed root: {error}"
    interp = str(interpreter or sys.executable)
    if not os.path.isabs(interp):
        return None, f"interpreter {interp!r} is not an absolute path"
    if timeout_seconds <= 0:
        return None, "timeout_seconds must be positive — a worker without a bound is a lease"
    if output_cap_bytes <= 0:
        return None, "output_cap_bytes must be positive"
    for host_root in host_roots:
        # A declared data root is a folder outside the plugin directory, so it reaches the
        # boundary as an absolute path and as a directory — the same two checks
        # `validate_data_roots` applies when the manifest loads. A name rebound here would
        # move the plugin directory itself, which is what the spec's own test now pins.
        if not os.path.isabs(str(host_root)):
            return None, f"host read root {host_root!r} is not absolute"
        if not os.path.isdir(host_root):
            return None, f"host read root {host_root!r} is not a directory"

    script = str(launcher or "")
    if script:
        if not os.path.isabs(script):
            return None, f"launcher {script!r} is not an absolute path"
        if not os.path.isfile(script):
            return None, "launcher is not a file"
    return (
        WorkerSpec(
            plugin_id=plugin_id,
            plugin_dir=root,
            entry=entry,
            interpreter=interp,
            args=tuple(str(a) for a in args),
            timeout_seconds=float(timeout_seconds),
            memory_cap_mb=int(memory_cap_mb),
            output_cap_bytes=int(output_cap_bytes),
            allowed_roots=tuple(allowed_roots),
            host_roots=tuple(str(path) for path in host_roots),
            launcher=script,
        ),
        "",
    )
