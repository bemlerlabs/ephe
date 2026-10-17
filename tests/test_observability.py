"""
◑ Ephe – observability tests (phase 4, item 15)
tests/test_observability.py

Verifies:
  - serve: X-Request-ID header on every response (+ body-id correlation)
  - serve: the error body carries stable error codes + request_id
  - serve: SSE stream errors emit error.code == "stream_error"
  - CLI:   the JSON error output carries a stable code_id beside the exit code

Runs offline: build_provider_client is mocked with a fake AsyncClient.
"""
from __future__ import annotations

import argparse
import json

import pytest
from fastapi.testclient import TestClient

from server.openai import create_openai_app

CHUNKS = ["Hello", " from", " the", " Black", " Forest"]


class FakeClient:
    """Stand-in for build_provider_client(): yields an AsyncIterator."""

    def chat(self, model, messages, stream):  # noqa: ARG002
        async def _gen():
            for chunk in CHUNKS:
                yield {"message": {"content": chunk}}

        return _gen()


class BreakingClient:
    """A chat that aborts with a RuntimeError after the first chunk (stream error)."""

    def chat(self, model, messages, stream):  # noqa: ARG002
        async def _gen():
            yield {"message": {"content": "teil"}}
            raise RuntimeError("upstream kaputt")

        return _gen()


@pytest.fixture
def fake_provider(monkeypatch):
    monkeypatch.setattr("server.openai.build_provider_client", lambda *a, **k: FakeClient())


@pytest.fixture
def breaking_provider(monkeypatch):
    monkeypatch.setattr("server.openai.build_provider_client", lambda *a, **k: BreakingClient())


# X-Request-ID Header


def test_models_response_has_request_id_header(fake_provider):
    with TestClient(create_openai_app()) as client:
        resp = client.get("/v1/models")
    assert resp.status_code == 200
    rid = resp.headers.get("x-request-id")
    assert rid and rid.startswith("chatcmpl-")


def test_chat_response_has_request_id_header_correlated_with_body(fake_provider):
    with TestClient(create_openai_app()) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={"model": "gemma4:12b", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 200
    rid = resp.headers.get("x-request-id")
    assert rid
    body_id = resp.json()["id"]
    assert body_id == rid  # the header and the body correlate


# Stable error codes


def test_validation_error_has_stable_code_and_request_id(fake_provider):
    with TestClient(create_openai_app()) as client:
        resp = client.post("/v1/chat/completions", json={"model": "gemma4:12b"})
    assert resp.status_code == 400
    body = resp.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["request_id"]
    assert resp.headers.get("x-request-id") == body["error"]["request_id"]


def test_auth_error_has_stable_code():
    with TestClient(create_openai_app(api_token="supersecret")) as client:
        resp = client.get("/v1/models")  # without X-Auth-Token
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "auth_error"
    assert body["error"]["request_id"]


def test_stream_error_emits_stable_code(breaking_provider):
    with TestClient(create_openai_app()) as client:
        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "gemma4:12b",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        ) as resp:
            assert resp.status_code == 200
            body = resp.read().decode()
    # first data chunk + error chunk (no [DONE], because the stream aborts)
    events = [e for e in body.split("\n\n") if e]
    data_lines = [e for e in events if e.startswith("data:")]
    err_payload = json.loads(data_lines[-1][len("data: ") :])
    assert err_payload["error"]["code"] == "stream_error"
    assert "upstream kaputt" in err_payload["error"]["message"]


def test_serve_stream_error_id_matches_header_and_log(breaking_provider, caplog):
    """WH-50: the serve SSE error envelope, its header and its log line share one id."""
    import logging

    caplog.set_level(logging.ERROR, logger="ephe.net")
    with TestClient(create_openai_app()) as client:
        with client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "gemma4:12b",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": True,
            },
        ) as resp:
            rid = resp.headers.get("x-request-id")
            body = resp.read().decode()
    assert rid and rid.startswith("chatcmpl-")
    data_lines = [e for e in body.split("\n\n") if e.startswith("data:")]
    err_payload = json.loads(data_lines[-1][len("data: ") :])
    assert err_payload["error"]["request_id"] == rid

    lines = [json.loads(r.getMessage()) for r in caplog.records if r.name == "ephe.net"]
    stream_errors = [ln for ln in lines if ln.get("event") == "stream_error"]
    assert stream_errors, "no stream_error log line"
    assert stream_errors[0]["request_id"] == rid


# PWA server (server/main.py) — request ID + stable error codes


def test_pwa_server_response_has_request_id_header():
    from server.main import create_app

    with TestClient(create_app()) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    rid = resp.headers.get("x-request-id")
    assert rid and rid.startswith("api")


def test_pwa_server_echoes_incoming_request_id():
    from server.main import create_app

    with TestClient(create_app()) as client:
        resp = client.get("/api/health", headers={"X-Request-ID": "cli-abc123"})
    assert resp.status_code == 200
    assert resp.headers.get("x-request-id") == "cli-abc123"


def test_pwa_server_lan_auth_error_has_stable_code_and_request_id():
    from server.main import create_app

    with TestClient(create_app(lan_mode=True)) as client:
        resp = client.get("/api/profile")  # without X-Auth-Token (/api/health is auth-out)
    assert resp.status_code == 401
    body = resp.json()
    assert body["error"]["code"] == "auth_error"
    assert body["error"]["request_id"]
    assert resp.headers.get("x-request-id") == body["error"]["request_id"]


def test_pwa_server_http_exception_has_stable_code():
    from server.main import create_app

    with TestClient(create_app()) as client:
        resp = client.get("/api/nonexistent-route")
    assert resp.status_code == 404
    body = resp.json()
    assert "error" in body and "code" in body["error"]
    assert resp.headers.get("x-request-id")


# WH-50 · request-id propagation end to end (PWA chat stream)


def _drive_chat_stream_error(monkeypatch, *, headers: dict | None = None):
    """POST /api/chat/stream with a chat_with_tools that aborts.

    Returns (status, headers, body) — the client sees the error envelope and the
    response header off the same request.
    """
    from server.routes import chat as chat_route

    async def _boom(**_kwargs):
        raise RuntimeError("engine kaputt")

    monkeypatch.setattr(chat_route, "chat_with_tools", _boom)

    from server.main import create_app

    with TestClient(create_app()) as client:
        with client.stream(
            "POST",
            "/api/chat/stream",
            json={"message": "hi", "session_id": "s-wh50"},
            headers=headers or {},
        ) as resp:
            body = "".join(resp.iter_text())
            return resp.status_code, dict(resp.headers), body


def _error_events(body: str) -> list[dict]:
    events = [json.loads(p[len("data: "):]) for p in body.split("\n\n") if p.startswith("data: ")]
    return [e for e in events if e.get("type") == "error"]


def test_pwa_chat_stream_error_envelope_echoes_request_id(monkeypatch):
    """One id: the client-supplied X-Request-ID lands in the header and the envelope."""
    status, headers, body = _drive_chat_stream_error(
        monkeypatch, headers={"X-Request-ID": "corr-wh50-1"}
    )
    assert status == 200
    assert headers.get("x-request-id") == "corr-wh50-1"
    errors = _error_events(body)
    assert errors, f"no error frame in stream: {body!r}"
    assert errors[0]["request_id"] == "corr-wh50-1"


def test_pwa_chat_stream_generated_request_id_is_consistent(monkeypatch):
    """Without an inbound id, header and envelope still share the generated one."""
    status, headers, body = _drive_chat_stream_error(monkeypatch)
    assert status == 200
    rid = headers.get("x-request-id")
    assert rid and rid.startswith("api")
    errors = _error_events(body)
    assert errors, f"no error frame in stream: {body!r}"
    assert errors[0]["request_id"] == rid


def test_pwa_chat_stream_error_log_line_carries_request_id(monkeypatch, caplog):
    """The correlated log line carries the same id as the header and the envelope."""
    import logging

    caplog.set_level(logging.ERROR, logger="ephe.chat")
    status, headers, body = _drive_chat_stream_error(
        monkeypatch, headers={"X-Request-ID": "corr-wh50-log"}
    )
    assert status == 200
    assert headers.get("x-request-id") == "corr-wh50-log"
    assert _error_events(body)[0]["request_id"] == "corr-wh50-log"

    lines = [
        json.loads(r.getMessage()) for r in caplog.records if r.name == "ephe.chat"
    ]
    stream_errors = [ln for ln in lines if ln.get("event") == "stream_error"]
    assert stream_errors, f"no stream_error log line: {[r.getMessage() for r in caplog.records]}"
    assert stream_errors[0]["request_id"] == "corr-wh50-log"


# CLI – stable error codes


def test_cli_emit_error_json_has_code_id(capsys):
    from ephe_cli import _emit_error

    args = argparse.Namespace(json=True)
    _emit_error(args, 1, "kaputt", "fix it")
    data = json.loads(capsys.readouterr().out)
    assert data["error"]["code"] == 1
    assert data["error"]["code_id"] == "runtime_error"
    assert data["error"]["message"] == "kaputt"
    assert data["error"]["fix"] == "fix it"


def test_cli_emit_error_usage_code_id(capsys):
    from ephe_cli import _emit_error

    args = argparse.Namespace(json=True)
    _emit_error(args, 2, "bad args", "")
    data = json.loads(capsys.readouterr().out)
    assert data["error"]["code"] == 2
    assert data["error"]["code_id"] == "usage_error"
