"""
◑ Ephe – GUI Automation Tests
tests/test_gui_automation.py
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import os

import core.vision
from core.vision import vision_click, SandboxConfirmationRequired

@pytest.fixture
def mock_config():
    with patch.dict(os.environ, {"EPHE_AUTONOMOUS_MODE": "0"}):
        mock_gui = MagicMock()
        mock_gui.FailSafeException = Exception
        token = core.vision._sandbox_cb_var.set(None)
        with patch("core.vision.pyautogui", mock_gui), \
             patch("core.vision.mss", MagicMock()), \
             patch("core.vision.Image", MagicMock()):
            try:
                yield
            finally:
                core.vision._sandbox_cb_var.reset(token)

@pytest.mark.asyncio
async def test_rule_1_sandbox_on_no_ui_callback_raises(mock_config):
    """
    GIVEN Autonomous Mode is OFF
    WHEN vision_click is called without WebUI setup
    THEN SandboxConfirmationRequired is raised
    """
    with patch("core.vision.ON_SANDBOX_CONFIRM", None):
        with pytest.raises(SandboxConfirmationRequired):
            await vision_click("Test Button")


@pytest.mark.asyncio
async def test_rule_1_sandbox_on_ui_rejected_returns_aborted(mock_config):
    """
    GIVEN Autonomous Mode is OFF
    WHEN WebUI callback rejects the action (user clicked Abort)
    THEN returns 'Action aborted by User Intervention'
    """
    async def mock_reject(name, args):
        return False

    with patch("core.vision.ON_SANDBOX_CONFIRM", mock_reject):
        with pytest.raises(Exception, match="Action aborted"):
            await vision_click("Test Button")


@pytest.mark.asyncio
async def test_rule_2_element_not_found(mock_config):
    """
    GIVEN vision_click searches for a button
    WHEN Gemma 4 returns None (element not found)
    THEN returns "Error: Element 'Missing Button' not found" and NO click occurs
    """
    async def mock_approve(name, args): return True

    with patch("core.vision.ON_SANDBOX_CONFIRM", mock_approve), \
         patch("core.vision._take_screenshot", return_value="dummy_b64"), \
         patch("core.vision._get_bounding_box", new_callable=AsyncMock) as mock_bb:

        mock_bb.return_value = None
        result = await vision_click("Missing Button")

        assert "not found" in result
        assert core.vision.pyautogui.click.called is False


@pytest.mark.asyncio
async def test_rule_3_failsafe_aborts(mock_config):
    """
    GIVEN vision_click executes
    WHEN user yanks the mouse (pyautogui raises FailSafeException)
    THEN returns 'Action aborted by User Intervention'
    """
    async def mock_approve(name, args): return True

    with patch("core.vision.ON_SANDBOX_CONFIRM", mock_approve), \
         patch("core.vision._take_screenshot", return_value="dummy_b64"), \
         patch("core.vision._get_bounding_box", new_callable=AsyncMock) as mock_bb:

        core.vision.pyautogui.size.return_value = (1000, 1000)
        core.vision.pyautogui.moveTo.side_effect = core.vision.pyautogui.FailSafeException()

        mock_bb.return_value = (0.1, 0.1, 0.2, 0.2)
        result = await vision_click("Safe Button")

        assert "Action aborted by User Intervention" in result

# vision_type Tests
from core.vision import vision_type

@pytest.mark.asyncio
async def test_vision_type_sandbox_raises(mock_config):
    """
    GIVEN Autonomous Mode is OFF
    WHEN vision_type is called without WebUI setup
    THEN SandboxConfirmationRequired is raised
    """
    with patch("core.vision.ON_SANDBOX_CONFIRM", None):
        with pytest.raises(SandboxConfirmationRequired):
            await vision_type("Hallo Welt", False)


@pytest.mark.asyncio
async def test_vision_type_autonomous_mode_still_requires_ui_callback():
    """
    GIVEN Autonomous Mode is ON
    WHEN vision_type is called without WebUI approval callback
    THEN SandboxConfirmationRequired is still raised.
    """
    mock_gui = MagicMock()
    mock_gui.FailSafeException = Exception
    with patch.dict(os.environ, {"EPHE_AUTONOMOUS_MODE": "1"}), \
         patch("core.vision.pyautogui", mock_gui), \
         patch("core.vision.mss", MagicMock()), \
         patch("core.vision.Image", MagicMock()), \
         patch("core.vision.ON_SANDBOX_CONFIRM", None):
        token = core.vision._sandbox_cb_var.set(None)
        try:
            with pytest.raises(SandboxConfirmationRequired):
                await vision_type("Hallo Welt", False)
        finally:
            core.vision._sandbox_cb_var.reset(token)

@pytest.mark.asyncio
async def test_vision_type_with_enter(mock_config):
    """
    GIVEN vision_type is called with press_enter=True
    WHEN the user approves the sandbox
    THEN pyautogui.write is called on the text AND pyautogui.press("enter") is called
    """
    async def mock_approve(name, args): return True

    with patch("core.vision.ON_SANDBOX_CONFIRM", mock_approve), \
         patch("core.vision.pyautogui.write") as mock_write, \
         patch("core.vision.pyautogui.press") as mock_press:

        res = await vision_type("Hallo Welt", press_enter=True)

        mock_write.assert_called_once_with("Hallo Welt", interval=0.03)
        mock_press.assert_called_once_with("enter")

        assert "Text typed successfully" in res

@pytest.mark.asyncio
async def test_vision_type_without_enter(mock_config):
    """
    GIVEN vision_type is called with press_enter=False
    WHEN the user approves the sandbox
    THEN pyautogui.write is called but NOT pyautogui.press
    """
    async def mock_approve(name, args): return True

    with patch("core.vision.ON_SANDBOX_CONFIRM", mock_approve), \
         patch("core.vision.pyautogui.write") as mock_write, \
         patch("core.vision.pyautogui.press") as mock_press:

        res = await vision_type("Nur Text", press_enter=False)

        mock_write.assert_called_once_with("Nur Text", interval=0.03)
        mock_press.assert_not_called()

        assert "Text typed successfully" in res
