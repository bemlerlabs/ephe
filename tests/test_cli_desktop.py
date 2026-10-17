"""
◑ Ephe – desktop CLI (`ephe desktop`, icon/brand wave)
tests/test_cli_desktop.py

Pins:
1. `ephe desktop --help` works and documents dev/build.
2. _desktop_bundle_path finds the macOS .app / AppImage / msi / nsis bundles.
3. Missing toolchain → exit 1 with an actionable message (fail-closed),
   no stack trace (subprocess path).
4. One command: the backend is started automatically BEFORE the app opens;
   if it already runs it is reused; if it does not start, the app still opens
   (the offline gate lives in the UI) — never a traceback.
5. Default build = only the .app (--bundles app); the DMG step (AppleScript
   window cosmetics in the installer) never blocks the start (--dmg is opt-in).
6. Isolation (CI run 37910013023, 2026-10-09): no test runs the node toolchain.
   The real CLI process is only started for `--help`/`doctor` (which build nothing)
   and for the fail-closed branch with npm OFF PATH; every build/backend/open path
   goes through the `_desktop_env` seams in-process. Nothing is ever written into
   `app/`, no bundle is built, no port is bound — `_no_frontend_build_side_effects`
   fails a test that does it anyway, and `_desktop_env` pins `sys.platform` so the
   darwin-only tail of the command is covered on the Linux runners too.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlparse

import pytest

from tests.subprocess_env import env_without_tools

ROOT = Path(__file__).resolve().parents[1]


def _run_cli(
    *args: str, env: dict[str, str] | None = None, timeout: int = 60
) -> subprocess.CompletedProcess[str]:
    """Starts the real CLI as a process (the argparse/exit-code/no-traceback contract).

    `env` is passed through wholesale: a caller that documents a missing toolchain
    has to get exactly that, and must not depend on what the dev machine or the
    runner happens to have installed.
    """
    return subprocess.run(
        [sys.executable, str(ROOT / "ephe_cli.py"), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


#: Build artifacts a real frontend run leaves in the working tree. `ensure_pwa_built`
#: (core/_cli_ollama.py) creates them from `ephe start` / `ephe doctor --fix` via
#: `npm ci` / `npm install` / `npm run build`, and `ephe desktop` creates them through
#: `tauri build` — in a fresh checkout, where `app/dist` is git-ignored and missing.
_BUILD_ARTIFACTS = ("app/dist", "app/node_modules", "app/package-lock.json")


@pytest.fixture(autouse=True)
def _no_frontend_build_side_effects():
    """No test in this file may build the frontend into the checkout.

    Not a style rule but a cross-test one: `npm install` writes `app/package-lock.json`,
    and that is what made
    `tests/test_r46_pnpm_single_source.py::test_single_lockfile_pnpm_only`
    fail later in the same CI run — one test's real npm call asserted against another
    test's working tree.

    Observed, not assumed: the artifacts are compared before/after the test, so a
    developer's own build (which exists here) is not reported and a CI checkout that a
    test built is.
    """
    before = {name: (ROOT / name).exists() for name in _BUILD_ARTIFACTS}
    yield
    created = [name for name, existed in before.items() if not existed and (ROOT / name).exists()]
    assert not created, (
        f"This test ran the node toolchain for real and created {', '.join(created)} in app/. "
        "Patch the CLI seam instead (`_desktop_env` for cmd_desktop, "
        "`patch('ephe_cli.ensure_pwa_built')` for start/doctor)."
    )


def test_desktop_help_documented():
    r = _run_cli("desktop", "--help")
    assert r.returncode == 0
    assert "Tauri" in r.stdout
    assert "--dev" in r.stdout


def test_desktop_bundle_path_finds_macos_app(tmp_path: Path):
    from ephe_cli import _desktop_bundle_path

    app = tmp_path / "bundle" / "macos" / "Ephe.app"
    app.mkdir(parents=True)
    assert _desktop_bundle_path(tmp_path) == app


def test_desktop_bundle_path_finds_appimage(tmp_path: Path):
    from ephe_cli import _desktop_bundle_path

    img = tmp_path / "bundle" / "appimage" / "ephe.AppImage"
    img.mkdir(parents=True)
    assert _desktop_bundle_path(tmp_path) == img


def test_desktop_bundle_path_none_when_missing(tmp_path: Path):
    from ephe_cli import _desktop_bundle_path

    assert _desktop_bundle_path(tmp_path) is None


def test_desktop_missing_toolchain_fails_closed():
    """Without npm: exit 1, a pointer to nodejs.org, no traceback.

    The npm-less PATH is the point: the case the docstring names was never the case
    that ran. With npm on PATH the same call built the desktop app for real, and on a
    runner where that build died its own exit code leaked into the assertion (127).
    """
    r = _run_cli("desktop", env=env_without_tools("npm", "cargo", "node"))
    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
    hosts = [urlparse(u).netloc for u in re.findall(r"https?://\S+", r.stdout)]
    assert hosts == ["nodejs.org"], r.stdout
    assert "Traceback" not in r.stderr
    assert r.stderr.strip() == "", r.stderr


def test_doctor_reports_cell_version_line():
    """E0: doctor lists the ephemora-cell line (the watch is fail-soft — offline
    must not break doctor).

    Real process, real probes, and no npm: `doctor` reaches `ensure_pwa_built` only
    behind `--fix` (ephe_cli.py:394), which this call does not pass, so nothing here
    can build. The offline tolerance IS the pin, so the run stays unmocked.
    """
    r = _run_cli("doctor")
    assert r.returncode in (0, 1)
    assert "ephemora-cell" in r.stdout
    assert "Traceback" not in r.stderr


def test_doctor_cell_outdated_bleibt_exit_0():
    """Offline-first: an updatable optional package from PyPI is a
    hint (a MISSING line with the repair command), but it does not tip the exit
    code of a working setup."""
    import ephe_cli as cli

    args = cli.build_parser().parse_args(["doctor", "--model", "gemma4:12b"])
    fake_resp = {"info": {"version": "999.0.0"}}
    import contextlib

    class _Resp(contextlib.AbstractContextManager):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            import json as _json

            return _json.dumps(fake_resp).encode()

    with (
        patch("ephe_cli._ollama_binary", return_value="/usr/local/bin/ollama"),
        patch("ephe_cli._model_installed", return_value=True),
        patch("ephe_cli._json_get") as json_get,
        patch("ephe_cli._model_loadable", return_value=(True, "test generation ok")),
        patch("ephe_cli._doctor_image_endpoint", return_value=(True, "ok")),
        patch("ephe_cli._doctor_voice", return_value=(True, "ok")),
        patch("ephe_cli._active_engine_choice", return_value=None),
        patch("urllib.request.urlopen", return_value=_Resp()),
    ):
        json_get.side_effect = [
            {"models": [{"name": "gemma4:12b"}]},
            {"status": "ok"},
        ]
        code = args.func(args)

    assert code == 0


# Desktop wave: one-command start (backend auto-start)


def _pin_darwin(monkeypatch) -> None:
    """Pin the host to darwin instead of reading it.

    `cmd_desktop` compares `sys.platform == "darwin"`, and that value is "linux2" on
    Python 2 and on Python 3 before 3.8 — a test that only compared against the
    current value would silently skip the branch on an old interpreter. Pinning the
    attribute the command reads is the isolation; the host never decides an assertion.
    """
    monkeypatch.setattr(sys, "platform", "darwin")


def _desktop_env(monkeypatch, tmp_path, calls):
    """Shared cmd_desktop isolation: toolchain present, build ok, bundle present.

    The host is pinned to darwin (_pin_darwin) because the whole tail of the command —
    write the icon line, install, bring the backend up, open the app — sits behind
    `if sys.platform == "darwin"` (ephe_cli.py:826). On the Linux runner that tail
    never ran, so `calls` stopped at the recorded build and the assertions downstream
    failed on an empty list — the spawn-order test lost its backend start, the
    install/open tests asserted against `[]`. The command's contract does not depend
    on the host that happens to run pytest, so the host is part of the isolation, not
    of the test.
    """
    import ephe_cli as cli

    _pin_darwin(monkeypatch)
    state = {"listening": False}
    monkeypatch.setattr(cli.shutil, "which", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(
        cli, "_run", lambda cmd, **k: calls.append(("run", list(cmd)))
        or subprocess.CompletedProcess(cmd, 0, "", "")
    )
    monkeypatch.setattr(
        cli, "_backend_listening", lambda port=8765, host="127.0.0.1": state["listening"]
    )

    def fake_spawn(port=8765):
        calls.append(("spawn", port))
        state["listening"] = True

    monkeypatch.setattr(cli, "_spawn_backend", fake_spawn)
    bundle = tmp_path / "Ephe.app"
    bundle.mkdir()
    monkeypatch.setattr(cli, "_desktop_bundle_path", lambda target: bundle)
    _install_dirs(monkeypatch, cli, tmp_path)
    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda cmd, **k: calls.append(("open", " ".join(str(x) for x in cmd)))
        or subprocess.CompletedProcess(cmd, 0, "", ""),
    )
    # Writer uses Path.home() and ignores EPHE_CONFIG_DIR (the Tauri reader does too) → isolate.
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path, raising=False)
    return cli


def _install_dirs(monkeypatch, cli, tmp_path: Path):
    """Never write into /Applications just because a test drives the command."""
    monkeypatch.setattr(cli, "APPLICATIONS_DIR", tmp_path / "Applications", raising=False)
    monkeypatch.setattr(cli, "TRASH_DIR", tmp_path / ".Trash", raising=False)
    return tmp_path / "Applications"


def test_desktop_starts_backend_before_opening_app(monkeypatch, tmp_path, capsys):
    """One command: the backend starts automatically BEFORE the app opens."""
    import ephe_cli as cli

    calls: list = []
    _desktop_env(monkeypatch, tmp_path, calls)
    r = cli.cmd_desktop(argparse.Namespace(dev=False, dmg=False))
    assert r == 0
    assert ("spawn", 8765) in calls, "the backend has to be started automatically"
    spawn_i = next(i for i, c in enumerate(calls) if c[0] == "spawn")
    open_i = next(i for i, c in enumerate(calls) if c[0] == "open")
    assert spawn_i < open_i, "the backend runs BEFORE the app opens"
    assert "Backend" in capsys.readouterr().out


def test_desktop_reuses_running_backend(monkeypatch, tmp_path):
    """Backend already runs → no second spawn, the app opens directly."""
    import ephe_cli as cli

    calls: list = []
    cli = _desktop_env(monkeypatch, tmp_path, calls)
    monkeypatch.setattr(cli, "_backend_listening", lambda port=8765, host="127.0.0.1": True)

    def no_spawn(port=8765):
        raise AssertionError("the backend already runs — no second spawn")

    monkeypatch.setattr(cli, "_spawn_backend", no_spawn)
    r = cli.cmd_desktop(argparse.Namespace(dev=False, dmg=False))
    assert r == 0
    assert not any(c[0] == "spawn" for c in calls), calls


def test_desktop_backend_start_failure_warns_but_opens(monkeypatch, tmp_path, capsys):
    """Spawn fails → warning, the app opens anyway (offline gate in the UI)."""
    import ephe_cli as cli

    # The warning lives in the darwin tail of the command — see _pin_darwin.
    _pin_darwin(monkeypatch)
    monkeypatch.setattr(cli.shutil, "which", lambda n: f"/usr/bin/{n}")
    monkeypatch.setattr(cli, "_backend_listening", lambda port=8765, host="127.0.0.1": False)

    def boom(port=8765):
        raise OSError("spawn refused (test)")

    monkeypatch.setattr(cli, "_spawn_backend", boom)
    monkeypatch.setattr(cli, "_run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 0, "", ""))
    bundle = tmp_path / "Ephe.app"
    bundle.mkdir()
    monkeypatch.setattr(cli, "_desktop_bundle_path", lambda target: bundle)
    _install_dirs(monkeypatch, cli, tmp_path)
    monkeypatch.setattr(
        cli.subprocess, "run", lambda cmd, **k: subprocess.CompletedProcess(cmd, 0, "", "")
    )
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path, raising=False)  # see _desktop_env
    r = cli.cmd_desktop(argparse.Namespace(dev=False, dmg=False))
    assert r == 0, "the app opens even though the backend stayed down"
    assert "Backend unreachable" in capsys.readouterr().out


def test_desktop_dev_also_ensures_backend(monkeypatch, tmp_path):
    """--dev also brings the backend up first (Vite proxy → 8765)."""
    import ephe_cli as cli

    calls: list = []
    _desktop_env(monkeypatch, tmp_path, calls)
    r = cli.cmd_desktop(argparse.Namespace(dev=True, dmg=False))
    assert r == 0
    assert ("spawn", 8765) in calls
    spawn_i = next(i for i, c in enumerate(calls) if c[0] == "spawn")
    run_i = next(i for i, c in enumerate(calls) if c[0] == "run")
    assert spawn_i < run_i, "the backend comes up before the dev shell"


def test_desktop_default_build_is_app_bundle_only(monkeypatch, tmp_path):
    """Default build: only the .app (--bundles app) — no DMG/AppleScript step."""
    import ephe_cli as cli

    calls: list = []
    cli = _desktop_env(monkeypatch, tmp_path, calls)
    monkeypatch.setattr(cli, "_backend_listening", lambda port=8765, host="127.0.0.1": True)
    cli.cmd_desktop(argparse.Namespace(dev=False, dmg=False))
    runs = [c[1] for c in calls if c[0] == "run"]
    build = runs[0]
    assert "tauri" in build and "build" in build
    assert "--bundles" in build and "app" in build, build
    cli.cmd_desktop(argparse.Namespace(dev=False, dmg=True))
    runs = [c[1] for c in calls if c[0] == "run"]
    full = runs[-1]
    assert "--bundles" not in full, full


def test_real_run_accepts_cwd(tmp_path):
    """Pin against masking: the REAL _run from core._cli_common (not the
    fake from the monkeypatch tests above) takes cwd — otherwise the
    release path of cmd_desktop only crashes in a real run."""
    from core._cli_common import _run as real_run

    r = real_run(["pwd"], capture_output=True, cwd=tmp_path)
    assert r.stdout.strip() == str(tmp_path)


def test_desktop_bundle_path_finds_real_release_layout(tmp_path: Path):
    """Pin against masking: the REAL Tauri layout is
    target/<profile>/bundle/<platform>/… — not target/bundle/…"""
    from ephe_cli import _desktop_bundle_path

    app = tmp_path / "release" / "bundle" / "macos" / "Ephe.app"
    app.mkdir(parents=True)
    assert _desktop_bundle_path(tmp_path) == app


# R5: one Ephe, not two
# `ephe desktop` used to build and open the bundle inside the target folder.
# Finder and Spotlight therefore knew two app bundles — the installed one and
# the built one. A LaunchServices sweep only finds registration entries, the second *file*
# remains; so the command has to clean up after itself.


def _bundle(mit_dir: Path, kern: bytes = b"ephe-bin") -> Path:
    app = mit_dir / "Ephe.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "MacOS" / "app").write_bytes(kern)
    return app


def test_install_kopiert_und_entfernt_den_baurest(tmp_path):
    from ephe_cli import _install_desktop_bundle

    bau = _bundle(tmp_path / "bau")
    ziel = tmp_path / "Applications"
    ort = _install_desktop_bundle(bau, ziel, tmp_path / ".Trash")

    assert ort == ziel / "Ephe.app"
    assert (ort / "Contents" / "MacOS" / "app").read_bytes() == b"ephe-bin"
    assert not bau.exists(), "the built bundle must not stay behind as a second Ephe"


def test_install_legt_die_ersetzte_in_den_paperkorb(tmp_path):
    from ephe_cli import _install_desktop_bundle

    bau = _bundle(tmp_path / "bau", b"neu")
    ziel = tmp_path / "Applications"
    alt = _bundle(ziel, b"alt")
    papier = tmp_path / ".Trash"

    ort = _install_desktop_bundle(bau, ziel, papier)

    assert (ort / "Contents" / "MacOS" / "app").read_bytes() == b"neu"
    umgezogen = list(papier.glob("Ephe-vor-*"))
    assert len(umgezogen) == 1, "the replaced app is in the trash, not gone"
    assert (umgezogen[0] / "Contents" / "MacOS" / "app").read_bytes() == b"alt"


def test_install_blascht_gleiches_bundle_nicht_zweimal_um(tmp_path):
    from ephe_cli import _install_desktop_bundle

    bau = _bundle(tmp_path / "bau", b"gleich")
    ziel = tmp_path / "Applications"
    _bundle(ziel, b"gleich")
    papier = tmp_path / ".Trash"

    _install_desktop_bundle(bau, ziel, papier)

    assert not papier.exists() or list(papier.iterdir()) == [], "no reason for a copy"
    assert not bau.exists()


def test_desktop_installiert_per_default_und_oeffnet_dort(monkeypatch, tmp_path, capsys):
    import ephe_cli as cli

    calls: list = []
    cli = _desktop_env(monkeypatch, tmp_path, calls)
    monkeypatch.setattr(cli, "_backend_listening", lambda port=8765, host="127.0.0.1": True)
    r = cli.cmd_desktop(argparse.Namespace(dev=False, dmg=False, install=True))

    assert r == 0
    geoeffnet = [c[1] for c in calls if c[0] == "open"]
    assert any(str(cli.APPLICATIONS_DIR) in weg for weg in geoeffnet), geoeffnet
    assert "exactly one Ephe" in capsys.readouterr().out


def test_desktop_no_install_oeffnet_im_zielordner(monkeypatch, tmp_path):
    import ephe_cli as cli

    calls: list = []
    cli = _desktop_env(monkeypatch, tmp_path, calls)
    monkeypatch.setattr(cli, "_backend_listening", lambda port=8765, host="127.0.0.1": True)
    r = cli.cmd_desktop(argparse.Namespace(dev=False, dmg=False, install=False))

    assert r == 0
    geoeffnet = [c[1] for c in calls if c[0] == "open"]
    assert any("Applications" not in weg for weg in geoeffnet), geoeffnet
    assert (cli.APPLICATIONS_DIR / "Ephe.app").exists() is False


# R7: the app icon needs a line of its own


def test_desktop_konfig_schreibt_interpreter_projekt_und_port(tmp_path):
    import json as _json

    from ephe_cli import _schreibe_desktop_konfig

    pfad = _schreibe_desktop_konfig(
        Path("/x/ephe"), "/x/.venv/bin/python", port=8765, home=tmp_path
    )
    assert pfad == tmp_path / ".ephe" / "desktop.json"
    inhalt = _json.loads(pfad.read_text(encoding="utf-8"))
    assert inhalt == {"python": "/x/.venv/bin/python", "project_root": "/x/ephe", "port": 8765}


def test_desktop_konfig_legt_die_werkbank_an(tmp_path):
    from ephe_cli import _schreibe_desktop_konfig

    ziel = tmp_path / "neu" / "tiefer"
    assert not ziel.exists()
    _schreibe_desktop_konfig(Path("/x/ephe"), "/p", home=ziel)
    assert (ziel / ".ephe" / "desktop.json").is_file()


def test_desktop_hinterlaesst_die_zeile_beim_bau(monkeypatch, tmp_path, capsys):
    """The path via the icon reads exactly this line later — so the
    build-and-install command has to leave it, otherwise the window stays alone."""
    import ephe_cli as cli

    calls: list = []
    cli = _desktop_env(monkeypatch, tmp_path, calls)
    monkeypatch.setattr(cli.Path, "home", lambda: tmp_path, raising=False)
    monkeypatch.setattr(
        cli, "_schreibe_desktop_konfig", lambda *a, **k: calls.append(("konfig", a[1]))
    )
    r = cli.cmd_desktop(argparse.Namespace(dev=False, dmg=False, install=True))
    assert r == 0
    assert any(c[0] == "konfig" for c in calls), calls
