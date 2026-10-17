"""
◑ Ephe – W4 S3: workspace_key normalization (dedupe/cache/persistence/correlation).
tests/test_r51_workspace_key.py

RULE: these tests were written BEFORE the implementation.

Pins:
1. A relative path == the absolute path (the same key).
2. A symlink == its target (resolve normalizes).
3. Identity wins: an explicit path beats os.getcwd().
4. ~-expansion (expanduser) before the resolve.
5. The skills cache uses the normalized key (identical tuples).
"""
from __future__ import annotations

import os
from pathlib import Path

from core.workspace_rules import workspace_key


def test_relative_equals_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "sub").mkdir()
    assert workspace_key("sub") == workspace_key(str(tmp_path / "sub"))


def test_symlink_equals_target(tmp_path):
    target = tmp_path / "real"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target)
    assert workspace_key(str(link)) == workspace_key(str(target))


def test_identity_wins_over_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    assert workspace_key(str(other)) == str(other.resolve())
    assert workspace_key(str(other)) != workspace_key()


def test_tilde_expansion():
    assert workspace_key("~") == str(Path("~").expanduser().resolve())


def test_no_arg_falls_back_to_resolved_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert workspace_key() == str(Path(tmp_path).resolve())


def test_skills_cache_uses_normalized_key():
    from core import skills as sk

    loader = sk.SkillLoader()
    loader.load_all()
    keys = list(sk._SKILL_LIST_CACHE)
    assert keys, "Cache wurde nicht befuellt"
    for key in keys:
        for part in key:
            assert part == str(Path(part).resolve()), "Cache-Key ist nicht normiert"
