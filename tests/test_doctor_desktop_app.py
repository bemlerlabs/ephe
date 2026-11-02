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


def test_a_machine_that_is_not_a_mac_says_nothing(tmp_path: Path):
    # The host facts are arguments, so this runs the same on a Linux runner as on the Mac
    # that has the app: no ambient read, no test that only passes where the product ships.
    assert mod._doctor_desktop_app({"version": "0.5.5"}, "linux", tmp_path / "Ephe.app") is None


def test_no_installed_app_is_said_plainly(tmp_path: Path):
    ok, detail = mod._doctor_desktop_app({"version": "0.5.5"}, "darwin", tmp_path / "Absent.app")
    assert ok is False
    assert "not installed" in detail
    assert str(tmp_path / "Absent.app") in detail


def test_an_other_bundle_with_the_same_identifier_is_named_with_the_command(
    tmp_path: Path, monkeypatch
):
    installed = tmp_path / "Applications" / "Ephe.app"
    impostor = tmp_path / "ephe-wt" / "night" / "Ephe.app"
    monkeypatch.setattr(mod, "_desktop_bundle_version", lambda _p: "0.5.5")
    monkeypatch.setattr(
        mod, "_desktop_bundles_other_than", lambda _p, **_k: ([str(impostor)], "")
    )

    ok, detail = mod._doctor_desktop_app({"version": "0.5.5"}, "darwin", installed)
    assert ok is False
    assert str(impostor) in detail
    assert "lsregister" in detail


def test_an_app_older_than_the_backend_names_both_numbers(tmp_path: Path, monkeypatch):
    installed = tmp_path / "Ephe.app"
    monkeypatch.setattr(mod, "_desktop_bundle_version", lambda _p: "0.5.4")
    monkeypatch.setattr(mod, "_desktop_bundles_other_than", lambda _p, **_k: ([], ""))

    ok, detail = mod._doctor_desktop_app({"version": "0.5.5"}, "darwin", installed)
    assert ok is False
    assert "0.5.4" in detail and "0.5.5" in detail


def test_one_bundle_matching_the_backend_is_the_quiet_answer(tmp_path: Path, monkeypatch):
    installed = tmp_path / "Ephe.app"
    monkeypatch.setattr(mod, "_desktop_bundle_version", lambda _p: "0.5.5")
    monkeypatch.setattr(mod, "_desktop_bundles_other_than", lambda _p, **_k: ([], ""))

    ok, detail = mod._doctor_desktop_app({"version": "0.5.5"}, "darwin", installed)
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


def test_the_scan_reports_the_bundles_it_found_and_drops_the_rest(
    tmp_path: Path, monkeypatch
):
    """The filtering the row answers for, driven on every platform.

    A copy that no longer exists cannot be opened, so it is not something a click can reach —
    and a test that let the real command answer would only pass where the runner indexes the
    folder the fixture lives in."""
    import subprocess

    installed = tmp_path / "Applications" / "Ephe.app"
    night = tmp_path / "night" / "Ephe.app"
    other = tmp_path / "other" / "Ephe.app"
    gone = tmp_path / "gone" / "Ephe.app"
    text = tmp_path / "not" / "a_text_file"
    for leaf in (installed, night, other, text):
        leaf.parent.mkdir(parents=True, exist_ok=True)
        leaf.mkdir() if leaf.suffix == ".app" else leaf.write_text("x")

    found = "\n".join(
        [str(installed), str(night), str(other), str(other), str(gone), str(text), ""]
    )
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, found, ""),
    )
    paths, error = mod._desktop_bundles_other_than(installed, seconds=1.0)
    assert error == ""
    assert paths == [str(night), str(other)]


def test_a_registry_that_cannot_be_read_is_said_as_that(tmp_path: Path, monkeypatch):
    """A failed read is itself the finding.

    The first version of this row caught its own parse error and answered "the only bundle"
    on a machine holding seventy-four. A diagnostic that goes quiet when it fails is worse
    than one that says it did not look."""

    def refuse(*_args, **_kwargs):
        raise OSError("no registry here")

    monkeypatch.setattr(mod.subprocess, "run", refuse)
    paths, error = mod._desktop_bundles_other_than(tmp_path / "Ephe.app", seconds=1.0)
    assert paths == []
    assert "OSError" in error


def test_the_row_names_an_unreadable_registry_instead_of_a_clean_machine(
    tmp_path: Path, monkeypatch
):
    installed = tmp_path / "Ephe.app"
    monkeypatch.setattr(mod, "_desktop_bundle_version", lambda _p: "0.5.5")
    monkeypatch.setattr(mod, "_desktop_bundles_other_than", lambda _p, **_k: ([], "lsregister died"))

    ok, detail = mod._doctor_desktop_app({"version": "0.5.5"}, "darwin", installed)
    assert ok is False
    assert "could not be read" in detail
    assert "lsregister died" in detail


def test_the_dump_parser_reads_the_record_that_carries_the_identifier():
    """`lsregister -dump` is a run of records; the identifier and the path sit in the same
    one, so the pair has to be kept together rather than searched line by line."""
    dump = "\n".join(
        [
            "-----",
            "bundle:                     Ephe (0x6190)",
            "path:                       /Applications/Ephe.app (0x7f10)",
            "identifier:                 com.ephe.ephe",
            "-----",
            "bundle:                     Other (0x1)",
            "path:                       /Applications/Other.app (0x2)",
            "identifier:                 com.other.other",
            "-----",
            "bundle:                     Ephe trash (0x9)",
            "path:                       /Users/dev/.Trash/Ephe.app (0xa)",
            "identifier:                 com.ephe.ephe",
        ]
    )
    assert mod._dump_paths_for(dump, "com.ephe.ephe") == [
        "/Applications/Ephe.app",
        "/Users/dev/.Trash/Ephe.app",
    ]


def test_the_places_line_counts_the_copies_where_they_sit(tmp_path: Path):
    places = mod._bundle_places(
        [str(tmp_path / "Trash" / f"Ephe-{i}.app") for i in range(3)]
        + [str(tmp_path / "tmp" / "Ephe.app")]
    )
    assert f"3 in {tmp_path / 'Trash'}" in places
    assert f"1 in {tmp_path / 'tmp'}" in places


def test_a_scan_that_never_answers_does_not_hold_the_doctor(tmp_path: Path, monkeypatch):
    """The probe gets a budget and no more — a doctor line must not become a hang."""

    def never(*_args, **_kwargs):
        threading.Event().wait(30)  # outlives the budget; the daemon thread is abandoned
        raise AssertionError("a late scan result is never read")

    monkeypatch.setattr(mod.subprocess, "run", never)
    assert mod._desktop_bundles_other_than(tmp_path / "Ephe.app", seconds=0.2)[1] != ""


def test_the_constants_name_the_bundle_and_the_install_path():
    assert mod.DESKTOP_BUNDLE_ID == "com.ephe.ephe"
    assert mod.DESKTOP_INSTALL_PATH == Path("/Applications/Ephe.app")
    assert mod.LSREGISTER.endswith("/lsregister")
