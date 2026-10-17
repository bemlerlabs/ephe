"""The two folders a user names in the settings: anywhere they work, not anywhere.

The value is the owner's own folder pick, so there is no root to jail it to — and that is
exactly why the refusals are listed rather than derived. A workspace inside this product's
own state directory nests the app in its own data, and a workspace at a credential
directory or at a system root costs more than the folder it names.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from core import engine_config as ec


@pytest.mark.parametrize("refused", ["/", "/etc", "/System", "~/.ssh", "~/.ephe", "~/.gnupg"])
def test_the_workspace_refuses_the_places_it_must(refused):
    with pytest.raises(ValueError):
        ec.validate_workspace_dir(str(Path(refused).expanduser()))


@pytest.mark.parametrize("refused", ["/", "/etc", "~/.ssh", "~/.ephe"])
def test_the_output_dir_refuses_the_same_places(refused):
    with pytest.raises(ValueError):
        ec.validate_output_dir(str(Path(refused).expanduser()))


def test_a_folder_inside_the_state_directory_is_refused_too(tmp_path, monkeypatch):
    """The refusal covers the whole tree under a refused directory."""
    monkeypatch.setenv("HOME", str(tmp_path))
    state = tmp_path / ".ephe"
    (state / "sessions").mkdir(parents=True)
    with pytest.raises(ValueError):
        ec.validate_workspace_dir(str(state / "sessions"))


def test_an_ordinary_folder_still_passes(tmp_path):
    workspace = tmp_path / "a-project"
    workspace.mkdir()
    assert ec.validate_workspace_dir(str(workspace)) == str(workspace.resolve())

    nested = tmp_path / "out" / "deep"
    assert ec.validate_output_dir(str(nested)) == str(nested)
    assert nested.is_dir()


def test_the_refusal_lands_before_the_existence_check(tmp_path, monkeypatch):
    """A refused folder that does not exist is refused for what it is.

    The message names the reason the user can act on, so the existence check never gets to
    answer with "does not exist" about a path the tool would refuse anyway."""
    monkeypatch.setenv("HOME", str(tmp_path))
    with pytest.raises(ValueError, match="must not sit in"):
        ec.validate_workspace_dir(str(tmp_path / ".ssh" / "not-there"))
