"""PERF-BE-REST: the first click no longer pays the handler imports.

Route modules are imported at startup, but a handler's core half is imported
where it runs. ``warm_request_paths`` runs those imports and the one-time builds
in a background thread while the shell polls /api/health. The production app
opts in; a TestClient that calls ``create_app()`` must not race its own config.
"""
from __future__ import annotations

import sys
import threading

from fastapi.testclient import TestClient

import server.main as main
from server import warmup


def test_warmup_imports_the_heavy_request_paths():
    warmup.warm_request_paths()
    for module in (
        "core.memory_embed",
        "core.multi_session",
        "core.session_lifecycle",
        "core.plugin_store",
    ):
        assert module in sys.modules, module
    # A second run is a no-op, not a crash: the scheduler may call it more than once.
    warmup.warm_request_paths()


def test_one_failing_step_does_not_hide_the_others(monkeypatch):
    calls: list[str] = []

    def _broken() -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        warmup,
        "_STEPS",
        (("broken", _broken), ("ok", lambda: calls.append("ok"))),
    )
    warmup.warm_request_paths()
    assert calls == ["ok"]


def test_create_app_does_not_warm_and_the_production_app_does(monkeypatch):
    monkeypatch.delenv("EPHE_WARMUP", raising=False)
    monkeypatch.setenv("EPHE_LAN", "0")
    assert main.create_app().state.warm_handlers is False
    assert main.get_app().state.warm_handlers is True
    monkeypatch.setenv("EPHE_WARMUP", "0")
    assert main.get_app().state.warm_handlers is False


def test_the_production_lifespan_runs_the_warmup(monkeypatch):
    monkeypatch.delenv("EPHE_WARMUP", raising=False)
    monkeypatch.setenv("EPHE_LAN", "0")
    ran = threading.Event()
    monkeypatch.setattr("server.warmup.warm_request_paths", lambda: ran.set())

    with TestClient(main.get_app(), base_url="http://127.0.0.1:8898") as client:
        assert ran.wait(2.0), "the production app did not schedule the warmup"
        assert client.get("/api/health").status_code == 200


def test_the_production_lifespan_sweeps_the_chat_trash(monkeypatch):
    """The running server itself enforces the window; no caller has to remember it."""
    monkeypatch.setenv("EPHE_LAN", "0")
    ran = threading.Event()
    from core import session_trash

    monkeypatch.setattr(session_trash, "purge_expired", lambda **kw: ran.set() or {})
    with TestClient(main.get_app(), base_url="http://127.0.0.1:8899") as client:
        assert ran.wait(2.0), "the production app did not sweep the trash"
        assert client.get("/api/health").status_code == 200


def test_an_app_built_by_a_test_sweeps_nothing(monkeypatch):
    monkeypatch.setenv("EPHE_LAN", "0")
    swept = threading.Event()
    from core import session_trash

    monkeypatch.setattr(session_trash, "purge_expired", lambda **kw: swept.set() or {})
    with TestClient(main.create_app(), base_url="http://127.0.0.1:8900") as client:
        assert client.get("/api/health").status_code == 200
    assert not swept.is_set(), "a test app must not empty the store its fixture arranged"


def test_a_skipped_warmup_still_bounds_the_trash(monkeypatch):
    """EPHE_WARMUP=0 is a measurement switch; an unbounded trash is a bug."""
    monkeypatch.setenv("EPHE_LAN", "0")
    monkeypatch.setenv("EPHE_WARMUP", "0")
    assert main.get_app().state.warm_handlers is False
    assert main.get_app().state.maintenance is True
