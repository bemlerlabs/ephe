"""`Authorization: Bearer <token>` is the same credential as `X-Auth-Token`.

Issue #201. `ephe serve` is documented as the OpenAI-compatible engine for other coding
CLIs (`docs/CLI.md`), but with `--token` it read one header only
(`server/openai.py:463-465`), and most such clients can set a base URL and an API key and
nothing else — the key travels as `Authorization: Bearer <key>`. They got 401 and could
not connect. The PWA server has the same gap in `server/middleware.py`.

Both spellings are the same credential on both surfaces; a wrong or missing one stays the
coded 401. `X-Auth-Token` keeps working, because the QR link, the PWA and the desktop
send it (`app/src/lib/api/http.ts`).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from fastapi.testclient import TestClient

from server.openai import create_openai_app

TOKEN = "supersecret"


@pytest.fixture
def serve_client():
    """`create_openai_app(api_token=TOKEN)` with a provider that lists no model."""
    with patch(
        "server.openai.get_active_provider",
        lambda: SimpleNamespace(model="", provider="local_ollama", base_url=""),
    ), patch("server.openai.TIER_MAP", {}):
        with TestClient(create_openai_app(api_token=TOKEN)) as client:
            yield client


class TestTheOpenAISurface:

    def test_bearer_is_accepted_where_the_header_was(self, serve_client):
        """GIVEN `ephe serve --token` WHEN /v1/models carries `Authorization: Bearer`
        THEN 200 — the `OpenAI(base_url=…, api_key=…)` client can connect."""
        response = serve_client.get(
            "/v1/models", headers={"Authorization": f"Bearer {TOKEN}"}
        )

        assert response.status_code == 200, response.text
        assert response.json()["object"] == "list"

    def test_the_product_header_still_works(self, serve_client):
        """GIVEN the same server WHEN the token rides X-Auth-Token
        THEN 200 — the spelling this product already documented is untouched."""
        response = serve_client.get("/v1/models", headers={"X-Auth-Token": TOKEN})

        assert response.status_code == 200, response.text

    def test_the_scheme_is_case_insensitive(self, serve_client):
        """GIVEN a client that writes `bearer` WHEN /v1/models is asked
        THEN 200 — RFC 9110 makes the scheme case-insensitive."""
        response = serve_client.get(
            "/v1/models", headers={"Authorization": f"bearer {TOKEN}"}
        )

        assert response.status_code == 200, response.text

    @pytest.mark.parametrize(
        "authorization",
        ["Bearer wrong-value", "Basic dXNlcjpwYXNz", "Bearer ", TOKEN],
        ids=["wrong-token", "other-scheme", "empty-bearer", "bare-token"],
    )
    def test_a_bad_credential_stays_a_coded_401(self, serve_client, authorization):
        """GIVEN a value that is not the token WHEN /v1/models is asked
        THEN 401 `auth_error` — the alias does not loosen the gate."""
        response = serve_client.get(
            "/v1/models", headers={"Authorization": authorization}
        )

        assert response.status_code == 401, response.text
        assert response.json()["error"]["code"] == "auth_error", response.json()

    def test_a_missing_credential_stays_a_coded_401(self, serve_client):
        """GIVEN no credential at all WHEN /v1/models is asked THEN 401 `auth_error`."""
        response = serve_client.get("/v1/models")

        assert response.status_code == 401, response.text
        assert response.json()["error"]["code"] == "auth_error", response.json()

    def test_the_completion_route_reads_the_bearer_too(self, serve_client):
        """GIVEN a bearer credential WHEN a body reaches the parser
        THEN it is past auth and answers the parse refusal — no 401 on the useful route."""
        response = serve_client.post(
            "/v1/chat/completions",
            json={"model": "test"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

        assert response.status_code == 400, response.text
        assert response.json()["error"]["code"] == "validation_error", response.json()


class TestThePwaServerInLanMode:
    """`--lan` on the PWA server accepts the same two spellings."""

    LAN_TOKEN = "lan-token-for-the-bearer-alias"

    @pytest.fixture
    def lan_app(self, tmp_path, monkeypatch):
        from server import middleware
        from server.main import create_app

        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
        monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
        app = create_app(lan_mode=True)
        middleware.LAN_AUTH_TOKEN = self.LAN_TOKEN
        try:
            yield app
        finally:
            middleware.init_auth(lan_mode=False)

    @staticmethod
    def _get(app, headers: dict[str, str] | None = None):
        async def run():
            transport = httpx.ASGITransport(app=app, client=("192.168.1.50", 50001))
            async with httpx.AsyncClient(
                transport=transport, base_url="http://ephe.invalid:8765"
            ) as client:
                return await client.get("/api/profile", headers=headers or {})

        return asyncio.run(run())

    def test_bearer_opens_a_token_gated_api_route(self, lan_app):
        """GIVEN `--lan` WHEN a LAN client sends the token as a bearer credential
        THEN /api/profile answers 200."""
        response = self._get(lan_app, {"Authorization": f"Bearer {self.LAN_TOKEN}"})

        assert response.status_code == 200, response.text

    def test_the_token_header_keeps_working(self, lan_app):
        """GIVEN the same server WHEN the token rides X-Auth-Token THEN 200."""
        response = self._get(lan_app, {"X-Auth-Token": self.LAN_TOKEN})

        assert response.status_code == 200, response.text

    def test_a_wrong_bearer_is_the_coded_401(self, lan_app):
        """GIVEN a wrong bearer value WHEN the route is asked
        THEN 401 `auth_error` with the LAN refusal, not a 500."""
        response = self._get(lan_app, {"Authorization": "Bearer wrong-value"})

        assert response.status_code == 401, response.text
        assert response.json()["error"]["code"] == "auth_error", response.json()

    def test_no_credential_is_still_a_coded_401(self, lan_app):
        """GIVEN no credential WHEN the route is asked THEN 401 `auth_error`."""
        response = self._get(lan_app)

        assert response.status_code == 401, response.text
        assert response.json()["error"]["code"] == "auth_error", response.json()
