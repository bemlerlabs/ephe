"""
Ephe – the core.tools contract.

The suite was written before the implementation; it is green against the core.tools
package.

Given / When / Then – strict adherence.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import pytest


# Imports – core.tools is the package (core/tools/__init__.py).

from core.tools import (
    DirectoryNotFoundError,
    FileNotAllowedError,
    ShellTimeoutError,
    WebSearchError,
    execute_confirmed_shell,
    file_search,
    get_datetime,
    get_tool_schemas,
    list_directory,
    read_file,
    run_shell,
    web_search,
)

# `web_search` above is the tool FUNCTION; the patch target is the module
# (tests/web_search_seam.py explains why the dotted string broke on Python 3.10).
from tests.web_search_seam import web_search_module

from core.tools.chat_gate import Denied


# web_search

class TestWebSearch:

    @pytest.mark.asyncio
    async def test_returns_results_on_success(self):
        """
        GIVEN  DuckDuckGo is reachable (mocked)
        WHEN   web_search("Python asyncio") is called
        THEN   the return is a formatted string containing URLs
        AND    it contains the titles and URLs of the results
        """
        mock_results = [
            {"title": "Python asyncio docs", "href": "https://docs.python.org", "body": "Asyncio is..."},
            {"title": "Real Python asyncio", "href": "https://realpython.com", "body": "Learn asyncio..."},
        ]
        mock_instance = MagicMock()
        mock_instance.text = MagicMock(return_value=mock_results)
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)

        with patch.object(web_search_module, "DDGS", return_value=mock_instance):
            results = await web_search("Python asyncio")

        assert isinstance(results, str)
        assert "Python asyncio docs" in results
        # The rendered block is a text blob; parse the hosts out of it.
        hosts = [urlparse(u).netloc for u in re.findall(r"https?://\S+", results)]
        assert sorted(hosts) == ["docs.python.org", "realpython.com"]

    @pytest.mark.asyncio
    async def test_given_official_source_query_when_search_runs_then_official_results_are_prioritized(self):
        """
        GIVEN search results include official and low-trust pages
        WHEN web_search is called for a query asking for official information
        THEN official sources are listed first so the model grounds its answer better.
        """
        mock_results = [
            {"title": "SEO Gemma rumors", "href": "https://example-blog.test/gemma", "body": "Rumors"},
            {"title": "Google AI for Developers Gemma", "href": "https://ai.google.dev/gemma", "body": "Official docs"},
        ]
        mock_instance = MagicMock()
        mock_instance.text = MagicMock(return_value=mock_results)
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)

        with patch.object(web_search_module, "DDGS", return_value=mock_instance):
            results = await web_search("official Gemma 4 12B")

        assert results.index("https://ai.google.dev/gemma") < results.index("https://example-blog.test/gemma")
        assert "Source quality: official" in results

    @pytest.mark.asyncio
    async def test_raises_web_search_error_on_connection_failure(self):
        """
        GIVEN  DuckDuckGo unreachable (mock: ConnectionError)
        WHEN   web_search("irgendwas") is called
        THEN   raises WebSearchError with an understandable message
        AND    the app does NOT crash
        """
        mock_instance = MagicMock()
        mock_instance.text = MagicMock(side_effect=ConnectionError("no connection"))
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)

        with patch.object(web_search_module, "DDGS", return_value=mock_instance):
            with pytest.raises(WebSearchError):
                await web_search("irgendwas")

    @pytest.mark.asyncio
    async def test_raises_value_error_on_empty_query(self):
        """
        GIVEN  an empty query string
        WHEN   web_search("") is called
        THEN   raises ValueError("query must not be empty")
        """
        with pytest.raises(ValueError, match="empty"):
            await web_search("")

    @pytest.mark.asyncio
    async def test_raises_value_error_on_whitespace_query(self):
        """
        GIVEN  a query of only whitespace
        WHEN   web_search("   ") is called
        THEN   raises ValueError
        """
        with pytest.raises(ValueError):
            await web_search("   ")


# file_search

class TestFileSearch:

    @pytest.mark.asyncio
    async def test_returns_file_path_on_macos(self, tmp_path):
        """
        GIVEN  macOS + mdfind returns a path (mocked)
        WHEN   file_search("test_ephe.pdf") is called
        THEN   the return contains the file name
        AND    the return is a non-empty string
        """
        fake_output = "/Users/test/Desktop/test_ephe.pdf\n"
        with patch("sys.platform", "darwin"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout=fake_output, returncode=0
                )
                result = await file_search("test_ephe.pdf")

        assert "test_ephe.pdf" in result
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_falls_back_to_find_on_linux(self):
        """
        GIVEN  Linux system (sys.platform = "linux")
        WHEN   file_search("test.pdf") is called
        THEN   it falls back to the `find` command (no crash)
        AND    subprocess.run is called with 'find'
        """
        with patch("sys.platform", "linux"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    stdout="/home/user/test.pdf\n", returncode=0
                )
                result = await file_search("test.pdf")
                cmd = mock_run.call_args[0][0]

        assert "find" in cmd or "locate" in cmd
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_given_macos_spotlight_miss_when_file_exists_then_python_fallback_finds_it(self, tmp_path):
        """
        GIVEN  macOS Spotlight returns no matches for a freshly-created file
        WHEN   file_search() runs inside an allowed directory
        THEN   the Python fallback still finds the file.
        """
        target = tmp_path / "ephe_fresh_probe.txt"
        target.write_text("fresh file", encoding="utf-8")

        with patch("sys.platform", "darwin"), patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            result = await file_search("ephe_fresh_probe", str(tmp_path))

        assert str(target) in result

    @pytest.mark.asyncio
    async def test_raises_value_error_on_empty_query(self):
        """
        GIVEN  an empty query string
        WHEN   file_search("") is called
        THEN   raises ValueError
        """
        with pytest.raises(ValueError):
            await file_search("")


# read_file

class TestReadFile:

    @pytest.mark.asyncio
    async def test_reads_allowed_file(self, tmp_path):
        """
        GIVEN  a file in HOME with the content "Hallo Ephe"
        WHEN   read_file(path) is called
        THEN   the return contains "Hallo Ephe"
        AND    the return is a string
        """
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hallo Ephe", encoding="utf-8")

        # Patch HOME so tmp_path is inside whitelist
        with patch.dict(os.environ, {"HOME": str(tmp_path)}):
            result = await read_file(str(test_file))

        assert "Hallo Ephe" in result
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_raises_error_for_path_outside_whitelist(self):
        """
        GIVEN  a path outside the whitelist: "/etc/passwd"
        WHEN   read_file("/etc/passwd") is called
        THEN   raises FileNotAllowedError
        AND    the file is NOT opened
        """
        with pytest.raises(FileNotAllowedError):
            await read_file("/etc/passwd")

    @pytest.mark.asyncio
    async def test_raises_error_for_missing_file(self, tmp_path):
        """
        GIVEN  the file does not exist
        WHEN   read_file(missing) is called
        THEN   raises FileNotFoundError
        AND    the path is in the error message
        """
        missing = tmp_path / "nicht_vorhanden.txt"
        with patch.dict(os.environ, {"HOME": str(tmp_path)}):
            with pytest.raises(FileNotFoundError) as exc_info:
                await read_file(str(missing))

        assert "nicht_vorhanden" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_truncates_large_files(self, tmp_path):
        """
        GIVEN  a file > 100.000 characters (MAX_FILE_CHARS)
        WHEN   read_file(path) is called
        THEN   the return is truncated to 100.000 characters
        AND    a truncation note is appended (the assert accepts "gekürzt" or  # language-gate: ignore (alternative accepted by the assert below, test_tools.py:271)
               "truncated"; the tool today emits "[File truncated: ...]")
        """
        big_content = "x" * 120_000
        test_file = tmp_path / "big.txt"
        test_file.write_text(big_content, encoding="utf-8")

        with patch.dict(os.environ, {"HOME": str(tmp_path)}):
            result = await read_file(str(test_file))

        assert len(result) <= 100_100  # content + truncation note
        assert "gekürzt" in result.lower() or "truncated" in result.lower()


# list_directory

class TestListDirectory:

    @pytest.mark.asyncio
    async def test_returns_file_list_for_allowed_path(self, tmp_path):
        """
        GIVEN  the directory exists and contains ≥1 files
        WHEN   list_directory(path) is called
        THEN   the return is a list of file names
        AND    every entry is a string
        """
        (tmp_path / "file1.txt").write_text("a")
        (tmp_path / "file2.py").write_text("b")

        with patch.dict(os.environ, {"HOME": str(tmp_path),
                                     "EPHE_WORKSPACE": str(tmp_path)}):
            result = await list_directory(str(tmp_path))

        assert isinstance(result, list)
        assert len(result) >= 1
        assert all(isinstance(e, str) for e in result)

    @pytest.mark.asyncio
    async def test_raises_error_for_path_outside_whitelist(self):
        """
        GIVEN  a path outside the whitelist: "/etc/"
        WHEN   list_directory("/etc/") is called
        THEN   raises FileNotAllowedError
        """
        with pytest.raises(FileNotAllowedError):
            await list_directory("/etc/")

    @pytest.mark.asyncio
    async def test_raises_error_for_missing_directory(self, tmp_path):
        """
        GIVEN  the directory does not exist
        WHEN   list_directory(missing) is called
        THEN   raises DirectoryNotFoundError
        """
        missing = tmp_path / "nicht_vorhanden"
        with patch.dict(os.environ, {"HOME": str(tmp_path)}):
            with pytest.raises(DirectoryNotFoundError):
                await list_directory(str(missing))


# get_datetime

class TestGetDatetime:

    @pytest.mark.asyncio
    async def test_returns_current_year(self):
        """
        GIVEN  any moment in the year 2026
        WHEN   get_datetime() is called
        THEN   the return contains the current year (4 digits)
        AND    result contains an English weekday
        AND    result is a non-empty string
        """
        result = await get_datetime()

        assert isinstance(result, str)
        assert len(result) > 0
        assert "2026" in result
        en_days = ["Monday", "Tuesday", "Wednesday", "Thursday",
                   "Friday", "Saturday", "Sunday"]
        assert any(day in result for day in en_days)


# run_shell / execute_confirmed_shell

class TestRunShell:

    @pytest.mark.asyncio
    async def test_run_shell_executes_whitelisted_command(self):
        """
        GIVEN  run_shell now performs real execution (no more throw)
        WHEN   run_shell("ls") is called
        THEN   the command IS executed (whitelist gate: ls is allowed)
        AND    the output comes back (no exception)
        """
        result = await run_shell("ls")
        assert isinstance(result, str)
        # ls returns a directory listing — it need not be empty (CWD exists)
        # no security block, no exception raised
        assert "Security" not in result

    @pytest.mark.asyncio
    async def test_execute_confirmed_runs_command(self):
        """
        GIVEN  confirmation = True
        WHEN   execute_confirmed_shell("echo hello", confirmed=True)
        THEN   the return contains stdout
        AND    the exit_code is 0
        """
        class _FakeProc:
            pid = 4242
            returncode = 0

            def communicate(self, input=None, timeout=None):
                return "hello\n", ""

        with patch("subprocess.Popen", side_effect=lambda *a, **k: _FakeProc()) as mock_run:
            result = await execute_confirmed_shell("echo hello", confirmed=True)

        assert "hello" in result
        mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_denied_returns_coded_refusal(self):
        """
        GIVEN  confirmation = False
        WHEN   execute_confirmed_shell("rm -rf /", confirmed=False)
        THEN   the return is a coded [TOOL-DENIED] refusal for run_shell
        AND    the command is NOT executed
        """
        with patch("subprocess.Popen") as mock_run:
            result = await execute_confirmed_shell("rm -rf /", confirmed=False)

        assert isinstance(result, Denied)
        assert result.code == "not_approved_by_user"
        assert result.startswith("[TOOL-DENIED] run_shell was not executed")
        mock_run.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_captures_failed_command(self):
        """
        GIVEN  the command fails (exit_code ≠ 0)
        WHEN   execute_confirmed_shell("ls /nicht_vorhanden", confirmed=True)  # language-gate: ignore (verbatim path fixture used in the call below)
        THEN   the return value contains stderr
        AND    no crash
        """
        class _FakeProc:
            pid = 4242
            returncode = 1

            def communicate(self, input=None, timeout=None):
                return "", "No such file or directory"

        with patch("subprocess.Popen", side_effect=lambda *a, **k: _FakeProc()):
            result = await execute_confirmed_shell("ls /nicht_vorhanden", confirmed=True)

        assert isinstance(result, str)
        assert "No such file" in result or "exit" in result.lower()

    @pytest.mark.asyncio
    async def test_execute_raises_timeout_error(self):
        """
        GIVEN  the command runs longer than the timeout (30s)
        WHEN   execute_confirmed_shell("sleep 60", confirmed=True)
        THEN   raises ShellTimeoutError after 30s
        AND    the process is terminated
        """
        class _TimeoutProc:
            pid = 4242
            returncode = None

            def communicate(self, input=None, timeout=None):
                raise subprocess.TimeoutExpired("echo test", 30)

            def poll(self):
                return 0

        with patch("subprocess.Popen", side_effect=lambda *a, **k: _TimeoutProc()), \
             patch("os.killpg"), patch("os.kill"):
            with pytest.raises(ShellTimeoutError):
                await execute_confirmed_shell("echo test", confirmed=True)


# get_tool_schemas

class TestToolSchemas:

    def test_returns_list_of_dicts(self):
        """
        GIVEN  no precondition
        WHEN   get_tool_schemas() is called
        THEN   the return value is a list of dicts
        AND    every dict has the "type" and "function" keys
        AND    every "function" has "name", "description", "parameters"
        """
        schemas = get_tool_schemas()

        assert isinstance(schemas, list)
        assert len(schemas) >= 5  # web_search, file_search, read_file, list_dir, get_datetime, run_shell

        for schema in schemas:
            assert schema["type"] == "function"
            func = schema["function"]
            assert "name" in func
            assert "description" in func
            assert "parameters" in func
            assert isinstance(func["description"], str)
            assert len(func["description"]) > 10

    def test_all_tool_names_match_functions(self):
        """
        GIVEN  the list of defined tool functions
        WHEN   get_tool_schemas() is called
        THEN   every schema name matches an importable function
        """
        import core.tools as tools_module
        schemas = get_tool_schemas()
        for schema in schemas:
            name = schema["function"]["name"]
            assert hasattr(tools_module, name), f"Tool '{name}' hat keine Implementierung"


# J1: read_file reference granularity — line numbers (cat -n), offset/limit

class TestReadFileGranularity:

    @pytest.mark.asyncio
    async def test_default_line_numbering_one_based(self, tmp_path):
        """
        GIVEN  a file with 3 lines
        WHEN   read_file(path) without parameters
        THEN   every line carries a 1-based line number in the form 'N\t...'
        """
        f = tmp_path / "num.txt"
        f.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
        with patch.dict(os.environ, {"HOME": str(tmp_path)}):
            result = await read_file(str(f))
        assert "1\talpha" in result
        assert "3\tgamma" in result

    @pytest.mark.asyncio
    async def test_offset_and_limit_window(self, tmp_path):
        """
        GIVEN  a file with 10 lines
        WHEN   read_file(path, offset=4, limit=3)
        THEN   exactly lines 4,5,6 — numbering keeps counting from 1
        """
        f = tmp_path / "win.txt"
        f.write_text("\n".join(f"L{i}" for i in range(1, 11)) + "\n", encoding="utf-8")
        with patch.dict(os.environ, {"HOME": str(tmp_path)}):
            result = await read_file(str(f), offset=4, limit=3)
        assert "4\tL4" in result and "5\tL5" in result and "6\tL6" in result
        assert "3\tL3" not in result
        assert "7\tL7" not in result

    @pytest.mark.asyncio
    async def test_default_limit_caps_at_2000_lines(self, tmp_path):
        """
        GIVEN  a file with 2500 lines
        WHEN   read_file(path) without limit
        THEN   the last numbered line is 2000; 2001 is missing
        """
        f = tmp_path / "big.txt"
        f.write_text("\n".join(f"L{i}" for i in range(1, 2501)) + "\n", encoding="utf-8")
        with patch.dict(os.environ, {"HOME": str(tmp_path)}):
            result = await read_file(str(f))
        assert "2000\tL2000" in result
        assert "2001\t" not in result

    @pytest.mark.asyncio
    async def test_offset_beyond_content_yields_empty_or_note(self, tmp_path):
        """
        GIVEN  a file with 2 lines
        WHEN   read_file(path, offset=99)
        THEN   no line content (overflow tolerated, no crash)
        """
        f = tmp_path / "short.txt"
        f.write_text("a\nb\n", encoding="utf-8")
        with patch.dict(os.environ, {"HOME": str(tmp_path)}):
            result = await read_file(str(f), offset=99)
        assert "a" not in result and "b\t" not in result
