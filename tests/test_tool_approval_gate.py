"""
◑ Ephe – I6-Fix P1-4 · TDD
tests/test_tool_approval_gate.py

RULE: these tests were written BEFORE the implementation.

Covers the approval gate for MUTATING tools on the PWA chat path. Before this,
only run_shell was gated (via on_shell_confirm); write_file/edit_file/run_tests
and the rest ran unprompted as long as no approval_policy was set (execute_tool
gates only when policy != None). That was a security hole: a model could write
files and trigger commands without being asked.

Deny-by-default: without a confirmation callback a mutating tool is not
executed. SAFE tools (read-only) always stay unprompted.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


from core.chat import chat_with_tools


# Helpers

def _make_ollama_response(content: str = "", tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    response = MagicMock()
    response.message = msg
    return response


def _make_tool_call(name: str, arguments: dict):
    func = MagicMock()
    func.name = name
    func.arguments = arguments
    tc = MagicMock()
    tc.function = func
    return tc


def _tool_messages_from_second_call(client) -> list[dict]:
    """Tool roles from the second provider.chat call (after tool execution).

    Call convention in chat_with_tools: client.chat(model=..., messages=...,
    tools=..., stream=False) — the history sits directly in the `messages` kwarg.
    """
    for entry in client.chat.call_args_list[1:]:
        msgs = entry.kwargs.get("messages") or []
        tool_msgs = [m for m in msgs if isinstance(m, dict) and m.get("role") == "tool"]
        if tool_msgs:
            return tool_msgs
    return []


# Chat-gate classification: which tools run without a dialog, which get asked —
# a single source of truth in core.tools.approval.

class TestChatGateClassification:

    def test_read_only_tools_never_require_confirm(self):
        """Read-only/compute tools run in chat without a confirmation dialog."""
        from core.tools.approval import chat_tool_requires_confirm

        for name in (
            "read_file", "file_search", "list_directory", "get_datetime",
            "web_search", "analyze_image", "analyze_project", "discover_projects",
            "inspect_pptx_template", "load_workspace", "manage_tasks",
            "qa_pptx_deck", "query_source_notebook", "verify_artifact",
        ):
            assert chat_tool_requires_confirm(name) is False, name

    def test_writing_and_executing_tools_require_confirm(self):
        """File-writing and executing tools have to be asked first."""
        from core.tools.approval import chat_tool_requires_confirm

        for name in (
            "write_file", "edit_file", "run_tests",
            "run_sandboxed_code", "scaffold_project", "create_pdf",
            "create_docx", "create_xlsx", "generate_chart", "generate_image",
            "build_document", "export_source_brief", "create_source_notebook",
        ):
            assert chat_tool_requires_confirm(name) is True, name

    def test_self_gated_vision_browser_cluster_not_double_prompted(self):
        """The vision/browser cluster gates itself via check_sandbox — no second
        dialog from the chat gate."""
        from core.tools.approval import chat_tool_requires_confirm

        for name in (
            "vision_click", "vision_type", "take_screenshot",
            "browser_go", "browser_click", "browser_type", "browser_press",
            "browser_screenshot",
        ):
            assert chat_tool_requires_confirm(name) is False, name

    def test_unknown_and_mcp_tools_are_gated(self):
        """Unknown == unsafe: the MCP namespace and foreign names get asked."""
        from core.tools.approval import chat_tool_requires_confirm

        assert chat_tool_requires_confirm("mcp_github_create_issue") is True
        assert chat_tool_requires_confirm("totally_unknown_tool") is True

    @pytest.mark.asyncio
    async def test_web_search_flows_unprompted_on_chat_path(self):
        """
        GIVEN  web_search (read-only) is requested without on_tool_confirm
        WHEN   chat_with_tools runs
        THEN   web_search executes (no dialog, no deny)
        """
        first = _make_ollama_response(
            tool_calls=[_make_tool_call("web_search", {"query": "test"})]
        )
        second = _make_ollama_response(content="Suchergebnis ok.")
        executor = AsyncMock(return_value="Treffer")

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            client = AsyncMock()
            client.chat = AsyncMock(side_effect=[first, second])
            MockClient.return_value = client
            with patch.dict("core.tools.registry.TOOL_MAP", {"web_search": executor}, clear=False):
                await chat_with_tools(
                    model="phi4-mini",
                    history=[{"role": "user", "content": "such das"}],
                    on_chunk=lambda t: None,
                )

        executor.assert_awaited_once()


# Mutating tool WITHOUT approval_policy → gate via on_tool_confirm

class TestMutatingToolGate:

    @pytest.mark.asyncio
    async def test_mutating_tool_without_confirm_callback_is_denied(self):
        """
        GIVEN  the model asks for write_file, no on_tool_confirm passed
        WHEN   chat_with_tools runs
        THEN   write_file is NOT executed
        AND    the tool result for the model carries [TOOL-DENIED]
        """
        first = _make_ollama_response(
            tool_calls=[_make_tool_call("write_file", {"path": "x.txt", "content": "hi"})]
        )
        second = _make_ollama_response(content="Verstanden.")
        executor = AsyncMock(return_value="geschrieben")

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            client = AsyncMock()
            client.chat = AsyncMock(side_effect=[first, second])
            MockClient.return_value = client
            with patch.dict("core.tools.registry.TOOL_MAP", {"write_file": executor}, clear=False):
                result = await chat_with_tools(
                    model="phi4-mini",
                    history=[{"role": "user", "content": "Schreib x.txt"}],
                    on_chunk=lambda t: None,
                )

        executor.assert_not_awaited()
        tool_msgs = [m for m in _tool_messages_from_second_call(client) if m.get("role") == "tool"]
        assert tool_msgs, "Modell bekam kein Tool-Result zurück"
        assert "[TOOL-DENIED]" in tool_msgs[0]["content"]
        assert result == "Verstanden."

    @pytest.mark.asyncio
    async def test_mutating_tool_approved_by_callback_executes(self):
        """
        GIVEN  on_tool_confirm returns True
        WHEN   chat_with_tools executes write_file
        THEN   the executor is called 1x with the arguments
        """
        first = _make_ollama_response(
            tool_calls=[_make_tool_call("write_file", {"path": "x.txt", "content": "hi"})]
        )
        second = _make_ollama_response(content="Erledigt.")
        executor = AsyncMock(return_value="geschrieben")
        confirm = AsyncMock(return_value=True)

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            client = AsyncMock()
            client.chat = AsyncMock(side_effect=[first, second])
            MockClient.return_value = client
            with patch.dict("core.tools.registry.TOOL_MAP", {"write_file": executor}, clear=False):
                result = await chat_with_tools(
                    model="phi4-mini",
                    history=[{"role": "user", "content": "Schreib x.txt"}],
                    on_chunk=lambda t: None,
                    on_tool_confirm=confirm,
                )

        executor.assert_awaited_once()
        assert confirm.await_args.args == ("write_file", {"path": "x.txt", "content": "hi"})
        assert result == "Erledigt."

    @pytest.mark.asyncio
    async def test_mutating_tool_denied_by_callback_not_executed(self):
        """
        GIVEN  on_tool_confirm returns False
        WHEN   chat_with_tools executes write_file
        THEN   the executor is NOT called, the tool result carries [TOOL-DENIED]
        """
        first = _make_ollama_response(
            tool_calls=[_make_tool_call("write_file", {"path": "x.txt", "content": "hi"})]
        )
        second = _make_ollama_response(content="Okay, dann nicht.")
        executor = AsyncMock(return_value="geschrieben")
        confirm = AsyncMock(return_value=False)

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            client = AsyncMock()
            client.chat = AsyncMock(side_effect=[first, second])
            MockClient.return_value = client
            with patch.dict("core.tools.registry.TOOL_MAP", {"write_file": executor}, clear=False):
                await chat_with_tools(
                    model="phi4-mini",
                    history=[{"role": "user", "content": "Schreib x.txt"}],
                    on_chunk=lambda t: None,
                    on_tool_confirm=confirm,
                )

        executor.assert_not_awaited()
        tool_msgs = [m for m in _tool_messages_from_second_call(client) if m.get("role") == "tool"]
        assert "[TOOL-DENIED]" in tool_msgs[0]["content"]

    @pytest.mark.asyncio
    async def test_safe_tool_never_triggers_confirm(self):
        """
        GIVEN  read_file (SAFE, read-only) is requested, on_tool_confirm present
        WHEN   chat_with_tools executes it
        THEN   on_tool_confirm is NEVER called, the executor runs 1x
        """
        first = _make_ollama_response(
            tool_calls=[_make_tool_call("read_file", {"path": "x.txt"})]
        )
        second = _make_ollama_response(content="Inhalt gelesen.")
        executor = AsyncMock(return_value="Inhalt")
        confirm = AsyncMock(return_value=False)

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            client = AsyncMock()
            client.chat = AsyncMock(side_effect=[first, second])
            MockClient.return_value = client
            with patch.dict("core.tools.registry.TOOL_MAP", {"read_file": executor}, clear=False):
                await chat_with_tools(
                    model="phi4-mini",
                    history=[{"role": "user", "content": "Lies x.txt"}],
                    on_chunk=lambda t: None,
                    on_tool_confirm=confirm,
                )

        confirm.assert_not_awaited()
        executor.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_run_shell_still_uses_shell_confirm_path(self):
        """
        GIVEN  run_shell with on_shell_confirm set (pre-existing behaviour)
        WHEN   chat_with_tools runs
        THEN   on_tool_confirm is NOT used for run_shell (no double gate)
        AND    execute_confirmed_shell receives confirmed=True from the callback
        """
        first = _make_ollama_response(
            tool_calls=[_make_tool_call("run_shell", {"command": "ls"})]
        )
        second = _make_ollama_response(content="Da sind Dateien.")
        shell_exec = AsyncMock(return_value="file.txt")
        shell_confirm = AsyncMock(return_value=True)
        tool_confirm = AsyncMock(return_value=True)

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            client = AsyncMock()
            client.chat = AsyncMock(side_effect=[first, second])
            MockClient.return_value = client
            with patch("core.chat.execute_confirmed_shell", shell_exec):
                await chat_with_tools(
                    model="phi4-mini",
                    history=[{"role": "user", "content": "ls"}],
                    on_chunk=lambda t: None,
                    on_shell_confirm=shell_confirm,
                    on_tool_confirm=tool_confirm,
                )

        tool_confirm.assert_not_awaited()
        shell_confirm.assert_called_once_with("ls")
        shell_exec.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_approval_policy_path_not_double_gated(self):
        """
        GIVEN  approval_policy set (CLI path), on_tool_confirm NOT passed
        WHEN   chat_with_tools executes write_file
        THEN   execute_tool receives the policy (the gate runs there as before) —
               the chat gate does not fire on top of it and does not block
        """
        first = _make_ollama_response(
            tool_calls=[_make_tool_call("write_file", {"path": "x.txt", "content": "hi"})]
        )
        second = _make_ollama_response(content="Fertig.")
        execute_spy = AsyncMock(return_value="geschrieben")
        policy = MagicMock(name="cli-policy")

        with patch("core.chat.ollama.AsyncClient") as MockClient:
            client = AsyncMock()
            client.chat = AsyncMock(side_effect=[first, second])
            MockClient.return_value = client
            with patch("core.chat.execute_tool", execute_spy):
                await chat_with_tools(
                    model="phi4-mini",
                    history=[{"role": "user", "content": "Schreib x.txt"}],
                    on_chunk=lambda t: None,
                    approval_policy=policy,
                )

        execute_spy.assert_awaited_once()
        assert execute_spy.await_args.args[0] == "write_file"
        assert execute_spy.await_args.kwargs.get("policy") is policy
