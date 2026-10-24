"""The confinement primitive: a child is inside a root, or it is not.

The cases here are the ones a prefix test gets wrong. `/srv/workspaces-evil` starts with
`/srv/workspaces` and is not inside it; a symlink out of the root is inside it by text and
outside it in fact; `..` segments have to be folded before anyone compares anything. Each of
them was an open finding on the security tab before this module existed.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from core.path_guard import confine, within


def test_a_child_inside_the_root_is_accepted():
    assert within(Path("/srv/workspaces/one"), Path("/srv/workspaces"))


def test_the_root_itself_counts_as_inside():
    assert within(Path("/srv/workspaces"), Path("/srv/workspaces"))


def test_a_sibling_that_shares_the_prefix_is_not_inside():
    """The whole reason this module exists: `/srv/workspaces-evil` is not a child."""
    assert not within(Path("/srv/workspaces-evil"), Path("/srv/workspaces"))


def test_the_filesystem_root_holds_every_absolute_path():
    assert within(Path("/etc/hosts"), Path("/"))
    assert within(Path("/"), Path("/"))
    assert not within(Path("relative/path"), Path("/"))


def test_dot_segments_are_folded_before_the_comparison():
    assert not within(Path("/srv/workspaces/../secrets"), Path("/srv/workspaces"))
    assert within(Path("/srv/workspaces/./one"), Path("/srv/workspaces"))


def test_confine_resolves_the_candidate_and_returns_the_checked_path(tmp_path):
    root = tmp_path / "root"
    child = root / "child"
    child.mkdir(parents=True)
    assert confine(child, root) == child.resolve()


def test_confine_refuses_a_symlink_out_of_the_root(tmp_path):
    """Text says inside, `resolve` says outside, and the fact wins."""
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    link = root / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("this filesystem does not carry symlinks")
    assert confine(link, root) is None


def test_confine_refuses_a_parent_traversal(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    assert confine(root / ".." / "elsewhere", root) is None


def test_confine_refuses_a_name_that_is_not_a_path(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    assert confine("", root) is None
    assert confine("\0", root) is None


def test_a_symlink_loop_is_never_mistaken_for_a_folder(tmp_path):
    """The two platforms answer differently and both answers are safe.

    Linux raises on the loop, so `confine` refuses it. macOS resolves it to its own text,
    which stays inside the root, and the caller's `is_dir()` is what sees that nothing is
    there. What must never happen is a loop coming back as a usable directory.
    """
    loop = tmp_path / "loop"
    try:
        loop.symlink_to(loop)
    except OSError:
        pytest.skip("this filesystem does not carry symlinks")
    resolved = confine(loop, tmp_path)
    assert resolved is None or not resolved.is_dir()


def test_confine_expands_a_user_home_spelling(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert confine("~/project", tmp_path) == (tmp_path / "project").resolve()
    assert confine("~/project", tmp_path / "other") is None


def test_a_root_with_a_trailing_separator_still_matches():
    """A caller that builds the root by joining gets no surprise from one extra slash."""
    assert within(Path("/srv/workspaces/one"), Path("/srv/workspaces/"))
    assert within(Path("/srv/workspaces"), Path(f"/srv{os.sep}"))


def test_the_verifier_may_read_a_generated_artifact(tmp_path, monkeypatch):
    from core.path_guard import verifiable_artifact

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    artifact = tmp_path / "artifacts" / "session" / "brief.pdf"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"%PDF-1.4")
    assert verifiable_artifact(str(artifact))


def test_the_verifier_still_refuses_config_and_credential_names(tmp_path, monkeypatch):
    from core.path_guard import verifiable_artifact

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    key = tmp_path / "engine.key"
    key.write_text("secret", encoding="utf-8")
    assert not verifiable_artifact(str(key))
    credential = tmp_path / "artifacts" / "session" / "credentials"
    credential.parent.mkdir(parents=True)
    credential.write_text("secret", encoding="utf-8")
    assert not verifiable_artifact(str(credential))


def test_a_symlink_out_of_the_artifact_root_is_refused(tmp_path, monkeypatch):
    from core.path_guard import verifiable_artifact

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    secret = tmp_path / "engine.key"
    secret.write_text("secret", encoding="utf-8")
    link = tmp_path / "artifacts" / "session" / "brief.pdf"
    link.parent.mkdir(parents=True)
    link.symlink_to(secret)
    assert not verifiable_artifact(str(link))


def test_the_deck_resolver_may_read_an_artifact_only_with_the_flag(tmp_path, monkeypatch):
    from core.tools._deck_common import _resolve_allowed_file

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr("core.tools._deck_common._is_path_allowed", lambda _path: False)
    artifact = tmp_path / "artifacts" / "session" / "deck.pptx"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"PK\x03\x04")
    assert _resolve_allowed_file(str(artifact), allow_artifacts=True) == artifact.resolve()
    with pytest.raises(PermissionError):
        _resolve_allowed_file(str(artifact))
