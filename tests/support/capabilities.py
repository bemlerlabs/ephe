"""Which OS boundary this machine really has, and what a test may claim without it.

`core.mcp_sandbox.platform_boundary()` names the rail the product will use, and it decides
with `shutil.which`: a `bwrap` the kernel refuses a namespace to still reads `bubblewrap`
there. A test needs the sharper question, because its two honest answers are "the proof
ran" and "the proof could not run, and here is why". The probe below runs the binary once
with the namespace flags both rails pass, and caches the verdict for the session.

`requires_boundary` marks a test whose claim is about code running inside the boundary.
With the capability present it runs; without one it skips, and the reason is the probe's
own sentence. `EPHE_REQUIRE_OS_BOUNDARY=1` — set by the CI leg that installs bubblewrap —
turns that skip into a failure, because a required leg must not go green by skipping the
proofs it exists to run.
"""
from __future__ import annotations

import functools
import os
import shutil
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest

#: Repository root, for the app toolchain the SDK check needs.
ROOT = Path(__file__).resolve().parents[2]

#: Set by a CI leg that is supposed to provide the boundary. A missing capability then
#: fails the leg instead of skipping every proof under it.
REQUIRE_BOUNDARY_ENV = "EPHE_REQUIRE_OS_BOUNDARY"

#: The flags the rails use for the namespaces the probe has to prove: a private pid tree
#: and no route to the host's sockets, over a read-only root.
_BWRAP_PROBE_FLAGS = (
    "--die-with-parent",
    "--unshare-pid",
    "--unshare-net",
    "--ro-bind",
    "/",
    "/",
)

requires_boundary = pytest.mark.requires_boundary

#: For the two claims that are about Seatbelt's syscall-level deny. bubblewrap answers the
#: same danger with a private namespace, where the same call is allowed and proves nothing,
#: so the test states the difference instead of quietly changing what it measures.
requires_seatbelt = pytest.mark.requires_seatbelt


def has_seatbelt() -> bool:
    return sys.platform == "darwin" and shutil.which("sandbox-exec") is not None


@functools.lru_cache(maxsize=1)
def _bwrap_probe() -> tuple[bool, str]:
    """`(usable, reason)` — whether bwrap can create the namespaces the rails ask for."""
    binary = shutil.which("bwrap")
    if binary is None:
        return False, "bubblewrap (bwrap) is not installed"
    command = shutil.which("true") or "/bin/true"
    try:
        done = subprocess.run(
            [binary, *_BWRAP_PROBE_FLAGS, "--", command],
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"the bubblewrap probe could not run ({type(exc).__name__})"
    if done.returncode == 0:
        return True, ""
    lines = (done.stderr or done.stdout).strip().splitlines()
    detail = lines[-1] if lines else f"exit {done.returncode}"
    return False, f"bwrap is installed but the kernel refuses it a namespace ({detail})"


def has_bwrap() -> bool:
    return _bwrap_probe()[0]


def has_boundary() -> bool:
    return has_seatbelt() or has_bwrap()


def boundary() -> str:
    if has_seatbelt():
        return "seatbelt"
    if has_bwrap():
        return "bubblewrap"
    return "unavailable"


def boundary_skip_reason() -> str:
    """The sentence a skip carries, naming which half of the capability is missing."""
    if has_boundary():
        return ""
    if sys.platform == "darwin":
        return "no OS boundary on this machine: sandbox-exec is not on PATH"
    if sys.platform.startswith("linux"):
        return f"no OS boundary on this machine: {_bwrap_probe()[1]}"
    return f"no OS boundary on this machine: {sys.platform} has no confinement rung"


def seatbelt_skip_reason() -> str:
    return (
        "the claim is about Seatbelt's syscall deny, which is not this host's boundary "
        f"({boundary()}): bubblewrap answers the same danger with a private network "
        "namespace, where the call is permitted; the reachability proof beside this test "
        "carries the promise there"
    )


def boundary_required() -> bool:
    return os.environ.get(REQUIRE_BOUNDARY_ENV, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def gate(item: pytest.Item) -> None:
    """Apply both capability markers to one collected test.

    `tests/conftest.py` calls this from `pytest_runtest_setup`, so the decision is made
    once per test with the probe's cached verdict and the skip reason is never a constant
    written in a test file.
    """
    if item.get_closest_marker("requires_boundary") is not None and not has_boundary():
        reason = boundary_skip_reason()
        if boundary_required():
            pytest.fail(
                f"{REQUIRE_BOUNDARY_ENV} is set but {reason}; the leg is supposed to "
                "provide the capability, so this proof cannot skip here",
                pytrace=False,
            )
        pytest.skip(reason)
    if item.get_closest_marker("requires_seatbelt") is not None and not has_seatbelt():
        pytest.skip(seatbelt_skip_reason())


def capability_report() -> dict[str, object]:
    """What this host offers, in the shape the CI step that asserts it prints."""
    return {
        "boundary": boundary(),
        "seatbelt": has_seatbelt(),
        "bubblewrap": has_bwrap(),
        "skip_reason": boundary_skip_reason(),
        "required": boundary_required(),
    }


@contextmanager
def spawn_without_boundary(monkeypatch, home: Path) -> Iterator[Path]:
    """Let the supervisor spawn its child with no boundary, to prove its classifier.

    `run_worker` asks the argv builder for a confined command line and refuses to spawn
    when the answer is None, which is the product's fail-closed guarantee. Which exit
    status means `crashed`, `oom` or `nonzero` is read after that spawn and never touches
    the boundary, so the builder is the single seam that stands aside here. The outcome's
    `boundary` field still reports what this host offers, and no confinement is claimed:
    use this where the subject is the classifier, never where it is the boundary.
    """
    from core import mcp_sandbox
    from core.sandbox import supervisor

    home.mkdir(parents=True, exist_ok=True)
    (home / "tmp").mkdir(exist_ok=True)
    monkeypatch.setattr(mcp_sandbox, "home_for", lambda server: home)
    monkeypatch.setattr(
        supervisor,
        "confined_argv",
        lambda command, args, *rest, **kwargs: [command, *args],
    )
    yield home
_RUSTC_MISSING = (
    "rustc is not installed or does not run - install the Rust toolchain "
    "(the cargo job installs it with dtolnay/rust-toolchain)"
)
_TSC_MISSING = (
    "the app toolchain (app/node_modules/.bin/tsc) is not installed or does not run - "
    "install it with `cd app && pnpm install --frozen-lockfile`"
)

# --- toolchain capabilities ---
# The same doctrine for a compiler or a type checker: availability means the tool
# runs, so a shim on PATH that dies inside a test becomes a named skip instead.


def _runs(argv: list[str]) -> bool:
    """True only when the tool really starts and exits 0."""
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=20)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0

def rustc_path() -> Path | None:
    return _tool_path("rustc")


def node_tsc_path() -> Path | None:
    """The app toolchain's ``tsc``, or None when ``app/`` was never installed.

    The checker lives in the app's own node_modules, so it is found there first: a
    `tsc` on PATH would be a different compiler version than the one the app pins.
    """
    tsc = ROOT / "app" / "node_modules" / ".bin" / "tsc"
    if not tsc.is_file():
        return None
    return tsc if _runs([str(tsc), "--version"]) else None


def _tool_path(name: str) -> Path | None:
    found = shutil.which(name)
    if found is None:
        return None
    return Path(found) if _runs([found, "--version"]) else None


requires_rustc = pytest.mark.skipif(rustc_path() is None, reason=_RUSTC_MISSING)
requires_node_toolchain = pytest.mark.skipif(node_tsc_path() is None, reason=_TSC_MISSING)
