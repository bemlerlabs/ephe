"""S3 capability guard: a model that answers without tools is asked without tools.

Two ways the fact enters one process-lifetime register — an endpoint that states
``supported_parameters`` without ``tools``, and an engine that refuses a turn carrying
the array. The tests name both, and the third side of the rule: an unknown model keeps
exactly the array it keeps today.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.chat import chat_with_tools
from core.model_capability import (
    ANSWER_ONLY_PHASE,
    entries,
    is_answer_only,
    looks_like_tool_rejection,
    note_metadata,
    note_rejection,
    reset,
)
from core.model_provider import ModelProviderConfig


@pytest.fixture(autouse=True)
def _clean_register():
    reset()
    yield
    reset()


class TestRegister:
    def test_a_rejection_is_remembered_per_endpoint_and_model(self):
        note_rejection("http://h:8000/v1", "small")
        assert is_answer_only("http://h:8000/v1", "small")
        assert not is_answer_only("http://h:8000/v1", "other")
        assert not is_answer_only("http://h:9000/v1", "small")

    def test_the_same_engine_with_a_trailing_slash_is_one_entry(self):
        note_rejection("http://h:8000/v1/", "small")
        assert is_answer_only("http://h:8000/v1", "small")

    def test_an_empty_model_never_enters(self):
        note_rejection("http://h:8000/v1", "")
        assert entries() == ()

    def test_metadata_records_only_a_stated_no(self):
        note_metadata(
            "http://h/v1",
            [
                {"id": "a", "supports_tools": False},
                {"id": "b", "supports_tools": True},
                {"id": "c", "supports_tools": None},
            ],
        )
        assert is_answer_only("http://h/v1", "a")
        assert not is_answer_only("http://h/v1", "b")
        assert not is_answer_only("http://h/v1", "c")


class TestRejectionClassifier:
    @pytest.mark.parametrize(
        "body",
        [
            '400 Bad Request: {"error": "This model does not support tools"}',
            '400: Unsupported parameter: "tools"',
            "400: The tool_choice parameter is not supported by this model",
            '400: Extra inputs are not permitted: {"function_call": true}',
            # Live, 2026-10-19: OpenRouter's routing refusal names no parameter at all.
            '404 Bad Request: {"error":{"message":"No endpoints found that support tool use. '
            'Try disabling \\"manage_tasks\\". To learn more about provider routing, visit: '
            'https://openrouter.ai/docs/guides/routing/provider-selection","code":404,'
            '"metadata":{"routing_funnel":[{"step":"Initial Endpoints","endpoint_count":1}],'
            '"failed_routing_step":"Filter by Tool Compatibility"}}}',
        ],
    )
    def test_a_refusal_of_the_array_is_a_capability_statement(self, body):
        assert looks_like_tool_rejection(body)

    @pytest.mark.parametrize(
        "body",
        [
            "",
            "400 Bad Request: {'detail': 'value is not a valid integer'}",
            "429: rate limit exceeded",
            "500: internal server error",
            "400: the messages field is required",
            # Same family, different cause: routing found no endpoint at all, so the
            # array is not what it refused and must not lose this model its tools.
            '404 Bad Request: {"error":{"message":"No endpoints found matching your '
            'data policy. Try disabling \\"manage_tasks\\".","code":404}}',
        ],
    )
    def test_an_ordinary_bad_request_is_not_one(self, body):
        # A wrong "no" here takes a working engine's tools away for the rest of the
        # process, so the classifier has to stay narrow.
        assert not looks_like_tool_rejection(body)


ENDPOINT = "http://engine.test"
MODEL = "capability-test-model"


def _provider():
    return ModelProviderConfig(
        provider="ollama",
        model=MODEL,
        base_url=ENDPOINT,
        label="test",
        offline_capable=True,
        requires_internet=False,
    )


def _response(content: str = "plain answer"):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = None
    response = MagicMock()
    response.message = msg
    return response


class _Engine:
    """A client that either takes the array or refuses it, and records both."""

    def __init__(self, refuses: bool):
        self.refuses = refuses
        self.seen: list = []

    async def chat(self, **kwargs):
        self.seen.append(kwargs.get("tools"))
        if self.refuses and kwargs.get("tools"):
            raise RuntimeError(
                '400 Bad Request: {"error": "this model does not support tools"}'
            )
        return _response()

    async def aclose(self):
        return None


async def _turn(engine, allowed_tool_names=None):
    phases: list[str] = []
    with patch("core.chat._resolve_provider", return_value=_provider()), patch(
        "core.chat.resolve_active_with_failover", new=AsyncMock(return_value=_provider())
    ), patch("core.chat.build_provider_client", return_value=engine):
        answer = await chat_with_tools(
            model=MODEL,
            history=[{"role": "user", "content": "hi"}],
            on_chunk=lambda c: None,
            on_phase=phases.append,
            allowed_tool_names=allowed_tool_names if allowed_tool_names is not None else ["read_file"],
        )
    return answer, phases


class TestTurnBuiltWithoutTools:
    async def test_the_first_refusal_is_remembered_and_the_turn_answers(self):
        engine = _Engine(refuses=True)
        answer, phases = await _turn(engine)
        assert answer == "plain answer"
        assert is_answer_only(ENDPOINT, MODEL)
        # The refusal is said out loud, after the ordinary start line.
        assert ANSWER_ONLY_PHASE in phases
        # asked twice: once with the array, once without — never a failed turn.
        assert len(engine.seen) == 2
        assert engine.seen[0] and engine.seen[1] == []

    async def test_the_next_turn_never_carries_the_array_again(self):
        first = _Engine(refuses=True)
        await _turn(first)
        second = _Engine(refuses=True)
        phases = (await _turn(second))[1]
        assert second.seen[0] == [], "the array was offered to a model already known against it"
        assert ANSWER_ONLY_PHASE not in phases

    async def test_an_unknown_model_keeps_the_array_untouched(self):
        engine = _Engine(refuses=False)
        answer, phases = await _turn(engine)
        assert answer == "plain answer"
        assert all(engine.seen), "a model nobody refused was asked without its array"
        assert phases and ANSWER_ONLY_PHASE not in phases
        assert not is_answer_only(ENDPOINT, MODEL)

    async def test_the_openrouter_routing_refusal_answers_instead_of_500(self):
        # The live shape: a 404 whose message says the endpoint list has nothing that
        # takes tools. Before the classifier knew this family the turn ended in a 500.
        class _OpenRouter:
            def __init__(self):
                self.seen: list = []

            async def chat(self, **kwargs):
                self.seen.append(kwargs.get("tools"))
                if kwargs.get("tools"):
                    raise RuntimeError(
                        '404 Bad Request: {"error":{"message":"No endpoints found that '
                        'support tool use. Try disabling \\"manage_tasks\\"."}}'
                    )
                return _response("routed answer")

            async def aclose(self):
                return None

        engine = _OpenRouter()
        answer, phases = await _turn(engine)
        assert answer == "routed answer"
        assert is_answer_only(ENDPOINT, MODEL)
        assert ANSWER_ONLY_PHASE in phases
        assert len(engine.seen) == 2 and engine.seen[-1] == []

    async def test_an_ordinary_failure_is_raised_not_remembered(self):
        class _Broken:
            async def chat(self, **kwargs):
                raise RuntimeError(
                    "400 Bad Request: {'detail': 'value is not a valid integer'}"
                )

            async def aclose(self):
                return None

        with pytest.raises(RuntimeError):
            await _turn(_Broken())
        assert not is_answer_only(ENDPOINT, MODEL)
