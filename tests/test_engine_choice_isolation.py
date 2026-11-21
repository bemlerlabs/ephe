"""A provider switch writes the test's own choice, never the machine's.

``tests/AGENTS.md`` names ``engine_config.CONFIG_DIR`` as the constant that binds at import and
therefore needs patching rather than an environment variable. This file is the counter that keeps
that rule true for the engine choice: it puts a tag no other test uses through the same seam the
PWA's model tab uses, and requires it to show up under the per-test home while the real ``~/.ephe``
stays free of it. The negative control runs the same request with the constant pointed at a
stand-in home, so the assertion cannot pass by the write having gone nowhere at all.

The case is not hypothetical. On 2026-11-17 a single-file run of
``tests/test_model_context_autofollow.py`` — the start-narrow command the agent files recommend —
wrote that module's fixture choice into the owner's ``engine.json``, and the chat refused every
turn afterwards with the key-binding refusal: the stored key is bound to the engine its owner
chose, and a foreign model tag there reads as a tampered key.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import core.engine_config as engine_config

PLANTED_TAG = "planted-choice-for-isolation"
FAKE_ENDPOINT = "http://engine.test:9997/v1"
PROVIDER_BODY = {"provider": {"type": "openai_compatible", "model": PLANTED_TAG,
                              "endpoint": FAKE_ENDPOINT}}


def _home_engine_text() -> str:
    """The real stored choice, or empty when this machine has none."""
    path = Path.home() / ".ephe" / "engine.json"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _switch_through_the_settings_route() -> int:
    """The route the PWA model tab posts to, with the engine probe answered locally.

    The probe is a network call to the provider being chosen; this suite answers it offline, so
    the request under test is the persistence and nothing else.
    """
    from server.main import create_app

    async def fake_probe(active):  # noqa: ARG001 (the seam's signature)
        return 204_800

    with patch("server.routes.model_provider._active_context_window", new=fake_probe):
        return TestClient(create_app()).post("/api/settings", json=PROVIDER_BODY).status_code


class TestTheChoiceStaysInTheTest:
    def test_the_switch_lands_in_the_per_test_home(self, tmp_path):
        assert _switch_through_the_settings_route() == 200
        written = tmp_path / "ephe-home" / "engine.json"
        assert written.is_file(), f"{written} never appeared; CONFIG_DIR is " \
                                  f"{engine_config.CONFIG_DIR}"
        assert PLANTED_TAG in written.read_text(encoding="utf-8")

    def test_the_machines_choice_is_left_alone(self):
        assert _switch_through_the_settings_route() == 200
        assert PLANTED_TAG not in _home_engine_text(), \
            "the suite wrote its provider choice into the developer's ~/.ephe/engine.json"

    def test_the_write_reaches_disk_when_the_constant_points_at_a_home(self, tmp_path, monkeypatch):
        """Counter-control: the assertions above are about the patch, not about a request that
        writes nothing anywhere — with the constant aimed at a home, it does write there."""
        stand_in = tmp_path / "stand-in-home"
        monkeypatch.setattr(engine_config, "CONFIG_DIR", stand_in)
        assert _switch_through_the_settings_route() == 200
        written = stand_in / "engine.json"
        assert written.is_file()
        assert PLANTED_TAG in written.read_text(encoding="utf-8")

    def test_the_resolved_path_follows_the_constant(self, tmp_path, monkeypatch):
        """``default_config_path()`` reads the constant at call time, which is what makes the
        per-test patch the whole isolation — a stale copy would defeat every fixture."""
        stand_in = tmp_path / "another-home"
        monkeypatch.setattr(engine_config, "CONFIG_DIR", stand_in)
        assert engine_config.default_config_path() == stand_in / engine_config.CONFIG_FILE
