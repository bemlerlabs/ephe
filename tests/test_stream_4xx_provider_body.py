"""
#51 — a 4xx that arrives on the STREAM path reaches the reader like a non-streamed one.

The non-streaming branch of `core/model_provider.py` opens the provider's body and raises
`"400 Bad Request: {body}"`, which is what the W13 mapper reads to hand the reader the engine's
own explanation. The streaming branch called `response.raise_for_status()` and walked away from a
body that is still in the buffer — and `.text` on such a response raises `httpx.ResponseNotRead`.
The friendly renderer then died on the way to its own sentence and the generic fallback put
`Client error '404 Not Found' for url '…'` in the bubble: a URL where the reason belongs, no
provider words, and no reason code beside the sentence.

Three things a streamed 4xx has to carry are pinned here: the provider's own words, the English
sentence, and the stable code a surface translates by. The tests drive the real stream client and
the real SSE route, since the defect lived in the seam between them.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import httpx
import pytest

from core.model_provider import ModelProviderConfig, OpenAICompatibleAsyncClient
from server.routes import chat as chat_route

ROOT = Path(__file__).resolve().parents[1]

#: the installation these tests speak for: a hosted engine, which is the one that answers a 4xx
HOSTED = ModelProviderConfig(
    provider="openai_compatible",
    model="ghost-9b",
    base_url="https://engine.test/v1",
    label="Hosted engine",
    offline_capable=False,
    requires_internet=True,
)

#: what a hosted engine answers when the model name it was asked for does not exist
GHOST_MODEL = {"error": {"message": "unknown model 'ghost-9b' for this endpoint"}}

#: status -> (reason code, the engine's own sentence for that refusal)
REFUSALS = {
    400: ("provider_request_refused", "unknown model 'ghost-9b' for this endpoint"),
    429: ("provider_rate_limited", "quota exhausted for this key"),
}

#: the three classes the code table knows; 401/403 are answered before the mapper is reached
PROVIDER_CODES = sorted(set(chat_route.PROVIDER_REFUSAL_CODES.values()))


class _UnreadBody(httpx.AsyncByteStream):
    """The body a streamed response holds until a caller reads it."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    async def __aiter__(self):
        yield self._data


#: held before any test patches the module attribute, so the substitute can build a real one
_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _client(
    monkeypatch, status: int, body: str, *, buffered: bool = False
) -> OpenAICompatibleAsyncClient:
    """A provider client whose one answer is `status` carrying `body`.

    `buffered=False` is the shape the streaming transport returns: the bytes sit in an
    unread stream, so `.text` raises until somebody calls `read()`.
    """
    raw = body.encode()

    def handler(_request: httpx.Request) -> httpx.Response:
        headers = {"content-type": "application/json"}
        if buffered:
            return httpx.Response(status, content=raw, headers=headers)
        return httpx.Response(status, stream=_UnreadBody(raw), headers=headers)

    real_client = _REAL_ASYNC_CLIENT
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    return OpenAICompatibleAsyncClient(base_url="https://engine.test/v1", api_key="test-key")


async def _stream_failure(monkeypatch, status: int, body: str) -> httpx.HTTPStatusError:
    """The exception the provider raises for a `status` that arrived while streaming."""
    client = _client(monkeypatch, status, body)
    with pytest.raises(httpx.HTTPStatusError) as caught:
        stream = await client.chat(
            model="ghost-9b", messages=[{"role": "user", "content": "hi"}], stream=True
        )
        async for _chunk in stream:
            pass
    return caught.value


def _raiser(exc: BaseException):
    async def _impl(**_kwargs):
        raise exc

    return _impl


def _server_errors(name: str) -> dict:
    bundle = json.loads((ROOT / "app" / "src" / "locales" / name).read_text(encoding="utf-8"))
    return bundle["serverError"]


def _bundle_sentence(name: str, code: str, params: dict) -> str:
    """The sentence a surface shows for `code`, rendered from the reader's own bundle."""
    sentence = _server_errors(name)[code]
    for key, value in params.items():
        sentence = sentence.replace("{{" + key + "}}", str(value))
    assert "{{" not in sentence, sentence
    return sentence


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-zäöüß]{4,}", text.lower()))


async def _error_frame(monkeypatch, exc: BaseException) -> dict:
    """The one `error` frame the real SSE route emits when the turn dies with `exc`."""
    monkeypatch.setattr(chat_route, "chat_with_tools", _raiser(exc))
    monkeypatch.setattr(chat_route, "get_active_provider", lambda: HOSTED)
    response = await chat_route.chat_stream(
        chat_route.StreamRequest(message="ping", session_id="s-51")
    )
    chunks: list[str] = []
    while True:
        try:
            chunks.append(await asyncio.wait_for(response.body_iterator.__anext__(), 5.0))
        except StopAsyncIteration:
            break
    events = [
        json.loads(part.strip()[len("data: ") :])
        for part in "".join(chunks).split("\n\n")
        if part.strip().startswith("data: ")
    ]
    frames = [event for event in events if event.get("type") == "error"]
    assert len(frames) == 1, events
    return frames[0]


# the provider side: the body survives the stream

async def test_a_streamed_4xx_hands_the_provider_body_on_instead_of_httpxs_line(monkeypatch):
    exc = await _stream_failure(monkeypatch, 404, json.dumps(GHOST_MODEL))
    assert exc.response.status_code == 404
    assert "ghost-9b" in exc.response.text
    assert "ghost-9b" in str(exc)


async def test_the_streaming_and_non_streaming_paths_read_one_4xx_the_same_way(monkeypatch):
    body = json.dumps(GHOST_MODEL)
    streamed = await _stream_failure(monkeypatch, 400, body)
    buffered_client = _client(monkeypatch, 400, body, buffered=True)
    with pytest.raises(httpx.HTTPStatusError) as caught:
        await buffered_client.chat(
            model="ghost-9b", messages=[{"role": "user", "content": "hi"}], stream=False
        )
    assert str(streamed) == str(caught.value)


# the reader's side: the frame carries the words, the sentence and the code

async def test_a_streamed_4xx_reaches_the_reader_with_the_engines_own_words(monkeypatch):
    exc = await _stream_failure(monkeypatch, 404, json.dumps(GHOST_MODEL))
    frame = await _error_frame(monkeypatch, exc)
    assert "ghost-9b" in frame["msg"]
    assert "HTTP 404" in frame["msg"]


@pytest.mark.parametrize("status", sorted(REFUSALS))
async def test_a_streamed_4xx_carries_the_reason_code_beside_its_sentence(monkeypatch, status):
    code, message = REFUSALS[status]
    exc = await _stream_failure(monkeypatch, status, json.dumps({"error": {"message": message}}))
    frame = await _error_frame(monkeypatch, exc)
    assert frame["reason_code"] == code
    assert frame["reason_params"] == {"status": status, "detail": message}
    assert message in frame["msg"]
    assert _bundle_sentence("en.json", code, frame["reason_params"]) == frame["msg"]


async def test_a_4xx_without_a_provider_sentence_adds_no_code(monkeypatch):
    """The frame rule of f5d88653: an uncoded result carries neither key."""
    exc = await _stream_failure(monkeypatch, 404, "")
    frame = await _error_frame(monkeypatch, exc)
    assert "reason_code" not in frame and "reason_params" not in frame
    assert frame["msg"] == (
        "The provider refused the request (HTTP 404). Check the engine's model name and settings, "
        "then send the message again."
    )
    assert _server_errors("en.json")["provider_request_refused"] == (
        "The provider refused the request (HTTP {{status}}). Check the engine's model name and "
        "settings, then send the message again. The engine answered: {{detail}}"
    )


async def test_a_streamed_5xx_keeps_the_wording_it_had(monkeypatch):
    """Only a 4xx is read: the 5xx path answers with the exception's own line, as it did."""
    exc = await _stream_failure(monkeypatch, 503, json.dumps({"error": {"message": "overloaded"}}))
    frame = await _error_frame(monkeypatch, exc)
    assert frame["msg"] == str(exc)
    assert "reason_code" not in frame


# a refused key: answered before either path opens a body, on both paths alike

async def test_a_refused_key_is_answered_by_the_challenge_branch_on_both_paths(monkeypatch):
    """401/403 leave through `_key_challenge` with the sentence that names where the key goes.

    That is the shape both paths already had, and the frame keeps it uncoded: the bundle
    sentence is the failure table's, this one is the challenge's own.
    """
    from core.model_provider import ProviderSetupError

    body = json.dumps({"error": {"message": "invalid api key provided"}})
    streamed_client = _client(monkeypatch, 401, body)
    with pytest.raises(ProviderSetupError) as streamed:
        stream = await streamed_client.chat(
            model="ghost-9b", messages=[{"role": "user", "content": "hi"}], stream=True
        )
        async for _chunk in stream:
            pass
    buffered_client = _client(monkeypatch, 401, body, buffered=True)
    with pytest.raises(ProviderSetupError) as buffered:
        await buffered_client.chat(
            model="ghost-9b", messages=[{"role": "user", "content": "hi"}], stream=False
        )
    assert str(streamed.value) == str(buffered.value)
    assert "refused the token it was given (HTTP 401)" in str(streamed.value)
    frame = await _error_frame(monkeypatch, streamed.value)
    assert frame["msg"] == str(streamed.value)
    assert "reason_code" not in frame


async def test_the_auth_class_the_mapper_sees_carries_the_key_code(monkeypatch):
    """A 401 that arrives as an HTTP failure goes through the mapper's 4xx branch.

    The provider client answers its own challenges, so this shape comes from a client that
    does not — the branch W13 built, now with the code beside its sentence.
    """
    request = httpx.Request("POST", "https://engine.test/v1/chat/completions")
    response = httpx.Response(
        401, request=request, json={"error": {"message": "invalid api key provided"}}
    )
    with pytest.raises(httpx.HTTPStatusError) as caught:
        response.raise_for_status()
    frame = await _error_frame(monkeypatch, caught.value)
    assert frame["reason_code"] == "provider_key_refused"
    assert frame["reason_params"] == {"status": 401, "detail": "invalid api key provided"}
    sentence = _bundle_sentence("en.json", "provider_key_refused", frame["reason_params"])
    assert sentence == frame["msg"]


@pytest.mark.parametrize("code", PROVIDER_CODES)
def test_the_code_table_covers_the_classes_the_moves_table_names(code):
    assert set(chat_route.PROVIDER_REFUSAL_CODES) == set(chat_route._PROVIDER_REFUSAL_MOVES), (
        "a refusal class without a code, or a code without a class"
    )
    assert set(chat_route.PROVIDER_REFUSAL_CODES.values()) == set(PROVIDER_CODES)
    assert re.fullmatch(r"[a-z][a-z0-9_]*", code), code


@pytest.mark.parametrize("code", PROVIDER_CODES)
def test_every_provider_code_has_a_translated_key_in_both_bundles(code):
    de, en = _server_errors("de.json"), _server_errors("en.json")
    assert de.get(code, "").strip() and en.get(code, "").strip(), code
    assert de[code] != en[code], code
    assert _words(de[code]) - _words(en[code]), f"{code} is copied, not translated"
    slots = set(re.findall(r"{{(\w+)}}", en[code]))
    assert slots == {"status", "detail"}, slots
    assert set(re.findall(r"{{(\w+)}}", de[code])) == slots
