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


def _device_argv(capsys, *argv: str):
    """Run the device verb through the real parser and hand back (code, stdout)."""
    args = ephe_cli.build_parser().parse_args(["device", *argv])
    code = args.func(args)
    captured = capsys.readouterr()
    return code, captured.out


@pytest.fixture
def device(tmp_path, monkeypatch):
    """A device folder with one entry of each answer the declaration gives."""
    home = tmp_path / "ephe-home"
    (home / "sessions").mkdir(parents=True)
    (home / "sessions" / "one.json").write_text("[]", encoding="utf-8")
    (home / "settings.json").write_text("{}\n", encoding="utf-8")
    (home / "audit.log").write_text("x\n", encoding="utf-8")
    (home / "hand-kept-backup").write_text("x", encoding="utf-8")
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(home))
    return home


def test_the_device_verb_lists_the_declaration_in_its_own_words(device, capsys):
    code, out = _device_argv(capsys)

    assert code == 0
    assert str(device) in out
    assert "entries are present" in out and "declared entries" in out
    assert "[forget] sessions" in out
    assert "[forget] settings.json" in out
    assert "[  keep] audit.log" in out, "the append-only log must be marked kept"
    assert "1 entry the declaration does not name" in out
    assert "[  keep] hand-kept-backup" in out
    assert "Nothing left the folder." in out
    assert (device / "sessions").is_dir(), "the dry run deleted"


def test_every_listed_row_names_the_room_it_takes(device, capsys):
    """The listing is where a person finds out where the gigabytes sit, so each row carries it."""
    (device / "artifacts").mkdir()
    (device / "artifacts" / "big.bin").write_bytes(b"x" * (3 * 1024 * 1024))
    (device / "sessions" / "one.json").write_text("x" * 2048, encoding="utf-8")

    code, out = _device_argv(capsys)
    rows = {
        line.split("]", 1)[1].split()[0]: line
        for line in out.splitlines()
        if line.startswith("  [")
    }

    assert code == 0
    assert "3.0 MB" in rows["artifacts"]
    assert "2 kB" in rows["sessions"]
    assert "3 B" in rows["settings.json"], "a few bytes must not print as 0.0 MB"
    assert rows["artifacts"].rstrip().endswith("the files a turn produced, one folder per task")


def test_a_size_is_read_in_the_unit_it_describes():
    """The column follows the size: bytes, then kilobytes, then megabytes."""
    assert ephe_cli._size_text(1023) == "1023 B"
    assert ephe_cli._size_text(1024) == "1 kB"
    assert ephe_cli._size_text(1024 * 1024 - 1) == "1024 kB"
    assert ephe_cli._size_text(1024 * 1024) == "1.0 MB"


def test_the_device_verb_removes_only_what_it_declared_forgettable(device, capsys):
    code, out = _device_argv(capsys, "--apply")

    assert code == 0
    assert "Removed " in out and "stay." in out
    assert not (device / "sessions").exists()
    assert not (device / "settings.json").exists()
    assert (device / "audit.log").exists(), "a kept row may not be deleted"
    assert (device / "hand-kept-backup").exists(), "an undeclared file is the person's to judge"


def test_the_device_verb_answers_in_json(device, capsys):
    code, out = _device_argv(capsys, "--json")

    payload = json.loads(out)
    assert code == 0 and payload["applied"] is False
    names = {row["name"] for row in payload["listing"]}
    assert {"sessions", "settings.json", "audit.log"} <= names
    assert payload["forget"]["unnamed"] == ["hand-kept-backup"]
    row = {r["name"]: r for r in payload["listing"]}["sessions"]
    assert row["bytes"] == 2 and row["writer"] == "core/session.py"


def test_an_entry_that_refuses_to_go_is_counted_as_kept(device, monkeypatch, capsys):
    """A file another process holds is not this verb's to force.

    The declaration said `settings.json` may go, the machine said no. The run reports the
    entry under `kept` and carries on with the rest of the folder, because a delete that
    meets a busy file has to leave the verb answering rather than aborting halfway.
    """
    real_unlink = Path.unlink

    def refuse(path, *args, **kwargs):
        if path.name == "settings.json":
            raise OSError("busy")
        return real_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", refuse)
    code, out = _device_argv(capsys, "--apply")

    assert code == 0
    assert (device / "settings.json").exists(), "the refusal was forced through"
    assert not (device / "sessions").exists(), "the rest of the folder was left undone"
    assert "stay." in out


def test_the_device_verb_offers_the_word_for_an_entry_it_cannot_name(device, capsys):
    code, out = _device_argv(capsys)

    assert code == 0
    assert "1 entry the declaration does not name" in out
    assert "--clear NAME moves it under trash/" in out, "the listing stops at a wall it does not open"


def test_the_device_verb_moves_a_named_leftover_only_when_applied(device, capsys):
    code, out = _device_argv(capsys, "--clear", "hand-kept-backup")

    assert code == 0
    assert "[would move] hand-kept-backup" in out
    assert str(device / "trash") in out, "the dry run says where the entry would land"
    assert (device / "hand-kept-backup").exists(), "the dry run moved"
    assert not (device / "trash").exists(), "the dry run created a folder"

    code, out = _device_argv(capsys, "--clear", "hand-kept-backup", "--apply")

    assert code == 0
    assert "[moved] hand-kept-backup" in out
    assert not (device / "hand-kept-backup").exists()
    landed = list((device / "trash").rglob("hand-kept-backup"))
    assert len(landed) == 1, "the bytes are meant to be findable, not gone"
    assert landed[0].read_text(encoding="utf-8") == "x"


def test_the_device_verb_refuses_to_clear_what_the_declaration_owns(device, capsys):
    """`--clear` reaches the unnamed half of the folder; `--apply` owns the declared rows."""
    code, out = _device_argv(capsys, "--clear", "audit.log", "--apply")

    assert code == 0
    assert "[refused] audit.log" in out
    assert (device / "audit.log").exists(), "a kept row was cleared by the wrong word"
    assert (device / "hand-kept-backup").exists(), "an unnamed entry moved that nobody named"


def test_the_device_verb_refuses_a_name_that_reaches_past_the_folder(device, capsys):
    """One name, one entry directly under the folder. Anything deeper is not this verb's reach.

    `trusted-keys` is a kept row, so a run that applied everything else still leaves the
    nested file in place for the assertion to mean something.
    """
    (device / "trusted-keys").mkdir()
    (device / "trusted-keys" / "first-party.json").write_text("{}", encoding="utf-8")

    code, out = _device_argv(capsys, "--clear", "trusted-keys/first-party.json", "--apply")

    assert code == 0
    assert "[refused] trusted-keys/first-party.json" in out
    assert (device / "trusted-keys" / "first-party.json").exists(), "a path reached into a kept row"


def test_the_device_verb_says_an_entry_is_absent_rather_than_inventing_a_move(device, capsys):
    code, out = _device_argv(capsys, "--clear", "never-there", "--apply")

    assert code == 0
    assert "[absent] never-there" in out
    assert "1 entry named to clear:" not in out, "an absent name was counted as a cleared one"


def test_the_device_verb_answers_for_the_clear_in_json(device, capsys):
    code, out = _device_argv(capsys, "--clear", "hand-kept-backup", "--apply", "--json")

    assert code == 0
    payload = json.loads(out)
    assert payload["clear"]["moved"] == ["hand-kept-backup"]
    assert payload["clear"]["refused"] == []
    trash = payload["clear"]["trash"]
    assert trash.startswith(f"{device / 'trash'}/"), trash
    assert trash.count("trash/") == 1, "the answer names the run it used"


@pytest.fixture
def ledgers(tmp_path, monkeypatch):
    """`count` run ledgers under the config dir's `run/`, oldest first, plus a pidfile.

    The folder is shared with `core/backend_lifecycle.py`, so the fixture plants one of
    those too: a prune that reached it would be caught by the count assertions below.
    """
    import os

    folder = tmp_path / "run"
    folder.mkdir(parents=True)
    made = []
    for step in range(5):
        path = folder / f"run{step:04d}.jsonl"
        path.write_text("x" * 40, encoding="utf-8")
        os.utime(path, (1_000_000 + step, 1_000_000 + step))
        made.append(path)
    (folder / "backend-8765.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    return folder, made


def test_the_prune_verb_names_the_ledger_it_bounds(ledgers, capsys):
    folder, made = ledgers

    code, out = _run(capsys, "--keep-runs", "2")

    assert code == 0
    assert "Run ledger: dry run — would delete 3 runs" in out
    assert "newest 2 kept" in out
    assert all(path.exists() for path in made), "the dry run deleted"


def test_the_prune_verb_empties_the_older_ledgers_only_with_the_word(ledgers, capsys):
    folder, made = ledgers

    code, out = _run(capsys, "--keep-runs", "2", "--apply")

    assert code == 0
    assert "Run ledger: deleted 3 runs" in out
    assert not any(path.exists() for path in made[:3])
    assert all(path.exists() for path in made[3:])
    assert (folder / "backend-8765.json").exists(), "the verb reached past its own store"


def test_the_ledger_count_comes_from_the_writer_unless_a_person_names_one(ledgers, capsys):
    from core.run import ledger

    _folder, made = ledgers

    code, out = _run(capsys)

    assert code == 0
    assert f"newest {ledger.DEFAULT_KEEP} kept" in out
    assert "would delete 0 runs" in out, "five runs are nowhere near the default count"
    assert all(path.exists() for path in made)


def test_the_prune_json_answers_for_the_ledger_too(ledgers, capsys):
    code, out = _run(capsys, "--keep-runs", "1", "--apply", "--json")

    assert code == 0
    payload = json.loads(out)
    assert payload["runs"]["cap"] == 1
    assert len(payload["runs"]["deleted"]) == 4
    assert payload["runs"]["remaining"] == {"run": 1}

