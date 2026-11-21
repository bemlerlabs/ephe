import pytest
from unittest.mock import patch
from utils.network import get_local_ip
from utils.tunnel import _extract_public_tunnel_url

def test_get_local_ip_success():
    class MockSocket:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def settimeout(self, timeout):
            pass
        def connect(self, addr):
            pass
        def getsockname(self):
            return ("10.0.0.5", 12345)

    with patch("socket.socket", return_value=MockSocket()):
        ip = get_local_ip()
        assert ip == "10.0.0.5"

def test_get_local_ip_fallback():
    class ExtMockSocket:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
        def settimeout(self, timeout):
            pass
        def connect(self, addr):
            raise Exception("Network Unreachable")
        def getsockname(self):
            return ("10.0.0.5", 12345)

    with patch("socket.socket", return_value=ExtMockSocket()):
        ip = get_local_ip()
        assert ip == "127.0.0.1"


def test_tunnel_url_parser_ignores_localhost_run_admin_url():
    assert _extract_public_tunnel_url("dashboard: https://admin.localhost.run") is None


def test_tunnel_url_parser_accepts_real_public_urls():
    assert _extract_public_tunnel_url("url: https://abc123.lhr.life") == "https://abc123.lhr.life"
    assert _extract_public_tunnel_url("url: https://ephe-42.localhost.run") == "https://ephe-42.localhost.run"
