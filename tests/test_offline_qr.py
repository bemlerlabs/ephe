import pytest
import os
from fastapi.testclient import TestClient
from server.main import create_app
from unittest.mock import patch

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_mobile_qr_offline_fallback(client):
    """Given air-gapped status, when GET /api/mobile/qr is requested, then it should use local IP."""
    with patch("server.routes.mobile.get_local_ip", return_value="192.168.1.50"), \
         patch("server.routes.mobile.tunnel_manager") as mock_tunnel, \
         patch("server.routes.mobile._lan_probe_succeeds", return_value=True):

        response = client.get("/api/mobile/qr")
        assert response.status_code == 200
        data = response.json()

        # Then: URL should be local, not from tunnel
        assert data["url"] == "http://192.168.1.50:8765/mobile.html"
        # And: Tunnel should NOT have been started
        mock_tunnel.start_tunnel.assert_not_called()

def test_mobile_qr_online_flow(client):
    """Given internet available, when GET /api/mobile/qr is requested, then it still uses LAN by default."""
    with patch("server.routes.mobile.get_local_ip", return_value="192.168.1.50"), \
         patch("server.routes.mobile.tunnel_manager") as mock_tunnel, \
         patch("server.routes.mobile._lan_probe_succeeds", return_value=True):

        mock_tunnel.public_url = "https://ephe.serveo.net"
        mock_tunnel.start_tunnel.return_value = None

        response = client.get("/api/mobile/qr")
        assert response.status_code == 200
        data = response.json()

        # Then: URL should remain local unless public mode is explicit
        assert data["url"] == "http://192.168.1.50:8765/mobile.html"
        assert data["mode"] == "lan"
        assert data["is_public"] is False
        # And: Tunnel should not start by default
        mock_tunnel.start_tunnel.assert_not_called()


def test_mobile_qr_public_mode_requires_explicit_mode(client):
    """Given explicit public mode, when internet and a tunnel URL are available, then the QR uses that public URL."""
    with patch("server.routes.mobile.get_local_ip", return_value="192.168.1.50"), \
         patch("server.routes.mobile.tunnel_manager") as mock_tunnel, \
         patch("server.routes.mobile._lan_probe_succeeds", return_value=True):

        mock_tunnel.public_url = "https://ephe.example.test"
        mock_tunnel.start_tunnel.return_value = None

        response = client.get("/api/mobile/qr?mode=public")
        assert response.status_code == 200
        data = response.json()

        assert data["url"] == "https://ephe.example.test/mobile.html"
        assert data["mode"] == "public"
        assert data["is_public"] is True
        assert data["requires_internet"] is True
        mock_tunnel.start_tunnel.assert_called_once_with(8765)


def test_mobile_qr_public_mode_falls_back_to_lan_when_internet_unavailable(client):
    """Given explicit public mode without internet, when QR is requested, then it falls back to LAN without a tunnel."""
    with patch("server.routes.mobile.get_local_ip", return_value="192.168.1.50"), \
         patch("server.routes.mobile.tunnel_manager") as mock_tunnel, \
         patch("server.routes.mobile._lan_probe_succeeds", return_value=True):

        mock_tunnel.public_url = None
        mock_tunnel.start_tunnel.return_value = None

        response = client.get("/api/mobile/qr?mode=public")
        assert response.status_code == 200
        data = response.json()

        assert data["url"] == "http://192.168.1.50:8765/mobile.html"
        assert data["mode"] == "lan"
        assert data["is_public"] is False
        assert data["requires_internet"] is False
        mock_tunnel.start_tunnel.assert_called_once_with(8765)


def test_mobile_qr_reports_unreachable_when_server_is_bound_to_loopback(client, monkeypatch):
    """
    GIVEN Ephe was started with the secure loopback default
    WHEN the user opens the mobile QR dialog
    THEN the QR payload warns that a phone cannot reach the LAN URL until LAN mode is enabled.
    """
    monkeypatch.setenv("EPHE_HOST", "127.0.0.1")
    # auto tries the public tunnel; if it does not come up, it falls back to the LAN warning.
    with patch("server.routes.mobile.get_local_ip", return_value="192.168.1.50"), \
         patch("server.routes.mobile._start_public_tunnel", return_value=None):

        response = client.get("/api/mobile/qr")
        assert response.status_code == 200
        data = response.json()

        assert data["url"] == "http://192.168.1.50:8765/mobile.html"
        assert data["mode"] == "lan"
        assert data["lan_reachable"] is False
        assert "ephe start --lan" in data["message"]


def test_mobile_qr_auto_mode_starts_public_tunnel_when_loopback_server_has_internet(client, monkeypatch):
    """
    GIVEN the app is running on the safe loopback default and internet is available
    WHEN the user opens the QR dialog in auto mode
    THEN auto falls back to the outgoing public tunnel so the phone connects without any
    firewall/LAN setup (outgoing-only model: outgoing connection => firewall-immune).
    """
    monkeypatch.setenv("EPHE_HOST", "127.0.0.1")
    with patch("server.routes.mobile.get_local_ip", return_value="192.168.1.50"), \
         patch("server.routes.mobile._start_public_tunnel", return_value="https://ephe.example.test") as start:

        response = client.get("/api/mobile/qr")
        assert response.status_code == 200
        data = response.json()

        assert data["url"] == "https://ephe.example.test/mobile.html"
        assert data["mode"] == "public"
        assert data["is_public"] is True
        assert data["requires_internet"] is True
        start.assert_called_once()


def test_mobile_qr_reports_reachable_when_server_is_started_in_lan_mode(client, monkeypatch):
    """
    GIVEN Ephe was started in explicit LAN mode
    WHEN the user opens the mobile QR dialog
    THEN the QR payload is marked reachable for phones on the same local network.
    """
    monkeypatch.setenv("EPHE_HOST", "0.0.0.0")
    with patch("server.routes.mobile.get_local_ip", return_value="192.168.1.50"), \
         patch("server.routes.mobile.tunnel_manager") as mock_tunnel, \
         patch("server.routes.mobile._lan_probe_succeeds", return_value=True):

        response = client.get("/api/mobile/qr")
        assert response.status_code == 200
        data = response.json()

        assert data["url"] == "http://192.168.1.50:8765/mobile.html"
        assert data["lan_reachable"] is True
        assert data["message"] == ""
        mock_tunnel.start_tunnel.assert_not_called()


def test_mobile_qr_reports_firewall_warning_when_lan_probe_fails(client, monkeypatch):
    """
    GIVEN Ephe is in LAN mode but macOS/firewall blocks the Wi-Fi address
    WHEN the QR payload is generated
    THEN the user receives an actionable network-permission warning.
    """
    monkeypatch.setenv("EPHE_HOST", "0.0.0.0")
    with patch("server.routes.mobile.get_local_ip", return_value="192.168.1.50"), \
         patch("server.routes.mobile.tunnel_manager") as mock_tunnel, \
         patch("server.routes.mobile._lan_probe_succeeds", return_value=False):

        response = client.get("/api/mobile/qr?mode=lan")
        assert response.status_code == 200
        data = response.json()

        assert data["lan_reachable"] is False
        assert "macOS Firewall" in data["message"]
        assert "Local Network" in data["message"]
        mock_tunnel.start_tunnel.assert_not_called()


def test_mobile_qr_auto_mode_uses_public_tunnel_when_lan_probe_fails(client, monkeypatch):
    """
    GIVEN LAN mode is bound but the Wi-Fi address does not answer (macOS firewall)
    WHEN internet is available
    THEN auto falls back to the outgoing public tunnel so the scan still works without the
    user touching firewall settings (outgoing-only model).
    """
    monkeypatch.setenv("EPHE_HOST", "0.0.0.0")
    with patch("server.routes.mobile.get_local_ip", return_value="192.168.1.50"), \
         patch("server.routes.mobile._lan_probe_succeeds", return_value=False), \
         patch("server.routes.mobile._start_public_tunnel", return_value="https://ephe.example.test") as start:

        response = client.get("/api/mobile/qr")
        assert response.status_code == 200
        data = response.json()

        assert data["url"] == "https://ephe.example.test/mobile.html"
        assert data["mode"] == "public"
        assert data["lan_reachable"] is True
        assert data["is_public"] is True
        start.assert_called_once()


def test_mobile_qr_auto_mode_uses_public_tunnel_in_docker_without_mobile_host(client, monkeypatch):
    """
    GIVEN Ephe runs in Docker without a configured phone-reachable host IP
    WHEN the QR payload is generated in auto mode
    THEN it stays LAN-first and warns that Docker needs an explicit phone-reachable host or public mode.
    """
    monkeypatch.setenv("EPHE_DOCKER", "1")
    monkeypatch.delenv("EPHE_MOBILE_HOST", raising=False)
    with patch("server.routes.mobile.get_local_ip", return_value="172.19.0.3"), \
         patch("server.routes.mobile.tunnel_manager") as mock_tunnel:

        mock_tunnel.public_url = "https://ephe.example.test"
        mock_tunnel.start_tunnel.return_value = None

        response = client.get("/api/mobile/qr")
        assert response.status_code == 200
        data = response.json()

        assert data["url"] == "http://172.19.0.3:8765/mobile.html"
        assert data["mode"] == "lan"
        assert data["is_public"] is False
        assert data["lan_reachable"] is False
        assert "choose public QR mode explicitly" in data["message"]
        mock_tunnel.start_tunnel.assert_not_called()


def test_mobile_qr_lan_mode_uses_configured_mobile_host_in_docker(client, monkeypatch):
    """
    GIVEN Docker is configured with the Mac Wi-Fi IP for mobile pairing
    WHEN the QR payload is generated in LAN mode
    THEN the QR uses that phone-reachable host instead of the Docker bridge IP.
    """
    monkeypatch.setenv("EPHE_DOCKER", "1")
    monkeypatch.setenv("EPHE_MOBILE_HOST", "192.168.1.50")
    with patch("server.routes.mobile.get_local_ip", return_value="172.19.0.3"), \
         patch("server.routes.mobile.tunnel_manager") as mock_tunnel, \
         patch("server.routes.mobile._lan_probe_succeeds", return_value=True):

        response = client.get("/api/mobile/qr?mode=lan")
        assert response.status_code == 200
        data = response.json()

        assert data["url"] == "http://192.168.1.50:8765/mobile.html"
        assert data["mode"] == "lan"
        assert data["lan_reachable"] is True
        assert "172.19.0.3" not in data["url"]
        mock_tunnel.start_tunnel.assert_not_called()

# EPHE_MOBILE_HOST is configuration a user writes by hand, and one of its forms
# reaches urllib.request.urlopen inside _lan_probe_succeeds. A host that names
# another protocol is therefore not a typo to be passed along.

@pytest.mark.parametrize(
    "value", ["ftp://192.168.1.10:8765", "gopher://x:1", "file:///etc/passwd"],
)
def test_mobile_host_of_another_protocol_is_refused(monkeypatch, value):
    """Given EPHE_MOBILE_HOST names a non-HTTP protocol, when the base URL is built,
    then it answers None so no probe leaves the HTTP family."""
    from server.routes import mobile

    monkeypatch.setenv("EPHE_MOBILE_HOST", value)
    assert mobile._configured_mobile_base_url(8765) is None


def test_mobile_host_without_an_authority_is_refused_too(monkeypatch):
    """Given a scheme with nothing after the slashes, when the base URL is built,
    then the answer is None rather than a URL that only looks like http."""
    from server.routes import mobile

    monkeypatch.setenv("EPHE_MOBILE_HOST", "http://")
    assert mobile._configured_mobile_base_url(8765) is None


@pytest.mark.parametrize(
    "value", ["data:text/html,x", "javascript:alert(1)", "mailto:someone@example.com"],
)
def test_mobile_host_with_a_bare_scheme_colon_is_refused(monkeypatch, value):
    """Given a scheme written without its slashes, when the base URL is built,
    then the answer is None instead of an http:// URL around that text."""
    from server.routes import mobile

    monkeypatch.setenv("EPHE_MOBILE_HOST", value)
    assert mobile._configured_mobile_base_url(8765) is None


@pytest.mark.parametrize(
    "value,expected",
    [
        ("192.168.1.10:9000", "http://192.168.1.10:9000"),
        ("[fe80::1]:9000", "http://[fe80::1]:9000"),
        ("[fe80::1]", "http://[fe80::1]:8765"),
    ],
)
def test_mobile_host_with_its_own_port_keeps_it(monkeypatch, value, expected):
    """Given a host that already names a port, when the base URL is built, then
    the route's default port is not appended a second time."""
    from server.routes import mobile

    monkeypatch.setenv("EPHE_MOBILE_HOST", value)
    assert mobile._configured_mobile_base_url(8765) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("http://192.168.1.10:8765", "http://192.168.1.10:8765"),
        ("https://ephe.example", "https://ephe.example"),
        ("https://ephe.example:8765/", "https://ephe.example:8765"),
        ("192.168.1.10", "http://192.168.1.10:8765"),
    ],
)
def test_mobile_host_in_the_http_family_still_answers(monkeypatch, value, expected):
    """Given a host a user means literally, when the base URL is built, then the
    address is handed back unchanged apart from the scheme and port it lacks."""
    from server.routes import mobile

    monkeypatch.setenv("EPHE_MOBILE_HOST", value)
    assert mobile._configured_mobile_base_url(8765) == expected
