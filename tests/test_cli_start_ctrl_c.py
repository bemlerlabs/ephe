"""QA residue 4 — Ctrl-C in `ephe start` is a shutdown, not a traceback.

`ephe start` runs the backend in the foreground. The terminal sends SIGINT to the whole
foreground process group, the backend handles it and exits — and the parent's wait raised
`KeyboardInterrupt` into the CLI, so the last thing a user saw after stopping their own
server was a Python traceback.

`cmd_start` now catches that interrupt on both foreground paths: it names the shutdown and
answers with 130, the code a shell reports for an interrupted foreground job. The
`--open` branch owns its child and asks a backend that did not receive the signal to
stop, so no process is left holding the port.
"""
from __future__ import annotations

import argparse
from types import SimpleNamespace

import pytest


def _start_args(*, open_: bool = False) -> argparse.Namespace:
    return argparse.Namespace(
        port=8899,
        host="127.0.0.1",
        lan=False,
        reload=False,
        open=open_,
        model=None,
        skip_model_check=True,
        takeover=False,
    )


def _allowed() -> SimpleNamespace:
    return SimpleNamespace(allowed=True, message="", stopped=False, reused=False)


def _prepare(monkeypatch: pytest.MonkeyPatch) -> None:
    import ephe_cli

    monkeypatch.setattr(ephe_cli, "_start_preflight", lambda args: _allowed())
    monkeypatch.setattr(ephe_cli, "resolve_engine_choice", lambda **kwargs: None)
    monkeypatch.setattr(ephe_cli, "ensure_pwa_built", lambda: True)


class _InterruptedChild:
    """The backend process as the parent sees it while SIGINT arrives."""

    def __init__(self) -> None:
        self.terminated = False
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        if self.terminated or self.killed:
            return 0
        raise KeyboardInterrupt

    def poll(self) -> int | None:
        return 0 if (self.terminated or self.killed) else None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


def test_ctrl_c_in_the_foreground_returns_130_without_a_traceback(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import ephe_cli

    _prepare(monkeypatch)

    def interrupted(*_args, **_kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(ephe_cli, "_run", interrupted)

    rc = ephe_cli.cmd_start(_start_args())

    printed = capsys.readouterr().out
    assert rc == 130
    assert "Traceback" not in printed
    assert "stopped" in printed.lower(), printed


def test_a_backend_that_stops_itself_keeps_its_own_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import ephe_cli

    _prepare(monkeypatch)
    monkeypatch.setattr(
        ephe_cli, "_run", lambda *_a, **_k: SimpleNamespace(returncode=3)
    )

    rc = ephe_cli.cmd_start(_start_args())

    assert rc == 3
    assert "Traceback" not in capsys.readouterr().out


def test_ctrl_c_in_the_open_branch_stops_the_child_it_owns(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import ephe_cli

    _prepare(monkeypatch)
    child = _InterruptedChild()
    monkeypatch.setattr(ephe_cli.subprocess, "Popen", lambda *a, **k: child)
    monkeypatch.setattr(ephe_cli, "_json_get", lambda *a, **k: {})
    monkeypatch.setattr(ephe_cli.webbrowser, "open", lambda *a, **k: True)

    rc = ephe_cli.cmd_start(_start_args(open_=True))

    printed = capsys.readouterr().out
    assert rc == 130
    assert "Traceback" not in printed
    assert child.terminated or child.killed, "the child was left without a shutdown request"
