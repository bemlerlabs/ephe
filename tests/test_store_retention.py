"""tests/test_store_retention.py — the config-dir stores say what they are and the
rebuildable one is pruned.

Finding 2026-10-14, measured on this machine: ``~/.ephe`` held 2.8 GB while the 8634
session directories together were 47 MB, and 2.4 GB of it was ``build/`` — the
CPython-for-WASI build scratch, rebuildable by ``build_cpython_guest.py`` and
bounded by no rule at all. Every case here runs against a temporary store: the owner's
real ``~/.ephe`` is never the target.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest


def _ret():
    from core import store_retention

    return store_retention


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """A private configuration dir, with a guest assumed installed (the normal machine)."""
    import core.engine_config as engine_config
    from core import cpython_guest

    home = tmp_path / "ephe-home"
    home.mkdir()
    monkeypatch.setattr(engine_config, "CONFIG_DIR", home)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(home))
    monkeypatch.setattr(cpython_guest, "guest_installed", lambda: True)
    return home


def _tree(root: Path, name: str, payload: bytes, mtime: float) -> Path:
    """A build-scratch directory of a known size and age."""
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "stage.bin").write_bytes(payload)
    os.utime(directory, (mtime, mtime))
    return directory


def _mkdir(root: Path, relative: str) -> Path:
    path = root / relative
    path.mkdir(parents=True)
    (path / "keep.me").write_text("state", encoding="utf-8")
    return path


def test_report_names_each_store_with_its_verdict(cfg):
    ret = _ret()
    kinds = {row["name"]: row["kind"] for row in ret.store_report()["stores"]}
    assert kinds["build"] == ret.CACHE
    for name in ("cells", "sessions", "memory", "trajectory", "artifacts"):
        assert kinds[name] == ret.STATE


def test_report_counts_bytes_and_entries_per_store(cfg):
    ret = _ret()
    now = time.time()
    (cfg / "build").mkdir()
    _tree(cfg / "build", "cpython-wasi", b"x" * 100, now)
    _mkdir(cfg, "sessions")
    (cfg / "trajectory.json").write_text("{}", encoding="utf-8")

    report = ret.store_report()
    rows = {row["name"]: row for row in report["stores"]}
    assert rows["build"]["bytes"] == 100
    assert rows["build"]["entries"] == 1
    assert rows["sessions"]["entries"] == 1
    assert rows["trajectory"]["entries"] == 1
    assert report["cache_bytes"] == 100
    assert report["state_bytes"] > 0
    assert report["config_dir"] == str(cfg)


def test_report_of_a_machine_without_build_reports_it_absent(cfg):
    ret = _ret()
    row = {r["name"]: r for r in ret.store_report()["stores"]}["build"]
    assert row["exists"] is False
    assert row["bytes"] == 0
    assert row["rebuild"] == ret.REBUILD_RECIPE
    assert ret.scratch_trees() == []


def test_prune_keeps_the_newest_and_removes_the_older(cfg):
    ret = _ret()
    now = time.time()
    (cfg / "build").mkdir()
    for i, name in enumerate(("cpython-wasi", "ad-hoc-1", "ad-hoc-2", "ad-hoc-3")):
        _tree(cfg / "build", name, b"x" * 10, now - i)

    res = ret.prune_stores(keep={"build": 2})
    assert res["deleted"] == ["ad-hoc-2", "ad-hoc-3"]
    assert res["kept"] == 2
    assert res["remaining"] == {"build": 2}
    assert (cfg / "build" / "cpython-wasi").is_dir()
    assert (cfg / "build" / "ad-hoc-1").is_dir()
    assert not (cfg / "build" / "ad-hoc-2").exists()


def test_prune_reserves_the_recipe_default_even_when_it_is_oldest(cfg):
    ret = _ret()
    now = time.time()
    (cfg / "build").mkdir()
    _tree(cfg / "build", "cpython-wasi", b"x" * 10, now - 900)
    _tree(cfg / "build", "ad-hoc-new", b"x" * 10, now)

    ret.prune_stores(keep={"build": 1})
    assert (cfg / "build" / "cpython-wasi").is_dir()
    assert not (cfg / "build" / "ad-hoc-new").exists()


def test_prune_defaults_bound_the_store(cfg):
    ret = _ret()
    now = time.time()
    (cfg / "build").mkdir()
    for i in range(ret.DEFAULT_KEEP["build"] + 3):
        _tree(cfg / "build", f"scratch-{i}", b"x" * 10, now - i)

    ret.prune_stores()
    assert len(ret.scratch_trees()) == ret.DEFAULT_KEEP["build"]


def test_dry_run_reports_the_work_without_doing_it(cfg):
    ret = _ret()
    now = time.time()
    (cfg / "build").mkdir()
    for i in range(3):
        _tree(cfg / "build", f"scratch-{i}", b"x" * 10, now - i)

    res = ret.prune_stores(keep={"build": 1}, dry_run=True)
    assert res["deleted"] == ["scratch-1", "scratch-2"]
    assert res["dry_run"] is True
    # a dry run reports the state it would leave behind, and unlinks nothing
    assert res["remaining"] == {"build": 1}
    assert res["kept"] == 1
    assert len(ret.scratch_trees()) == 3


def test_prune_declines_while_no_guest_is_installed(cfg, monkeypatch):
    ret = _ret()
    from core import cpython_guest

    now = time.time()
    (cfg / "build").mkdir()
    for i in range(4):
        _tree(cfg / "build", f"scratch-{i}", b"x" * 10, now - i)
    monkeypatch.setattr(cpython_guest, "guest_installed", lambda: False)

    res = ret.prune_stores(keep={"build": 1})
    assert res["deleted"] == []
    assert res["bytes_freed"] == 0
    assert res["declined"]
    assert len(ret.scratch_trees()) == 4


def test_prune_reports_the_bytes_it_freed(cfg):
    ret = _ret()
    now = time.time()
    (cfg / "build").mkdir()
    _tree(cfg / "build", "cpython-wasi", b"x" * 10, now)
    _tree(cfg / "build", "ad-hoc", b"y" * 4096, now - 1)

    res = ret.prune_stores(keep={"build": 1})
    assert res["bytes_freed"] == 4096
    assert res["deleted"] == ["ad-hoc"]


def test_prune_never_touches_a_state_store(cfg):
    ret = _ret()
    now = time.time()
    (cfg / "build").mkdir()
    for relative in ("cells/work/dbg-1", "sessions", "memory/kepta", "artifacts", "bench/run-1"):
        _mkdir(cfg, relative)
    for i in range(4):
        _tree(cfg / "build", f"scratch-{i}", b"x" * 10, now - i)

    ret.prune_stores(keep={"build": 1})
    for relative in ("cells/work/dbg-1", "sessions", "memory/kepta", "artifacts", "bench/run-1"):
        assert (cfg / relative / "keep.me").exists(), relative


def test_prune_leaves_a_stray_file_in_build_alone(cfg):
    ret = _ret()
    now = time.time()
    (cfg / "build").mkdir()
    stray = cfg / "build" / "wasi-sdk.tar.gz"
    stray.write_bytes(b"z" * 32)
    for i in range(4):
        _tree(cfg / "build", f"scratch-{i}", b"x" * 10, now - i)

    ret.prune_stores(keep={"build": 1})
    assert stray.exists()
    assert len(ret.scratch_trees()) == 1


def test_prune_of_an_empty_build_dir_is_a_no_op(cfg):
    ret = _ret()
    (cfg / "build").mkdir()
    assert ret.prune_stores() == {
        "deleted": [],
        "kept": 0,
        "bytes_freed": 0,
        "remaining": {"build": 0},
        "declined": "",
        "dry_run": False,
    }


def test_prune_of_a_machine_without_build_is_a_no_op(cfg):
    ret = _ret()
    res = ret.prune_stores()
    assert res["deleted"] == [] and res["kept"] == 0 and res["bytes_freed"] == 0


def test_the_readers_survive_a_path_that_is_not_there(tmp_path):
    ret = _ret()
    gone = tmp_path / "not-there"
    assert ret._mtime(gone) == 0.0
    assert ret._entry_count(gone) == 0
    assert ret.scratch_trees(gone) == []


def test_scratch_trees_of_a_build_file_is_empty(cfg):
    ret = _ret()
    (cfg / "build").write_text("not a directory", encoding="utf-8")
    assert ret.scratch_trees() == []
