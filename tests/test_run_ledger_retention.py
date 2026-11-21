"""tests/test_run_ledger_retention.py — the ledger folder keeps its newest runs.

`core/run/ledger.py` wrote one file per turn and nothing ever removed one. Measured on the
owner's Mac 2026-11-16: 327 files, 2 567 149 bytes between 2026-10-18 and 2026-11-16 — 11.3
runs and 87 KB a day. The folder is declared in `core/persistence.py` and was missing from
`core/store_retention.py`, so `ephe prune` could not see it either. These cases pin the
count that bounds it now and the two properties a prune owes: a dry run first, and a newest
file no count can evict.
"""

from __future__ import annotations

import os
from pathlib import Path

from core.run import ledger

SIZE = 40
_BASE = 1_000_000


def _runs(folder: Path, count: int, *, size: int = SIZE) -> list[Path]:
    """`count` ledger files with distinct, increasing mtimes, oldest first."""
    folder.mkdir(parents=True, exist_ok=True)
    made: list[Path] = []
    for step in range(count):
        path = folder / f"run{step:04d}.jsonl"
        path.write_text("x" * size, encoding="utf-8")
        os.utime(path, (_BASE + step, _BASE + step))
        made.append(path)
    return made


class TestRunFiles:
    def test_given_a_folder_of_ledgers_and_pidfiles_when_listed_then_only_ledgers_are_candidates(
        self, tmp_path
    ):
        """`run/` is shared with the backend pidfiles (`core/backend_lifecycle.py`)."""
        made = _runs(tmp_path, 3)
        (tmp_path / "backend-8765.json").write_text("{}", encoding="utf-8")

        listed = ledger.run_files(tmp_path)

        assert [path.name for path in listed] == [made[2].name, made[1].name, made[0].name]

    def test_given_no_folder_when_listed_then_the_answer_is_empty(self, tmp_path):
        assert ledger.run_files(tmp_path / "never-created") == []


class TestPruneRuns:
    def test_given_more_runs_than_the_count_when_pruned_then_nothing_moves_in_a_dry_run(
        self, tmp_path
    ):
        made = _runs(tmp_path, 5)

        result = ledger.prune_runs(keep=2, root=tmp_path)

        assert result["deleted"] == sorted(path.name for path in made[:3])
        assert result["kept"] == 2
        assert result["bytes_freed"] == 3 * SIZE
        assert result["dry_run"] is True
        assert result["root"] == str(tmp_path)
        assert all(path.exists() for path in made), "the dry run deleted"

    def test_given_the_same_folder_when_applied_then_the_older_runs_go(self, tmp_path):
        made = _runs(tmp_path, 5)

        result = ledger.prune_runs(keep=2, root=tmp_path, dry_run=False)

        assert result["deleted"] == sorted(path.name for path in made[:3])
        assert not any(path.exists() for path in made[:3])
        assert all(path.exists() for path in made[3:])
        assert result["remaining"] == {"run": 2}

    def test_given_a_count_of_zero_when_applied_then_the_folder_is_emptied_of_ledgers(
        self, tmp_path
    ):
        made = _runs(tmp_path, 3)
        (tmp_path / "backend-8765.json").write_text("{}", encoding="utf-8")

        result = ledger.prune_runs(keep=0, root=tmp_path, dry_run=False)

        assert len(result["deleted"]) == 3
        assert not any(path.exists() for path in made)
        assert (tmp_path / "backend-8765.json").exists(), "a pidfile is not this store's"

    def test_given_no_count_when_pruned_then_the_writer_owns_the_default(self, tmp_path):
        made = _runs(tmp_path, ledger.DEFAULT_KEEP + 3)

        result = ledger.prune_runs(root=tmp_path)

        assert result["cap"] == ledger.DEFAULT_KEEP
        assert result["deleted"] == sorted(path.name for path in made[:3])
        assert all(path.exists() for path in made), "a report is not an apply"

    def test_given_a_turn_running_now_when_pruned_then_it_is_not_a_candidate(
        self, tmp_path, monkeypatch
    ):
        """The rule the count leans on: a live run holds the newest file in the folder."""
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        older = _runs(tmp_path / "run", 4)
        live = ledger.RunLedger("live-one", request_id="r1")
        live.append("now", "run_started")

        result = ledger.prune_runs(keep=1)

        assert result["deleted"] == sorted(path.name for path in older)
        live_file = tmp_path / "run" / "live-one.jsonl"
        assert live_file.exists(), "the run in flight was pruned"
        assert live_file.read_text(encoding="utf-8").splitlines(), "its first line never landed"

    def test_given_a_file_that_refuses_when_applied_then_it_is_not_counted_as_deleted(
        self, tmp_path, monkeypatch
    ):
        made = _runs(tmp_path, 3)
        real_unlink = Path.unlink

        def refuse(self, *args, **kwargs):
            if self.name == made[0].name:
                raise OSError("busy")
            return real_unlink(self, *args, **kwargs)

        monkeypatch.setattr(Path, "unlink", refuse)
        result = ledger.prune_runs(keep=1, root=tmp_path, dry_run=False)

        assert result["deleted"] == [made[1].name]
        assert made[0].exists(), "the refusal was forced through"
        assert result["bytes_freed"] == SIZE
        assert result["remaining"] == {"run": 2}, "the held file is still in the folder"


class TestStoreRow:
    def test_given_a_run_folder_when_the_report_runs_then_it_answers_for_it(self, tmp_path, monkeypatch):
        """The folder was declared in `core/persistence.py` and absent from the store table."""
        from core import store_retention as ret

        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
        _runs(tmp_path / "run", 2)

        rows = {row["name"]: row for row in ret.store_report()["stores"]}

        assert rows["run"]["kind"] == ret.STATE
        assert rows["run"]["owner"] == "core.run.ledger"
        assert rows["run"]["entries"] == 2
        assert rows["run"]["bytes"] == 2 * SIZE
