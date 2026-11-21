"""tests/test_tool_exceptions_survive_a_copy.py — an exception is allowed to travel.

`SandboxConfirmationRequired` carried the tool arguments in `self.args` and then
called `super().__init__(message)`, which refilled that attribute with the message
tuple. The arguments were therefore never reachable on the exception, and
`__reduce__` handed the message tuple to a constructor expecting two different
arguments, so copying or pickling one raised TypeError.

The file also pins `_get_allowed_roots`, the function that decides which folder a
file tool may read. It bound two different things under one name — the plugin's
(workspace, data_roots) pair and the plain list of home roots — which is the shape
that lets a future edit return the wrong one.
"""
from __future__ import annotations

import copy
import pickle
from pathlib import Path

import pytest

from core.tools import base


def test_the_message_names_the_tool_and_the_arguments_stay_reachable():
    exc = base.SandboxConfirmationRequired("vision_click", {"target_description": "Save"})
    assert str(exc) == "Sandbox confirmation required for: vision_click"
    assert exc.tool_name == "vision_click"
    assert exc.tool_args == {"target_description": "Save"}


def test_the_tuple_every_exception_carries_stays_a_tuple_of_the_message():
    exc = base.SandboxConfirmationRequired("vision_click", {"target_description": "Save"})
    assert exc.args == ("Sandbox confirmation required for: vision_click",)


@pytest.mark.parametrize("way", ["pickle", "copy", "deepcopy"])
def test_a_cloned_exception_still_names_its_tool_and_carries_its_arguments(way):
    exc = base.SandboxConfirmationRequired("vision_click", {"target_description": "Save"})
    if way == "pickle":
        other = pickle.loads(pickle.dumps(exc))
    elif way == "copy":
        other = copy.copy(exc)
    else:
        other = copy.deepcopy(exc)
    assert isinstance(other, base.SandboxConfirmationRequired)
    assert other.tool_name == "vision_click"
    assert other.tool_args == {"target_description": "Save"}
    assert str(other) == str(exc)


def test_the_home_roots_are_returned_whole_and_the_workspace_joins_them(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / "Desktop").mkdir(parents=True)
    workspace = tmp_path / "ephe"
    workspace.mkdir()
    monkeypatch.setattr(base, "PLUGIN_FILE_SCOPE", type("Ctx", (), {"get": staticmethod(lambda: None)})())
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.setattr(base.os, "environ", {**base.os.environ, "TMPDIR": str(tmp_path / "tmpdir")})
    import core.engine_config as engine_config

    monkeypatch.setattr(engine_config, "get_workspace_dir", lambda: str(workspace))
    roots = base._get_allowed_roots()
    assert isinstance(roots, list)
    assert all(isinstance(r, Path) for r in roots)
    assert home in roots
    assert home / "Desktop" in roots
    assert Path("/tmp") in roots
    assert workspace in roots, "the user's project folder is an explicit allowance"


def test_a_plugin_scope_answers_with_its_workspace_and_data_roots(tmp_path, monkeypatch):
    workspace = tmp_path / "ws"
    data = [tmp_path / "state", tmp_path / "cache"]
    monkeypatch.setattr(
        base, "PLUGIN_FILE_SCOPE", type("Ctx", (), {"get": staticmethod(lambda: "p")})()
    )
    monkeypatch.setattr(base, "_plugin_file_roots", lambda plugin: (workspace, data))
    assert base._get_allowed_roots() == [workspace, *data]


def test_a_plugin_scope_without_roots_reads_nothing(monkeypatch):
    monkeypatch.setattr(
        base, "PLUGIN_FILE_SCOPE", type("Ctx", (), {"get": staticmethod(lambda: "p")})()
    )
    monkeypatch.setattr(base, "_plugin_file_roots", lambda plugin: None)
    assert base._get_allowed_roots() == []
