"""
Ephe — one error classifier for every surface (serve, chat, cli)
tests/test_provider_error_surfaces.py

core/provider_errors.py owns the failure table; every surface reads it instead of
carrying a private substring list:

  - the served app maps an HTTP status to a code through the table (401 auth,
    404/405 not_found, else validation) and stamps kind/retryable onto an SSE
    stream-error frame
  - the chat loop raises its transport/model-missing exceptions from the same
    table (a drop the old private substring list missed now reads as unreachable)
  - the CLI reports the stable code and exit code from the table

Runs offline: no Ollama, no network, the provider is scripted.
"""
from __future__ import annotations

import argparse
import json

import pytest
from fastapi.testclient import TestClient

from core import provider_errors
from core._cli_common import _emit_error
from core.chat_stream import (
    OllamaModelNotFoundError,
    OllamaNotReachableError,
    RetryPolicy,
    stream_response,
)
from core.model_provider import ProviderSetupError
from core.observability import ErrorCode
from server.openai import create_openai_app

BODY = {"model": "mine:work", "messages": [{"role": "user", "content": "hi"}]}
CHAT_URL = "/v1/chat/completions"
NO_WAIT = RetryPolicy(max_attempts=1, base_delay=0.0)


# the one table: every surface projects the same failure the same way


@pytest.mark.parametrize(
    "error, code, status, exit_code",
    [
        (ConnectionError("connection refused"), ErrorCode.UPSTREAM, 502, 1),
        (RuntimeError("HTTP 429 Too Many Requests"), ErrorCode.UPSTREAM, 429, 1),
        (RuntimeError("HTTP 401 unauthorized"), ErrorCode.AUTH, 401, 1),
        (ProviderSetupError("opt-in provider incomplete"), ErrorCode.VALIDATION, 400, 2),
        (RuntimeError("boom"), ErrorCode.INTERNAL, 500, 1),
    ],
)
def test_every_surface_reads_one_table(error, code, status, exit_code):
    assert provider_errors.error_code_for(error) is code
    assert provider_errors.http_status_for(error) == status
    assert provider_errors.exit_code_for(error) == exit_code


@pytest.mark.parametrize(
    "status, code",
    [
        (400, ErrorCode.VALIDATION),
        (401, ErrorCode.AUTH),
        (403, ErrorCode.AUTH),
        (404, ErrorCode.NOT_FOUND),
        (405, ErrorCode.NOT_FOUND),
        (409, ErrorCode.VALIDATION),
        (500, ErrorCode.VALIDATION),
    ],
)
def test_serve_status_codes_come_from_the_table(status, code):
    assert provider_errors.status_error_code(status) is code


# serve


def test_unknown_route_reads_the_not_found_code():
    with TestClient(create_openai_app()) as client:
        resp = client.get("/v1/nope")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == ErrorCode.NOT_FOUND.value


def test_missing_auth_reads_the_auth_code():
    with TestClient(create_openai_app(api_token="secret")) as client:
        resp = client.get("/v1/models")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == ErrorCode.AUTH.value


class _ScriptedClient:
    """Provider stand-in whose chat() raises on every attempt."""

    def __init__(self, message):
        self._message = message
        self.calls = 0

    def chat(self, model, messages, stream):
        self.calls += 1

        async def _gen():
            raise RuntimeError(self._message)
            yield  # make it a generator

        return _gen()


def _install(monkeypatch, client):
    monkeypatch.setattr("server.openai.build_provider_client", lambda *a, **k: client)


def test_stream_error_frame_carries_the_classified_kind(monkeypatch):
    _install(monkeypatch, _ScriptedClient("HTTP 429 Too Many Requests"))
    app = create_openai_app()
    app.state.retry_policy = NO_WAIT
    with TestClient(app) as client:
        resp = client.post(CHAT_URL, json={**BODY, "stream": True})
    assert resp.status_code == 200
    frame = next(
        json.loads(line[len("data: "):])
        for line in resp.text.splitlines()
        if line.startswith("data: ") and '"error"' in line
    )
    error = frame["error"]
    assert error["code"] == ErrorCode.STREAM.value
    assert error["kind"] == "rate_limit"
    assert error["retryable"] is True


# chat


def _raising_client(exc):
    from unittest.mock import AsyncMock, patch

    patcher = patch("core.chat.ollama.AsyncClient")
    mock_class = patcher.start()
    instance = AsyncMock()
    instance.chat.side_effect = exc
    mock_class.return_value = instance
    return patcher


async def test_chat_transport_drop_reads_unreachable(monkeypatch):
    patcher = _raising_client(Exception("connection reset by peer"))
    try:
        with pytest.raises(OllamaNotReachableError):
            await stream_response(model="llama3.2", history=[], on_chunk=lambda _: None)
    finally:
        patcher.stop()


async def test_chat_model_missing_reads_model_not_found(monkeypatch):
    patcher = _raising_client(Exception("the model does not exist"))
    try:
        with pytest.raises(OllamaModelNotFoundError):
            await stream_response(model="ghost:1b", history=[], on_chunk=lambda _: None)
    finally:
        patcher.stop()


# cli


def _json_error(capsys):
    return json.loads(capsys.readouterr().out)["error"]


def test_cli_reports_the_upstream_code_for_a_transport_failure(capsys):
    args = argparse.Namespace(json=True)
    _emit_error(args, 1, "engine down", "Start the engine", error=ConnectionError("refused"))
    error = _json_error(capsys)
    assert error["code_id"] == ErrorCode.UPSTREAM.value
    assert error["code"] == 1


def test_cli_reports_the_validation_code_and_exit_for_a_setup_error(capsys):
    args = argparse.Namespace(json=True)
    _emit_error(args, 1, "no key", "Set the key", error=ProviderSetupError("incomplete"))
    error = _json_error(capsys)
    assert error["code_id"] == ErrorCode.VALIDATION.value
    assert error["code"] == 2


def test_cli_without_an_exception_keeps_the_numeric_rule(capsys):
    args = argparse.Namespace(json=True)
    _emit_error(args, 2, "bad flag", "")
    error = _json_error(capsys)
    assert error["code_id"] == ErrorCode.USAGE.value
    assert error["code"] == 2
