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
    assert "the backend runs the same 0.5.5" in detail


def test_a_backend_that_never_answered_is_not_reported_as_a_match(tmp_path: Path, monkeypatch):
    """The row compares the backend it actually read."""
    # Measured 2026-11-03 with the server stopped: this row claimed "matching the backend"
    # two rows under the doctor's own "Ephe server — not running".
    installed = tmp_path / "Ephe.app"
    monkeypatch.setattr(mod, "_desktop_bundle_version", lambda _p: "0.5.5")
    monkeypatch.setattr(mod, "_desktop_bundles_other_than", lambda _p, **_k: ([], ""))

    ok, detail = mod._doctor_desktop_app(None, "darwin", installed)
    assert ok is True
    assert "no backend answered" in detail
    assert "matching" not in detail


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


def test_a_registry_that_answers_with_nothing_is_an_error(tmp_path: Path, monkeypatch):
    """The quiet failure this row exists to catch.

    `lsregister` can exit non-zero with an empty body. Parsed, that is a list of zero bundles,
    which is the same answer a clean machine gives — so the return code is read before the
    body is trusted."""
    import subprocess

    def fails(*_a, **_k):
        return subprocess.CompletedProcess([], 1, "", "registration database unavailable")

    monkeypatch.setattr(mod.subprocess, "run", fails)
    paths, error = mod._registered_bundle_paths(seconds=1.0)
    assert paths == []
    assert "lsregister answered 1" in error


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


def test_the_repair_is_silent_where_there_is_no_bundle_registry(tmp_path: Path):
    ok, detail = mod._repair_desktop_bundles(
        installed=tmp_path / "Ephe.app", runner=lambda _a: 0, platform="linux"
    )
    assert ok is True
    assert "skipped" in detail


def test_the_repair_says_so_when_there_is_nothing_to_clear(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(mod, "_desktop_bundles_other_than", lambda _p: ([], ""))
    calls: list[list[str]] = []
    ok, detail = mod._repair_desktop_bundles(
        installed=tmp_path / "Ephe.app", runner=lambda a: calls.append(a) or 0, platform="darwin"
    )
    assert ok is True
    assert "nothing to clear" in detail
    assert calls == []


def test_the_repair_forgets_each_stale_bundle_and_keeps_the_installed_one(
    tmp_path: Path, monkeypatch
):
    """The order the person depends on: forget the copies, then make sure the real app answers."""
    installed = tmp_path / "Applications" / "Ephe.app"
    stale = [
        str(tmp_path / ".Trash" / "Ephe-0.3.0.app"),
        str(tmp_path / "tmp" / "buildA.app"),
    ]
    reads = iter([(stale, ""), ([], "")])
    monkeypatch.setattr(mod, "_desktop_bundles_other_than", lambda _p: next(reads))
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> int:
        calls.append(argv)
        return 0

    ok, detail = mod._repair_desktop_bundles(
        installed=installed, runner=runner, platform="darwin"
    )
    assert ok is True
    assert "unregistered 2" in detail
    assert [c[2] for c in calls[:2]] == [stale[0], stale[1]]
    assert calls[0][0] == mod.LSREGISTER and calls[0][1] == "-u"
    assert calls[-1][1] == "-f" and calls[-1][2] == str(installed)
    assert str(installed) not in [c[2] for c in calls if c[1] == "-u"]
    assert all(c[0] == mod.LSREGISTER for c in calls)


def test_the_repair_reports_a_registry_it_cannot_read(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        mod, "_desktop_bundles_other_than", lambda _p: ([], "lsregister answered 1")
    )
    ok, detail = mod._repair_desktop_bundles(
        installed=tmp_path / "Ephe.app", runner=lambda _a: 0, platform="darwin"
    )
    assert ok is False
    assert "could not be read" in detail


def test_the_repair_says_when_the_copies_are_still_there(tmp_path: Path, monkeypatch):
    """A forget that the registry refused is not reported as a clean machine."""
    installed = tmp_path / "Applications" / "Ephe.app"
    stale = [
        str(tmp_path / ".Trash" / "Ephe-0.3.0.app"),
        str(tmp_path / ".Trash" / "Ephe-old.app"),
    ]
    reads = iter([(stale, ""), ([stale[1]], "")])
    monkeypatch.setattr(mod, "_desktop_bundles_other_than", lambda _p: next(reads))

    ok, detail = mod._repair_desktop_bundles(
        installed=installed,
        runner=lambda argv: 1 if argv[1] == "-u" and argv[2] == stale[1] else 0,
        platform="darwin",
    )
    assert ok is False
    assert "1 of 2 still answer" in detail
    assert "refused: 1" in detail


def test_the_repair_names_a_installed_app_it_cannot_re_register(tmp_path: Path, monkeypatch):
    installed = tmp_path / "Applications" / "Ephe.app"
    reads = iter((([str(tmp_path / "a.app")], ""), ([], "")))
    monkeypatch.setattr(mod, "_desktop_bundles_other_than", lambda _p: next(reads))

    ok, detail = mod._repair_desktop_bundles(
        installed=installed,
        runner=lambda argv: 1 if argv[1] == "-f" else 0,
        platform="darwin",
    )
    assert ok is False
    assert "could not re-register" in detail


def test_the_repair_is_wired_into_the_fix_run():
    source = (ROOT / "ephe_cli.py").read_text(encoding="utf-8")
    assert '("Repair desktop bundles", bundles_ok, bundles_detail)' in source
    # A repair, so it belongs to `--fix` — and it is the one that answers the owner's
    # standing complaint, so it must not be buried behind a flag nobody reads.
    assert "_repair_desktop_bundles()" in source


def test_a_repair_never_touches_the_host_it_is_tested_on(tmp_path: Path, monkeypatch):
    """The guard, and the way a caller steps around it.

    `_run_doctor_repairs` calls this with no arguments, so a forgotten stub would run real
    `lsregister -u` commands against the developer's own applications. Naming the bundle is
    the signal that the caller is answering a question about a path, not fixing a machine."""
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    calls: list[list[str]] = []
    monkeypatch.setattr(mod, "_desktop_bundles_other_than", lambda _p: ([str(tmp_path / "a.app")], ""))
    mod._repair_desktop_bundles(runner=lambda a: calls.append(a) or 0, platform="darwin")
    assert calls, "a named host is repaired when the suite is not running"

    # Under the suite, with no bundle named, the same call changes nothing.
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "tests/test_doctor_desktop_app.py::x")
    untouched: list[list[str]] = []
    ok, detail = mod._repair_desktop_bundles(
        runner=lambda a: untouched.append(a) or 0, platform="darwin"
    )
    assert ok is True
    assert untouched == []
    assert "does not run inside the suite" in detail


def test_the_default_runner_reports_a_missing_tool_instead_of_raising(
    tmp_path: Path, monkeypatch
):
    """The repair's own command path, with no runner injected.

    Every other case hands the repair a fake because the real `lsregister` exists on one
    operating system. This one answers the question the fake never asks: what happens on a
    machine where the tool is simply not there. The answer has to be a sentence the person can
    read, and never a traceback out of a repair they asked for — and the re-register is the
    command that says so first, because a forget that never ran leaves nothing to report."""
    installed = tmp_path / "Applications" / "Ephe.app"
    stale = str(tmp_path / ".Trash" / "Ephe-old.app")

    def absent(*_a, **_k):
        raise FileNotFoundError("no lsregister here")

    monkeypatch.setattr(mod, "_desktop_bundles_other_than", lambda _p: ([stale], ""))
    monkeypatch.setattr(mod.subprocess, "run", absent)

    ok, detail = mod._repair_desktop_bundles(installed=installed, platform="darwin")
    assert ok is False
    assert "could not re-register" in detail


def test_a_repair_that_cannot_re_read_after_clearing_says_that(
    tmp_path: Path, monkeypatch
):
    """Success has to be seen before it is claimed.

    The forget commands all answered zero; the registry then would not say what it holds now.
    Reporting "cleared" from that state is the same claim the row was built to stop making."""
    installed = tmp_path / "Applications" / "Ephe.app"
    stale = [str(tmp_path / ".Trash" / "Ephe-old.app")]
    reads = iter([(stale, ""), ([], "the dump stopped answering")])
    monkeypatch.setattr(mod, "_desktop_bundles_other_than", lambda _p: next(reads))

    ok, detail = mod._repair_desktop_bundles(
        installed=installed, runner=lambda _a: 0, platform="darwin"
    )
    assert ok is False
    assert "could not be re-read" in detail
    assert "cleared 1" in detail
