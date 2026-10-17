"""Wave I1-4: /api/proxy keeps what its docstring promises — reach and volume.

The docstring promised a "fixed port range" while the code read 1..65535: that
makes every loopback service on the machine a read channel for the model — the
Docker API on 2375, redis on 6379, our own engine on 11434, privileged rpcbind
on 111. On top of that `body=resp.text` without any cap: a dev server (or an
answer built to be large) delivers 500 MB into the JSON of a single response.

Given / When / Then — tests first, then the code.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from server.main import create_app


@pytest.fixture
def client():
    return TestClient(create_app())


# Reach: which ports the preview proxy may touch


class TestProxyPortScope:
    @pytest.mark.parametrize("port", ["5173", "3000", "8080", "4200", "5000", "1024"])
    def test_dev_server_ports_are_reachable(self, port):
        """The purpose of the proxy stays untouched: dev servers on high ports."""
        from server.routes import proxy

        assert proxy._validate_port(port) == int(port)

    @pytest.mark.parametrize("port", ["abc", "0", "70000", "-1"])
    def test_nonsense_stays_rejected(self, port):
        from server.routes import proxy

        with pytest.raises(HTTPException) as err:
            proxy._validate_port(port)
        assert err.value.status_code == 400

    @pytest.mark.parametrize("port", ["22", "111", "445", "631", "1023"])
    def test_privileged_ports_are_refused(self, port):
        """Below 1024 sit services nobody opens as a preview — ssh, rpcbind, SMB."""
        from server.routes import proxy

        with pytest.raises(HTTPException) as err:
            proxy._validate_port(port)
        assert err.value.status_code == 400

    @pytest.mark.parametrize(
        "port,service",
        [
            ("2375", "docker"),
            ("5432", "postgres"),
            ("6379", "redis"),
            ("11434", "ollama"),
            ("11211", "memcached"),
            ("9200", "elasticsearch"),
        ],
    )
    def test_local_service_ports_are_refused(self, port, service):
        """A local service is not a dev server: its API would be a data channel."""
        from server.routes import proxy

        with pytest.raises(HTTPException) as err:
            proxy._validate_port(port)
        assert err.value.status_code == 400
        assert service in str(err.value.detail).lower(), "die Absage muss nennen, was sie schuetzt"

    def test_the_refusal_names_the_opt_out(self):
        """A wall without an action hint is helplessness — the user may widen it."""
        from server.routes import proxy

        with pytest.raises(HTTPException) as err:
            proxy._validate_port("6379")
        assert "EPHE_PROXY_PORTS" in str(err.value.detail)

    def test_the_env_opt_out_widens_without_weakening_the_default(self, monkeypatch):
        """EPHE_PROXY_PORTS is an explicit widening, not a default that loosens."""
        from server.routes import proxy

        monkeypatch.setenv("EPHE_PROXY_PORTS", "6379, 11434")
        assert proxy._validate_port("6379") == 6379
        assert proxy._validate_port("11434") == 11434
        with pytest.raises(HTTPException):
            proxy._validate_port("2375")
        with pytest.raises(HTTPException):
            proxy._validate_port("22")

    def test_ws_tunnel_shares_the_same_wall(self):
        """The HMR tunnel is the same line: without this check it would be the exit."""
        import inspect

        from server.routes import proxy

        source = inspect.getsource(proxy.proxy_ws)
        assert "_validate_port" in source

    def test_route_refuses_a_service_port_before_any_request(self, client):
        r = client.get("/api/proxy/6379/INFO")
        assert r.status_code == 400


# Volume: the answer is a panel body, not a stream


class TestProxyBodyCap:
    @pytest.fixture
    def huge_http(self, monkeypatch):
        import httpx

        class _Resp:
            status_code = 200

            def __init__(self, payload: bytes):
                self._payload = payload

            @property
            def content(self) -> bytes:
                return self._payload

            @property
            def text(self) -> str:
                # The old path: unlimited, decoded, gullible.
                return self._payload.decode()

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get(self, url):
                return _Resp(b"<html>" + b"A" * (6 * 1024 * 1024) + b"</html>")

        monkeypatch.setattr(httpx, "AsyncClient", _Client)

    def test_body_is_capped_and_the_cut_is_spoken(self, client, huge_http):
        from core.net_guard import MAX_DOWNLOAD_BYTES
        from server.routes import proxy

        r = client.get("/api/proxy/5173/index.html")
        assert r.status_code == 200
        body = r.json()["body"]
        assert len(body.encode()) <= MAX_DOWNLOAD_BYTES + proxy.PROXY_CAP_MARKER_BYTES
        assert "nicht uebergeben" in body, "eine stille Kappung ist die alte Falschaussage"

    def test_cap_comes_from_net_guard_not_from_a_second_number(self):
        """Two numbers for one cap drifted apart — the proxy uses the one from fetch_url."""
        from core import net_guard
        from server.routes import proxy

        assert proxy.PROXY_MAX_BODY_BYTES == net_guard.MAX_DOWNLOAD_BYTES

    def test_small_body_claims_no_cap(self, client, monkeypatch):
        import httpx

        class _Resp:
            status_code = 200
            content = b"<html>klein</html>"

            @property
            def text(self):
                return self.content.decode()

        class _Client:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def get(self, url):
                return _Resp()

        monkeypatch.setattr(httpx, "AsyncClient", _Client)
        r = client.get("/api/proxy/5173/index.html")
        assert r.json()["body"] == "<html>klein</html>"
        assert "nicht uebergeben" not in r.json()["body"]
        assert "PROXY_MAX_BODY_BYTES" not in r.json()["body"]

    def test_the_docstring_no_longer_promises_what_the_code_did_not_do(self):
        """Docstring and code are a contract — after this wave it holds again."""
        from server.routes import proxy

        doc = proxy.__doc__ or ""
        assert "1024" in doc, "die Reichweite steht jetzt in der Zahl, nicht im Adjektiv"
        assert "2375" in doc or "Datenbank" in doc
