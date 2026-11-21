"""The entry point's three exits: a named next step, the bare command, the script.

`ephe_cli.py` carries the 100% floor because it is the surface a user meets first.
These are the branches no verb exercises: a doctor run whose only finding has no
named cause, a start with no verb at all, and the file executed as a script.
"""
from __future__ import annotations

import io
import runpy
import sys
from pathlib import Path

import pytest

import ephe_cli


def test_a_finding_with_no_named_cause_ends_on_doctor_fix() -> None:
    step, why = ephe_cli._doctor_next_step(
        ["Permissions"], engine=object(), engine_usable=True
    )
    assert step == "ephe doctor --fix"
    assert "safe local repairs" in why


def test_no_verb_outside_a_terminal_prints_usage_and_exits(monkeypatch) -> None:
    out = io.StringIO()
    monkeypatch.setattr(sys, "argv", ["ephe"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    monkeypatch.setattr(sys, "stdout", out)

    with pytest.raises(SystemExit) as exc:
        ephe_cli.main()

    assert exc.value.code == 2
    assert "usage" in out.getvalue().lower()


def test_the_file_runs_as_a_script(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["ephe_cli.py"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    monkeypatch.setattr(sys, "stdout", io.StringIO())

    with pytest.raises(SystemExit) as exc:
        runpy.run_path(str(Path(ephe_cli.__file__)), run_name="__main__")

    assert exc.value.code == 2
