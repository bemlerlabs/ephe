"""SOL phase 4 in the turn: one episode per turn, rules gated on the two runs.

The thesis is a childhood, not a memory: the second attempt at the same task is
what decides whether the correction was worth keeping. These tests pin the three
outcomes — a failed attempt leaves its baseline, a repeat that did not improve
keeps no rule, and a repeat that beat its predecessor does.
"""
from __future__ import annotations

from pathlib import Path

from core.sol import episodes
from core.sol.session import SolTurn, close_sol_turn, open_sol_turn

TASK = "fix the failing build"
FAILED_ROUND = ("run_tests", "{}", "pytest\n[exit 1]\n1 failed")


def _turn_with_failure(root: Path) -> SolTurn:
    turn = SolTurn(root, [], active=True)
    turn.reflect_round(1, [FAILED_ROUND])
    assert turn.failures, "the sample result has to classify as a failure"
    return turn


def _previous(root: Path, *, ok: bool, rounds: int) -> None:
    episodes.record(root, episodes.Episode(task=TASK, ok=ok, rounds=rounds))


def test_a_failed_attempt_leaves_its_episode_and_no_rule(tmp_path: Path) -> None:
    turn = _turn_with_failure(tmp_path)

    assert turn.finish(False, last_round=3, task=TASK) == []

    rows = episodes.read(tmp_path)
    assert len(rows) == 1
    assert rows[0]["task"] == TASK
    assert rows[0]["ok"] is False
    assert rows[0]["failures"], "the failure class is what a later pass is compared on"


def test_a_repeat_that_did_not_get_cheaper_keeps_no_rule(tmp_path: Path) -> None:
    _previous(tmp_path, ok=True, rounds=2)
    turn = _turn_with_failure(tmp_path)

    written = turn.finish(True, last_round=2, task=TASK)

    assert written == []
    assert turn.learned == []
    assert episodes.read(tmp_path)[-1]["rules"] == []


def test_a_repeat_that_beat_a_failed_attempt_keeps_its_rule(tmp_path: Path) -> None:
    _previous(tmp_path, ok=False, rounds=4)
    turn = _turn_with_failure(tmp_path)

    written = turn.finish(True, last_round=2, task=TASK)

    assert written, "a pass after a failed attempt is the evidence the rule needs"
    assert episodes.read(tmp_path)[-1]["rules"]


def test_the_closed_turn_carries_the_task_into_the_episode(tmp_path: Path) -> None:
    turn = _turn_with_failure(tmp_path)
    sol, token = open_sol_turn(turn)

    close_sol_turn(sol, token, ok=True, task=TASK)

    assert episodes.previous_for(tmp_path, TASK) is not None
