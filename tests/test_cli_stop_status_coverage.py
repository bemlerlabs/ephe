"""The two lifecycle commands a person types: `ephe stop` and `ephe status`.

The lifecycle module is tested end to end in `test_backend_lifecycle.py`; these cover the command
bodies themselves — the plain text, the `--json` payloads and the exit codes — because a command
whose body never runs is a command nobody has seen work.
"""
from __future__ import annotations

import json

import pytest

import ephe_cli
from core import backend_lifecycle as lifecycle


def _state(**overrides):
    base = dict(
        port=8765,
        kind="ours",
        listening=True,
        pid=4242,
        owner="owner-token",
        version="0.6.3",
        root="/tmp/ephe",
        api_contract=1,
        start_time="",
        health={"status": "ok", "owner": "owner-token", "pid": 4242, "version": "0.6.3"},
        pidfile=None,
    )
    base.update(overrides)
    return lifecycle.PortState(**base)


class _Result:
    def __init__(self, status="stopped", message="stopped pid 4242", pid=4242, exit_code=0):
        self.status = status
        self.message = message
        self.pid = pid
        self.exit_code = exit_code


def test_stop_prints_the_result_and_returns_its_exit_code(monkeypatch):
    monkeypatch.setattr(ephe_cli, "stop_backend", lambda *a, **k: _Result(), raising=True)
    rc = ephe_cli.cmd_stop(type("A", (), {"port": 8765, "timeout": 5.0, "json": False})())
    assert rc == 0


def test_stop_answers_json_when_asked(monkeypatch, capsys):
    monkeypatch.setattr(ephe_cli, "stop_backend", lambda *a, **k: _Result(), raising=True)
    rc = ephe_cli.cmd_stop(type("A", (), {"port": 8765, "timeout": 5.0, "json": True})())
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["status"] == "stopped"
    assert payload["port"] == 8765


def test_stop_reports_a_process_it_does_not_own(monkeypatch, capsys):
    monkeypatch.setattr(
        ephe_cli,
        "stop_backend",
        lambda *a, **k: _Result("foreign", "pid 7 is not an Ephe backend", 7, 1),
        raising=True,
    )
    rc = ephe_cli.cmd_stop(type("A", (), {"port": 8765, "timeout": 5.0, "json": True})())
    assert rc == 1
    assert json.loads(capsys.readouterr().out)["pid"] == 7


def test_status_reports_a_running_backend(monkeypatch, capsys):
    monkeypatch.setattr(ephe_cli, "inspect_port", lambda port: _state(), raising=True)
    rc = ephe_cli.cmd_status(type("A", (), {"port": 8765, "json": False})())
    out = capsys.readouterr().out
    assert rc == 0
    assert "running" in out


def test_status_answers_json_for_an_unowned_backend(monkeypatch, capsys):
    monkeypatch.setattr(
        ephe_cli, "inspect_port", lambda port: _state(health={"status": "ok", "pid": 4242, "version": "0.6.3"}), raising=True
    )
    rc = ephe_cli.cmd_status(type("A", (), {"port": 8765, "json": True})())
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["running"] is True
    assert payload["pidfile"] is None  # no pidfile, so nothing proves this process is ours


def test_status_reports_nothing_listening(monkeypatch, capsys):
    monkeypatch.setattr(
        ephe_cli,
        "inspect_port",
        lambda port: _state(kind="not_running", listening=False, health={}),
        raising=True,
    )
    rc = ephe_cli.cmd_status(type("A", (), {"port": 8765, "json": False})())
    out = capsys.readouterr().out
    assert rc == 1
    assert "not running" in out


# The preflight branches the start and serve bodies act on.

class _Decision:
    def __init__(self, *, allowed=True, stopped=False, reused=False, message=""):
        self.allowed = allowed
        self.stopped = stopped
        self.reused = reused
        self.message = message


def _args(**over):
    base = dict(
        port=8765,
        host="127.0.0.1",
        open=False,
        model=None,
        lan=False,
        token=None,
        takeover=False,
        json=False,
        timeout=5.0,
    )
    base.update(over)
    return type("A", (), base)()


def test_start_refuses_a_port_it_may_not_take(monkeypatch, capsys):
    monkeypatch.setattr(
        ephe_cli,
        "_start_preflight",
        lambda args: _Decision(allowed=False, message="port 8765 holds a foreign backend"),
    )
    rc = ephe_cli.cmd_start(_args())
    assert rc == 1
    assert "foreign backend" in capsys.readouterr().out


def test_start_reports_a_takeover_and_reuses_a_running_backend(monkeypatch, capsys):
    monkeypatch.setattr(
        ephe_cli,
        "_start_preflight",
        lambda args: _Decision(stopped=True, reused=True, message="reusing pid 7"),
    )
    opened = []
    monkeypatch.setattr(ephe_cli, "_open_local_app", lambda port, host: opened.append(port))
    rc = ephe_cli.cmd_start(_args(open=True))
    out = capsys.readouterr().out
    assert rc == 0
    assert "reusing pid 7" in out
    assert opened == [8765]


def test_serve_refuses_a_foreign_listener(monkeypatch, capsys):
    monkeypatch.setattr(
        ephe_cli,
        "_serve_preflight",
        lambda args: _Decision(allowed=False, message="port 8766 is not ours"),
    )
    rc = ephe_cli.cmd_serve(_args(port=8766))
    assert rc == 1
    assert "not ours" in capsys.readouterr().out


def test_serve_reuses_a_running_engine(monkeypatch, capsys):
    monkeypatch.setattr(
        ephe_cli,
        "_serve_preflight",
        lambda args: _Decision(reused=True, message="reusing the running engine"),
    )
    rc = ephe_cli.cmd_serve(_args(port=8766))
    assert rc == 0
    assert "reusing the running engine" in capsys.readouterr().out


def test_status_names_a_foreign_listener(monkeypatch, capsys):
    monkeypatch.setattr(
        ephe_cli,
        "inspect_port",
        lambda port: _state(kind=lifecycle.NOT_EPHE, health={"status": "ok"}),
        raising=True,
    )
    rc = ephe_cli.cmd_status(_args())
    out = capsys.readouterr().out
    assert rc == 1
    assert "not an Ephe backend" in out


def test_status_names_an_ephe_backend_of_another_install(monkeypatch, capsys):
    monkeypatch.setattr(
        ephe_cli,
        "inspect_port",
        lambda port: _state(kind="foreign_install", health={"status": "ok", "pid": 1}),
        raising=True,
    )
    rc = ephe_cli.cmd_status(_args())
    out = capsys.readouterr().out
    assert rc == 1
    assert "did not" in out


def test_stop_prints_plain_text_for_a_refusal(monkeypatch, capsys):
    monkeypatch.setattr(
        ephe_cli,
        "stop_backend",
        lambda *a, **k: _Result("foreign", "pid 7 is not an Ephe backend", 7, 1),
        raising=True,
    )
    rc = ephe_cli.cmd_stop(_args())
    out = capsys.readouterr().out
    assert rc == 1
    assert "not an Ephe backend" in out


def test_open_local_app_uses_the_loopback_address_for_a_wildcard_host(monkeypatch):
    opened = []
    monkeypatch.setattr(ephe_cli.webbrowser, "open", lambda url: opened.append(url))
    ephe_cli._open_local_app(8765, "0.0.0.0")
    ephe_cli._open_local_app(8765, "127.0.0.1")
    assert opened == ["http://127.0.0.1:8765", "http://127.0.0.1:8765"]


def test_serve_reports_a_takeover_then_reuses_the_engine(monkeypatch, capsys):
    monkeypatch.setattr(
        ephe_cli,
        "_serve_preflight",
        lambda args: _Decision(stopped=True, reused=True, message="replaced a stale engine"),
    )
    rc = ephe_cli.cmd_serve(_args(port=8766))
    assert rc == 0
    assert "replaced a stale engine" in capsys.readouterr().out


def test_doctor_survives_unreadable_package_metadata(monkeypatch, tmp_path):
    """A broken metadata backend is a state, not a crash and not a fetch."""
    import importlib.metadata as md

    monkeypatch.setattr(ephe_cli, "PROJECT_ROOT", tmp_path)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "index.html").write_text("x")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "generate_skills_lock.py").write_text("def verify(root):\n    return True, []\n")
    real_version = md.version

    def fake_version(name):
        if name == "ephemora-cell":
            raise RuntimeError("metadata backend down")
        return real_version(name)

    monkeypatch.setattr(md, "version", fake_version)
    code = ephe_cli.cmd_doctor(ephe_cli.build_parser().parse_args(["doctor"]))
    assert code in (0, 1)  # the row is informational; the crash is what must not happen
