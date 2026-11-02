"""The doctor names the app a click opens, and the copies that can answer instead.

Measured 2026-11-02 on the machine that ships Ephe: the owner updated the app, restarted
it, and saw none of the new work. The updater had written 0.5.5 into `/Applications`
correctly — twenty other bundles carried the same `com.ephe.ephe` identifier (leftovers of
mounted DMGs, Tauri builds inside worktrees), and macOS resolves an identifier when a click
chooses the app. Nothing in the product could see that, so the row is the instrument: the
installed version, the backend version, and every other bundle Spotlight answers with.

The cases drive the helper directly with the host facts replaced, because a test must not
pass or fail depending on what happens to sit in a developer's `~/Downloads`.
"""
from __future__ import annotations

import importlib.util
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("ephe_cli_doctor_app", ROOT / "ephe_cli.py")
assert _spec is not None and _spec.loader is not None
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_a_machine_that_is_not_a_mac_says_nothing():
    original = mod.sys.platform
    try:
        mod.sys.platform = "linux"
        assert mod._doctor_desktop_app({"version": "0.5.5"}) is None
    finally:
        mod.sys.platform = original


def test_no_installed_app_is_said_plainly(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(mod, "DESKTOP_INSTALL_PATH", tmp_path / "Absent.app")
    ok, detail = mod._doctor_desktop_app({"version": "0.5.5"})
    assert ok is False
    assert "not installed" in detail


def test_an_other_bundle_with_the_same_identifier_is_named_with_the_command(
    tmp_path: Path, monkeypatch
):
    installed = tmp_path / "Applications" / "Ephe.app"
    impostor = tmp_path / "ephe-wt" / "night" / "Ephe.app"
    monkeypatch.setattr(mod, "DESKTOP_INSTALL_PATH", installed)
    monkeypatch.setattr(mod, "_desktop_bundle_version", lambda _p: "0.5.5")
    monkeypatch.setattr(mod, "_desktop_bundles_other_than", lambda _p: [str(impostor)])

    ok, detail = mod._doctor_desktop_app({"version": "0.5.5"})
    assert ok is False
    assert str(impostor) in detail
    assert "lsregister" in detail


def test_an_app_older_than_the_backend_names_both_numbers(tmp_path: Path, monkeypatch):
    installed = tmp_path / "Ephe.app"
    monkeypatch.setattr(mod, "DESKTOP_INSTALL_PATH", installed)
    monkeypatch.setattr(mod, "_desktop_bundle_version", lambda _p: "0.5.4")
    monkeypatch.setattr(mod, "_desktop_bundles_other_than", lambda _p: [])

    ok, detail = mod._doctor_desktop_app({"version": "0.5.5"})
    assert ok is False
    assert "0.5.4" in detail and "0.5.5" in detail


def test_one_bundle_matching_the_backend_is_the_quiet_answer(tmp_path: Path, monkeypatch):
    installed = tmp_path / "Ephe.app"
    monkeypatch.setattr(mod, "DESKTOP_INSTALL_PATH", installed)
    monkeypatch.setattr(mod, "_desktop_bundle_version", lambda _p: "0.5.5")
    monkeypatch.setattr(mod, "_desktop_bundles_other_than", lambda _p: [])

    ok, detail = mod._doctor_desktop_app({"version": "0.5.5"})
    assert ok is True
    assert "only bundle" in detail


def test_the_version_is_read_from_the_bundle_itself(tmp_path: Path):
    app = tmp_path / "Ephe.app"
    (app / "Contents").mkdir(parents=True)
    import plistlib

    with (app / "Contents" / "Info.plist").open("wb") as handle:
        plistlib.dump({"CFBundleShortVersionString": "0.5.5", "CFBundleIdentifier": "com.ephe.ephe"}, handle)

    assert mod._desktop_bundle_version(app) == "0.5.5"
    assert mod._desktop_bundle_version(tmp_path / "Nope.app") is None


def test_the_row_is_installed_under_the_desktop_checks():
    source = (ROOT / "ephe_cli.py").read_text(encoding="utf-8")
    assert '("Desktop app"' in source
    # A state, never an exit code: a machine without the desktop app is a valid machine.
    assert source.index('informational.append(("Desktop app"') > source.index(
        'informational.append(("Update"'
    )
    assert "checks.append((\"Desktop app\"" not in source


def test_a_scan_that_never_answers_does_not_hold_the_doctor(tmp_path: Path, monkeypatch):
    """The probe gets a budget and no more — a doctor line must not become a hang."""

    def never(*_args, **_kwargs):
        threading.Event().wait(30)  # outlives the budget; the daemon thread is abandoned
        raise AssertionError("a late scan result is never read")

    monkeypatch.setattr(mod.subprocess, "run", never)
    assert mod._desktop_bundles_other_than(tmp_path / "Ephe.app", seconds=0.2) == []


def test_the_constants_name_the_bundle_and_the_install_path():
    assert mod.DESKTOP_BUNDLE_ID == "com.ephe.ephe"
    assert mod.DESKTOP_INSTALL_PATH == Path("/Applications/Ephe.app")
    assert mod.LSREGISTER.endswith("/lsregister")
