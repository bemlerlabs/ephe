"""WG-49: drive the served engine with a real OpenAI client.

The engine ``server.openai.create_openai_app`` — what ``ephe serve`` binds — is
the surface an outside agent CLI or an OpenAI SDK attaches to. This module
starts that app under a real uvicorn server on a loopback socket and drives it
the way a third-party client does: over TCP, with the OpenAI wire shapes.

Two halves, one receipt:

1. the served app is started for real (thread + uvicorn + bound port) and hit
   with ``httpx`` over the socket, asserting the OpenAI contract a consumer
   reads: the ``/v1/models`` list, a non-stream ``chat.completion``, the SSE
   chunk stream ending in ``data: [DONE]``, the token gate and the error
   envelope, the request-id header.
2. when the real ``openai`` SDK is importable it drives the same server through
   ``OpenAI(base_url=...)`` — ``models.list``, ``chat.completions.create``
   (non-stream and stream). The leg is skipped when the SDK is absent, which is
   the shipped ``.venv`` here; the wire half runs either way.

Only the provider client is faked (an offline async generator), at the seam
``server.openai`` reads at call time. The app, routes, middleware, SSE framing
and error handling are the shipped code. No Ollama, no network.
"""
from __future__ import annotations

import json
import socket
import threading
import time
from types import SimpleNamespace

import httpx
import pytest
import uvicorn

import server.openai as openai_mod
from core.model_config import ModelConfig, ModelTier

TOKEN = "wg49-serve-token"
MODEL = "e2e-serve:fast"
CHUNKS = ("Hallo", " aus", " dem", " Schwarzwald")
FULL = "".join(CHUNKS)


class _FakeEngine:
    """Stands in for build_provider_client(): a deterministic async stream."""

    def chat(self, model, messages, stream):  # noqa: ARG002
        async def _gen():
            for piece in CHUNKS:
                yield {"message": {"content": piece}}

        return _gen()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture(scope="module")
def served_base_url():
    """The real app behind a running uvicorn server; yields its base URL.

    The provider seam is patched for the whole module so the served app answers
    offline and deterministically, then restored.
    """
    saved = (
        openai_mod.build_provider_client,
        openai_mod.get_active_provider,
        openai_mod.TIER_MAP,
    )
    openai_mod.build_provider_client = lambda *a, **k: _FakeEngine()
    openai_mod.get_active_provider = lambda: SimpleNamespace(
        model=MODEL, provider="local_ollama", base_url=""
    )
    openai_mod.TIER_MAP = {ModelTier.FAST: ModelConfig(name=MODEL, tier=ModelTier.FAST)}

    app = openai_mod.create_openai_app(api_token=TOKEN)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 15
    try:
        while True:
            try:
                httpx.get(f"{base}/v1/models", headers={"X-Auth-Token": TOKEN}, timeout=1.0)
                break
            except httpx.HTTPError:
                if time.monotonic() > deadline:
                    raise RuntimeError(f"served app never became ready on {base}")
                time.sleep(0.05)
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        (
            openai_mod.build_provider_client,
            openai_mod.get_active_provider,
            openai_mod.TIER_MAP,
        ) = saved


def _auth() -> dict[str, str]:
    return {"X-Auth-Token": TOKEN}


def test_models_list_matches_the_openai_model_list_shape(served_base_url):
    resp = httpx.get(f"{served_base_url}/v1/models", headers=_auth(), timeout=5.0)

    assert resp.status_code == 200
    assert resp.headers["x-model-provider"] == "ephe"
    body = resp.json()
    assert body["object"] == "list"
    assert isinstance(body["data"], list)
    ids = [item["id"] for item in body["data"]]
    assert MODEL in ids
    for item in body["data"]:
        assert item["object"] == "model"
        assert item["owned_by"] == "ephe"
        assert isinstance(item["created"], int)


def test_non_stream_completion_matches_the_openai_chat_completion_shape(served_base_url):
    resp = httpx.post(
        f"{served_base_url}/v1/chat/completions",
        headers=_auth(),
        json={"model": MODEL, "messages": [{"role": "user", "content": "hi"}]},
        timeout=5.0,
    )

    assert resp.status_code == 200
    # The transparency headers a consumer keys on — and the request ID middleware.
    assert resp.headers["x-model-tier"] == "explicit"
    assert resp.headers["x-model-name"] == MODEL
    assert resp.headers["x-request-id"].startswith("chatcmpl-")

    body = resp.json()
    assert body["object"] == "chat.completion"
    assert body["id"].startswith("chatcmpl-")
    assert body["model"] == MODEL
    assert isinstance(body["created"], int)
    choice = body["choices"][0]
    assert choice["index"] == 0
    assert choice["message"] == {"role": "assistant", "content": FULL}
    assert choice["finish_reason"] == "stop"

    usage = body["usage"]
    assert usage["prompt_tokens"] > 0
    assert usage["completion_tokens"] > 0
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
    assert isinstance(usage["usage_estimated"], bool)


def test_stream_emits_openai_sse_chunks_and_the_done_sentinel(served_base_url):
    with httpx.stream(
        "POST",
        f"{served_base_url}/v1/chat/completions",
        headers=_auth(),
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
        timeout=5.0,
    ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        lines = [ln for ln in resp.iter_lines() if ln]

    assert lines[-1] == "data: [DONE]"
    collected = ""
    for line in lines[:-1]:
        assert line.startswith("data: ")
        payload = json.loads(line[len("data: "):])
        assert payload["object"] == "chat.completion.chunk"
        assert payload["model"] == MODEL
        assert payload["choices"][0]["delta"]["content"]
        collected += payload["choices"][0]["delta"]["content"]
    assert collected == FULL


def test_missing_token_is_rejected_with_the_openai_error_envelope(served_base_url):
    resp = httpx.get(f"{served_base_url}/v1/models", timeout=5.0)

    assert resp.status_code == 401
    error = resp.json()["error"]
    assert error["code"] == "auth_error"
    assert error["request_id"]


def test_real_openai_sdk_drives_models_and_chat(served_base_url):
    """The gold path: the shipped openai SDK as the client.

    Skipped where the SDK is not installed (the repo .venv). Present, it is the
    real consumer: the SDK builds the request, parses the response into its own
    typed models, and would reject any field the wire shape got wrong.

    Auth is Ephe's `X-Auth-Token`; the SDK sends `Authorization: Bearer`, so the
    client adds the header explicitly. That the SDK accepts the value as
    ``api_key`` too is incidental.
    """
    openai = pytest.importorskip("openai", reason="openai SDK not installed")

    client = openai.OpenAI(
        base_url=f"{served_base_url}/v1",
        api_key=TOKEN,
        default_headers={"X-Auth-Token": TOKEN},
    )

    models = client.models.list()
    assert MODEL in [m.id for m in models.data]

    completion = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "hi"}],
    )
    assert completion.object == "chat.completion"
    assert completion.choices[0].message.content == FULL
    assert completion.choices[0].finish_reason == "stop"

    stream = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
    )
    streamed = "".join(chunk.choices[0].delta.content or "" for chunk in stream)
    assert streamed == FULL
