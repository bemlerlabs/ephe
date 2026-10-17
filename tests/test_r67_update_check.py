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
