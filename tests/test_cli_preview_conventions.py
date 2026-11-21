"""tests/test_cli_preview_conventions.py — one preview-vs-commit lever for every verb.

Measured 2026-10-15: the CLI had two conventions for the same decision. `ephe publish`,
`ephe tool` and `ephe run` write unless `--dry-run` says otherwise; `ephe prune` and
`ephe import` write only when `--apply` says so and treat `--dry-run` as an unknown flag.
So a user who learned the `--dry-run` convention from the write-first verbs, and typed it
on `ephe prune` to look at what the store would drop, hit `error: unrecognized arguments:
--dry-run` — and the safe reading of that message ("my flag was ignored") is exactly the
call that would have deleted files had the flag been accepted as anything other than a
preview.

The alias is the fix, and the property these cases pin is the one the user reasons about:
naming `--dry-run` removes nothing, whatever the retention caps say. `--apply` stays the
only lever that deletes.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import pytest

import ephe_cli


def _write(sdir: Path, name: str, mtime: float | None = None) -> Path:
    path = sdir / f"{name}.json"
    path.write_text("[]", encoding="utf-8")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A private store, the same shape tests/test_w4_prune_cli.py uses."""
    import core.multi_session as ms

    sdir = tmp_path / "sessions"
    sdir.mkdir()
    monkeypatch.setattr(ms, "SESSIONS_DIR", sdir)
    monkeypatch.setenv("EPHE_SEARCH_DB", str(tmp_path / "search.db"))
    return sdir


@pytest.fixture
def seeded(store):
    """11 files, with caps low enough that a committing run deletes 5 of them."""
    _write(store, "aaaa1111", mtime=1_700_000_000)
    _write(store, "bbbb2222", mtime=1_700_000_100)
    _write(store, "cccc3333", mtime=1_700_000_200)
    for i in range(4):
        _write(store, f"rest-{i}", mtime=1_700_000_300 + i)
    for i in range(3):
        _write(store, f"pwa-{i}", mtime=1_700_000_400 + i)
    (store / "registry.json").write_text(
        json.dumps({"sessions": [{"id": "aaaa1111"}, {"id": "bbbb2222"}, {"id": "cccc3333"}]}),
        encoding="utf-8",
    )
    return store


def _subparser(verb: str) -> argparse.ArgumentParser:
    """The parser a verb was registered with, so its own help can be read back."""
    for action in ephe_cli.build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return action.choices[verb]
    raise AssertionError("build_parser() registers no subparsers")


def _flat_help(verb: str) -> str:
    """The verb's help with argparse's wrapping collapsed, so a phrase survives it."""
    return " ".join(_subparser(verb).format_help().split())


# `ephe prune`


def test_prune_dry_run_is_accepted_and_removes_nothing(seeded, capsys):
    """
    GIVEN a store whose named caps would delete 5 files
    WHEN `ephe prune --dry-run` runs
    THEN the flag is accepted, the run reports what it would free, and all 11 files stay.
    """
    args = ephe_cli.build_parser().parse_args(
        ["prune", "--keep-rest", "1", "--keep-pwa", "1", "--dry-run"]
    )

    assert args.func(args) == 0

    out = capsys.readouterr().out
    assert "Dry run" in out
    assert "would delete 5 files" in out
    assert "Deleted" not in out
    assert len(list(seeded.glob("*.json"))) == 11


def test_prune_apply_is_still_the_only_lever_that_deletes(seeded, capsys):
    """
    GIVEN the same store and the same caps
    WHEN `ephe prune --apply` runs
    THEN the 5 files the dry run named are gone and the newest per group stays.
    """
    args = ephe_cli.build_parser().parse_args(
        ["prune", "--keep-rest", "1", "--keep-pwa", "1", "--apply"]
    )
    assert args.func(args) == 0

    out = capsys.readouterr().out
    assert "Deleted 5 files" in out
    assert not (seeded / "rest-0.json").exists()
    assert (seeded / "rest-3.json").exists()
    assert not (seeded / "pwa-0.json").exists()
    assert (seeded / "pwa-2.json").exists()


def test_prune_help_names_the_alias_on_both_flags():
    """
    GIVEN `ephe prune --help`
    WHEN it is read
    THEN both the `--apply` row and the `--dry-run` row name the alias, so a user who
         learned the convention elsewhere finds it here.
    """
    help_text = _flat_help("prune")

    assert "--dry-run" in help_text
    assert "--apply Delete for real; without it — or with --dry-run — the run changes nothing" in help_text
    assert "--dry-run The default, named: report what would be freed and remove nothing" in help_text


# `ephe import`


def test_import_dry_run_is_accepted_and_writes_nothing(tmp_path, monkeypatch, capsys):
    """
    GIVEN a source directory of another agent's setup
    WHEN `ephe import <src> --dry-run` runs
    THEN the flag is accepted as the plan-only default and nothing reaches the config dir.
    """
    source = tmp_path / "other-agent"
    source.mkdir()
    (source / "SOUL.md").write_text("# persona\n", encoding="utf-8")
    cfg = tmp_path / "cfg"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))

    args = ephe_cli.build_parser().parse_args(["import", str(source), "--dry-run"])
    assert args.apply is False
    assert args.func(args) == 0

    out = capsys.readouterr().out
    assert "Import plan" in out
    assert "Dry run" in out
    assert not (cfg / "persona.md").exists()


def test_import_apply_writes_the_same_plan(tmp_path, monkeypatch, capsys):
    """
    GIVEN the same source
    WHEN `ephe import <src> --apply` runs
    THEN the plan is applied — the alias never weakens the committing flag.
    """
    source = tmp_path / "other-agent"
    source.mkdir()
    (source / "SOUL.md").write_text("# persona\n", encoding="utf-8")
    cfg = tmp_path / "cfg"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(cfg))

    args = ephe_cli.build_parser().parse_args(["import", str(source), "--apply"])
    assert args.func(args) == 0

    out = capsys.readouterr().out
    assert "Applied:" in out
    assert (cfg / "persona.md").exists()


def test_import_help_names_the_alias_on_both_flags():
    """
    GIVEN `ephe import --help`
    WHEN it is read
    THEN the plan-only default and the alias that names it are both spelled out.
    """
    help_text = _flat_help("import")

    assert "--apply Write the import (default: plan only; --dry-run names it)" in help_text
    assert "--dry-run The default, named: write nothing and print the plan" in help_text
