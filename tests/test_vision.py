"""
◑ Ephe – Vision & Workspace Tool Tests
tests/test_vision.py

TDD tests for analyze_image and load_workspace.
When/Given/Then specifications.
"""
from __future__ import annotations

import struct
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.tools import (
    analyze_image,
    load_workspace,
    FileNotAllowedError,
    DirectoryNotFoundError,
    SUPPORTED_IMAGE_EXTENSIONS,
    MAX_WORKSPACE_CHARS,
)


# Helpers

# allowed test directory inside the whitelist
_TEST_TMP = Path.home() / "tmp"
_TEST_TMP.mkdir(exist_ok=True)


def _create_minimal_png(path: Path) -> None:
    """Creates a minimal valid PNG file (1x1 pixel, red)."""
    # minimal PNG header + IHDR + IDAT + IEND
    header = b'\x89PNG\r\n\x1a\n'
    # IHDR chunk
    ihdr_data = struct.pack('>IIBBBB B', 1, 1, 8, 2, 0, 0, 0)
    ihdr_crc = 0x1CFC26  # pre-computed for 1x1 RGB
    ihdr = struct.pack('>I', 13) + b'IHDR' + ihdr_data + struct.pack('>I', ihdr_crc)
    # Write minimal valid PNG-ish bytes (good enough for base64 test)
    path.write_bytes(header + ihdr)


# analyze_image Tests

class TestAnalyzeImage:
    """Vision tool for image analysis."""

    @pytest.mark.asyncio
    async def test_GIVEN_path_outside_whitelist_WHEN_called_THEN_raises_FileNotAllowedError(self):
        """
        GIVEN an image path outside the whitelist (e.g. /etc/secret.png)
        WHEN  analyze_image() is called
        THEN  FileNotAllowedError is raised
        """
        with pytest.raises(FileNotAllowedError):
            await analyze_image(path="/etc/secret.png")

    @pytest.mark.asyncio
    async def test_GIVEN_nonexistent_image_WHEN_called_THEN_raises_FileNotFoundError(self):
        """
        GIVEN a path that does not exist (inside the whitelist)
        WHEN  analyze_image() is called
        THEN  FileNotFoundError is raised
        """
        with pytest.raises(FileNotFoundError):
            await analyze_image(path=str(_TEST_TMP / "nonexistent_image_xyz.png"))

    @pytest.mark.asyncio
    async def test_GIVEN_non_image_file_WHEN_called_THEN_returns_error_message(self):
        """
        GIVEN a .txt file instead of an image
        WHEN  analyze_image() is called
        THEN  the return value contains the error "Unsupported image format"
        """
        with tempfile.NamedTemporaryFile(suffix=".txt", dir=str(_TEST_TMP), delete=False) as f:
            f.write(b"Hello World")
            tmp_path = f.name

        try:
            result = await analyze_image(path=tmp_path)
            assert "Unsupported image format" in result
            assert ".txt" in result
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_GIVEN_valid_image_WHEN_called_THEN_calls_ollama_with_base64(self, monkeypatch):
        """
        GIVEN a valid image in the allowed directory
        WHEN  analyze_image() is called
        THEN  Ollama is called with the base64-encoded image
        """
        monkeypatch.setenv("EPHE_MODEL", "vision-fixture:1b")
        with tempfile.NamedTemporaryFile(suffix=".png", dir=str(_TEST_TMP), delete=False) as f:
            _create_minimal_png(Path(f.name))
            tmp_path = f.name

        mock_response = MagicMock()
        mock_response.message.content = "Ein rotes Pixel."

        # base.py imports `ollama` LAZY inside _get_shared_client() (there is no
        # module-global `core.tools.base.ollama`) — so the REAL module
        # `ollama.AsyncClient` has to be patched and the shared-client state
        # reset before the test (same root cause as
        # tests/test_finding_04_shared_client.py).
        import core.tools.base as base
        saved_client = base._shared_client
        base._shared_client = None

        try:
            with patch("ollama.AsyncClient") as MockClient:
                instance = AsyncMock()
                instance.chat = AsyncMock(return_value=mock_response)
                MockClient.return_value = instance

                result = await analyze_image(path=tmp_path)

                assert result == "Ein rotes Pixel."
                # Verify chat was called with images parameter
                call_args = instance.chat.call_args
                assert "images" in call_args.kwargs.get("messages", [{}])[0]
        finally:
            Path(tmp_path).unlink(missing_ok=True)
            base._shared_client = saved_client

    def test_GIVEN_supported_extensions_THEN_contains_common_formats(self):
        """
        GIVEN the SUPPORTED_IMAGE_EXTENSIONS
        THEN  PNG, JPG, JPEG, WebP are included
        """
        assert ".png" in SUPPORTED_IMAGE_EXTENSIONS
        assert ".jpg" in SUPPORTED_IMAGE_EXTENSIONS
        assert ".jpeg" in SUPPORTED_IMAGE_EXTENSIONS
        assert ".webp" in SUPPORTED_IMAGE_EXTENSIONS


# load_workspace Tests

class TestLoadWorkspace:
    """Workspace loader for the 128K context."""

    @pytest.mark.asyncio
    async def test_GIVEN_directory_with_files_WHEN_load_workspace_THEN_returns_concatenated_content(self):
        """
        GIVEN a directory with Python files
        WHEN  load_workspace(path, extensions=[".py"]) is called
        THEN  the return value contains the content of every file with path headers
        """
        with tempfile.TemporaryDirectory(dir=str(_TEST_TMP)) as tmpdir:
            # Create test files
            (Path(tmpdir) / "main.py").write_text("print('hello')")
            (Path(tmpdir) / "utils.py").write_text("def add(a, b): return a + b")
            (Path(tmpdir) / "readme.md").write_text("# Test")  # Should be filtered

            result = await load_workspace(tmpdir, extensions=[".py"])

            assert "main.py" in result
            assert "utils.py" in result
            assert "print('hello')" in result
            assert "def add(a, b)" in result
            assert "readme.md" not in result  # Filtered by extension

    @pytest.mark.asyncio
    async def test_GIVEN_directory_outside_whitelist_WHEN_called_THEN_raises_error(self):
        """
        GIVEN a path outside the whitelist
        WHEN  load_workspace() is called
        THEN  FileNotAllowedError is raised
        """
        with pytest.raises(FileNotAllowedError):
            await load_workspace(path="/etc/")

    @pytest.mark.asyncio
    async def test_GIVEN_nonexistent_directory_WHEN_called_THEN_raises_error(self):
        """
        GIVEN a non-existent directory (inside the whitelist)
        WHEN  load_workspace() is called
        THEN  DirectoryNotFoundError is raised
        """
        with pytest.raises(DirectoryNotFoundError):
            await load_workspace(path=str(_TEST_TMP / "nonexistent_dir_xyz_123"))

    @pytest.mark.asyncio
    async def test_GIVEN_empty_directory_WHEN_called_THEN_returns_no_files_message(self):
        """
        GIVEN an empty directory
        WHEN  load_workspace() is called
        THEN  the return value contains "No matching files"
        """
        with tempfile.TemporaryDirectory(dir=str(_TEST_TMP)) as tmpdir:
            result = await load_workspace(tmpdir, extensions=[".xyz"])
            assert "No matching files" in result

    @pytest.mark.asyncio
    async def test_GIVEN_nested_directories_WHEN_called_THEN_reads_recursively(self):
        """
        GIVEN nested directories with files
        WHEN  load_workspace() is called
        THEN  files from sub-directories are loaded too
        """
        with tempfile.TemporaryDirectory(dir=str(_TEST_TMP)) as tmpdir:
            base = Path(tmpdir)
            sub = base / "subdir"
            sub.mkdir()
            (base / "root.py").write_text("root_content")
            (sub / "nested.py").write_text("nested_content")

            result = await load_workspace(tmpdir, extensions=[".py"])

            assert "root_content" in result
            assert "nested_content" in result

    @pytest.mark.asyncio
    async def test_GIVEN_hidden_files_WHEN_called_THEN_skips_them(self):
        """
        GIVEN a directory with hidden files (.gitignore)
        WHEN  load_workspace() is called
        THEN  hidden files are skipped
        """
        with tempfile.TemporaryDirectory(dir=str(_TEST_TMP)) as tmpdir:
            (Path(tmpdir) / ".gitignore").write_text("node_modules/")
            (Path(tmpdir) / "visible.py").write_text("visible_content")

            result = await load_workspace(tmpdir)

            assert "visible_content" in result
            assert ".gitignore" not in result
