"""tests/test_w4_prune_cli.py — `ephe prune` gives the store a second door.

`POST /api/sessions/prune` and `core/session_lifecycle.prune_store` were a finished
backend with no caller (`grep -rn 'sessions/prune' app/src ephe_cli.py core/ server/`
found only the route's own definition). The CLI verb is the caller for the terminal
user; these cases pin the two properties the verb promises:

* the default run is a **dry run** — it prints what it would free and unlinks
  nothing, so a user who typed the verb to look cannot have deleted anything;
* the numbers printed are the store's own, and the file count is *named* as a file
  count. `total` sums all three groups and is not the task list — the finding was
  exactly that the two numbers read as a defect when neither says which it is.

Every case runs against a temporary store; the owner's sessions are never a target.
"""
from __future__ import annotations

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
    """A private store, the same shape tests/test_session_lifecycle.py uses."""
    import core.multi_session as ms

    sdir = tmp_path / "sessions"
    sdir.mkdir()
    monkeypatch.setattr(ms, "SESSIONS_DIR", sdir)
    monkeypatch.setenv("EPHE_SEARCH_DB", str(tmp_path / "search.db"))
    return sdir


def _run(capsys, *argv: str):
    """Build the real parser, run the verb, hand back (code, stdout)."""
    args = ephe_cli.build_parser().parse_args(["prune", *argv])
    code = args.func(args)
    captured = capsys.readouterr()
    return code, captured.out


@pytest.fixture
def seeded(store):
    """3 tasks, 4 REST files, 3 browser files — newest first by mtime."""
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


def test_the_default_run_is_a_dry_run_and_says_so(seeded, capsys):
    code, out = _run(capsys, "--keep-rest", "1", "--keep-pwa", "1")

    assert code == 0
    assert "Dry run" in out
    assert "--apply" in out
    # Nothing left the disk: 3 tasks + 4 rest + 3 browser.
    assert len(list(seeded.glob("*.json"))) == 11


def test_the_dry_run_names_both_numbers_so_they_cannot_disagree(seeded, capsys):
    _, out = _run(capsys)

    # 10 files (3 tasks + 4 + 3), of which lists reach only the 3 tasks.
    assert "Holds 10 files" in out
    assert "3 tasks a list shows" in out
    assert "7 files no list reaches" in out


def test_apply_deletes_the_older_files_and_keeps_the_newest(seeded, capsys):
    code, out = _run(capsys, "--keep-rest", "1", "--keep-pwa", "1", "--apply")

    assert code == 0
    assert "Deleted 5 files" in out
    # The newest of each mirror survives; the tasks are untouched (no count named).
    assert (seeded / "rest-3.json").exists()
    assert (seeded / "pwa-2.json").exists()
    assert not (seeded / "rest-0.json").exists()
    assert not (seeded / "pwa-0.json").exists()
    assert (seeded / "aaaa1111.json").exists()


def test_the_registered_tasks_are_only_bounded_when_a_count_names_them(seeded, capsys):
    _, out_default = _run(capsys, "--keep-rest", "0", "--keep-pwa", "0")
    assert "registered" not in out_default.split("Retention:")[1].split("\n")[0]

    _, out_named = _run(capsys, "--keep-rest", "0", "--keep-pwa", "0", "--keep-registered", "1")
    assert "registered<=1" in out_named
    assert (seeded / "aaaa1111.json").exists()  # still a dry run


def test_a_confirmed_run_removes_the_named_tasks_and_reports_what_stays(seeded, capsys):
    code, out = _run(capsys, "--keep-rest", "0", "--keep-pwa", "0", "--keep-registered", "1", "--apply")

    assert code == 0
    assert "Deleted 9 files" in out
    assert "The store now holds 1 file" in out
    # The newest task (by mtime) is the one kept.
    assert (seeded / "cccc3333.json").exists()
    assert not (seeded / "aaaa1111.json").exists()


def test_the_json_form_carries_the_same_numbers_as_the_store(seeded, capsys):
    from core import session_lifecycle as life

    stats = life.store_stats()
    code, out = _run(capsys, "--json", "--keep-rest", "1")

    assert code == 0
    payload = json.loads(out)
    assert payload["store"]["total"] == stats["total"] == 10
    assert payload["keep"]["rest-"] == 1
    assert payload["keep"]["pwa-"] == 200  # the store's default, not a copy here
    assert payload["result"]["dry_run"] is True


def test_the_verb_is_not_typing_blind(seeded, capsys):
    """The counts the help and the run name quote are the store's own defaults."""
    from core import session_lifecycle as life

    args = ephe_cli.build_parser().parse_args(["prune"])
    assert args.keep_rest is None  # unset means "take the store's default"
    _, out = _run(capsys)
    assert f"rest-<={life.DEFAULT_KEEP['rest-']}" in out
    assert f"pwa-<={life.DEFAULT_KEEP['pwa-']}" in out


def test_the_verb_also_bounds_the_build_scratch(store, capsys, tmp_path, monkeypatch):
    """The config-dir caches get the same door (core/store_retention.py `prune_stores`).

    Same contract as the session report above: a dry run unlinks nothing, and only
    `--apply` removes the older trees — the newest ``DEFAULT_KEEP['build']`` survive.
    """
    from core import cpython_guest

    home = tmp_path / "ephe-home"
    for i, name in enumerate(("t0", "t1", "t2")):
        tree = home / "build" / name
        tree.mkdir(parents=True)
        os.utime(tree, (1_700_000_000 + i, 1_700_000_000 + i))
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(home))
    monkeypatch.setattr(cpython_guest, "guest_installed", lambda: True)

    _, dry = _run(capsys)
    assert "Build scratch" in dry
    assert (home / "build" / "t0").exists()  # a dry run unlinks nothing

    code, out = _run(capsys, "--apply")
    assert code == 0
    assert "Build scratch" in out
    assert (home / "build" / "t2").exists()  # newest kept
    assert not (home / "build" / "t0").exists()  # the oldest tree goes


def test_the_scratch_run_declines_when_no_guest_is_installed(store, capsys, tmp_path, monkeypatch):
    """With no guest the scratch is the only path back to one, so the run declines.

    ``prune_stores`` reports the reason instead of removing the trees; the verb prints
    it under the count line, and nothing is unlinked on a dry run.
    """
    from core import cpython_guest

    home = tmp_path / "ephe-home"
    (home / "build" / "t0").mkdir(parents=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(home))
    monkeypatch.setattr(cpython_guest, "guest_installed", lambda: False)

    code, out = _run(capsys)
    assert code == 0
    assert "no installed guest" in out  # the decline names itself
    assert (home / "build" / "t0").exists()
