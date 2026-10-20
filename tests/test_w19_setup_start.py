"""W19 — setup-mode start without an engine (web onboarding for non-terminal users).

Before: ``run_server`` aborted with exit 1 when engine.json/env were missing — a
newcomer without terminal knowledge never saw the UI. Now: a loopback start
enters setup mode (server runs, /api/setup/status reports configured=false, the
setup gate shows the setup page); chat stays fail-closed. ``--lan``/0.0.0.0 still
aborts — no unconfigured LAN exposure.
"""
from __future__ import annotations

import sys

import pytest


@pytest.fixture
def _no_engine(monkeypatch):
    from core.engine_config import EngineNotConfigured

    monkeypatch.setattr(
        "core.engine_config.resolve_engine_choice",
        lambda **_kw: (_ for _ in ()).throw(EngineNotConfigured("No engine configured.")),
    )
    monkeypatch.delenv("EPHE_MODEL_PROVIDER", raising=False)
    # W19 hygiene: a LAN marker would push the loopback start into the LAN branch
    # (fail-closed) — these pins test setup mode, not the LAN.
    monkeypatch.delenv("EPHE_LAN", raising=False)
    monkeypatch.delenv("EPHE_HOST", raising=False)


def test_loopback_start_without_engine_enters_setup_mode(_no_engine, capsys):
    import run_server

    monkey_patch_argv = ["run_server.py", "--port", "8765"]
    monkeypatch_argv = pytest.MonkeyPatch()
    monkeypatch_argv.setattr(sys, "argv", monkey_patch_argv)
    try:
        assert run_server._bootstrap_engine_choice() is None  # no SystemExit
    finally:
        monkeypatch_argv.undo()
    out = capsys.readouterr().out
    assert "SETUP MODE" in out


def test_a_persisted_incomplete_engine_enters_setup_mode(monkeypatch, capsys):
    """GIVEN engine.json names openai_compatible without api_url
    WHEN a loopback start resolves it
    THEN the server enters setup mode and names the missing field, instead of
    aborting on an uncaught configuration error."""
    import run_server
    from core.engine_config import EngineChoice

    monkeypatch.setattr(
        "core.engine_config.resolve_engine_choice",
        lambda **_kw: EngineChoice("openai_compatible", "m", None),
    )
    monkeypatch.delenv("EPHE_SETUP_MODE", raising=False)
    monkeypatch.delenv("EPHE_LAN", raising=False)
    monkeypatch.delenv("EPHE_HOST", raising=False)
    mp = pytest.MonkeyPatch()
    mp.setattr(sys, "argv", ["run_server.py", "--port", "8765"])
    try:
        assert run_server._bootstrap_engine_choice() is None
    finally:
        mp.undo()
    out = capsys.readouterr().out
    assert "SETUP MODE" in out
    assert "api_url" in out


def test_lan_start_without_engine_still_fails_closed(_no_engine, capsys):
    import run_server

    mp = pytest.MonkeyPatch()
    mp.setattr(sys, "argv", ["run_server.py", "--lan"])
    try:
        with pytest.raises(SystemExit) as excinfo:
            run_server._bootstrap_engine_choice()
    finally:
        mp.undo()
    assert excinfo.value.code == 1
    assert "Fix:" in capsys.readouterr().err


def test_host_0000_without_engine_fails_closed_without_lan_flag(_no_engine, capsys):
    """Defence-in-depth: ``python run_server.py --host 0.0.0.0`` (no --lan flag)
    must not slip into setup mode while the engine is missing — otherwise an
    unconfigured server binds to the LAN (release bar)."""
    import run_server

    mp = pytest.MonkeyPatch()
    mp.setattr(sys, "argv", ["run_server.py", "--host", "0.0.0.0"])
    try:
        with pytest.raises(SystemExit) as excinfo:
            run_server._bootstrap_engine_choice()
    finally:
        mp.undo()
    assert excinfo.value.code == 1


def test_ephe_spawn_env_without_engine_fails_closed(_no_engine, capsys, monkeypatch):
    """``ephe start --lan`` spawns without the --lan flag but with
    EPHE_HOST=0.0.0.0 in the env — this path stays fail-closed as well."""
    import run_server

    mp = pytest.MonkeyPatch()
    mp.setattr(sys, "argv", ["run_server.py", "--host", "0.0.0.0"])
    mp.setenv("EPHE_HOST", "0.0.0.0")
    try:
        with pytest.raises(SystemExit) as excinfo:
            run_server._bootstrap_engine_choice()
    finally:
        mp.undo()
    assert excinfo.value.code == 1


# Chat fail-closed in setup mode


def test_setup_mode_sets_flag_and_explicit_env_does_not(_no_engine, capsys, monkeypatch):
    """Setup mode sets the chat fail-closed flag; with an explicit env
    (already configured) it stays unset."""
    import run_server

    monkeypatch.delenv("EPHE_SETUP_MODE", raising=False)
    mp = pytest.MonkeyPatch()
    mp.setattr(sys, "argv", ["run_server.py", "--port", "8765"])
    try:
        assert run_server._bootstrap_engine_choice() is None
        assert __import__("os").environ.get("EPHE_SETUP_MODE") == "1"
    finally:
        mp.undo()

    mp2 = pytest.MonkeyPatch()
    mp2.setenv("EPHE_MODEL_PROVIDER", "local_ollama")
    mp2.delenv("EPHE_SETUP_MODE", raising=False)
    try:
        assert run_server._bootstrap_engine_choice() is None
        assert __import__("os").environ.get("EPHE_SETUP_MODE") != "1"
    finally:
        mp2.undo()


def test_chat_guard_fails_closed_only_in_setup_mode(monkeypatch):
    """Without the setup flag the guard lets the call pass; with the flag and no
    engine (no env, no engine.json, no session override) it raises 409 with a setup
    hint; after an engine choice (engine.json persisted) the chat opens again."""
    from fastapi import HTTPException

    from server.routes.chat import _ensure_engine_ready

    class _FakeEngine:
        provider = "local_ollama"
        model = "gemma4:12b"
        api_url = None

    monkeypatch.setenv("EPHE_SETUP_MODE", "1")
    monkeypatch.setattr("core.engine_config.load_engine_config", lambda *a, **kw: None)
    with pytest.raises(HTTPException) as excinfo:
        _ensure_engine_ready()
    assert excinfo.value.status_code == 409
    assert "Setup page" in excinfo.value.detail

    # Engine chosen (setup UI persisted engine.json) → chat open.
    monkeypatch.setattr("core.engine_config.load_engine_config", lambda *a, **kw: _FakeEngine())
    _ensure_engine_ready()  # no raise

    # A session override (set_active_provider) is enough as well.
    monkeypatch.setattr("core.engine_config.load_engine_config", lambda *a, **kw: None)
    import core.model_provider as mp_mod

    monkeypatch.setattr(mp_mod, "_ACTIVE_OVERRIDE", _FakeEngine(), raising=False)
    _ensure_engine_ready()  # no raise

    # Without the setup flag (normal server with an engine) the guard is a no-op.
    monkeypatch.delenv("EPHE_SETUP_MODE")
    monkeypatch.setattr(mp_mod, "_ACTIVE_OVERRIDE", None, raising=False)
    _ensure_engine_ready()  # no raise


def test_chat_endpoint_returns_409_in_setup_mode(monkeypatch):
    """End-to-end: in setup mode /api/chat answers 409 + a setup hint,
    not an Ollama connection error."""
    from fastapi.testclient import TestClient

    from server.main import app

    monkeypatch.setenv("EPHE_SETUP_MODE", "1")
    monkeypatch.setattr("core.engine_config.load_engine_config", lambda *a, **kw: None)
    with TestClient(app, raise_server_exceptions=False) as client:
        resp = client.post("/api/chat", json={"message": "hi"})
    assert resp.status_code == 409
    body = resp.json()["error"]
    assert "Setup page" in body["message"]
    assert body["code"] == "setup_required"
