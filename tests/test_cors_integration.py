import pytest
from fastapi.testclient import TestClient
from server.main import create_app

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_cors_blocks_unpaired_lan_origins(client):
    # Simulate a request from a random LAN page trying to reach the local API.
    headers = {
        "Origin": "http://192.168.1.50:8765",
        "Access-Control-Request-Method": "GET",
    }

    # Pre-flight OPTIONS request
    response = client.options("/api/mobile/qr", headers=headers)
    assert response.status_code in (200, 400)

    # The local app is served same-origin; unrelated LAN origins must not be granted CORS.
    cors_allow_origin = response.headers.get("access-control-allow-origin")
    assert cors_allow_origin is None


def _preflight(client, origin):
    return client.options(
        "/api/mobile/qr",
        headers={"Origin": origin, "Access-Control-Request-Method": "GET"},
    )


def test_cors_blocks_another_servers_localhost_origin(client):
    """The finding: every local page was granted, not only ours.

    Nothing of ours runs on 9999, so this origin is a different program's page asking for
    credentialed access to the local API.
    """
    assert _preflight(client, "http://localhost:9999").headers.get(
        "access-control-allow-origin"
    ) is None


def test_cors_blocks_a_loopback_spelling_we_do_not_serve(client):
    assert _preflight(client, "http://127.0.0.1:9999").headers.get(
        "access-control-allow-origin"
    ) is None


def test_cors_grants_the_servers_own_origin(client):
    """The page this server serves may call it under the other loopback spelling."""
    assert _preflight(client, "http://127.0.0.1:8765").headers.get(
        "access-control-allow-origin"
    ) == "http://127.0.0.1:8765"


def test_cors_grants_the_desktop_shell(client):
    assert (
        _preflight(client, "tauri://localhost").headers.get("access-control-allow-origin")
        == "tauri://localhost"
    )


def test_cors_grants_the_desktop_shell_spelling_other_platforms_use(client):
    assert (
        _preflight(client, "http://tauri.localhost").headers.get("access-control-allow-origin")
        == "http://tauri.localhost"
    )


def test_a_dev_server_can_name_its_origin(monkeypatch):
    """A dev server run without the proxy names its own origin.

    Nothing is granted in advance: the list is what the operator wrote down."""
    monkeypatch.setenv("EPHE_DEV_ORIGINS", "http://localhost:5173")
    response = _preflight(TestClient(create_app()), "http://localhost:5173")
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
