"""
A subsystem that cannot start, or cannot stop, does not take the server with it.

`server/main.py`'s lifespan attaches four subsystems around the request handler — the
speech-model warmup, the scheduler, the plugin registry migration and the MCP servers —
and detaches three on the way out. Each call is wrapped in its own try/except with a
logged line and no re-raise: a box whose scheduler cannot start still serves, and a
shutdown whose MCP teardown fails still finishes. A test that only enters and leaves
the context manager would pass without exercising those branches, so each case
patches one subsystem to raise and asserts both halves: the call was reached, and the
server answered anyway.

The mounted `/mobile.html` entrypoint is pinned here too — a build artefact the QR
target must not depend on.
"""
from __future__ import annotations

import threading

from fastapi.testclient import TestClient


def _app(tmp_path, monkeypatch):
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    from server.main import create_app

    return create_app()


def _serves(client: TestClient) -> None:
    """The app is up and its route table answers: the OpenAPI document, not a stub."""
    response = client.get("/openapi.json")
    assert response.status_code == 200, response.text
    assert "/api/plugins" in response.json()["paths"]


def test_a_scheduler_that_cannot_start_leaves_a_serving_server(tmp_path, monkeypatch):
    """GIVEN the background scheduler refuses to start
    WHEN the app's lifespan starts
    THEN the refusal is caught, the server answers, and the scheduler was asked."""
    import core.scheduler

    calls: list[str] = []

    def _refuse() -> None:
        calls.append("start")
        raise RuntimeError("scheduler thread is gone")

    monkeypatch.setattr(core.scheduler.ephe_scheduler, "start", _refuse)

    with TestClient(_app(tmp_path, monkeypatch)) as client:
        assert calls == ["start"], "the lifespan never asked the scheduler to start"
        _serves(client)


def test_a_registry_migration_that_fails_leaves_a_serving_server(tmp_path, monkeypatch):
    """GIVEN the legacy plugin registry cannot be migrated
    WHEN the app's lifespan starts
    THEN the server still answers and the migration was attempted."""
    import core.plugin_runtime

    calls: list[str] = []

    def _refuse():
        calls.append("lifecycle")
        raise RuntimeError("registry is unreadable")

    monkeypatch.setattr(core.plugin_runtime, "lifecycle", _refuse)

    with TestClient(_app(tmp_path, monkeypatch)) as client:
        assert calls == ["lifecycle"], "the lifespan never migrated the plugin registry"
        _serves(client)


def test_mcp_servers_that_fail_to_attach_leave_a_serving_server(tmp_path, monkeypatch):
    """GIVEN the configured MCP servers cannot be attached
    WHEN the app's lifespan starts
    THEN the server answers and the attach was attempted."""
    import core.mcp_config

    calls: list[str] = []

    async def _refuse():
        calls.append("init")
        raise RuntimeError("no stdio server would start")

    monkeypatch.setattr(core.mcp_config, "init_mcp_from_config", _refuse)

    with TestClient(_app(tmp_path, monkeypatch)) as client:
        assert calls == ["init"], "the lifespan never tried to attach the MCP servers"
        _serves(client)


def test_a_warmup_that_raises_is_caught_in_its_thread(tmp_path, monkeypatch):
    """GIVEN the speech-model warmup raises
    WHEN the lifespan starts and the warmup thread runs
    THEN the exception stays in the thread: the server answers while it is caught."""
    import core.transcribe

    raised = threading.Event()

    def _refuse() -> None:
        raised.set()
        raise RuntimeError("the model cache is corrupt")

    monkeypatch.setattr(core.transcribe, "warm_if_cached", _refuse)

    with TestClient(_app(tmp_path, monkeypatch)) as client:
        assert raised.wait(10.0), "the warmup thread never ran the patched warmup"
        _serves(client)


def test_every_teardown_fault_is_caught_so_the_shutdown_finishes(tmp_path, monkeypatch):
    """GIVEN the scheduler, the channels and the MCP clients all refuse to stop
    WHEN the app's lifespan ends
    THEN each stop was attempted and the shutdown still completes."""
    import core.scheduler
    import core.tools.mcp_client
    from server.routes import channels

    calls: list[str] = []

    def _refuse_stop() -> None:
        calls.append("scheduler.stop")
        raise RuntimeError("the scheduler will not stop")

    async def _refuse_channels() -> None:
        calls.append("channels")
        raise RuntimeError("a channel is stuck")

    async def _refuse_mcp() -> None:
        calls.append("mcp")
        raise RuntimeError("a client's transport is already gone")

    monkeypatch.setattr(core.scheduler.ephe_scheduler, "stop", _refuse_stop)
    monkeypatch.setattr(channels, "shutdown_channels", _refuse_channels)
    monkeypatch.setattr(core.tools.mcp_client, "close_all_mcp_clients", _refuse_mcp)

    with TestClient(_app(tmp_path, monkeypatch)) as client:
        _serves(client)

    assert calls == ["scheduler.stop", "channels", "mcp"], calls


def test_the_mobile_entrypoint_is_served_without_a_build(tmp_path, monkeypatch):
    """GIVEN the QR target a phone opens
    WHEN it is fetched
    THEN the HTML comes from the server itself: app/dist is git-ignored, so a build
    step would leave a phone without the page."""
    with TestClient(_app(tmp_path, monkeypatch)) as client:
        response = client.get("/mobile.html")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "/api/mobile/ping" in response.text, "the page no longer pings before it redirects"


def test_registered_mcp_tools_are_reported_at_startup(tmp_path, monkeypatch, caplog):
    """GIVEN an MCP attach that registered two tools
    WHEN the app's lifespan starts
    THEN the names are logged at startup, so a box whose servers did attach says so
    instead of leaving the reader to guess from a missing tool."""
    import logging

    import core.mcp_config

    async def _registered():
        return ["mcp_echo", "mcp_search"]

    monkeypatch.setattr(core.mcp_config, "init_mcp_from_config", _registered)

    with (
        caplog.at_level(logging.INFO, logger="uvicorn.access"),
        TestClient(_app(tmp_path, monkeypatch)) as client,
    ):
        _serves(client)

    assert "MCP tools registered: mcp_echo, mcp_search" in caplog.text, caplog.text
