"""The two update channels: `release` (tags only) and `commit` (main's head).

`appearance.update_channel` — or `EPHE_UPDATE_CHANNEL` — decides what the
desktop app and the PWA offer. `release` is the default: only tagged releases.
`commit` additionally follows merges on `main` between tags. An unknown value
falls back to `release`, never silently to the unquiet channel.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import update_check  # noqa: E402

INSTALLED = "2a1405a837f0c1d9e4b5a6978877665544332211"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv(update_check.CHANNEL_ENV, raising=False)
    monkeypatch.setattr(update_check, "installed_commit", lambda: "")
    update_check._reset_cache()


def _same_version_release(monkeypatch, version: str | None = None) -> None:
    tag = version or update_check.current_version()
    monkeypatch.setattr(
        update_check,
        "_fetch_latest",
        lambda: {"tag": f"v{tag}", "url": "u", "notes": ""},
    )


def _pin_installed(monkeypatch, commit: str = INSTALLED) -> None:
    monkeypatch.setattr(update_check, "installed_commit", lambda: commit)



# Naming, parsing, and the branch the channel may read.


def test_release_is_the_default():
    assert update_check.update_channel() == "release"


def test_the_setting_can_select_commit(monkeypatch):
    monkeypatch.setattr("core.settings_schema.deep_select", lambda key: "commit")
    assert update_check.update_channel() == "commit"


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("release", "release"),
        ("commit", "commit"),
        ("stable", "release"),  # the name before the channel was called release
        ("main", "commit"),  # the branch name is not a channel name
        ("yesterday", "release"),  # unknown never becomes the unquiet channel
        ("", "release"),
    ],
)
def test_names_normalise_and_unknown_falls_back_to_release(monkeypatch, stored, expected):
    monkeypatch.setattr("core.settings_schema.deep_select", lambda key: stored)
    assert update_check.update_channel() == expected


def test_the_environment_names_the_channel_for_one_process(monkeypatch):
    monkeypatch.setattr("core.settings_schema.deep_select", lambda key: "release")
    monkeypatch.setenv(update_check.CHANNEL_ENV, "commit")
    assert update_check.update_channel() == "commit"


def test_an_unknown_environment_value_falls_back_to_release(monkeypatch):
    monkeypatch.setattr("core.settings_schema.deep_select", lambda key: "commit")
    monkeypatch.setenv(update_check.CHANNEL_ENV, "nightly")
    assert update_check.update_channel() == "release"


def test_a_broken_settings_file_keeps_the_default(monkeypatch):
    def boom(key):
        raise OSError("settings.json is unreadable")

    monkeypatch.setattr("core.settings_schema.deep_select", boom)
    assert update_check.update_channel() == "release"



# Naming, parsing, and the branch the channel may read.


def test_release_never_asks_the_branch(monkeypatch):
    _pin_installed(monkeypatch)
    _same_version_release(monkeypatch)
    asked: list[str] = []
    monkeypatch.setattr(
        update_check,
        "_fetch_main_compare",
        lambda commit: asked.append(commit) or pytest.fail("the release channel read main"),
    )
    monkeypatch.setattr(
        update_check,
        "_fetch_head",
        lambda: pytest.fail("the release channel read the branch head"),
    )

    out = update_check.check_for_update(force=True, channel="release")

    assert asked == []
    assert out["available"] is False
    assert out["channel"] == "release"
    assert out["updateChannel"] == "release"


def test_the_default_check_is_the_release_channel(monkeypatch):
    _pin_installed(monkeypatch)
    _same_version_release(monkeypatch)
    monkeypatch.setattr(
        update_check,
        "_fetch_main_compare",
        lambda commit: pytest.fail("the default channel must not read main"),
    )
    update_check._reset_cache()

    out = update_check.check_for_update(force=True)

    assert out["updateChannel"] == "release"
    assert out["channel"] == "release"



# Naming, parsing, and the branch the channel may read.


def test_the_commit_channel_reports_a_newer_branch_sha(monkeypatch):
    _pin_installed(monkeypatch)
    _same_version_release(monkeypatch)
    monkeypatch.setattr(
        update_check,
        "_fetch_main_compare",
        lambda commit: {
            "ahead": 3,
            "behind": 0,
            "tip": "deadbeefcafe0123",
            "message": "fix(chat): quieter tool rows",
        },
    )
    update_check._reset_cache()

    out = update_check.check_for_update(force=True, channel="commit")

    current = update_check.current_version()
    assert out["available"] is True
    assert out["channel"] == "commit"
    assert out["updateChannel"] == "commit"
    assert out["commitsBehind"] == 3
    # The honest version of an untagged build: the release number plus the sha.
    assert out["latest"] == f"{current}+deadbeefcafe"
    assert out["git_sha"] == "deadbeefcafe"
    assert out["commit"] == INSTALLED[:12]
    assert out["url"].endswith(f"compare/{INSTALLED}...main")
    assert out["notes"] == "fix(chat): quieter tool rows"


def test_the_commit_channel_is_quiet_at_the_branch_tip(monkeypatch):
    _pin_installed(monkeypatch)
    _same_version_release(monkeypatch)
    monkeypatch.setattr(
        update_check,
        "_fetch_main_compare",
        lambda commit: {"ahead": 0, "behind": 0, "tip": "", "message": ""},
    )
    update_check._reset_cache()

    out = update_check.check_for_update(force=True, channel="commit")

    assert out["available"] is False
    assert out["updateChannel"] == "commit"
    assert "git_sha" not in out


def test_a_diverged_checkout_is_not_told_to_update(monkeypatch):
    _pin_installed(monkeypatch)
    _same_version_release(monkeypatch)
    monkeypatch.setattr(
        update_check,
        "_fetch_main_compare",
        lambda commit: {"ahead": 2, "behind": 1, "tip": "t" * 40, "message": ""},
    )
    update_check._reset_cache()

    out = update_check.check_for_update(force=True, channel="commit")

    assert out["available"] is False
    assert "commitsBehind" not in out


def test_a_newer_release_outranks_the_commit_channel(monkeypatch):
    _pin_installed(monkeypatch)
    monkeypatch.setattr(
        update_check,
        "_fetch_latest",
        lambda: {"tag": "v1.1.0", "url": "https://x/r/2", "notes": "n"},
    )

    def no_branch(commit: str) -> dict:
        raise AssertionError("a newer release needs no branch lookup")

    monkeypatch.setattr(update_check, "_fetch_main_compare", no_branch)
    update_check._reset_cache()

    out = update_check.check_for_update(force=True, channel="commit")

    assert out["available"] is True
    assert out["channel"] == "release"
    assert out["updateChannel"] == "commit"
    assert out["latest"] == "1.1.0"


def test_an_unknown_explicit_channel_is_release(monkeypatch):
    _pin_installed(monkeypatch)
    _same_version_release(monkeypatch)
    monkeypatch.setattr(
        update_check,
        "_fetch_main_compare",
        lambda commit: pytest.fail("an unknown channel read main"),
    )
    update_check._reset_cache()

    out = update_check.check_for_update(force=True, channel="nightly")

    assert out["updateChannel"] == "release"


def test_the_cache_is_kept_per_channel(monkeypatch):
    calls = {"n": 0}

    def fetch():
        calls["n"] += 1
        return {"tag": f"v{update_check.current_version()}", "url": "u", "notes": ""}

    monkeypatch.setattr(update_check, "_fetch_latest", fetch)
    update_check._reset_cache()

    update_check.check_for_update(force=True, channel="release")
    update_check.check_for_update(force=True, channel="commit")
    update_check.check_for_update(channel="release")

    assert calls["n"] == 2


def test_a_commit_answer_carries_the_apply_verdict(monkeypatch):
    from core import update_apply

    _pin_installed(monkeypatch)
    _same_version_release(monkeypatch)
    monkeypatch.setattr(
        update_check,
        "_fetch_main_compare",
        lambda commit: {
            "ahead": 2,
            "behind": 0,
            "tip": "deadbeefcafe0123",
            "message": "",
        },
    )
    monkeypatch.setattr(
        update_apply,
        "probe",
        lambda root=None, release=False: {"ok": False, "code": "not_a_checkout"},
    )
    update_check._reset_cache()

    out = update_check.check_for_update(force=True, channel="commit")

    assert out["channel"] == "commit"
    assert out["apply"] == {"ok": False, "code": "not_a_checkout"}
    assert out["releaseUrl"] == "u"


def test_a_release_answer_carries_the_apply_verdict_too(monkeypatch):
    """The PWA takes a release through the backend; the answer says whether this
    installation is a checkout that can run it."""
    from core import update_apply

    monkeypatch.setattr(
        update_check,
        "_fetch_latest",
        lambda: {"tag": "v9.9.9", "url": "https://x/r", "notes": ""},
    )
    monkeypatch.setattr(
        update_apply,
        "probe",
        lambda root=None, release=False: {"ok": release, "code": "" if release else "not_on_main"},
    )
    update_check._reset_cache()

    out = update_check.check_for_update(force=True, channel="release")

    assert out["channel"] == "release"
    assert out["apply"] == {"ok": True, "code": ""}
