"""The CLI seams scripts read: one JSON document, a plugin listing a script can parse,
and a hint that names a command the parser accepts.

Each test here failed before the change it guards and names the surface it protects.
"""

from __future__ import annotations

import json
import shlex
import types

import ephe_cli


def _parser():
    return ephe_cli.build_parser()


def _fake_run(returncode: int = 0, stdout: str = "", stderr: str = ""):
    def runner(_cmd, *_a, **_k):
        return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    return runner


# update --json


def test_update_json_is_exactly_one_document(monkeypatch, capsys, tmp_path):
    """A consumer pipes this verb into a parser: two concatenated objects is not JSON."""
    monkeypatch.setattr(ephe_cli, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / "install.sh").write_text("x")
    monkeypatch.setattr(ephe_cli, "_run", _fake_run(0))

    assert ephe_cli.cmd_update(_parser().parse_args(["update", "--json"])) == 0

    parsed = json.loads(capsys.readouterr().out)
    assert parsed["ok"] is True
    assert parsed["exit_code"] == 0


def test_update_json_keeps_the_children_voice_off_stdout(monkeypatch, capsys, tmp_path):
    """`git pull` and install.sh write prose; in --json mode it belongs on stderr."""
    monkeypatch.setattr(ephe_cli, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / "install.sh").write_text("x")
    monkeypatch.setattr(ephe_cli, "_run", _fake_run(0, stdout="Already up to date.\n"))

    assert ephe_cli.cmd_update(_parser().parse_args(["update", "--json"])) == 0

    captured = capsys.readouterr()
    assert json.loads(captured.out)["ok"] is True
    assert "Already up to date." in captured.err


# plugin list --json


def test_plugin_list_json_names_state_and_version(monkeypatch, capsys):
    """Scripts branch on whether a plugin is on; the table was the only shape offered."""
    from core import plugin_runtime, plugin_store

    catalog = {
        "public": [{"name": "alpha", "version": "1.2.0"}],
        "personal": [{"name": "beta", "version": "0.1.0"}],
    }
    monkeypatch.setattr(plugin_store, "load_catalog", lambda: catalog)
    monkeypatch.setattr(plugin_runtime, "effective_enabled", lambda pid: pid == "alpha")

    args = _parser().parse_args(["plugin", "list", "--json"])
    assert ephe_cli.cmd_plugin(args) == 0

    rows = json.loads(capsys.readouterr().out)["plugins"]
    assert rows == [
        {"name": "alpha", "enabled": True, "version": "1.2.0"},
        {"name": "beta", "enabled": False, "version": "0.1.0"},
    ]


# session list hint


def test_session_list_hint_names_a_command_the_parser_accepts(monkeypatch, capsys, tmp_path):
    """The printed way out has to run: `session new` takes --title, never a positional."""
    from core import multi_session as ms

    directory = tmp_path / "sessions"
    directory.mkdir()
    monkeypatch.setattr(ms, "SESSIONS_DIR", directory)
    monkeypatch.setattr(ms, "REGISTRY_FILE", directory / "registry.json")
    monkeypatch.setattr(ms, "LEGACY_FILE", directory / "default.json")

    assert ephe_cli.cmd_session(_parser().parse_args(["session", "list"])) == 0
    out = capsys.readouterr().out
    hint = out.split("`")[1]
    assert hint.startswith("ephe session new")

    args = _parser().parse_args(shlex.split(hint)[1:])
    assert ephe_cli.cmd_session(args) == 0
    assert len(ms.list_sessions()) == 1
