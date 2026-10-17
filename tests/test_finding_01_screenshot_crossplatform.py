"""
tests/test_finding_01_screenshot_crossplatform.py

Finding 1: take_screenshot() was macOS-only (screencapture).
Fix: cross-platform through sys.platform → mss on Linux/Windows.

Given-When-Then Tests:
  1. GIVEN Linux → WHEN take_screenshot() → THEN mss is called (not screencapture)
  2. GIVEN macOS → WHEN take_screenshot() → THEN screencapture is called
  3. GIVEN mss fails → WHEN take_screenshot() → THEN graceful error message
"""
import asyncio
import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def image_dir(tmp_path):
    d = tmp_path / "images"
    d.mkdir()
    return d


# Test 1: GIVEN Linux WHEN screenshot THEN mss used

@pytest.mark.asyncio
async def test_given_linux_when_screenshot_then_uses_mss(image_dir, monkeypatch):
    """GIVEN platform is Linux WHEN take_screenshot() THEN mss.shot() is called."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("EPHE_IMAGE_DIR", str(image_dir))

    mock_sct = MagicMock()
    mock_sct.shot = MagicMock()
    mock_mss_ctx = MagicMock()
    mock_mss_ctx.__enter__ = MagicMock(return_value=mock_sct)
    mock_mss_ctx.__exit__ = MagicMock(return_value=False)

    mock_mss_module = MagicMock()
    mock_mss_module.mss.return_value = mock_mss_ctx

    with patch.dict("sys.modules", {"mss": mock_mss_module}):
        from core.tools import take_screenshot
        result = await take_screenshot()

    assert "![Screenshot]" in result
    assert "Screenshot failed" not in result
    mock_sct.shot.assert_called_once()


# Test 2: GIVEN macOS WHEN screenshot THEN screencapture used

@pytest.mark.asyncio
async def test_given_macos_when_screenshot_then_uses_screencapture(image_dir, monkeypatch):
    """GIVEN platform is macOS WHEN take_screenshot() THEN screencapture is called."""
    from core.tools import take_screenshot  # Import BEFORE patching platform

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("EPHE_IMAGE_DIR", str(image_dir))

    with patch("core.tools.system_tools.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = await take_screenshot()

    assert "![Screenshot]" in result
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert args[0] == "screencapture"


# Test 3: GIVEN mss fails WHEN screenshot THEN graceful error

@pytest.mark.asyncio
async def test_given_mss_fails_when_screenshot_then_graceful_error(image_dir, monkeypatch):
    """GIVEN mss raises exception WHEN take_screenshot() THEN returns error string, no crash."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("EPHE_IMAGE_DIR", str(image_dir))

    mock_mss_module = MagicMock()
    mock_mss_module.mss.side_effect = RuntimeError("No display available")

    with patch.dict("sys.modules", {"mss": mock_mss_module}):
        from core.tools import take_screenshot
        result = await take_screenshot()

    assert "Screenshot failed" in result
    assert "No display available" in result


@pytest.mark.asyncio
async def test_given_macos_screencapture_blocked_when_screenshot_then_actionable_error(image_dir, monkeypatch):
    """GIVEN macOS blocks screen recording WHEN take_screenshot() THEN the user gets an actionable error."""
    from core.tools import take_screenshot

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("EPHE_IMAGE_DIR", str(image_dir))

    with patch("core.tools.system_tools.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, ["screencapture", "-x", "out.png"])
        result = await take_screenshot()

    assert "Screenshot failed" in result
    assert "Screen Recording" in result
    assert "System Settings" in result
