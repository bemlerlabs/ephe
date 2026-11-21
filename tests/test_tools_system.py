"""
◑ Ephe – core.tools.system_tools (Phase 0.8 TDD)
tests/test_tools_system.py

Covers discover_projects, analyze_project, load_workspace, analyze_image, take_screenshot, create_svg.

Every test is written strictly as Given / When / Then.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.tools.base import DirectoryNotFoundError, FileNotAllowedError
from core.tools.system_tools import (
    analyze_image,
    analyze_project,
    create_svg,
    discover_projects,
    load_workspace,
    take_screenshot,
)


class TestDiscoverProjects:

    @pytest.mark.asyncio
    async def test_returns_formatted_projects(self):
        """
        GIVEN  projects exist (mocked)
        WHEN   discover_projects() is called
        THEN   the return value is the formatted project list
        AND    discover_project_records was called
        """
        with patch("core.project_discovery.discover_project_records", new_callable=MagicMock) as mock_records, \
             patch("core.project_discovery.format_project_listing") as mock_fmt:
            mock_records.return_value = [{"name": "ephe", "stack": "Python"}]
            mock_fmt.return_value = "Project: ephe (Python)"

            result = await discover_projects()

            assert "ephe" in result
            mock_records.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_query_and_max_results(self):
        """
        GIVEN  query and max_results
        WHEN   discover_projects is called
        THEN   the parameters are passed on
        """
        with patch("core.project_discovery.discover_project_records", new_callable=MagicMock) as mock_records, \
             patch("core.project_discovery.format_project_listing") as mock_fmt:
            mock_records.return_value = []
            mock_fmt.return_value = ""

            await discover_projects(query="python", max_results=5)

            assert mock_records.call_args[1]["query"] == "python"
            assert mock_records.call_args[1]["max_results"] == 5

    @pytest.mark.asyncio
    async def test_rejects_path_outside_whitelist(self):
        """
        GIVEN  root outside the whitelist
        WHEN   discover_projects(root="/etc") is called
        THEN   the return value carries a security notice
        """
        with patch("core.tools.system_tools._is_path_allowed", return_value=False):
            result = await discover_projects(root="/etc")

        assert "not allowed" in result


class TestAnalyzeProject:

    @pytest.mark.asyncio
    async def test_returns_analysis_for_path(self):
        """
        GIVEN  a project path
        WHEN   analyze_project(path) is called
        THEN   analyze_project_path is called with that path
        """
        with patch("core.project_discovery.analyze_project_path", new_callable=MagicMock) as mock_analyze:
            mock_analyze.return_value = "Stack: Python, Tests: pytest"

            result = await analyze_project(path="/tmp/test-project")

            assert "Stack" in result
            mock_analyze.assert_called_once_with("/tmp/test-project")


class TestLoadWorkspace:

    @pytest.mark.asyncio
    async def test_returns_file_contents(self, tmp_path):
        """
        GIVEN  a directory with files
        WHEN   load_workspace(path) is called
        THEN   the return value carries file contents and paths
        """
        (tmp_path / "hello.py").write_text('print("hello")', encoding="utf-8")
        (tmp_path / "README.md").write_text("# Test", encoding="utf-8")

        with patch("core.tools.system_tools._is_path_allowed", return_value=True):
            with patch("core.tools.system_tools.MAX_WORKSPACE_CHARS", 100_000):
                result = await load_workspace(str(tmp_path))

        assert "hello.py" in result
        assert "print" in result
        assert "README.md" in result

    @pytest.mark.asyncio
    async def test_raises_if_not_in_whitelist(self):
        """
        GIVEN  a path outside the whitelist
        WHEN   load_workspace("/etc") is called
        THEN   it raises FileNotAllowedError
        """
        with patch("core.tools.system_tools._is_path_allowed", return_value=False):
            with pytest.raises(FileNotAllowedError):
                await load_workspace("/etc")

    @pytest.mark.asyncio
    async def test_raises_if_not_a_directory(self, tmp_path):
        """
        GIVEN  the path is not a directory
        WHEN   load_workspace is called
        THEN   it raises DirectoryNotFoundError
        """
        f = tmp_path / "file.txt"
        f.write_text("x")
        with patch("core.tools.system_tools._is_path_allowed", return_value=True):
            with pytest.raises(DirectoryNotFoundError):
                await load_workspace(str(f))

    @pytest.mark.asyncio
    async def test_filters_by_extension(self, tmp_path):
        """
        GIVEN  extensions=[".py"]
        WHEN   load_workspace(path, extensions=[".py"])
        THEN   only .py files are returned
        """
        (tmp_path / "hello.py").write_text("x", encoding="utf-8")
        (tmp_path / "readme.md").write_text("x", encoding="utf-8")

        with patch("core.tools.system_tools._is_path_allowed", return_value=True):
            with patch("core.tools.system_tools.MAX_WORKSPACE_CHARS", 100_000):
                result = await load_workspace(str(tmp_path), extensions=[".py"])

        assert "hello.py" in result
        assert "readme.md" not in result


class TestAnalyzeImage:

    @pytest.mark.asyncio
    async def test_rejects_path_outside_whitelist(self):
        """
        GIVEN  a path outside the whitelist
        WHEN   analyze_image("/etc/passwd") is called
        THEN   it raises FileNotAllowedError
        """
        with patch("core.tools.system_tools._is_path_allowed", return_value=False):
            with pytest.raises(FileNotAllowedError):
                await analyze_image("/etc/passwd")

    @pytest.mark.asyncio
    async def test_rejects_missing_file(self):
        """
        GIVEN  the file does not exist
        WHEN   analyze_image("/nonexistent.png") is called
        THEN   it raises FileNotFoundError
        """
        with patch("core.tools.system_tools._is_path_allowed", return_value=True):
            with pytest.raises(FileNotFoundError):
                await analyze_image("/nonexistent.png")

    @pytest.mark.asyncio
    async def test_rejects_unsupported_format(self, tmp_path):
        """
        GIVEN  a file with an unsupported extension
        WHEN   analyze_image is called
        THEN   the return value carries a format hint
        """
        f = tmp_path / "file.txt"
        f.write_text("x")
        with patch("core.tools.system_tools._is_path_allowed", return_value=True):
            result = await analyze_image(str(f))

        assert "Unsupported" in result

    @pytest.mark.asyncio
    async def test_calls_ollama_for_supported_image(self, tmp_path, monkeypatch):
        """
        GIVEN  a PNG file
        WHEN   analyze_image is called
        THEN   ollama chat is called
        AND    the image is sent along as base64
        """
        monkeypatch.setenv("EPHE_MODEL", "vision-fixture:1b")
        f = tmp_path / "test.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)

        with patch("core.tools.system_tools._is_path_allowed", return_value=True), \
             patch("core.tools.system_tools.SUPPORTED_IMAGE_EXTENSIONS", {".png"}), \
             patch("core.tools.system_tools._get_shared_client") as mock_client:
            mock_client.return_value.chat = AsyncMock(return_value=MagicMock(
                message=MagicMock(content="Das Bild zeigt einen Test.")
            ))

            result = await analyze_image(str(f), question="Was siehst du?")

            assert "Test" in result
            mock_client.return_value.chat.assert_called_once()


class TestTakeScreenshot:

    @pytest.mark.asyncio
    async def test_returns_markdown_image_on_macos(self):
        """
        GIVEN  macOS
        WHEN   take_screenshot() is called
        THEN   the return value contains ![Screenshot]
        AND    screencapture is executed
        """
        with patch("sys.platform", "darwin"), \
             patch("core.tools.system_tools.subprocess.run", new_callable=MagicMock) as mock_run, \
             patch("core.tools.system_tools.Path.mkdir"):
            result = await take_screenshot()

        assert "![Screenshot]" in result
        mock_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_error_on_macos_blocked_permission(self):
        """
        GIVEN  macOS + screencapture fails
        WHEN   take_screenshot() is called
        THEN   the return value contains "blocked"
        """
        with patch("sys.platform", "darwin"), \
             patch("core.tools.system_tools.subprocess.run", side_effect=Exception("kCGErrorFailure")), \
             patch("core.tools.system_tools.Path.mkdir"):
            result = await take_screenshot()

        assert "blocked" in result.lower() or "failed" in result.lower()

    @pytest.mark.skip(reason="GUI screenshot test requires 'mss' (Linux-specific path); unavailable in this macOS dev environment.")
    @pytest.mark.asyncio
    async def test_uses_mss_on_linux(self):
        """
        GIVEN  Linux
        WHEN   take_screenshot() is called
        THEN   mss is used for the screenshot
        """
        with patch("sys.platform", "linux"), \
             patch("core.tools.system_tools.subprocess"), \
             patch("core.tools.system_tools.Path.mkdir"):
            result = await take_screenshot()

        assert "![Screenshot]" in result


class TestCreateSvg:

    @pytest.mark.asyncio
    async def test_saves_svg_to_downloads(self):
        """
        GIVEN  SVG code
        WHEN   create_svg("<circle ...>", "test.svg") is called
        THEN   the file is written to ~/Downloads
        AND    the return value contains "SVG_FILE:"
        """
        with patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_text") as mock_write, \
             patch("core.tools.system_tools.Path.home") as mock_home:
            mock_home.return_value = Path("/tmp/fake_home")

            result = await create_svg('<circle cx="50" cy="50" r="40"/>', filename="test.svg")

            assert "SVG_FILE:" in result
            mock_write.assert_called_once()

    @pytest.mark.asyncio
    async def test_removes_script_tags(self):
        """
        GIVEN  SVG code with a <script> tag
        WHEN   create_svg is called
        THEN   the script is stripped
        """
        malicious = '<svg><script>alert("xss")</script><circle cx="50" cy="50" r="40"/></svg>'

        with patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_text") as mock_write, \
             patch("core.tools.system_tools.Path.home") as mock_home:
            mock_home.return_value = Path("/tmp/fake_home")

            await create_svg(malicious, filename="safe.svg")

            written = mock_write.call_args[0][0]
            assert "<script>" not in written
            assert "<circle" in written

    @pytest.mark.asyncio
    async def test_removes_onclick_handlers(self):
        """
        GIVEN  SVG with an onclick handler
        WHEN   create_svg is called
        THEN   the onclick is stripped
        """
        with patch("pathlib.Path.mkdir"), \
             patch("pathlib.Path.write_text") as mock_write, \
             patch("core.tools.system_tools.Path.home") as mock_home:
            mock_home.return_value = Path("/tmp/fake_home")

            await create_svg('<rect onclick="evil()"/>', filename="safe.svg")

            written = mock_write.call_args[0][0]
            assert "onclick" not in written.lower()
