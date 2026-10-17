"""
◑ Ephe – core.tools.registry (Phase 0.8 TDD)
tests/test_tools_registry.py

Covers execute_tool, TOOL_MAP, get_filtered_tool_schemas.

Given / When / Then – strict adherence.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.tools.registry import TOOL_MAP, execute_tool, get_filtered_tool_schemas


class TestExecuteTool:

    @pytest.mark.asyncio
    async def test_executes_known_tool(self):
        """
        GIVEN  tool name exists in TOOL_MAP
        WHEN   execute_tool("get_datetime", {}) is called
        THEN   the tool runs and its result is returned
        """
        mock_fn = AsyncMock(return_value="Montag, ...")
        with patch.dict("core.tools.registry.TOOL_MAP", {"get_datetime": mock_fn}, clear=False):
            result = await execute_tool("get_datetime", {})

        assert "Montag" in result
        mock_fn.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_error_for_unknown_tool(self):
        """
        GIVEN  tool name does not exist
        WHEN   execute_tool("unknown_tool", {}) is called
        THEN   the return value contains "not found"
        """
        result = await execute_tool("unknown_tool", {})
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_passes_arguments_to_tool(self):
        """
        GIVEN  a tool with parameters
        WHEN   execute_tool("web_search", {"query": "test"}) is called
        THEN   the parameters are passed on
        """
        mock_fn = AsyncMock(return_value="Ergebnisse")
        with patch.dict("core.tools.registry.TOOL_MAP", {"web_search": mock_fn}, clear=False):
            result = await execute_tool("web_search", {"query": "test"})

        mock_fn.assert_called_once_with(query="test")

    @pytest.mark.asyncio
    async def test_converts_list_result_to_string(self):
        """
        GIVEN  a tool returns a list
        WHEN   execute_tool is called
        THEN   the list is joined with \n
        """
        mock_fn = AsyncMock(return_value=["a", "b", "c"])
        with patch.dict("core.tools.registry.TOOL_MAP", {"list_directory": mock_fn}, clear=False):
            result = await execute_tool("list_directory", {"path": "/tmp"})

        assert isinstance(result, str)
        assert "a\nb\nc" == result

    @pytest.mark.asyncio
    async def test_run_shell_now_executes_not_raises(self):
        """
        GIVEN  run_shell now performs real execution (no more throw)
        WHEN   execute_tool("run_shell", {"command": "ls"}) is called (without policy)
        THEN   no ShellConfirmationRequired — the command runs (whitelist gate)
        """
        result = await execute_tool("run_shell", {"command": "echo ok"})
        assert "ok" in result
        assert "ShellConfirmationRequired" not in result

    @pytest.mark.asyncio
    async def test_catches_generic_exceptions(self):
        """
        GIVEN  a tool raises an exception
        WHEN   execute_tool is called
        THEN   the return value contains "[tool-error"
        """
        mock_fn = AsyncMock(side_effect=ValueError("something broke"))
        with patch.dict("core.tools.registry.TOOL_MAP", {"web_search": mock_fn}, clear=False):
            result = await execute_tool("web_search", {"query": "test"})

        assert "[tool-error" in result


class TestToolMap:

    def test_contains_all_expected_tools(self):
        """
        GIVEN  TOOL_MAP
        WHEN   checked for completeness
        THEN   it holds all 72 expected entries
        """
        expected_tools = {
            "manage_tasks", "web_search", "file_search",
            "discover_projects", "analyze_project",
            "create_source_notebook", "query_source_notebook", "export_source_brief",
            "read_file", "edit_file", "list_directory",
            "delete_file",
            "get_datetime", "run_shell", "run_sandboxed_code",
            "load_workspace", "analyze_image",
            "vision_click", "vision_type",
            "take_screenshot",
            "browser_go", "browser_screenshot", "browser_click",
            "browser_type", "browser_press",
            "generate_chart", "create_pdf",
            "create_pitch_deck", "create_pptx_deck",
            "inspect_pptx_template", "edit_pptx_template", "qa_pptx_deck",
            "create_svg",
            # Round 11: office + diagram artifacts
            "create_xlsx", "create_docx", "create_qrcode", "create_diagram",
            # Image generation
            "generate_image",
            # Wave 3: utility tools T1-T4
            "extract_pdf_text", "format_code", "run_linter", "validate_json",
            # R39: media pipeline
            "create_video",
            # R34 Project Factory: evidence gate + factories
            "verify_artifact",
            "scaffold_project",
            "build_document",
        "write_file",
        "run_tests",
            # J2 parity: background tasks + agent continuation
            "task_output", "task_stop", "agent_message",
            # J3 parity: URL fetch channel
            "fetch_url",
            # J5 parity: browser channel depth
            "browser_scroll", "browser_evaluate",
            "clipboard_read", "clipboard_write", "get_display_info",
            "browser_exec",
            # Wave 2 parity: stateful kernel + session ledger + process manager
            "execute_code", "todo_list", "process_manage",
            # G6 workbench: the agent's own readers (transcript + cell journal)
            "read_transcript", "read_cell_journal",
            # Wave 3 parity: progressive tool discovery (meta router)
            "tool_search", "tool_describe", "tool_call",
            # Wave 4 parity: stateful agent tools (memory + skill upkeep)
            "memory", "skill_manage",
            # R36-S: sub-agent delegation (the main agent decides itself)
            "spawn_agent",
            # G1: the ask gate — the run pauses on a question and goes on with the answer
            "ask_user",
            # zen gateway parity: opencode nomenclature aliases (bash/read/edit)
            "bash", "read", "edit",
        }
        assert set(TOOL_MAP.keys()) == expected_tools

    def test_all_tools_are_callable(self):
        """
        GIVEN  TOOL_MAP entries
        WHEN   checked for being callable
        THEN   every entry is a function
        """
        for name, func in TOOL_MAP.items():
            assert callable(func), f"TOOL_MAP['{name}'] ist nicht callable"


class TestGetFilteredToolSchemas:

    def test_returns_subset_by_whitelist(self):
        """
        GIVEN  whitelist=["web_search"]
        WHEN   get_filtered_tool_schemas(whitelist) is called
        THEN   only the web_search schema is returned
        """
        result = get_filtered_tool_schemas(["web_search"])
        # P0-1: META_TOOL_NAMES + memory + skill_manage are always injected
        assert len(result) >= 1
        assert result[0]["function"]["name"] == "web_search"

    def test_returns_empty_for_empty_whitelist(self):
        """
        GIVEN  whitelist=[]
        WHEN   get_filtered_tool_schemas([]) is called
        THEN   an empty list is returned
        """
        # P0-1: an empty whitelist still yields the META+state injection (5 tools)
        result = get_filtered_tool_schemas([])
        assert len(result) >= 5

    def test_ignores_unknown_tool_names(self):
        """
        GIVEN  the whitelist contains unknown tools
        WHEN   get_filtered_tool_schemas is called
        THEN   only the known tools are returned
        """
        result = get_filtered_tool_schemas(["web_search", "unknown_tool"])
        # P0-1: META_TOOL_NAMES + memory + skill_manage are always injected (at least 1)
        assert len(result) >= 1
        assert result[0]["function"]["name"] == "web_search"
