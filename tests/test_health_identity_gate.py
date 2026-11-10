"""On `--lan`, the host identity in `/api/health` is behind the token.

Issue #196. Measured on `16320b7`: `ephe start --lan` binds `0.0.0.0`, and
`GET /api/health` was exempt from the token — it answered the absolute checkout path,
the pid, the git sha and the instance id to anyone on the network, while
`/api/sessions` answered 401. The answer now follows the caller:

- a caller that presents the LAN token (either accepted spelling) gets the full answer;
- the desktop on the machine — loopback peer *and* loopback `Host`, the same trust
  `tests/test_tunnel_loopback_auth.py` pins for `/api/chat` — gets it without a token,
  because `app/src-tauri/src/backend.rs` `statement()` reads `pid`/`root`/`instance_id`
  off this body to recognise the backend it started;
- every other caller gets liveness only: `status`, `version`, `api_contract`.

The projection holds for the degraded answer too (`tests/test_health_engine_env_state.py`),
so a half-written engine environment cannot leak the identity either.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from core.model_provider import ModelProviderConfig

#: A peer on the LAN: not loopback, so `AuthMiddleware` is the gate.
REMOTE_PEER = ("192.168.1.50", 50001)
MINIMAL_KEYS = {"status", "version", "api_contract"}
IDENTITY_FIELDS = ("root", "pid", "git_sha", "instance_id")
LAN_TOKEN = "lan-token-for-the-identity-gate"


def _get(app, *, headers: dict[str, str] | None = None, loopback: bool = False):
    """One GET /api/health from the given peer, driven through the real middleware stack."""
    peer = ("127.0.0.1", 50002) if loopback else REMOTE_PEER
    base = "http://127.0.0.1:8765" if loopback else "http://ephe.invalid:8765"

    async def run():
        transport = httpx.ASGITransport(app=app, client=peer)
        async with httpx.AsyncClient(transport=transport, base_url=base) as client:
            return await client.get("/api/health", headers=headers or {})

    return asyncio.run(run())


@pytest.fixture
def engine(monkeypatch):
    """A reachable OpenAI-compatible engine, so no test dials this machine's Ollama."""
    provider = ModelProviderConfig(
        provider="openai_compatible",
        model="identity-test-model",
        base_url="http://engine.invalid:8888/v1",
        label="Identity test engine",
        offline_capable=False,
        requires_internet=True,
    )
    monkeypatch.setattr("server.routes.health.get_active_provider", lambda: provider)
    monkeypatch.setattr(
        "server.routes.health._quick_engine_status",
        AsyncMock(return_value=(True, "engine reachable", ["identity-test-model"], "ok", False)),
    )
    return provider


@pytest.fixture
def lan_app(tmp_path, monkeypatch, engine):
    """The PWA server in `--lan` shape: auth and rate limit installed, a known token."""
    from server import middleware
    from server.main import create_app

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    monkeypatch.delenv("EPHE_SETUP_MODE", raising=False)
    app = create_app(lan_mode=True)
    middleware.LAN_AUTH_TOKEN = LAN_TOKEN
    try:
        yield app
    finally:
        middleware.init_auth(lan_mode=False)


class TestLanHealthWithoutAToken:
    """The stranger on the network sees that the server is alive, nothing more."""

    def test_a_remote_caller_gets_liveness_only(self, lan_app):
        """GIVEN `--lan` WHEN a LAN peer asks /api/health without a token
        THEN 200 with exactly `status`, `version`, `api_contract`."""
        response = _get(lan_app)

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == MINIMAL_KEYS, body
        assert body["status"] in {"ok", "degraded"}, body
        assert body["version"], body
        assert body["api_contract"] > 0, body

    @pytest.mark.parametrize("field", IDENTITY_FIELDS)
    def test_the_identifying_fields_are_absent(self, lan_app, field):
        """GIVEN the same request WHEN the body is read
        THEN the checkout path, the pid, the commit and the instance id stay home."""
        body = _get(lan_app).json()

        assert field not in body, body

    def test_a_wrong_token_is_no_token(self, lan_app):
        """GIVEN `--lan` WHEN a LAN peer presents the wrong bearer value
        THEN the answer is the minimal form, not the full one."""
        response = _get(lan_app, headers={"Authorization": "Bearer not-the-token"})

        assert response.status_code == 200, response.text
        assert set(response.json()) == MINIMAL_KEYS, response.json()

    def test_the_degraded_answer_is_projected_too(self, lan_app, monkeypatch):
        """GIVEN `--lan` and a half-written engine env WHEN a LAN peer asks without a token
        THEN the state travels (200, `degraded`) and the identity still does not."""
        from core.engine_config import EngineNotConfigured

        def _break():
            raise EngineNotConfigured(
                "EPHE_MODEL_PROVIDER=openai_compatible is set, but "
                "EPHE_OPENAI_COMPAT_MODEL is missing.",
                hint="set EPHE_OPENAI_COMPAT_MODEL",
            )

        monkeypatch.setattr("server.routes.health.get_active_provider", _break)

        response = _get(lan_app)

        assert response.status_code == 200, response.text
        body = response.json()
        assert set(body) == MINIMAL_KEYS, body
        assert body["status"] == "degraded", body


class TestLanHealthWithTheToken:
    """Whoever holds the token is the operator: the full statement is theirs."""

    def test_the_token_header_opens_the_full_answer(self, lan_app):
        """GIVEN `--lan` WHEN a LAN peer sends the LAN token in X-Auth-Token
        THEN 200 with the identity the desktop reads."""
        response = _get(lan_app, headers={"X-Auth-Token": LAN_TOKEN})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["instance_id"], body
        assert body["pid"] > 0, body
        assert body["root"], body
        assert "git_sha" in body, body
        assert body["api_contract"] > 0, body

    def test_the_bearer_form_opens_the_full_answer(self, lan_app):
        """GIVEN `--lan` WHEN a LAN peer sends the token as `Authorization: Bearer`
        THEN the same full answer — an OpenAI client can read the statement (#201)."""
        response = _get(lan_app, headers={"Authorization": f"Bearer {LAN_TOKEN}"})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["instance_id"], body
        assert body["pid"] > 0, body


class TestTheDesktopKeepsItsStatement:
    """The loopback caller is the app on this machine — it never carried a token."""

    def test_loopback_gets_the_full_answer_without_a_token(self, lan_app):
        """GIVEN `--lan` WHEN the desktop on 127.0.0.1 asks /api/health
        THEN the full answer, token or not."""
        response = _get(lan_app, loopback=True)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["instance_id"], body
        assert body["pid"] > 0, body
        assert body["root"], body

    def test_a_server_without_lan_mode_answers_the_full_shape(self, tmp_path, monkeypatch, engine):
        """GIVEN a tokenless (desktop) server WHEN the app asks /api/health
        THEN the identity is there — the gate only exists where the token does."""
        from server import middleware
        from server.main import create_app

        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
        monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
        monkeypatch.setattr(middleware, "LAN_AUTH_TOKEN", None)
        app = create_app()

        body = _get(app, loopback=True).json()

        assert body["instance_id"], body
        assert body["pid"] > 0, body
