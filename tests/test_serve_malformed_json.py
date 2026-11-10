"""A malformed body on the OpenAI surface is a 400, not a 500 with the decoder's text.

Issue #199. Measured on `16320b7` (`ephe serve --token testtoken`): a body of
`{not json` or `text/plain: hello` on `POST /v1/chat/completions` answered
`500 {"error":{"code":"internal_error"}}` carrying the `json` decoder's own sentence,
because `_parse_body` awaited `request.json()` and only validated the decoded type.
OpenAI-compatible clients read 5xx as a server fault and retry, so a local typo looked
like a broken engine.

The surface already answers bad input with `400 validation_error`; these cases pin that
the malformed body joins it, that no exception text travels, and that the neighbouring
routes (`/v1/models`, `/api/chat`) stay off the 5xx path as well.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from server.openai import create_openai_app

TOKEN_HEADERS = {"X-Auth-Token": "testtoken"}
#: What Python's `json` module writes. None of it may reach a client.
DECODER_TEXT = ("Expecting", "line 1 column", "JSONDecodeError", "UnicodeDecodeError")


@pytest.fixture
def served_client():
    """The `ephe serve` app with a token, and a provider that never answers.

    The parse happens before any provider work, so no engine is needed: a request that
    reaches the provider has already failed this contract.
    """
    with patch(
        "server.openai.get_active_provider",
        lambda: SimpleNamespace(model="", provider="local_ollama", base_url=""),
    ):
        with TestClient(create_openai_app(api_token="testtoken")) as client:
            yield client


def _post(client, body: bytes, content_type: str = "application/json"):
    return client.post(
        "/v1/chat/completions",
        content=body,
        headers={**TOKEN_HEADERS, "content-type": content_type},
    )


class TestMalformedBody:

    @pytest.mark.parametrize(
        ("body", "content_type"),
        [
            (b"{not json", "application/json"),
            (b"hello", "text/plain"),
            (b"", "application/json"),
            (b'{"messages": [1, 2', "application/json"),
            (b"\xff\xfe\x00garbage", "application/json"),
        ],
        ids=["truncated-object", "plain-text", "empty", "unclosed-array", "not-utf8"],
    )
    def test_a_malformed_body_is_a_coded_400(self, served_client, body, content_type):
        """GIVEN `ephe serve` with a token WHEN the body is not JSON
        THEN 400 `validation_error`, no exception text, and the sentence names JSON."""
        response = _post(served_client, body, content_type)

        assert response.status_code == 400, response.text
        error = response.json()["error"]
        assert error["code"] == "validation_error", error
        assert error["request_id"], error
        assert "not valid JSON" in error["message"], error["message"]
        for leak in DECODER_TEXT:
            assert leak not in response.text, response.text

    def test_a_json_scalar_is_still_the_object_refusal(self, served_client):
        """GIVEN valid JSON that is not an object WHEN it is posted
        THEN the existing 400 sentence keeps its shape (no regression from the parse fix)."""
        response = _post(served_client, b"[]")

        assert response.status_code == 400, response.text
        error = response.json()["error"]
        assert error["code"] == "validation_error", error
        assert error["message"] == "Request body must be a JSON object", error

    def test_a_valid_body_still_reaches_the_provider(self, served_client):
        """GIVEN a well-formed body WHEN it is posted
        THEN the request passes validation and fails later at the provider."""
        with patch(
            "server.openai.build_provider_client",
            side_effect=RuntimeError("provider reached"),
        ):
            response = _post(
                served_client,
                b'{"model": "test", "messages": [{"role": "user", "content": "hi"}]}',
            )

        assert response.status_code == 500, response.text
        assert "provider reached" in response.text


class TestTheNeighbouringRoutes:
    """The issue asks for the same check on the routes beside the completion."""

    def test_models_ignores_a_body_it_does_not_read(self, served_client):
        """GIVEN a GET that carries junk WHEN /v1/models answers
        THEN 200 — a GET has no body contract and must not answer 5xx."""
        response = served_client.request(
            "GET",
            "/v1/models",
            content=b"{not json",
            headers={**TOKEN_HEADERS, "content-type": "application/json"},
        )

        assert response.status_code == 200, response.text

    def test_api_chat_answers_a_malformed_body_without_leaking(self, tmp_path, monkeypatch):
        """GIVEN the PWA server WHEN POST /api/chat gets `{not json`
        THEN a 4xx envelope and no decoder text — the route never reaches 5xx."""
        monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
        monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
        monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
        from server.main import create_app

        with TestClient(create_app()) as client:
            response = client.post(
                "/api/chat",
                content=b"{not json",
                headers={"content-type": "application/json"},
            )

        assert 400 <= response.status_code < 500, response.text
        assert "internal_error" not in response.text, response.text
        for leak in DECODER_TEXT:
            assert leak not in response.text, response.text
