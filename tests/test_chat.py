"""
Tests for core/chat.py

Uses mocks to avoid requiring a running Ollama instance.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.chat import (
    OllamaModelNotFoundError,
    OllamaNotReachableError,
    check_ollama_connection,
    send_message_safe,
    stream_response,
)
from core.types import Message


# Helpers


def make_stream_mock(chunks: list[str]):
    """Returns an async generator mock for ollama.AsyncClient().chat()"""

    async def fake_stream():
        for chunk in chunks:
            yield {"message": {"content": chunk}}

    return fake_stream()


SAMPLE_HISTORY: list[Message] = [
    Message(role="user", content="Hello from Bad Liebenzell"),
]


# stream_response – happy path


async def test_stream_response_collects_chunks():
    chunks = ["Hello", " from", " the", " forest", "!"]
    received: list[str] = []

    with patch("core.chat.ollama.AsyncClient") as mock_class:
        instance = MagicMock()
        instance.chat = AsyncMock(return_value=make_stream_mock(chunks))
        mock_class.return_value = instance

        result = await stream_response(
            model="llama3.2",
            history=SAMPLE_HISTORY,
            on_chunk=received.append,
        )

    assert "".join(received) == "Hello from the forest!"
    assert result == "Hello from the forest!"


async def test_stream_response_chunks_in_order():
    chunks = ["A", "B", "C", "D"]
    received: list[str] = []

    with patch("core.chat.ollama.AsyncClient") as mock_class:
        instance = MagicMock()
        instance.chat = AsyncMock(return_value=make_stream_mock(chunks))
        mock_class.return_value = instance

        await stream_response(
            model="llama3.2",
            history=SAMPLE_HISTORY,
            on_chunk=received.append,
        )

    assert "".join(received) == "ABCD"


async def test_stream_response_empty_chunks_ignored():
    chunks = ["Hello", "", " world", ""]
    received: list[str] = []

    with patch("core.chat.ollama.AsyncClient") as mock_class:
        instance = MagicMock()
        instance.chat = AsyncMock(return_value=make_stream_mock(chunks))
        mock_class.return_value = instance

        result = await stream_response(
            model="llama3.2",
            history=SAMPLE_HISTORY,
            on_chunk=received.append,
        )

    # Empty chunks are not forwarded
    assert "" not in received
    assert result == "Hello world"


# stream_response – error cases


async def test_connection_refused_raises_ollama_not_reachable():
    with patch("core.chat.ollama.AsyncClient") as mock_class:
        instance = AsyncMock()
        instance.chat.side_effect = ConnectionRefusedError("refused")
        mock_class.return_value = instance

        with pytest.raises(OllamaNotReachableError):
            await stream_response(
                model="llama3.2",
                history=SAMPLE_HISTORY,
                on_chunk=lambda _: None,
            )


async def test_connection_error_string_raises_ollama_not_reachable():
    with patch("core.chat.ollama.AsyncClient") as mock_class:
        instance = AsyncMock()
        instance.chat.side_effect = Exception("connection refused by server")
        mock_class.return_value = instance

        with pytest.raises(OllamaNotReachableError):
            await stream_response(
                model="llama3.2",
                history=SAMPLE_HISTORY,
                on_chunk=lambda _: None,
            )


async def test_model_not_found_raises_custom_error():
    with patch("core.chat.ollama.AsyncClient") as mock_class:
        instance = AsyncMock()
        instance.chat.side_effect = Exception("model 'xyz' not found")
        mock_class.return_value = instance

        with pytest.raises(OllamaModelNotFoundError) as exc_info:
            await stream_response(
                model="xyz",
                history=SAMPLE_HISTORY,
                on_chunk=lambda _: None,
            )

        assert exc_info.value.model == "xyz"


async def test_cancelled_error_propagates():
    """CancelledError must NOT be caught – it signals worker cancellation."""

    async def cancel_stream():
        raise asyncio.CancelledError()
        yield  # make it a generator

    with patch("core.chat.ollama.AsyncClient") as mock_class:
        instance = MagicMock()
        instance.chat = AsyncMock(side_effect=asyncio.CancelledError())
        mock_class.return_value = instance

        with pytest.raises(asyncio.CancelledError):
            await stream_response(
                model="llama3.2",
                history=SAMPLE_HISTORY,
                on_chunk=lambda _: None,
            )


# send_message_safe – fallback


async def test_safe_fallback_called_on_streaming_error():
    fallback_called = []
    chunks = ["Fallback response"]

    with patch("core.chat.ollama.AsyncClient") as mock_class:
        instance = MagicMock()
        # First call (streaming) raises, second call (non-stream) succeeds
        call_count = 0

        async def chat_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Stream died mid-way")
            # Non-streaming response
            return {"message": {"content": "Fallback response"}}

        instance.chat = AsyncMock(side_effect=chat_side_effect)
        mock_class.return_value = instance

        result = await send_message_safe(
            model="llama3.2",
            history=SAMPLE_HISTORY,
            on_chunk=lambda _: None,
            on_fallback=lambda: fallback_called.append(True),
        )

    assert fallback_called == [True]
    assert result == "Fallback response"


async def test_safe_not_reachable_still_raises():
    """
    OllamaNotReachableError from stream_response must propagate through
    send_message_safe without triggering the fallback.
    """
    with patch("core.chat.ollama.AsyncClient") as mock_class:
        instance = AsyncMock()
        # Use a descriptive message so the 'connection' keyword check matches
        instance.chat.side_effect = ConnectionRefusedError(
            "connection refused by ollama server"
        )
        mock_class.return_value = instance

        with pytest.raises(OllamaNotReachableError):
            await send_message_safe(
                model="llama3.2",
                history=SAMPLE_HISTORY,
                on_chunk=lambda _: None,
            )


# check_ollama_connection


async def test_check_connection_success():
    """
    ollama 0.4+ returns pydantic models from .list().
    The mock must expose a .models attribute with objects that have .model attribute.
    """
    # Build a minimal mock that looks like ollama's ListResponse pydantic object
    model_entry = MagicMock()
    model_entry.model = "llama3.2:latest"

    list_response = MagicMock()
    list_response.models = [model_entry]

    with patch("core.chat.ollama.AsyncClient") as mock_class:
        instance = AsyncMock()
        instance.list.return_value = list_response
        mock_class.return_value = instance

        connected, msg, available = await check_ollama_connection("llama3.2")

    assert connected is True
    assert "connected" in msg
    assert isinstance(available, list)


async def test_check_connection_offline():
    with patch("core.chat.ollama.AsyncClient") as mock_class:
        instance = AsyncMock()
        instance.list.side_effect = ConnectionRefusedError()
        mock_class.return_value = instance

        connected, msg, available = await check_ollama_connection("llama3.2")

    assert connected is False
    assert "offline" in msg


async def test_check_connection_timeout():
    with patch("core.chat.ollama.AsyncClient") as mock_class:
        instance = AsyncMock()
        instance.list.side_effect = asyncio.TimeoutError()
        mock_class.return_value = instance

        connected, msg, available = await check_ollama_connection("llama3.2")

    assert connected is False
    assert available == []
