"""The update channel: a published release, or the branch as it moves.

`appearance.update_channel` decides which answer the surface offers. `commit`
is the default — a reader who follows the work wants the merges, not only the
tags — and `stable` must never leak a branch answer into the release path.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import update_check  # noqa: E402


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(update_check, "installed_commit", lambda: "")
    update_check._reset_cache()


def _same_version_release(monkeypatch) -> None:
    monkeypatch.setattr(
        update_check,
        "_fetch_latest",
        lambda: {"tag": f"v{update_check.current_version()}", "url": "u", "notes": ""},
    )


def test_the_commit_channel_is_the_default():
    assert update_check.update_channel() == "commit"


def test_an_unknown_value_falls_back_to_the_default(monkeypatch):
    monkeypatch.setattr(
        "core.settings_schema.deep_select", lambda key: "yesterday", raising=True
    )
    assert update_check.update_channel() == "commit"


def test_a_stable_channel_never_asks_the_branch(monkeypatch):
    monkeypatch.setattr(update_check, "update_channel", lambda: "stable")
    monkeypatch.setattr(update_check, "installed_commit", lambda: "a" * 40)
    _same_version_release(monkeypatch)
    asked: list[str] = []
    monkeypatch.setattr(
        update_check,
        "_main_channel",
        lambda commit: asked.append(commit) or {"available": True, "channel": "main"},
    )
    update_check._reset_cache()

    out = update_check.check_for_update(force=True)

    assert asked == []
    assert out["updateChannel"] == "stable"
    assert out["channel"] == "release"
    assert out["available"] is False


def test_the_commit_channel_reports_the_merges_ahead(monkeypatch):
    monkeypatch.setattr(update_check, "installed_commit", lambda: "b" * 40)
    _same_version_release(monkeypatch)
    monkeypatch.setattr(
        update_check,
        "_main_channel",
        lambda commit: {
            "available": True,
            "channel": "main",
            "commitsBehind": 3,
            "latest": "abc1234",
            "commit": commit[:12],
            "notes": "a merge",
        },
    )
    update_check._reset_cache()

    out = update_check.check_for_update(force=True)

    assert out["channel"] == "main"
    assert out["commitsBehind"] == 3
    assert out["available"] is True
    assert out["updateChannel"] == "commit"
