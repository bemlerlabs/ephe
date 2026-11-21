"""
◑ Ephe – Phase 3 TDD
tests/test_react.py

RULE: tests BEFORE implementation. RED first, then GREEN.
Given / When / Then — strictly.

ReAct = Reason + Act + Observe + Reflect
Reflexion = self-critique + revision when the answer is insufficient
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.react import (
    ReActStep,
    ReflexionResult,
    reflect,
    react_loop,
)


# Test data

GOOD_ANSWER = (
    "Ollama ist ein Open-Source-Tool zum lokalen Ausführen von LLMs. "
    "Es läuft vollständig offline auf deinem Computer."
)

BAD_ANSWER = "Ich weiß es nicht."

QUESTION = "Was ist Ollama?"


# Tests: reflect()

class TestReflect:

    @pytest.mark.asyncio
    async def test_good_answer_needs_no_revision(self):
        """
        GIVEN  a complete, correct answer to a question
        WHEN   reflect(response=GOOD_ANSWER, question=QUESTION, model=...) is called
        THEN   returns: needs_revision=False
        AND    reason is a string (may be empty)
        AND    no crash
        """
        with patch("core.react.build_provider_client") as mock_build_client:
            client = AsyncMock()
            client.chat = AsyncMock(return_value=MagicMock(
                message=MagicMock(content="Die Antwort ist vollständig und korrekt. REVISION: NEIN")
            ))
            mock_build_client.return_value = client

            result = await reflect(
                response=GOOD_ANSWER,
                question=QUESTION,
                model="phi4-mini",
            )

        assert isinstance(result, ReflexionResult)
        assert result.needs_revision is False
        assert isinstance(result.reason, str)

    @pytest.mark.asyncio
    async def test_bad_answer_triggers_revision(self):
        """
        GIVEN  the incomplete answer held in BAD_ANSWER
        WHEN   reflect(response=BAD_ANSWER, question=QUESTION, model=...) is called
        THEN   returns: needs_revision=True
        AND    reason carries the justification (non-empty string)
        """
        with patch("core.react.build_provider_client") as mock_build_client:
            client = AsyncMock()
            client.chat = AsyncMock(return_value=MagicMock(
                message=MagicMock(
                    content="Die Antwort ist unvollständig. REVISION: JA\nGrund: Keine konkreten Informationen."
                )
            ))
            mock_build_client.return_value = client

            result = await reflect(
                response=BAD_ANSWER,
                question=QUESTION,
                model="phi4-mini",
            )

        assert isinstance(result, ReflexionResult)
        assert result.needs_revision is True
        assert isinstance(result.reason, str)
        assert len(result.reason) > 0

    @pytest.mark.asyncio
    async def test_reflect_returns_reflexion_result_always(self):
        """
        GIVEN  Ollama returns an unexpected answer (no REVISION: JA/NEIN marker)
        WHEN   reflect() is called
        THEN   the return value is a ReflexionResult (no crash)
        AND    needs_revision is a bool
        """
        with patch("core.react.build_provider_client") as mock_build_client:
            client = AsyncMock()
            client.chat = AsyncMock(return_value=MagicMock(
                message=MagicMock(content="Ich bin ein Sprachmodell.")
            ))
            mock_build_client.return_value = client

            result = await reflect(
                response="Test-Antwort",
                question="Test-Frage",
                model="phi4-mini",
            )

        assert isinstance(result, ReflexionResult)
        assert isinstance(result.needs_revision, bool)

    @pytest.mark.asyncio
    async def test_given_gemma4_12b_when_reflect_runs_then_native_thinking_is_disabled(self):
        """
        GIVEN Gemma 4 12B can put short non-streaming answers into native thinking
        WHEN reflect evaluates an answer
        THEN it sends think=False so the critique result remains visible.
        """
        with patch("core.react.build_provider_client") as mock_build_client:
            client = AsyncMock()
            client.chat = AsyncMock(return_value=MagicMock(
                message=MagicMock(content="Korrekt. REVISION: NEIN")
            ))
            mock_build_client.return_value = client

            await reflect(
                response=GOOD_ANSWER,
                question=QUESTION,
                model="gemma4:12b",
            )

        assert client.chat.call_args.kwargs.get("think") is False


# Tests: react_loop()

class TestReactLoop:

    @pytest.mark.asyncio
    async def test_simple_question_terminates(self):
        """
        GIVEN  a simple question that needs no tool (mock: direct answer)
        WHEN   react_loop(question, model=...) runs
        THEN   returns a non-empty string
        AND    no crash
        AND    terminates within ≤5 iterations
        """
        steps_recorded: list[ReActStep] = []

        with patch("core.react.chat_with_tools", new=AsyncMock(
            return_value=GOOD_ANSWER
        )):
            with patch("core.react.reflect", new=AsyncMock(
                return_value=ReflexionResult(needs_revision=False, reason="")
            )):
                result = await react_loop(
                    question=QUESTION,
                    model="phi4-mini",
                    on_step=steps_recorded.append,
                )

        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_revision_triggered_once_on_bad_answer(self):
        """
        GIVEN  the first answer is incomplete (reflect: needs_revision=True)
        AND    the second answer is good (reflect: needs_revision=False)
        WHEN   react_loop() runs
        THEN   exactly 2 chat_with_tools calls (original + revision)
        AND    the final answer is the improved text
        AND    at most 1 revision (no infinite loop)
        """
        call_count = [0]

        async def mock_chat(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return BAD_ANSWER
            return GOOD_ANSWER

        revision_count = [0]

        async def mock_reflect(response, question, model, provider_config=None, api_url=None):
            revision_count[0] += 1
            if revision_count[0] == 1:
                return ReflexionResult(needs_revision=True, reason="Unvollständig")
            return ReflexionResult(needs_revision=False, reason="")

        with patch("core.react.chat_with_tools", new=mock_chat):
            with patch("core.react.reflect", new=mock_reflect):
                result = await react_loop(
                    question=QUESTION,
                    model="phi4-mini",
                )

        assert call_count[0] == 2
        assert result == GOOD_ANSWER

    @pytest.mark.asyncio
    async def test_max_revisions_respected(self):
        """
        GIVEN  reflect() returns needs_revision=True on EVERY call
        WHEN   react_loop() runs
        THEN   the loop breaks after MAX_REVISIONS (=2)
        AND    no crash, it still returns an answer
        """
        with patch("core.react.chat_with_tools", new=AsyncMock(
            return_value=BAD_ANSWER
        )):
            with patch("core.react.reflect", new=AsyncMock(
                return_value=ReflexionResult(needs_revision=True, reason="Immer schlecht")
            )):
                result = await react_loop(
                    question=QUESTION,
                    model="phi4-mini",
                )

        assert isinstance(result, str)
        assert len(result) > 0  # returns last_response, no crash

    @pytest.mark.asyncio
    async def test_on_step_callback_called(self):
        """
        GIVEN  react_loop with an on_step callback
        WHEN   the loop runs
        THEN   on_step is called at least once
        AND    every call passes a ReActStep object
        """
        steps: list[ReActStep] = []

        with patch("core.react.chat_with_tools", new=AsyncMock(
            return_value=GOOD_ANSWER
        )):
            with patch("core.react.reflect", new=AsyncMock(
                return_value=ReflexionResult(needs_revision=False, reason="")
            )):
                await react_loop(
                    question=QUESTION,
                    model="phi4-mini",
                    on_step=steps.append,
                )

        assert len(steps) >= 1
        for step in steps:
            assert isinstance(step, ReActStep)

    @pytest.mark.asyncio
    async def test_react_step_has_required_fields(self):
        """
        GIVEN  one iteration of the react_loop
        WHEN   the on_step callback is called
        THEN   ReActStep has: iteration, answer, reflexion
        AND    iteration is an int ≥ 1
        """
        steps: list[ReActStep] = []

        with patch("core.react.chat_with_tools", new=AsyncMock(
            return_value=GOOD_ANSWER
        )):
            with patch("core.react.reflect", new=AsyncMock(
                return_value=ReflexionResult(needs_revision=False, reason="")
            )):
                await react_loop(
                    question=QUESTION,
                    model="phi4-mini",
                    on_step=steps.append,
                )

        step = steps[0]
        assert hasattr(step, "iteration")
        assert hasattr(step, "answer")
        assert hasattr(step, "reflexion")
        assert isinstance(step.iteration, int)
        assert step.iteration >= 1


# Tests: live streaming (root-cause fix 2026-08-23)
# The old strategy buffered the answer and replayed it only AFTER reflect()
# (a second LLM call, ~8s network gap). In that window the user saw only the
# thinking block + an empty answer surface (screenshot finding). New strategy:
# stream the answer LIVE, reflect() runs afterwards; a revision = on_revision +
# re-stream (same standard as the PWA /chat/stream pipeline).

class TestLiveStreaming:

    @pytest.mark.asyncio
    async def test_answer_streams_before_reflect_runs(self):
        """
        GIVEN  react_loop with an on_chunk callback
        AND    reflect() needs "time" (simulated through the call order)
        WHEN   the answer is generated
        THEN   on_chunk fires BEFORE the reflect() call
        AND    the user sees the answer immediately, not after the reflection
        """
        event_log: list[str] = []

        async def mock_chat(**kwargs):
            cb = kwargs.get("on_chunk")
            if cb:
                cb("Antwort ")
                event_log.append("chunk")
                cb("text")
                event_log.append("chunk")
            return "Antwort text"

        async def mock_reflect(*args, **kwargs):
            event_log.append("reflect")
            return ReflexionResult(needs_revision=False, reason="")

        with patch("core.react.chat_with_tools", new=mock_chat):
            with patch("core.react.reflect", new=mock_reflect):
                await react_loop(
                    question=QUESTION,
                    model="phi4-mini",
                    on_chunk=lambda c: event_log.append("on_chunk:" + c),
                )

        first_chunk = event_log.index("on_chunk:Antwort ")
        reflect_at = event_log.index("reflect")
        assert first_chunk < reflect_at, (
            f"Antwort muss LIVE vor reflect() streamen: {event_log}"
        )

    @pytest.mark.asyncio
    async def test_revision_triggers_on_revision_callback(self):
        """
        GIVEN  the first answer is incomplete (reflect: needs_revision=True)
        AND    the on_revision callback is set
        WHEN   react_loop() runs
        THEN   on_revision is called exactly once with the reason
        AND    the revision answer is likewise streamed LIVE via on_chunk
        """
        revision_calls: list[str] = []
        chunk_calls: list[str] = []
        call_count = [0]

        async def mock_chat(**kwargs):
            call_count[0] += 1
            cb = kwargs.get("on_chunk")
            if cb:
                text = "Drauft" if call_count[0] == 1 else "Volle Antwort"
                cb(text)
                chunk_calls.append(f"iter{call_count[0]}:{text}")
            return "Drauft" if call_count[0] == 1 else "Volle Antwort"

        async def mock_reflect(*args, **kwargs):
            return ReflexionResult(needs_revision=(call_count[0] == 1), reason="Zu kurz")

        with patch("core.react.chat_with_tools", new=mock_chat):
            with patch("core.react.reflect", new=mock_reflect):
                result = await react_loop(
                    question=QUESTION,
                    model="phi4-mini",
                    on_chunk=lambda c: None,
                    on_revision=lambda reason: revision_calls.append(reason),
                )

        assert revision_calls == ["Zu kurz"], f"on_revision-Reason: {revision_calls}"
        assert "iter2:Volle Antwort" in chunk_calls, "Revision muss LIVE streamen"
        assert result == "Volle Antwort"

    @pytest.mark.asyncio
    async def test_no_revision_no_on_revision(self):
        """
        GIVEN  reflect() says needs_revision=False
        WHEN   react_loop() runs
        THEN   on_revision is NOT called (no needless resets)
        """
        revision_calls: list[str] = []

        async def mock_chat(**kwargs):
            return GOOD_ANSWER

        with patch("core.react.chat_with_tools", new=mock_chat):
            with patch("core.react.reflect", new=AsyncMock(
                return_value=ReflexionResult(needs_revision=False, reason="")
            )):
                await react_loop(
                    question=QUESTION,
                    model="phi4-mini",
                    on_revision=lambda reason: revision_calls.append(reason),
                )

        assert revision_calls == []

    @pytest.mark.asyncio
    async def test_revision_stream_ordering(self):
        """
        GIVEN  a revision is needed
        WHEN   react_loop() runs
        THEN   callback order: chunks(iter1) → on_revision → chunks(iter2)
        AND    the UI consumer sees: answer 1, then a reset, then answer 2
        """
        log: list[str] = []
        call_count = [0]

        async def mock_chat(**kwargs):
            call_count[0] += 1
            cb = kwargs.get("on_chunk")
            if cb:
                cb(f"A{call_count[0]}")
                log.append(f"chunk{call_count[0]}")
            return f"A{call_count[0]}"

        async def mock_reflect(*args, **kwargs):
            log.append("revision")
            return ReflexionResult(needs_revision=(call_count[0] == 1), reason="r")

        with patch("core.react.chat_with_tools", new=mock_chat):
            with patch("core.react.reflect", new=mock_reflect):
                await react_loop(
                    question=QUESTION,
                    model="phi4-mini",
                    on_revision=lambda r: log.append("on_revision"),
                )

        assert log == ["chunk1", "revision", "on_revision", "chunk2"], f"Reihenfolge: {log}"
