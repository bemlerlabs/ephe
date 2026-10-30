"""What `ephe doctor` does when the setup is not ready.

The rows describe the machine. The part a reader acts on is the last line: one
command that moves the setup forward, and an exit code that names a broken setup
without failing a state the app resolves by itself.
"""

from __future__ import annotations

import importlib.metadata as im
import urllib.request as ur

import pytest

import ephe_cli
from core.engine_config import EngineChoice


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

    repairs = ephe_cli._run_doctor_repairs(_parser().parse_args(["doctor"]))

    model_rows = [row for row in repairs if row[0] == "Repair model"]
    assert model_rows and model_rows[0][1] is True
    assert all(ok for _name, ok, _detail in repairs)
