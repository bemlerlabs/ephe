"""R67 — Update experience (update-check backend + route).

The app tells the user when a newer release exists (PWA + desktop share the
same source of truth). Contract:

1. semver comparison handles "v"-prefixed tags and equal versions.
2. check_for_update() is fail-soft: an unreachable release source returns an
   honest result with available=False, never a crash.
3. A TTL cache prevents hammering the release source (default 6 h, injectable
   clock for tests); force=True bypasses it.
4. The deep setting `appearance.update_check` (default ON) gates the whole
   feature — privacy-first: opt-out instead of opt-in, but never hidden.
5. GET /api/update/check returns the contract JSON.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import update_check  # noqa: E402

_REAL_INSTALLED_COMMIT = update_check.installed_commit
_REAL_MAIN_COMPARE = update_check._fetch_main_compare


@pytest.fixture(autouse=True)
def _no_installed_commit(monkeypatch):
    """The continuous channel is opt-in per test: a unit test must never reach
    GitHub just because the checkout it runs in happens to have a HEAD."""
    monkeypatch.setattr(update_check, "installed_commit", lambda: "")
    update_check._reset_cache()


class TestSemver:
    def test_compare_handles_v_prefix_and_equal(self):
        assert update_check._semver("v1.2.0") == (1, 2, 0)
        assert update_check._semver("1.1.0") == (1, 1, 0)
        assert update_check._semver("1.1.0") == update_check._semver("v1.1.0")

    def test_newer_older_equal(self):
        assert update_check._is_newer("v1.2.0", "1.1.0") is True
        assert update_check._is_newer("1.0.9", "1.1.0") is False
        assert update_check._is_newer("v1.1.0", "1.1.0") is False


class TestCheckForUpdate:

    def test_update_available(self, monkeypatch):
        monkeypatch.setattr(
            update_check, "_fetch_latest",
            lambda: {"tag": "v1.2.0", "url": "https://x/r/1", "notes": "bugfixes"},
        )
        update_check._reset_cache()
        out = update_check.check_for_update()
        assert out["available"] is True
        assert out["latest"] == "1.2.0"
        assert out["current"]
        assert out["url"].endswith("/1")

    def test_same_version_not_available(self, monkeypatch):
        monkeypatch.setattr(
            update_check, "_fetch_latest",
            lambda: {"tag": f"v{update_check.current_version()}", "url": "u", "notes": ""},
        )
        update_check._reset_cache()
        assert update_check.check_for_update()["available"] is False

    def test_unreachable_source_is_fail_soft(self, monkeypatch):
        def boom():
            raise OSError("no network")

        monkeypatch.setattr(update_check, "_fetch_latest", boom)
        update_check._reset_cache()
        out = update_check.check_for_update()
        assert out["available"] is False
        assert out.get("error")

    def test_ttl_cache_prevents_refetch(self, monkeypatch):
        calls = {"n": 0}

        def fake_fetch():
            calls["n"] += 1
            return {"tag": "v9.0.0", "url": "u", "notes": ""}

        monkeypatch.setattr(update_check, "_fetch_latest", fake_fetch)
        update_check._reset_cache()
        update_check.check_for_update()
        update_check.check_for_update()
        assert calls["n"] == 1  # cached within TTL
        update_check.check_for_update(force=True)
        assert calls["n"] == 2  # force bypasses

    def test_deep_setting_gates_feature(self, monkeypatch):
        from core import settings_schema as ss

        monkeypatch.setattr(
            ss, "load_deep_settings",
            lambda: {"appearance": {"appearance.update_check": False}},
        )
        update_check._reset_cache()
        out = update_check.check_for_update()
        assert out.get("enabled") is False


    def test_env_opt_out_stops_the_fetch_and_keeps_the_contract(self, monkeypatch):
        """docs/CLI.md promises `EPHE_NO_UPDATE_CHECK=1` turns the check off —
        the terminal app asked the feed through `check_for_update` directly and
        reached GitHub despite the switch. The gate now sits at the one network
        seam, so the check answers "not possible" instead of phoning home."""

        monkeypatch.setenv(update_check.OPT_OUT_ENV, "1")
        update_check._reset_cache()
        out = update_check.check_for_update(force=True)
        assert out["available"] is False
        assert "could not be reached" in out["error"]
        assert update_check.daily_check() == {
            "enabled": False,
            "available": False,
        }
        update_check._reset_cache()


class TestRoute:

    def test_route_contract(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        monkeypatch.setattr(
            update_check, "_fetch_latest",
            lambda: {"tag": "v1.2.0", "url": "https://x/r/1", "notes": "n"},
        )
        update_check._reset_cache()
        from server.main import create_app

        with TestClient(create_app()) as client:
            r = client.get("/api/update/check")
            assert r.status_code == 200
            body = r.json()
            assert body["available"] is True
            assert body["current"] and body["latest"] == "1.2.0"
            assert "url" in body


class TestPrereleaseOrder:
    """A product that ships betas has its whole update story in the prerelease
    field: the numeric tuple alone cannot tell 0.1.0-beta.2 from 0.1.0-beta.1,
    and reading it as equal means the app never offers the next beta."""

    def test_a_later_beta_is_newer(self):
        assert update_check._is_newer("0.1.0-beta.2", "0.1.0-beta.1") is True
        assert update_check._is_newer("v0.1.0-beta.2", "0.1.0-beta.1") is True

    def test_beta_numbers_order_numerically_not_as_text(self):
        assert update_check._is_newer("0.1.0-beta.10", "0.1.0-beta.9") is True
        assert update_check._is_newer("0.1.0-beta.9", "0.1.0-beta.10") is False

    def test_a_release_outranks_its_own_prereleases(self):
        assert update_check._is_newer("0.1.0", "0.1.0-beta.9") is True
        assert update_check._is_newer("0.1.0-beta.9", "0.1.0") is False

    def test_equal_prereleases_are_not_an_update(self):
        assert update_check._is_newer("0.1.0-beta.1", "0.1.0-beta.1") is False

    def test_an_unparseable_tag_never_offers_an_update(self):
        assert update_check._is_newer("nightly", "0.1.0-beta.1") is False
        assert update_check._is_newer("0.1.0-beta.1", "nightly") is False

    def test_a_beta_release_reaches_the_result(self, monkeypatch):
        monkeypatch.setattr(update_check, "current_version", lambda: "1.0.0-beta.1")
        monkeypatch.setattr(
            update_check, "_fetch_latest",
            lambda: {"tag": "v1.0.0-beta.2", "url": "https://x/r/2", "notes": "n"},
        )
        update_check._reset_cache()
        out = update_check.check_for_update()
        assert out["available"] is True
        assert out["latest"] == "1.0.0-beta.2"


class TestFailureIsNotCachedLikeAnAnswer:
    """A stale failure reads as a broken button, so it may not sit in the cache
    for six hours — and a click must be able to override it either way."""

    def test_a_failed_check_is_replayed_briefly_and_a_forced_one_is_live(self, monkeypatch):
        calls = {"n": 0}

        def boom():
            calls["n"] += 1
            raise OSError("no network")

        monkeypatch.setattr(update_check, "_fetch_latest", boom)
        update_check._reset_cache()
        first = update_check.check_for_update()
        assert first["available"] is False and "error" in first
        assert update_check.check_for_update()["error"] == first["error"]
        assert calls["n"] == 1
        update_check.check_for_update(force=True)
        assert calls["n"] == 2

    def test_a_successful_answer_keeps_the_long_ttl(self, monkeypatch):
        calls = {"n": 0}

        def latest():
            calls["n"] += 1
            return {"tag": "v1.2.0", "url": "https://x/r/1", "notes": "n"}

        monkeypatch.setattr(update_check, "_fetch_latest", latest)
        update_check._reset_cache()
        update_check.check_for_update()
        update_check.check_for_update()
        assert calls["n"] == 1


class TestRouteForce:
    """The button's click sends force=1; the background poll must not."""

    def test_the_route_passes_force_through(self, tmp_path, monkeypatch):
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        seen: dict[str, bool] = {}

        def fake(force: bool = False) -> dict:
            seen["force"] = force
            return {"enabled": True, "available": False}

        monkeypatch.setattr(update_check, "check_for_update", fake)
        from server.main import create_app

        with TestClient(create_app()) as client:
            client.get("/api/update/check")
            assert seen["force"] is False
            client.get("/api/update/check?force=1")
            assert seen["force"] is True


class TestContinuousChannel:
    """A merge on the default branch is an update the user can take before the
    next tag. The comparison is ancestry-based, so only a checkout that is
    behind is told to update — never one that is ahead or has diverged."""

    COMMIT = "2a1405a837f0c1d9e4b5a6978877665544332211"

    def _pin(self, monkeypatch, *, commit: str | None = None, release: str = "1.0.0"):
        monkeypatch.setattr(
            update_check, "installed_commit", lambda: self.COMMIT if commit is None else commit,
        )
        monkeypatch.setattr(update_check, "current_version", lambda: release)
        monkeypatch.setattr(
            update_check, "_fetch_latest",
            lambda: {"tag": f"v{release}", "url": "https://x/r/1", "notes": "n"},
        )

    def test_behind_main_is_an_update_on_the_main_channel(self, monkeypatch):
        # The shape GitHub answers for `compare/<build>...main` when the build is
        # behind: the head (main) is ahead, so `ahead_by` carries the count.
        self._pin(monkeypatch)
        monkeypatch.setattr(
            update_check, "_fetch_main_compare",
            lambda c: {"ahead": 3, "behind": 0,
                       "tip": "deadbeefcafe0123", "message": "fix(chat): quieter rows"},
        )
        out = update_check.check_for_update()
        assert out["available"] is True
        assert out["channel"] == "main"
        assert out["commitsBehind"] == 3
        assert out["latest"] == "deadbeefcafe"
        assert out["commit"] == self.COMMIT[:12]
        assert out["url"].endswith(f"compare/{self.COMMIT}...main")
        assert out["notes"] == "fix(chat): quieter rows"

    def test_a_newer_release_outranks_the_main_channel(self, monkeypatch):
        self._pin(monkeypatch)
        monkeypatch.setattr(
            update_check, "_fetch_latest",
            lambda: {"tag": "v1.1.0", "url": "https://x/r/2", "notes": "n"},
        )

        def compare(_commit: str) -> dict:
            raise AssertionError("a newer release needs no ancestry lookup")

        monkeypatch.setattr(update_check, "_fetch_main_compare", compare)
        out = update_check.check_for_update()
        assert out["available"] is True and out["channel"] == "release"

    @pytest.mark.parametrize(
        ("ahead", "behind"),
        [(0, 4), (2, 1), (0, 0)],
        ids=["build-ahead", "diverged", "identical"],
    )
    def test_never_told_to_go_backwards(self, monkeypatch, ahead, behind):
        self._pin(monkeypatch)
        monkeypatch.setattr(
            update_check, "_fetch_main_compare",
            lambda c: {"ahead": ahead, "behind": behind, "tip": "t" * 40, "message": ""},
        )
        out = update_check.check_for_update()
        assert out["available"] is False
        assert out["channel"] == "release"
        assert "commitsBehind" not in out

    def test_an_unknown_commit_skips_the_lookup(self, monkeypatch):
        self._pin(monkeypatch, commit="")
        monkeypatch.setattr(
            update_check, "_fetch_main_compare",
            lambda c: pytest.fail("no commit, no comparison"),
        )
        out = update_check.check_for_update()
        assert out["available"] is False and out["channel"] == "release"
        assert "commit" not in out

    def test_a_failed_lookup_keeps_the_release_answer(self, monkeypatch):
        self._pin(monkeypatch)

        def boom(_commit: str) -> dict:
            raise OSError("no network")

        monkeypatch.setattr(update_check, "_fetch_main_compare", boom)
        out = update_check.check_for_update()
        assert out["available"] is False
        assert out["channel"] == "release"
        assert "error" not in out

    def test_installed_commit_prefers_the_baked_commit(self, monkeypatch):
        monkeypatch.setattr(update_check, "installed_commit", _REAL_INSTALLED_COMMIT)
        monkeypatch.setenv("EPHE_BUILD_COMMIT", "  abc123  ")
        assert update_check.installed_commit() == "abc123"

    def test_installed_commit_reads_a_checkout_head(self, monkeypatch):
        monkeypatch.setattr(update_check, "installed_commit", _REAL_INSTALLED_COMMIT)
        monkeypatch.delenv("EPHE_BUILD_COMMIT", raising=False)
        if not (ROOT / ".git").exists():
            pytest.skip("not a checkout, so there is no HEAD to read")
        assert len(_REAL_INSTALLED_COMMIT()) == 40


class TestComparePayload:
    """GitHub answers a build that is only behind with an empty commit list, so
    the range alone names neither the tip nor what changed. The counts come from
    the build's side: `ahead_by` is what main has and the build lacks."""

    def test_a_behind_compare_fills_the_tip_and_the_subject(self, monkeypatch):
        monkeypatch.delenv(update_check.OPT_OUT_ENV, raising=False)
        monkeypatch.setattr(update_check, "_fetch_main_compare", _REAL_MAIN_COMPARE)
        payloads = [
            {"status": "ahead", "ahead_by": 2, "behind_by": 0, "commits": [],
             "base_commit": {"sha": "abc123def456"}},
            {"sha": "feedfacecafe", "commit": {"message": "feat(companion): the pet moves\n\nbody"}},
        ]

        class Resp:
            def __init__(self, body):
                self._body = body

            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def read(self):
                return json.dumps(self._body).encode()

        monkeypatch.setattr(update_check.urllib.request, "urlopen", lambda *_a, **_k: Resp(payloads.pop(0)))
        out = update_check._fetch_main_compare("abc123def456")
        assert out["ahead"] == 2 and out["behind"] == 0
        assert out["tip"] == "feedfacecafe"
        assert out["message"] == "feat(companion): the pet moves"

    def test_a_build_with_its_own_commits_asks_for_no_further_read(self, monkeypatch):
        monkeypatch.delenv(update_check.OPT_OUT_ENV, raising=False)
        monkeypatch.setattr(update_check, "_fetch_main_compare", _REAL_MAIN_COMPARE)

        def fail(*_a, **_k):
            raise AssertionError("a build with its own commits needs no head read")

        class Resp:
            def __enter__(self):
                return self

            def __exit__(self, *_exc):
                return False

            def read(self):
                return json.dumps({"status": "behind", "ahead_by": 0, "behind_by": 3, "commits": []}).encode()

        monkeypatch.setattr(update_check.urllib.request, "urlopen", lambda *_a, **_k: Resp())
        assert update_check._fetch_main_compare("abc")["tip"] == ""
        monkeypatch.setattr(update_check.urllib.request, "urlopen", fail)
