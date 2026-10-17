import pytest
import re
from fastapi.testclient import TestClient
from server.main import create_app
from unittest.mock import patch, PropertyMock

@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)

def test_mobile_qr_payload_format(client):
    with patch("server.routes.mobile.get_local_ip", return_value="10.0.0.99"), \
         patch("server.routes.mobile.tunnel_manager") as mock_tunnel:
        # Simulate no tunnel available → fallback to local IP
        mock_tunnel.public_url = None
        mock_tunnel.start_tunnel = lambda port: None

        response = client.get("/api/mobile/qr")
        assert response.status_code == 200
        data = response.json()

        target_url = data["url"]
        qr_base64 = data["qr_base64"]

        # Test URL format – now points to /mobile.html
        assert target_url.endswith("/mobile.html"), f"URL should end with /mobile.html, got: {target_url}"

        # Should be local IP since tunnel is mocked as unavailable
        assert target_url in ("http://10.0.0.99:80/mobile.html", "http://10.0.0.99:8765/mobile.html")

        # Verify base64 starts as a valid PNG payload
        assert len(qr_base64) > 100
        assert qr_base64.startswith("iVBORw0K")  # PNG base64 header


def test_mobile_qr_tunnel_crash_falls_back_not_500(client):
    # Regression (first-user QA 2026-09-04): the ssh/localhost.run tunnel raises
    # "[Errno 32] Broken pipe" → /api/mobile/qr must NOT answer 500, it falls back
    # to the LAN URL + a user hint (the first user sees QR + explanation, no crash).
    def _boom(port):
        raise OSError(32, "Broken pipe")

    with patch("server.routes.mobile.get_local_ip", return_value="10.0.0.99"), \
         patch("server.routes.mobile.tunnel_manager") as mock_tunnel:
        mock_tunnel.public_url = None
        mock_tunnel.start_tunnel = _boom
        response = client.get("/api/mobile/qr")
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["url"].endswith("/mobile.html")
        assert data["message"], "Erwartet Nutzer-Hinweis statt Silent-Crash"

