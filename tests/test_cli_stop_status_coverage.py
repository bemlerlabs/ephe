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
