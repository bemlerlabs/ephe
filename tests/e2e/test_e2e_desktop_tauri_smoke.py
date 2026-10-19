"""The built Tauri shell: the artifact on disk and a real launch of it.

`tauri build` compiles `app/dist/` into the binary, so a green PWA build says
nothing about the desktop shell. These tests read the bundle that build produced
and start the shipped executable, watching for the state the shell only reaches
after setup ran: its single-instance socket bound and the process still alive.
When no bundle is on disk the tests skip with the command that builds one — a
smoke that passes against no artifact is worse than a recorded skip.
"""

from __future__ import annotations

import json
import os
import plistlib
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
TAURI_DIR = REPO / "app" / "src-tauri"
TAURI_CONF = TAURI_DIR / "tauri.conf.json"

#: The shell opens a window and claims its instance in the same call, so a cold
#: start on a shared machine can take a few seconds. Loose enough not to flake,
#: tight enough that a hang still fails.
START_DEADLINE_S = 20.0
SIGTERM_GRACE_S = 10.0
POLL_S = 0.2

#: Two-byte Mach-O magic prefixes: thin 64-bit, thin 32-bit, and fat.
_MACHO_MAGICS = (b"\xcf\xfa", b"\xce\xfa", b"\xfe\xed", b"\xca\xfe")

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="the desktop smoke reads the macOS .app bundle and its Mach-O executable",
)


def _tauri_conf() -> dict:
    return json.loads(TAURI_CONF.read_text(encoding="utf-8"))


def _release_dir() -> Path:
    override = os.environ.get("EPHE_TAURI_RELEASE_DIR")
    return Path(override) if override else TAURI_DIR / "target" / "release"


def _bundle_or_skip() -> tuple[Path, Path, dict, dict]:
    """The `.app`, its shipped executable, the Info.plist and tauri.conf.json.

    Skips with the build command when any of them is absent: the bundle lives
    under `app/src-tauri/target/`, which is a build output and not in git.
    """
    cfg = _tauri_conf()
    app = _release_dir() / "bundle" / "macos" / f"{cfg['productName']}.app"
    build_hint = "build it first: `cd app && npm run tauri build`"
    if not app.is_dir():
        pytest.skip(f"no desktop bundle at {app}; {build_hint}")

    plist_path = app / "Contents" / "Info.plist"
    if not plist_path.is_file():
        pytest.skip(f"{app} has no Info.plist; {build_hint}")
    meta = plistlib.loads(plist_path.read_bytes())

    executable = app / "Contents" / "MacOS" / str(meta.get("CFBundleExecutable", ""))
    if not executable.is_file():
        pytest.skip(f"bundle executable {executable} is missing; {build_hint}")

    return app, executable, meta, cfg


def _gui_session_available() -> bool:
    """`launchctl managername` is Aqua in a logged-in desktop session.

    Without one the window server is absent and the shell cannot start; the test
    skips there instead of charging the absence to the code. An unanswerable
    query (no launchctl, error) is treated as available so the launch decides.
    """
    try:
        done = subprocess.run(
            ["launchctl", "managername"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    return done.stdout.strip() == "Aqua"


def _rpm_spelling(version: str) -> str:
    """The same release in the one spelling an RPM version field allows.

    tauri-bundler 2.10.3 rejects a hyphen there, so the release job bundles the RPM
    with the prerelease separator moved to `+` (`.github/workflows/release.yml`,
    owner decision 2026-10-18: keep the CLI version, work around the validator). The
    bundle that step leaves in the same target dir carries it, and it is the same
    release — so the smoke test accepts either face of it and nothing else.
    """
    return version.replace("-", "+", 1)


def test_desktop_bundle_exists_and_matches_tauri_conf():
    app, executable, meta, cfg = _bundle_or_skip()

    assert meta["CFBundleIdentifier"] == cfg["identifier"]
    assert meta["CFBundleShortVersionString"] in (
        str(cfg["version"]),
        _rpm_spelling(str(cfg["version"])),
    ), f"{meta['CFBundleShortVersionString']} is neither the config version nor its RPM face"
    assert os.access(executable, os.X_OK), f"{executable} is not executable"

    # A stub or a text file would pass `is_file`; the shipped shell is Mach-O.
    head = executable.open("rb").read(4)
    assert head[:2] in _MACHO_MAGICS, f"{executable} is not a Mach-O executable (head={head!r})"

    targets = cfg["bundle"]["targets"]
    wants_dmg = targets == "all" or (isinstance(targets, list) and "dmg" in targets)
    if wants_dmg:
        dmg_dir = _release_dir() / "bundle" / "dmg"
        dmgs = sorted(dmg_dir.glob("*.dmg")) if dmg_dir.is_dir() else []
        assert dmgs, (
            f"bundle.targets is {targets!r} but {dmg_dir} holds no .dmg; "
            "`cd app && npm run tauri build`"
        )


def test_desktop_executable_starts_and_holds_its_instance():
    _app, executable, _meta, cfg = _bundle_or_skip()
    if not _gui_session_available():
        pytest.skip("no Aqua session; the shell opens a window and cannot start headless")

    # A unix socket path is capped at 103 bytes on macOS (sun_path is 104 with the
    # NUL). The shell binds `<config>/ephe-desktop.sock`, and on an un-bindable path
    # it falls back to "no guard" and keeps starting — which would silently void
    # this check. A short temp root keeps the path bindable; a machine whose TMPDIR
    # still overflows it cannot judge the shell and skips.
    with tempfile.TemporaryDirectory(prefix="ed-") as root:
        home = Path(root)
        config_dir = home  # the shell binds the socket directly in the config dir
        socket = config_dir / "ephe-desktop.sock"
        if len(str(socket).encode()) > 103:
            pytest.skip(f"TMPDIR too long for the shell's unix socket ({socket})")

        env = dict(os.environ)
        # Isolated home and config: no backend is spawned (no desktop.json) and
        # the instance socket cannot collide with a copy the user already runs.
        env["HOME"] = root
        env["EPHE_CONFIG_DIR"] = str(config_dir)

        log = home / "shell.log"
        with log.open("wb") as sink:
            proc = subprocess.Popen(
                [str(executable)],
                env=env,
                stdout=sink,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

        bound = False
        terminated_cleanly = False
        try:
            deadline = time.monotonic() + START_DEADLINE_S
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    break
                if socket.exists():
                    bound = True
                    break
                time.sleep(POLL_S)

            assert proc.poll() is None, (
                f"the shell exited rc={proc.returncode} before it held its instance; "
                f"log:\n{log.read_text(errors='replace')[:2000]}"
            )
            assert bound, (
                f"the shell stayed up but never bound {cfg['identifier']}'s "
                f"instance socket at {socket}"
            )
        finally:
            if proc.poll() is None:
                proc.send_signal(signal.SIGTERM)
                try:
                    proc.wait(timeout=SIGTERM_GRACE_S)
                    terminated_cleanly = True
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

        assert terminated_cleanly, "the shell ignored SIGTERM"
        assert proc.returncode is not None
