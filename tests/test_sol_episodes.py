"""SOL phase 4 — an episode is counted, and a rule needs a better second run."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.sol import episodes  # noqa: E402


def _episode(task: str, ok: bool, rounds: int) -> episodes.Episode:
    return episodes.Episode(task=task, ok=ok, rounds=rounds, failures=("command-not-found",))


def test_an_episode_lands_as_one_json_line(tmp_path: Path) -> None:
    episodes.record(tmp_path, _episode("run the tests", ok=False, rounds=6))
    rows = episodes.read(tmp_path)
    assert len(rows) == 1
    assert rows[0]["task"] == "run the tests"
    assert rows[0]["ok"] is False
    assert rows[0]["failures"] == ["command-not-found"]


def test_the_task_key_is_normalised_and_short(tmp_path: Path) -> None:
    assert episodes.task_key("  run   the   tests\n") == "run the tests"
    assert len(episodes.task_key("x" * 400)) == episodes.TASK_CHARS


def test_the_previous_attempt_is_the_same_task(tmp_path: Path) -> None:
    episodes.record(tmp_path, _episode("run the tests", ok=False, rounds=6))
    episodes.record(tmp_path, _episode("another task", ok=True, rounds=2))
    previous = episodes.previous_for(tmp_path, "run  the tests")
    assert previous is not None and previous["task"] == "run the tests"


def test_a_pass_beats_a_fail_before_the_round_count(tmp_path: Path) -> None:
    before = {"ok": False, "rounds": 1}
    after = {"ok": True, "rounds": 9}
    assert episodes.better(before, after) == "after"


def test_with_the_same_result_the_shorter_run_wins() -> None:
    assert episodes.better({"ok": True, "rounds": 9}, {"ok": True, "rounds": 3}) == "after"
    assert episodes.better({"ok": True, "rounds": 3}, {"ok": True, "rounds": 9}) == "before"
    assert episodes.better({"ok": True, "rounds": 3}, {"ok": True, "rounds": 3}) == "tie"


def test_a_rule_needs_a_pass_after_a_failure() -> None:
    assert episodes.should_keep_rule({"ok": False, "rounds": 6}, {"ok": True, "rounds": 4}) is True


def test_a_second_failure_is_not_a_lesson() -> None:
    assert episodes.should_keep_rule({"ok": False, "rounds": 6}, {"ok": False, "rounds": 9}) is False


def test_a_slower_pass_does_not_earn_a_rule() -> None:
    assert episodes.should_keep_rule({"ok": True, "rounds": 3}, {"ok": True, "rounds": 5}) is False


def test_the_first_attempt_alone_earns_nothing() -> None:
    assert episodes.should_keep_rule(None, {"ok": True, "rounds": 2}) is False


def test_a_corrupt_line_is_skipped_not_fatal(tmp_path: Path) -> None:
    target = tmp_path / ".ephe" / "learning"
    target.mkdir(parents=True)
    (target / episodes.EPISODES_NAME).write_text(
        json.dumps({"task": "a", "ok": True, "rounds": 1}) + "\nnot-json\n"
    )
    assert [row["task"] for row in episodes.read(tmp_path)] == ["a"]
