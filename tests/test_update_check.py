"""One look a day across starts, and the update the terminal app runs on request.

The release-feed contract itself (semver, fail-soft, TTL) is pinned in
tests/test_r67_update_check.py. Here: the day-long store that outlives a
process, and the pull-plus-install the app triggers from the prompt.
"""

from __future__ import annotations

import json
import time

import pytest

from core import update_check


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv(update_check.OPT_OUT_ENV, raising=False)
    monkeypatch.delenv("EPHE_UPDATE_REPO", raising=False)
    update_check._reset_cache()
    yield tmp_path
    update_check._reset_cache()


class _Done:
    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def _state_file(config_dir):
    return config_dir / update_check.STATE_FILE


def _store(config_dir, result: dict, age_seconds: float = 0) -> None:
    _state_file(config_dir).write_text(
        json.dumps({"checked_at": time.time() - age_seconds, "result": result})
    )


def _checkout(config_dir):
    checkout = config_dir / "checkout"
    (checkout / ".git").mkdir(parents=True)
    return checkout


def test_the_answer_of_the_day_is_reused(isolated, monkeypatch: pytest.MonkeyPatch) -> None:
    _store(isolated, {"enabled": True, "available": True, "latest": "0.6.0"})

    def _no_network(*args, **kwargs):
        pytest.fail("the feed was asked twice in one day")

    monkeypatch.setattr(update_check, "check_for_update", _no_network)
    assert update_check.daily_check()["latest"] == "0.6.0"


def test_a_day_old_answer_is_asked_again(isolated, monkeypatch: pytest.MonkeyPatch) -> None:
    _store(isolated, {"enabled": True, "available": False}, age_seconds=update_check.DAY_S + 1)
    asked: list[bool] = []

    def _fresh(force: bool = False):
        asked.append(force)
        return {"enabled": True, "available": True, "latest": "0.6.0"}

    monkeypatch.setattr(update_check, "check_for_update", _fresh)

    assert update_check.daily_check()["available"] is True
    assert asked == [True]
    assert json.loads(_state_file(isolated).read_text())["result"]["latest"] == "0.6.0"


def test_the_opt_out_stops_before_the_feed(isolated, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(update_check.OPT_OUT_ENV, "1")

    def _no_network(*args, **kwargs):
        pytest.fail("the feed was asked while the check is off")

    monkeypatch.setattr(update_check, "check_for_update", _no_network)
    assert update_check.daily_check()["available"] is False


def test_a_disabled_feature_stores_nothing(isolated, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        update_check,
        "check_for_update",
        lambda force=False: {"enabled": False, "available": False},
    )
    update_check.daily_check()
    assert not _state_file(isolated).exists()


def test_updating_without_an_installer_reports_it(isolated) -> None:
    checkout = _checkout(isolated)
    ok, line = update_check.run_update(root=checkout)
    assert ok is False
    assert line == "install.sh not found"


def test_a_failed_pull_reports_its_last_line(
    isolated, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkout = _checkout(isolated)
    (checkout / "install.sh").write_text("#!/bin/sh\n")
    monkeypatch.setattr(
        update_check,
        "_git",
        lambda root, *args: _Done(
            returncode=1, stderr="error: local changes\nfatal: not fast-forward"
        ),
    )
    ok, line = update_check.run_update(root=checkout)
    assert ok is False
    assert line == "fatal: not fast-forward"


def test_a_successful_update_clears_the_day(isolated, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout = _checkout(isolated)
    (checkout / "install.sh").write_text("#!/bin/sh\n")
    _store(isolated, {"enabled": True, "available": True, "latest": "0.6.0"})
    monkeypatch.setattr(update_check, "_git", lambda root, *args: _Done())

    class _Installed:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(
        update_check.subprocess, "run", lambda *args, **kwargs: _Installed()
    )

    ok, line = update_check.run_update(root=checkout)

    assert (ok, line) == (True, "updated")
    assert not _state_file(isolated).exists()
