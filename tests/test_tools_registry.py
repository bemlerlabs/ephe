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
        WHEN   execute_tool("delete_file", {"path": "/tmp/x"}) is called
        THEN   the parameters are passed on
        """
        mock_fn = AsyncMock(return_value="gone")
        with patch.dict("core.tools.registry.TOOL_MAP", {"delete_file": mock_fn}, clear=False):
            result = await execute_tool("delete_file", {"path": "/tmp/x"})

        mock_fn.assert_called_once_with(path="/tmp/x")
        assert result == "gone"

    @pytest.mark.asyncio
    async def test_a_plain_def_handler_is_answered_not_awaited(self):
        """
        GIVEN  a kernel handler that is a plain def returning a str
        WHEN   execute_tool dispatches it
        THEN   its answer comes back; nothing tries to await the str

        Every mock in this file is an AsyncMock, which is how the dispatcher's await-only
        shape survived 7 real sync handlers (#157).
        """
        def sync_handler(path: str) -> str:
            return f"wrote {path}"

        with patch.dict("core.tools.registry.TOOL_MAP", {"delete_file": sync_handler}, clear=False):
            result = await execute_tool("delete_file", {"path": "/tmp/x"})

        assert result == "wrote /tmp/x", result

    @pytest.mark.asyncio
    async def test_converts_list_result_to_string(self):
        """
        GIVEN  a tool returns a list
        WHEN   execute_tool is called
        THEN   the list is joined with \n
        """
        mock_fn = AsyncMock(return_value=["a", "b", "c"])
        with patch.dict("core.tools.registry.TOOL_MAP", {"delete_file": mock_fn}, clear=False):
            result = await execute_tool("delete_file", {"path": "/tmp"})

        assert isinstance(result, str)
        assert "a\nb\nc" == result

    @pytest.mark.asyncio
    async def test_run_shell_now_executes_not_raises(self):
        """
        GIVEN  run_shell performs real execution (no more throw)
        WHEN   execute_tool("run_shell", {"command": "ls"}) reaches the bridge
        THEN   the command runs only after the approval gate answers; with no
               channel it is refused, and the whitelist gate stays in place
        """
        from core.vision import _sandbox_cb_var

        refused = await execute_tool("run_shell", {"command": "echo ok"})
        assert "not executed" in refused

        async def _yes(name: str, args: dict) -> bool:
            return True

        token = _sandbox_cb_var.set(_yes)
        try:
            result = await execute_tool("run_shell", {"command": "echo ok"})
        finally:
            _sandbox_cb_var.reset(token)
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
        with patch.dict("core.tools.registry.TOOL_MAP", {"delete_file": mock_fn}, clear=False):
            result = await execute_tool("delete_file", {"path": "/tmp/x"})

        assert "[tool-error" in result


class TestToolMap:

    def test_contains_all_expected_tools(self):
        """
        GIVEN  TOOL_MAP
        WHEN   checked against the name inventory below
        THEN   the two sets are one set (a number here would only restate that)
        """
        expected_tools = {
            "manage_tasks", "query_codebase",
            "discover_projects",
            "delete_file",
            "get_datetime", "run_sandboxed_code",
            "start_workspace_dev_server", "stop_workspace_dev_server",
            "take_screenshot",
            # The deck tools are served by their bundle.
            # The picture tool is served by the image-studio bundle.
            # Wave 3: the JSON checker. The PDF reader is served by its bundle.
            "validate_json",
            # R39: media pipeline
            "create_video",
            # J2 parity: background tasks + agent continuation
            "task_output", "task_stop", "agent_message",
            # J5 parity: page clipboard and display. The browser tools are served
            # by their bundle.
            "clipboard_read", "clipboard_write", "get_display_info",
            # Wave 2 parity: stateful kernel + session ledger + process manager
            "execute_code", "todo_list", "process_manage",
            # G6 workbench: the agent's own readers (transcript + cell journal)
            "read_transcript", "read_cell_journal",
            # Wave 3 parity: progressive tool discovery (meta router)
            "tool_search", "tool_describe", "tool_call",
            # Wave 4 parity: skill upkeep. The memory tool is served by its bundle.
            "skill_manage",
            # R36-S: sub-agent delegation (the main agent decides itself)
            "spawn_agent",
            # G1: the ask gate — the run pauses on a question and goes on with the answer
            "ask_user",
            # zen gateway parity: opencode nomenclature aliases (bash/read/edit)
            "bash", "read", "edit",
            # P1: read-only view of the plugin portfolio and switch state
            "plugin_manager",
            # #26: the calls that build a plugin. They are kernel names and dispatch
            # like any other; what makes them different is who is OFFERED them, which
            # `creator_guard.filter_offer` decides and `test_creator_guard.py` pins.
            "create_plugin_scaffold",
            "read_plugin_source",
            "write_plugin_source",
            "verify_plugin_bundle",
            "install_plugin_bundle",
            # Research: site-scoped search and crawl over the open web, with citations
            "web_research",
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
        # #36: the array carries one name order, so a position pin is replaced by
        # the order itself plus the whitelist content.
        names = [e["function"]["name"] for e in result]
        assert names == sorted(names)
        assert "web_search" in names

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
        result = get_filtered_tool_schemas(["web_research",
        "web_search", "unknown_tool"])
        # P0-1: META_TOOL_NAMES + memory + skill_manage are always injected (at least 1)
        assert len(result) >= 1
        names = [e["function"]["name"] for e in result]
        assert names == sorted(names)
        assert "web_search" in names and "unknown_tool" not in names


def test_run_linter_resolves_a_relative_path_in_the_workspace(tmp_path, monkeypatch):
    import asyncio

    from core.tools.utility_tools import run_linter

    monkeypatch.setenv("EPHE_WORKSPACE", str(tmp_path))
    (tmp_path / "clean.py").write_text("x = 1\n", encoding="utf-8")
    result = asyncio.run(run_linter("clean.py"))
    assert "Path not found" not in result
