"""The confined plugin worker starts from an install that sits under the denied home.

Live 0.6.4, measured on this macOS: an installed plugin tool died with

    sandbox-exec: execvp() of '<home>/.local/share/ephe/current/.venv/bin/python'
    failed: Operation not permitted

and exit 71. The interpreter of an installed tree is a chain of two symlinks —

    .venv/bin/python -> python3.12 -> <uv>/cpython-3.12-macos-aarch64-none/bin/python3.12

— where `cpython-3.12-macos-aarch64-none` is itself a directory symlink to the
versioned `cpython-3.12.16-…` tree. `os.path.realpath` collapses that alias on the
way to the versioned prefix, so a profile that re-opens the *resolved* prefix never
opens the alias itself; `execvp` asks for its metadata, the whole-home deny answers,
and the child is refused before `python` runs. The kernel log names the exact vnode:

    Sandbox: sandbox-exec(NNN) deny(1) file-read-metadata
      /Users/<user>/.local/share/uv/python/cpython-3.12-macos-aarch64-none

The live tests build that same shape below a temporary home and run the real
`sandbox-exec` over it: a fix that opens the resolved prefix but not the hops is
the bug this file exists to keep out. The access test measures what the profile
must still refuse beside what it now opens. `tests/support/capabilities.py` owns
the skip: `requires_seatbelt` states that the claim is Seatbelt's, so a Linux host
does not go green by running a proof under a different boundary.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from core import mcp_sandbox
from core.sandbox import supervisor
from core.sandbox.runner import _classify
from core.sandbox.supervisor import WorkerOutcome

#: An absolute path a browser or a model must never receive from a refusal line.
_HOST_PATH = re.compile(r"/(?:Users|home|private|var|tmp)/")


def _new_home() -> Path:
    """A home the write rules can be measured against.

    `pytest`'s temporary directory lives under `/private/var/folders`, which the
    profile allows wholesale for temp files — a write beside the child home would
    then be legal for a reason this file must not claim. `/tmp` is not in that
    allowance, so a refusal here is the profile's answer and not the host's.
    """
    return Path(tempfile.mkdtemp(prefix="ephe-worker-start-", dir="/tmp"))


@pytest.fixture()
def installed_home(monkeypatch):
    """A fake `$HOME` holding a uv-style installed tree, and the paths a worker needs."""
    home = _new_home()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("EPHE_CONFIG_DIR", raising=False)

    # The versioned runtime tree, with an executable in it. A `#!/bin/sh` script stands
    # in for the interpreter so the probes can run real commands: the subject is the
    # path chain, not CPython's own import machinery. A copy of a signed system binary
    # is killed by the code-signing check on Apple silicon, so the stand-in is a script.
    versioned = home / ".local/share/uv/python/cpython-3.12.16-macos-aarch64-none"
    binary = versioned / "bin/python3.12"
    binary.parent.mkdir(parents=True)
    binary.write_text('#!/bin/sh\nexec /bin/sh "$@"\n', encoding="utf-8")
    binary.chmod(0o755)

    # uv's unversioned alias: a directory symlink collapsed by realpath, and the vnode
    # the kernel refuses when only the resolved prefix is opened.
    alias = home / ".local/share/uv/python/cpython-3.12-macos-aarch64-none"
    alias.symlink_to(versioned, target_is_directory=True)

    # The installed venv interpreter: two hops, the second one through the alias.
    venv_bin = home / ".local/share/ephe/current/.venv/bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python3.12").symlink_to(alias / "bin/python3.12")
    (venv_bin / "python").symlink_to("python3.12")

    # The worker script, in the install tree the home deny covers.
    launcher_dir = home / ".local/share/ephe/current/core/sandbox"
    launcher_dir.mkdir(parents=True)
    shutil.copy(
        Path(__file__).resolve().parents[1] / "core/sandbox/worker_launcher.py",
        launcher_dir / "worker_launcher.py",
    )

    state = mcp_sandbox.home_for("plugin_demo")
    (state / "own.txt").write_text("the worker's own file", encoding="utf-8")

    yield {
        "home": home,
        "interpreter": venv_bin / "python",
        "alias": alias,
        "versioned": versioned,
        "launcher": launcher_dir / "worker_launcher.py",
        "state": state,
    }
    shutil.rmtree(home, ignore_errors=True)


@pytest.mark.requires_seatbelt
def test_the_installed_interpreter_starts_under_the_profile(installed_home) -> None:
    """The live failure, reproduced: `execvp` of the installed interpreter must work.

    Red before the fix with exit 71 and the exact live stderr; the profile has to
    open every hop of the chain.
    """
    interpreter = str(installed_home["interpreter"])
    argv = supervisor.confined_argv(
        interpreter, ["-c", "echo STARTED"], str(installed_home["state"]),
        [str(installed_home["launcher"].parent)],
    )
    assert argv is not None and argv[0] == "sandbox-exec"

    run = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False)

    assert run.returncode == 0, run.stderr
    assert "STARTED" in run.stdout
    assert "Operation not permitted" not in run.stderr


def test_the_profile_opens_every_hop_and_the_resolved_prefix(installed_home) -> None:
    """The inventory rule: each vnode `execvp` walks gets its own literal allow.

    The alias keeps its own name: `realpath` would turn the rule into the versioned
    path, which is exactly the rule that was already there and did not help.
    """
    profile = mcp_sandbox.build_profile(
        str(installed_home["state"]), str(installed_home["interpreter"])
    )

    alias = os.path.join(
        os.path.realpath(installed_home["alias"].parent), installed_home["alias"].name
    )
    versioned = os.path.realpath(installed_home["versioned"])
    assert f'(allow file-read* (literal "{alias}"))' in profile
    assert f'(allow file-read* (subpath "{versioned}"))' in profile
    # The interpreter itself, through its own name, before the child-home rule.
    assert profile.index(f'literal "{alias}"') > profile.index("(deny file-read*")


@pytest.mark.requires_seatbelt
def test_the_profile_opens_the_worker_files_and_refuses_the_key_and_a_foreign_home(
    installed_home, tmp_path
) -> None:
    """One run, every direction: what a worker needs is open, what it must not see is not.

    A grant proven only on the side that succeeds proves nothing, so the key, a
    sibling file in the same home, a second plugin's state home and a write beside
    the child home are measured in the same child.
    """
    home = installed_home["home"]
    state = installed_home["state"]
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "handlers.py").write_text("def ping(arguments, state_dir):\n    return 0\n")

    key = home / ".ephe/engine.key"
    key.write_text("sk-live-secret", encoding="utf-8")
    foreign = home / ".ephe/mcp/homes/plugin_other"
    foreign.mkdir(parents=True)
    (foreign / "secret.txt").write_text("another bundle's data", encoding="utf-8")
    sibling = home / "escape.txt"
    sibling.write_text("outside the child home", encoding="utf-8")
    system_tmp = Path(tempfile.gettempdir())

    probe = tmp_path / "probe.sh"
    probe.write_text(
        """#!/bin/sh
report() { if eval "$2" >/dev/null 2>&1; then echo "$1=ok"; else echo "$1=denied"; fi; }
report own_read "cat '$STATE/own.txt'"
report own_write "printf x > '$STATE/tmp/out.txt'"
report plugin_read "cat '$PLUGIN/handlers.py'"
report launcher_read "cat '$LAUNCHER'"
report key_read "cat '$KEY'"
report foreign_home_read "cat '$FOREIGN/secret.txt'"
report home_sibling_read "cat '$SIBLING'"
report home_sibling_write "printf x > '$SIBLING'"
report temp_write "printf x > '$SYSTEM_TMP/ephe-worker-start.out'"
""",
        encoding="utf-8",
    )

    argv = supervisor.confined_argv(
        str(installed_home["interpreter"]),
        [str(probe)],
        str(state),
        [str(plugin), str(installed_home["launcher"].parent)],
    )
    assert argv is not None and argv[0] == "sandbox-exec"
    env = dict(os.environ)
    env.update(
        STATE=str(state),
        PLUGIN=str(plugin),
        LAUNCHER=str(installed_home["launcher"]),
        KEY=str(key),
        FOREIGN=str(foreign),
        SIBLING=str(sibling),
        SYSTEM_TMP=str(system_tmp),
        HOME=str(state),
    )

    run = subprocess.run(
        argv, capture_output=True, text=True, timeout=60, env=env, check=False
    )

    assert run.returncode == 0, run.stderr
    seen = dict(line.split("=", 1) for line in run.stdout.strip().splitlines() if "=" in line)
    assert seen["own_read"] == "ok"
    assert seen["own_write"] == "ok"
    assert seen["plugin_read"] == "ok"
    assert seen["launcher_read"] == "ok"
    assert seen["temp_write"] == "ok"
    assert seen["key_read"] == "denied", "the engine key was readable from the worker"
    assert seen["foreign_home_read"] == "denied", "another bundle's home was readable"
    assert seen["home_sibling_read"] == "denied", "a sibling file in the home was readable"
    assert seen["home_sibling_write"] == "denied", "a write beside the child home was allowed"
    (system_tmp / "ephe-worker-start.out").unlink(missing_ok=True)


def test_a_boundary_that_refuses_the_start_is_a_code_not_raw_sandbox_text() -> None:
    """The fallback answer: code, reason and the move left — never the launcher's line.

    `sandbox-exec` writes one sentence about `execvp` and a host path, which names
    neither the tool nor an action. The classifier answers with the sandbox module's
    own form instead.
    """
    stderr = (
        "sandbox-exec: execvp() of "
        "'/Users/sanji/.local/share/ephe/current/.venv/bin/python' failed: "
        "Operation not permitted\n"
    )
    result = _classify(
        "plugin_demo_ping", WorkerOutcome(status="nonzero", exit_code=71, stderr=stderr), 20.0
    )

    assert result.kind == "refusal"
    assert result.code == mcp_sandbox.SANDBOX_START_REFUSED
    assert "sandbox-exec" not in result.text
    assert not _HOST_PATH.search(result.text), result.text
    assert "interpreter" in result.text
    assert "run the tool again" in result.text


def test_a_real_nonzero_exit_keeps_its_own_stderr() -> None:
    """The classifier narrows; it does not swallow a worker's own failure."""
    result = _classify(
        "plugin_demo_ping", WorkerOutcome(status="nonzero", exit_code=2, stderr="boom\n"), 20.0
    )

    assert result.kind == "error"
    assert "exited with code 2" in result.text
    assert "boom" in result.text


@pytest.mark.requires_seatbelt
def test_a_refused_start_becomes_a_coded_result_end_to_end(installed_home) -> None:
    """The live path, twice: the boundary's own refusal, then the coded answer.

    The profile is the pre-fix shape — the hop rules are stripped — so this is the
    real `sandbox-exec` refusal 0.6.4 answered with. The
    classifier must turn that into the sandbox module's form.
    """
    interpreter = str(installed_home["interpreter"])
    profile = mcp_sandbox.build_profile(str(installed_home["state"]), interpreter)
    hopless = "".join(
        line
        for line in profile.splitlines(True)
        if not line.startswith('(allow file-read* (literal "')
    )
    argv = ["sandbox-exec", "-p", hopless, interpreter, "-c", "echo never"]
    run = subprocess.run(argv, capture_output=True, text=True, timeout=60, check=False)

    assert run.returncode == 71, run.stderr
    assert "execvp() of" in run.stderr

    result = _classify(
        "plugin_demo_ping",
        WorkerOutcome(status="nonzero", exit_code=run.returncode, stderr=run.stderr),
        20.0,
    )
    assert result.kind == "refusal"
    assert result.code == mcp_sandbox.SANDBOX_START_REFUSED
    assert "execvp" not in result.text
    assert not _HOST_PATH.search(result.text), result.text
