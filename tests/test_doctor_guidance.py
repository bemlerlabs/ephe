"""What `ephe doctor` does when the setup is not ready.

The rows describe the machine. The part a reader acts on is the last line: one
command that moves the setup forward, and an exit code that names a broken setup
without failing a state the app resolves by itself.
"""

from __future__ import annotations

import importlib.metadata as im
import json
import urllib.request as ur

import pytest

import ephe_cli
from core.engine_config import EngineChoice

#: The real voice row, captured before `doctor_box` replaces it: the read-only test
#: below runs the doctor's own probe rather than the fixture's stand-in.
_REAL_DOCTOR_VOICE = ephe_cli._doctor_voice


def _parser():
    return ephe_cli.build_parser()


def _offline(*_a, **_k):
    raise OSError("offline")


@pytest.fixture
def doctor_box(monkeypatch, tmp_path):
    """A local, healthy machine; each test overrides the one row it is about."""
    monkeypatch.setattr(ephe_cli, "PROJECT_ROOT", tmp_path)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "index.html").write_text("x")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "generate_skills_lock.py").write_text("def verify(root):\n    return True, []\n")
    monkeypatch.setattr(ephe_cli, "_ollama_binary", lambda: "/usr/local/bin/ollama")
    monkeypatch.setattr(ephe_cli, "_local_chosen_tag", lambda: "")
    monkeypatch.setattr(ephe_cli, "_doctor_image_endpoint", lambda: (True, "ok"))
    monkeypatch.setattr(ephe_cli, "_doctor_voice", lambda: (True, "ok"))
    monkeypatch.setattr(ephe_cli, "_model_installed", lambda _m: True)
    monkeypatch.setattr(ephe_cli, "_model_loadable", lambda _m: (True, "ok"))
    monkeypatch.setattr(ephe_cli, "_cell_pinned_ceiling", lambda: None)
    monkeypatch.setattr(im, "version", lambda _n: "0.2.0")
    monkeypatch.setattr(ur, "urlopen", _offline)
    return monkeypatch


def test_a_half_written_config_is_named_instead_of_probed(doctor_box, capsys):
    """A remote choice without its endpoint used to reach the endpoint probe, whose
    answer was a key-binding complaint about an engine that has no endpoint."""
    doctor_box.setattr(
        ephe_cli,
        "_active_engine_choice",
        lambda: EngineChoice(provider="openai_compatible", model="a-tag", api_url=None),
    )
    probed: list[tuple] = []
    doctor_box.setattr(
        ephe_cli,
        "_probe_active_remote_engine",
        lambda *a: (probed.append(a), (False, "unused"))[1],
    )
    doctor_box.setattr(ephe_cli, "_json_get", lambda *_a, **_k: None)

    code = ephe_cli.cmd_doctor(_parser().parse_args(["doctor"]))

    out = capsys.readouterr().out
    assert "Engine config" in out
    assert "api_url" in out
    assert probed == []
    assert "Next: ephe" in out
    assert code == 1


def test_a_stopped_app_is_not_a_broken_setup(doctor_box, capsys):
    """The terminal app serves itself; a server that is not running is a state."""
    doctor_box.setattr(ephe_cli, "_active_engine_choice", lambda: None)
    doctor_box.setattr(ephe_cli, "_json_get", lambda *_a, **_k: None)

    code = ephe_cli.cmd_doctor(_parser().parse_args(["doctor"]))

    out = capsys.readouterr().out
    assert "Ephe server" in out
    assert "start it with: ephe start" in out
    assert "Next: ephe" in out
    assert code == 0


def test_no_engine_at_all_is_a_state_the_app_resolves(doctor_box, capsys):
    doctor_box.setattr(ephe_cli, "_active_engine_choice", lambda: None)
    doctor_box.setattr(ephe_cli, "_json_get", lambda *_a, **_k: None)

    code = ephe_cli.cmd_doctor(_parser().parse_args(["doctor"]))

    out = capsys.readouterr().out
    assert "none chosen yet" in out
    assert "Next: ephe   # no engine chosen yet — the app opens its setup" in out
    assert code == 0


def test_a_missing_model_names_the_pull_command(doctor_box, capsys):
    doctor_box.setattr(ephe_cli, "_active_engine_choice", lambda: None)
    doctor_box.setattr(ephe_cli, "_json_get", lambda *_a, **_k: {"models": []})
    doctor_box.setattr(ephe_cli, "_model_installed", lambda _m: False)

    code = ephe_cli.cmd_doctor(_parser().parse_args(["doctor", "--model", "gemma:2b"]))

    out = capsys.readouterr().out
    assert "Next: ephe update --model gemma:2b" in out
    assert code == 1


def test_fix_without_a_model_is_a_skip_and_not_a_failure(doctor_box, monkeypatch):
    """`--fix` on a box with no model chose nothing to repair; it must stay green."""
    monkeypatch.setattr(ephe_cli, "_repair_repo", lambda: (True, "ok"))
    monkeypatch.setattr(ephe_cli, "_repair_dependencies", lambda: (True, "ok"))
    monkeypatch.setattr(ephe_cli, "ensure_pwa_built", lambda: True)
    monkeypatch.setattr(ephe_cli, "_repair_desktop_bundles", lambda: (True, "nothing to clear"))

    repairs = ephe_cli._run_doctor_repairs(_parser().parse_args(["doctor"]))

    model_rows = [row for row in repairs if row[0] == "Repair model"]
    assert model_rows and model_rows[0][1] is True
    assert all(ok for _name, ok, _detail in repairs)


def test_the_desktop_row_reaches_the_report_without_bearing_the_exit_code(doctor_box, capsys):
    """The row is the instrument for "updated, restarted, nothing changed", so it has to
    appear where a person reads the doctor — and a machine whose `.app` is an old copy must
    not turn a working setup red. The same box is run twice: the row's own answer changes,
    the verdict does not."""
    doctor_box.setattr(
        ephe_cli,
        "_doctor_desktop_app",
        lambda _health: (False, "0.5.4 while the backend runs 0.5.5"),
    )
    with_row = ephe_cli.cmd_doctor(_parser().parse_args(["doctor"]))
    out_with = capsys.readouterr().out

    doctor_box.setattr(ephe_cli, "_doctor_desktop_app", lambda _health: None)
    without_row = ephe_cli.cmd_doctor(_parser().parse_args(["doctor"]))
    out_without = capsys.readouterr().out

    assert "Desktop app - 0.5.4 while the backend runs 0.5.5" in out_with
    assert "Desktop app" not in out_without
    assert with_row == without_row


def test_the_desktop_row_is_optional_not_a_failure(doctor_box, capsys):
    """`OPTIONAL`, never `FAIL`: the desktop app is one surface of many, and a box that
    runs the CLI alone is a valid box."""
    doctor_box.setattr(ephe_cli, "_doctor_desktop_app", lambda _health: (False, "no bundle here"))

    ephe_cli.cmd_doctor(_parser().parse_args(["doctor"]))

    line = [l for l in capsys.readouterr().out.splitlines() if "Desktop app" in l]
    assert len(line) == 1
    assert line[0].lstrip().startswith("OPTIONAL")


def _cell_row(out: str) -> str:
    rows = [line for line in out.splitlines() if "ephemora-cell" in line]
    assert len(rows) == 1, out
    return rows[0]


def test_a_missing_optional_cell_names_the_install_not_the_network(doctor_box, capsys):
    """An absent `ephemora-cell` is the optional extra nobody installed, not a network
    outage: the row names the package, the extra and the repair, and asks PyPI nothing."""

    def _version(name: str) -> str:
        if name == "ephemora-cell":
            raise im.PackageNotFoundError(name)
        return "0.2.0"

    fetched: list[str] = []

    def _record(url, *_a, **_k):
        fetched.append(str(url))
        raise AssertionError("a package that is not installed has no version to compare")

    doctor_box.setattr(im, "version", _version)
    doctor_box.setattr(ur, "urlopen", _record)
    # The developer's shell may carry an engine env; this test is about the cell row.
    doctor_box.setattr(ephe_cli, "_active_engine_choice", lambda: None)
    doctor_box.setattr(ephe_cli, "_json_get", lambda *_a, **_k: None)

    code = ephe_cli.cmd_doctor(_parser().parse_args(["doctor"]))

    row = _cell_row(capsys.readouterr().out)
    assert "not installed" in row
    assert "ephe[sandbox]" in row
    assert "optional" in row.lower()
    assert "offline" not in row.lower()
    assert row.lstrip().startswith("OPTIONAL")
    assert code == 0
    assert fetched == []


class _PyPIResponse:
    """The one method the watch uses: `json.load(resp)` reads `resp.read()`."""

    def __init__(self, payload: dict) -> None:
        self._raw = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self) -> bytes:
        return self._raw


def test_an_installed_cell_is_compared_with_pypi_and_stays_optional(doctor_box, capsys):
    """The other state: the package is there, so the watch runs and PyPI decides the line.
    A failed fetch is the only case that may say `offline`."""
    doctor_box.setattr(
        im, "version", lambda name: "1.1.5" if name == "ephemora-cell" else "0.2.0"
    )
    doctor_box.setattr(
        ur,
        "urlopen",
        lambda *_a, **_k: _PyPIResponse({"info": {"version": "1.1.5", "license": "BUSL-1.1"}}),
    )
    doctor_box.setattr(ephe_cli, "_active_engine_choice", lambda: None)
    doctor_box.setattr(ephe_cli, "_json_get", lambda *_a, **_k: None)

    code = ephe_cli.cmd_doctor(_parser().parse_args(["doctor"]))

    out = capsys.readouterr().out
    row = _cell_row(out)
    assert "1.1.5" in row and "PyPI current" in row
    assert "offline" not in row.lower()
    assert code == 0, out


def test_doctor_on_a_fresh_home_creates_no_voice_folder(doctor_box, tmp_path, capsys):
    """`ephe doctor` is a check. On a fresh HOME with `piper` on PATH it used to create
    `~/.ephe/voices` through the lookup helper and then report the folder it had made."""
    import core.engine_config as engine_config
    import core.voice_config as voice_config

    config_dir = tmp_path / "home" / ".ephe"
    doctor_box.setattr(engine_config, "CONFIG_DIR", config_dir)
    doctor_box.setattr(voice_config, "piper_binary_available", lambda: True)
    doctor_box.setattr("core.transcribe.is_whisper_available", lambda: False)
    doctor_box.setattr(ephe_cli, "_doctor_voice", _REAL_DOCTOR_VOICE)
    # The developer's shell may carry an engine env; this test is about the folder.
    doctor_box.setattr(ephe_cli, "_active_engine_choice", lambda: None)
    doctor_box.setattr(ephe_cli, "_json_get", lambda *_a, **_k: None)

    code = ephe_cli.cmd_doctor(_parser().parse_args(["doctor"]))

    out = capsys.readouterr().out
    assert "Voice (TTS)" in out
    assert not (config_dir / "voices").exists(), "the voice row created the folder it looked for"
    assert not config_dir.exists(), "a read-only probe left state behind"
    assert code == 0
