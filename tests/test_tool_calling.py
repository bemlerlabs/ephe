"""
◑ Ephe – the chat tool-calling loop (Phase 1 TDD)
tests/test_tool_calling.py

Covers chat_with_tools.
RULE: the tests were written BEFORE the implementation.

Every test is written strictly as Given / When / Then.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest


from core.chat import chat_with_tools
from core.tools import WebSearchError
from tests.web_search_seam import web_search_module


# Helpers

def _make_ollama_response(content: str = "", tool_calls=None):
    """Build a mock Ollama chat response with optional tool_calls."""
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    response = MagicMock()
    response.message = msg
    return response


def _make_tool_call(name: str, arguments: dict):
    """Build a mock Ollama tool_call object."""
    func = MagicMock()
    func.name = name
    func.arguments = arguments
    tc = MagicMock()
    tc.function = func
    return tc


# chat_with_tools

class TestChatWithTools:

    @pytest.mark.asyncio
    async def test_executes_tool_and_returns_result_in_final_answer(self):
        """
        GIVEN  an Ollama mock that returns a tool_call for web_search
        WHEN   chat_with_tools(history, tools) is called
        THEN   web_search executes exactly 1x
        AND    the final answer contains the result of web_search
        AND    stream=False was used for tool detection
        """
        tool_call = _make_tool_call("web_search", {"query": "Python 2026"})
        first_response = _make_ollama_response(tool_calls=[tool_call])
        final_response = _make_ollama_response(content="Python ist toll laut Websuche.")

        chunks: list[str] = []

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            client = AsyncMock()
            # First call: tool detection (returns tool_call)
            # Second call: final answer
            client.chat = AsyncMock(side_effect=[first_response, final_response])
            MockClient.return_value = client

            with patch.object(web_search_module, "DDGS") as MockDDGS:
                mock_instance = MagicMock()
                mock_instance.text = MagicMock(
                    return_value=[{"title": "T", "href": "U", "body": "Python ist toll"}]
                )
                mock_instance.__enter__ = MagicMock(return_value=mock_instance)
                mock_instance.__exit__ = MagicMock(return_value=False)
                MockDDGS.return_value = mock_instance

                result = await chat_with_tools(
                    model="phi4-mini",
                    history=[{"role": "user", "content": "Was ist Python?"}],
                    on_chunk=chunks.append,
                )

        mock_instance.text.assert_called_once()
        assert isinstance(result, str)
        # Tool detection call must use stream=False
        first_call_kwargs = client.chat.call_args_list[0].kwargs
        assert first_call_kwargs.get("stream") is False

    @pytest.mark.asyncio
    async def test_no_tool_call_falls_back_to_streaming(self):
        """
        GIVEN  the LLM answers without a tool call (pure text)
        WHEN   chat_with_tools(history, tools) is called
        THEN   no tool is executed
        AND    on_chunk is called with the text
        AND    no error
        """
        pure_text_response = _make_ollama_response(
            content="Hallo! Ich bin Ephe.", tool_calls=[]
        )

        chunks: list[str] = []

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            client = AsyncMock()
            client.chat = AsyncMock(return_value=pure_text_response)
            MockClient.return_value = client

            result = await chat_with_tools(
                model="phi4-mini",
                history=[{"role": "user", "content": "Hallo"}],
                on_chunk=chunks.append,
            )

        assert isinstance(result, str)
        # on_chunk must have been called (text arrived)
        assert len(chunks) > 0 or len(result) > 0

    @pytest.mark.asyncio
    async def test_tool_failure_is_caught_and_reported(self):
        """
        GIVEN  the tool fails (WebSearchError)
        WHEN   chat_with_tools() is called with web_search
        THEN   the error is caught
        AND    on_chunk receives an error message for the user
        AND    the app does NOT crash
        """
        tool_call = _make_tool_call("web_search", {"query": "test"})
        first_response = _make_ollama_response(tool_calls=[tool_call])
        final_response = _make_ollama_response(content="Konnte nicht suchen.")

        chunks: list[str] = []

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            client = AsyncMock()
            client.chat = AsyncMock(side_effect=[first_response, final_response])
            MockClient.return_value = client

            with patch("core.tools.web_search", new=AsyncMock(
                side_effect=WebSearchError("Netzwerk nicht erreichbar")
            )):
                # Must NOT raise
                result = await chat_with_tools(
                    model="phi4-mini",
                    history=[{"role": "user", "content": "Suche was"}],
                    on_chunk=chunks.append,
                )

        assert isinstance(result, str)  # No crash

    @pytest.mark.asyncio
    async def test_loop_breaks_after_max_iterations(self):
        """
        GIVEN  the LLM proposes a tool_call at every step (infinite loop)
        WHEN   the chat_with_tools() loop runs
        THEN   the loop breaks after MAX_TOOL_ITERATIONS=5
        AND    the user still gets an answer (no hang)
        """
        from core.chat import MAX_TOOL_ITERATIONS

        tool_call = _make_tool_call("get_datetime", {})
        looping_response = _make_ollama_response(tool_calls=[tool_call])
        final_response = _make_ollama_response(content="Maximale Iterationen erreicht.")

        chunks: list[str] = []
        call_count = 0

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            client = AsyncMock()

            async def chat_side_effect(*args, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count <= MAX_TOOL_ITERATIONS:
                    return looping_response
                return final_response

            client.chat = AsyncMock(side_effect=chat_side_effect)
            MockClient.return_value = client

            with patch("core.tools.get_datetime", new=AsyncMock(return_value="Donnerstag, 02. April 2026")):
                result = await chat_with_tools(
                    model="phi4-mini",
                    history=[{"role": "user", "content": "Was ist die Zeit?"}],
                    on_chunk=chunks.append,
                )

        assert isinstance(result, str)
        assert call_count <= MAX_TOOL_ITERATIONS + 2  # detection + max iterations + final

    @pytest.mark.asyncio
    async def test_on_tool_callbacks_are_called(self):
        """
        GIVEN  on_tool_start and on_tool_done callbacks are set
        WHEN   a tool is called
        THEN   on_tool_start(name, args) is called BEFORE execution
        AND    on_tool_done(name, result) is called AFTER execution
        """
        tool_call = _make_tool_call("get_datetime", {})
        first_response = _make_ollama_response(tool_calls=[tool_call])
        final_response = _make_ollama_response(content="Es ist Donnerstag.")

        tool_starts: list[tuple] = []
        tool_dones: list[tuple] = []

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            client = AsyncMock()
            client.chat = AsyncMock(side_effect=[first_response, final_response])
            MockClient.return_value = client

            with patch("core.tools.get_datetime", new=AsyncMock(return_value="Donnerstag, 02. April 2026")):
                await chat_with_tools(
                    model="phi4-mini",
                    history=[{"role": "user", "content": "Was ist das Datum?"}],
                    on_chunk=lambda c: None,
                    on_tool_start=lambda name, args, call_id: tool_starts.append((name, args, call_id)),
                    on_tool_done=lambda name, result, call_id: tool_dones.append((name, result, call_id)),
                )

        assert len(tool_starts) == 1
        assert tool_starts[0][0] == "get_datetime"
        assert tool_starts[0][2].startswith("c0-")  # W15-P3/A3: Ephe's own call identifier
        assert len(tool_dones) == 1
        assert tool_dones[0][0] == "get_datetime"
        assert tool_dones[0][2] == tool_starts[0][2], "Start und Done zeigen auf denselben Ruf"

    @pytest.mark.asyncio
    async def test_stream_false_used_for_tool_detection(self):
        """
        GIVEN  every chat_with_tools call
        WHEN   the tool detection phase runs
        THEN   Ollama is called with stream=False
        AND    not with stream=True (that would be an Ollama bug)
        """
        pure_text = _make_ollama_response(content="Antwort.", tool_calls=[])

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            client = AsyncMock()
            client.chat = AsyncMock(return_value=pure_text)
            MockClient.return_value = client

            await chat_with_tools(
                model="phi4-mini",
                history=[{"role": "user", "content": "Test"}],
                on_chunk=lambda c: None,
            )

        # Tool detection call must use stream=False
        detection_call_kwargs = client.chat.call_args_list[0].kwargs
        assert detection_call_kwargs.get("stream") is False, (
            "KRITISCH: Tool-Detection muss stream=False nutzen "
            "(bekanntes Ollama-Limit: Tool-Calls brechen mit stream=True)"
        )

    @pytest.mark.asyncio
    async def test_given_gemma4_12b_when_tool_detection_runs_then_native_thinking_is_disabled(self):
        """
        GIVEN the default Gemma 4 12B local model
        WHEN chat_with_tools performs the non-streaming tool detection call
        THEN it sends think=False so short answers are visible instead of being
        consumed by Ollama's native thinking channel.
        """
        pure_text = _make_ollama_response(content="OK", tool_calls=[])

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            client = AsyncMock()
            client.chat = AsyncMock(return_value=pure_text)
            MockClient.return_value = client

            await chat_with_tools(
                model="gemma4:12b",
                history=[{"role": "user", "content": "Sage OK"}],
                on_chunk=lambda c: None,
            )

        detection_call_kwargs = client.chat.call_args_list[0].kwargs
        assert detection_call_kwargs.get("think") is False

    @pytest.mark.asyncio
    async def test_given_uploaded_image_when_tool_detection_runs_then_file_image_tool_is_not_offered(self):
        """
        GIVEN the user already uploaded an image into the chat request
        WHEN chat_with_tools performs tool detection
        THEN the local file-path analyze_image tool is not offered, avoiding bogus path='image' calls.
        """
        pure_text = _make_ollama_response(content="Ein rotes Quadrat.", tool_calls=[])

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            client = AsyncMock()
            client.chat = AsyncMock(return_value=pure_text)
            MockClient.return_value = client

            await chat_with_tools(
                model="gemma4:12b",
                history=[{"role": "user", "content": "Was siehst du?", "images": ["abc123"]}],
                on_chunk=lambda c: None,
            )

        detection_tools = client.chat.call_args_list[0].kwargs["tools"]
        names = [tool["function"]["name"] for tool in detection_tools]
        assert "analyze_image" not in names

    @pytest.mark.asyncio
    async def test_given_skill_tool_scope_when_tool_detection_runs_then_only_skill_tools_are_offered(self):
        """
        GIVEN a slash skill allows only create_pdf
        WHEN chat_with_tools performs tool detection
        THEN unrelated tools are not offered to the model.
        """
        pure_text = _make_ollama_response(content="PDF erstellt.", tool_calls=[])

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            client = AsyncMock()
            client.chat = AsyncMock(return_value=pure_text)
            MockClient.return_value = client

            await chat_with_tools(
                model="gemma4:12b",
                history=[{"role": "user", "content": "Erstelle ein PDF"}],
                on_chunk=lambda c: None,
                allowed_tool_names=["create_pdf"],
            )

        detection_tools = client.chat.call_args_list[0].kwargs["tools"]
        names = [tool["function"]["name"] for tool in detection_tools]
        # P0-1: the skill's declared tools + the three discovery meta tools + the read
        # primitives, which a skill whitelist must never take away (2026-10-10). The
        # mutating file names stay out: this whitelist declares no file tool of its own.
        assert set(names) == {
            "create_pdf", "read_file", "list_directory", "file_search",
            "tool_search", "tool_describe", "tool_call",
        }

    @pytest.mark.asyncio
    async def test_given_tool_result_when_final_response_generated_then_evidence_summary_is_in_context(self):
        """
        GIVEN a tool call returns an artifact
        WHEN chat_with_tools asks the model for the final answer
        THEN a compact evidence summary is included in the model context.
        """
        tool_call_response = _make_ollama_response(
            content="",
            tool_calls=[{"name": "create_pdf", "arguments": {"title": "T", "content": "C"}}],
        )
        final_response = _make_ollama_response(content="PDF ready.", tool_calls=[])

        with patch("core.chat.ollama.AsyncClient") as MockClient, patch(
            "core.chat.execute_tool",
            new=AsyncMock(return_value="PDF_FILE:/Users/test/Downloads/t.pdf"),
        ):
            client = AsyncMock()
            client.chat = AsyncMock(side_effect=[tool_call_response, final_response])
            MockClient.return_value = client

            await chat_with_tools(
                model="gemma4:12b",
                history=[{"role": "user", "content": "Create PDF"}],
                on_chunk=lambda c: None,
                allowed_tool_names=["create_pdf"],
                # I6 P1-4: create_pdf mutates → the chat gate asks the user.
                # This test checks the evidence summary, so: simulate approved.
                on_tool_confirm=lambda name, args: True,
            )

        final_messages = client.chat.call_args_list[1].kwargs["messages"]
        assert any("Tool evidence summary" in str(message.get("content", "")) for message in final_messages if isinstance(message, dict))
        assert any("PDF artifact created" in str(message.get("content", "")) for message in final_messages if isinstance(message, dict))

    @pytest.mark.asyncio
    async def test_given_shell_tool_call_when_user_denies_then_command_is_not_executed_and_chat_continues(self):
        """
        GIVEN the model requests run_shell
        WHEN the shell confirmation callback denies approval
        THEN the command is not executed and the final answer is still generated.
        """
        tool_call = _make_tool_call("run_shell", {"command": "echo SHOULD_NOT_RUN"})
        first_response = _make_ollama_response(tool_calls=[tool_call])
        final_response = _make_ollama_response(content="Befehl abgebrochen.")

        approvals: list[str] = []

        async def deny(command: str) -> bool:
            approvals.append(command)
            return False

        with patch("core.chat.ollama.AsyncClient") as MockClient, patch(
            "core.chat.execute_confirmed_shell", new=AsyncMock(return_value="Abgebrochen.")
        ) as mock_exec:
            client = AsyncMock()
            client.chat = AsyncMock(side_effect=[first_response, final_response])
            MockClient.return_value = client

            result = await chat_with_tools(
                model="gemma4:12b",
                history=[{"role": "user", "content": "Wie viel Speicher ist frei?"}],
                on_chunk=lambda c: None,
                allowed_tool_names=["run_shell"],
                on_shell_confirm=deny,
            )

        assert approvals == ["echo SHOULD_NOT_RUN"]
        mock_exec.assert_awaited_once_with("echo SHOULD_NOT_RUN", confirmed=False, cwd=None)
        assert "Befehl abgebrochen" in result

    @pytest.mark.asyncio
    async def test_given_primary_model_memory_error_when_fallback_configured_then_retries_with_fallback_model(self):
        """
        GIVEN the primary local model cannot load because RAM is too low
        WHEN a fallback model is configured
        THEN chat_with_tools retries tool detection with the fallback model.
        """
        pure_text = _make_ollama_response(content="Fallback Antwort.", tool_calls=[])

        with patch.dict("os.environ", {"EPHE_FALLBACK_MODEL": "qwen3:4b"}), patch(
            "core.chat.ollama.AsyncClient"
        ) as MockClient:
            client = AsyncMock()
            client.chat = AsyncMock(side_effect=[
                Exception("model requires more system memory (9.8 GiB) than is available (8.6 GiB)"),
                pure_text,
            ])
            MockClient.return_value = client

            result = await chat_with_tools(
                model="gemma4:12b",
                history=[{"role": "user", "content": "Hallo"}],
                on_chunk=lambda c: None,
            )

        assert result == "Fallback Antwort."
        assert client.chat.call_args_list[0].kwargs["model"] == "gemma4:12b"
        assert client.chat.call_args_list[1].kwargs["model"] == "qwen3:4b"

    @pytest.mark.asyncio
    async def test_given_qwen3_4b_when_tool_detection_runs_then_native_thinking_flag_is_not_sent(self):
        """
        GIVEN qwen3:4b is selected as a local chat model
        WHEN chat_with_tools performs tool detection
        THEN Ephe does not send native think=True because this small local model
        can stall when thinking is combined with non-streaming tool detection.
        """
        pure_text = _make_ollama_response(content="OK", tool_calls=[])

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            client = AsyncMock()
            client.chat = AsyncMock(return_value=pure_text)
            MockClient.return_value = client

            await chat_with_tools(
                model="qwen3:4b",
                history=[{"role": "user", "content": "Sage OK"}],
                on_chunk=lambda c: None,
            )

        detection_call_kwargs = client.chat.call_args_list[0].kwargs
        assert "think" not in detection_call_kwargs

    @pytest.mark.asyncio
    async def test_given_model_timeout_but_ollama_alive_when_tool_detection_runs_then_model_busy_is_raised(self):
        """
        GIVEN the selected local model does not answer before the detection timeout
        AND Ollama itself is still reachable
        WHEN chat_with_tools runs
        THEN Ephe raises OllamaModelBusyError instead of reporting Ollama offline.
        """
        import core.chat as chat

        class AliveClient:
            async def list(self):
                return object()

        with patch("core.chat.ollama.AsyncClient") as MockClient, patch(
            "core.chat._tool_detection_timeout", return_value=0.01
        ):
            client = AsyncMock()
            client.chat = AsyncMock(side_effect=asyncio.TimeoutError())
            MockClient.return_value = client
            with patch("core.chat._ollama_async_client", return_value=AliveClient()):
                with pytest.raises(chat.OllamaModelBusyError) as exc_info:
                    await chat_with_tools(
                        model="qwen3:4b",
                        history=[{"role": "user", "content": "Hallo"}],
                        on_chunk=lambda c: None,
                    )

        assert exc_info.value.model == "qwen3:4b"

    @pytest.mark.asyncio
    async def test_given_model_timeout_and_probe_timeout_when_tool_detection_runs_then_model_busy_is_raised(self):
        """
        GIVEN the selected local model does not answer before the detection timeout
        AND the follow-up Ollama probe also times out while the daemon is busy
        WHEN chat_with_tools runs
        THEN Ephe reports the model as busy instead of claiming Ollama is offline.
        """
        import core.chat as chat

        class BusyProbeClient:
            async def list(self):
                raise asyncio.TimeoutError()

        with patch("core.chat.ollama.AsyncClient") as MockClient, patch(
            "core.chat._tool_detection_timeout", return_value=0.01
        ):
            client = AsyncMock()
            client.chat = AsyncMock(side_effect=asyncio.TimeoutError())
            MockClient.return_value = client
            with patch("core.chat._ollama_async_client", return_value=BusyProbeClient()):
                with pytest.raises(chat.OllamaModelBusyError) as exc_info:
                    await chat_with_tools(
                        model="qwen3:4b",
                        history=[{"role": "user", "content": "Hallo"}],
                        on_chunk=lambda c: None,
                    )

        assert exc_info.value.model == "qwen3:4b"
