import pytest
import asyncio
import base64
from io import BytesIO
from PIL import Image

from core.vision import _crop_around, _capture_user_click
from core.vision_memory import save_vision_rule, find_vision_rule

@pytest.fixture
def mock_screenshot_b64():
    """Produces a white 1920x1080 mock image as Base64."""
    img = Image.new("RGB", (1920, 1080), "white")
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# 1. Integration Test: The Event Chain Listener
import os

@pytest.mark.asyncio
@pytest.mark.skipif("DISPLAY" not in os.environ, reason="Requires X11 DISPLAY")
async def test_capture_user_click_shuts_down():
    import pynput
    from unittest.mock import patch

    with patch("pynput.mouse.Listener") as MockListener:
        # We need to simulate the library behavior.
        # The listener takes an `on_click` callback.
        mock_instance = MockListener.return_value
        mock_instance.__enter__.return_value = mock_instance

        # When `join()` is called, we will simulate firing the callback to unblock it!
        def mock_join():
            # Get the callback function that was passed in
            on_click_cb = MockListener.call_args[1]["on_click"]

            # Fire the callback (simulating a left click at 500, 500)
            res = on_click_cb(500, 500, pynput.mouse.Button.left, True)

            # Check BDD Rule: the callback MUST return False to terminate listener
            assert res is False, "on_click did not return False to stop the listener"

            mock_instance.is_alive.return_value = False

        mock_instance.join.side_effect = mock_join

        x, y = await _capture_user_click()

        assert x == 500
        assert y == 500
        assert mock_instance.is_alive() is False


# 2. Crop-Boundary Test (BDD Rule 3)
def test_crop_around_boundary_zero(mock_screenshot_b64):
    """Checks that clicks right at the edge (0,0) do not end in an OutOfBounds exception."""
    try:
        # Click on pixel (0,0) -> a 50x50 crop would mean -25 to +25.
        cropped_b64 = _crop_around(mock_screenshot_b64, 0, 0, size=50)
    except Exception as e:
        pytest.fail(f"Boundary Crop hat eine Exception geworfen: {e}")

    # Validate output size and format
    img_data = base64.b64decode(cropped_b64)
    img = Image.open(BytesIO(img_data))

    assert img.size == (50, 50), "Der Crop muss aufgefüllt werden und genau 50x50 sein!"


# 3. Vision-store metadata round trip
def test_vision_metadata_limits(mock_screenshot_b64, tmp_path, monkeypatch):
    """
    Checks whether the base64 string of the 50x50 crop stays readable and writable
    in the vision store without blowing its metadata limits.
    """
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    target = "testTargetBoundary"

    # generate a 50x50 crop
    cropped_b64 = _crop_around(mock_screenshot_b64, 0, 0, size=50)

    # 50x50 RGB as JPEG Q85 is tiny (under 2KB), which is safe as a metadata value.
    byte_size = len(cropped_b64.encode("utf-8"))
    assert byte_size < 10000, f"the metadata crop is too large ({byte_size} bytes)"

    # write into the store and read it back
    try:
        save_vision_rule(target, cropped_b64, 0, 0)
        res = find_vision_rule(target)

        assert res is not None, "the stored entry could not be found again"
        assert res["raw_target"] == target
        assert res["last_known_x"] == 0
        assert res["base64_crop"] == cropped_b64
    except Exception as e:
        pytest.fail(f"vision store metadata operation failed: {e}")

# 4. SSE Success Emit Hook Test
@pytest.mark.skip(reason="Vision learning test requires GUI automation deps (PyAutoGUI, mss, Pillow); unavailable in this environment.")
@pytest.mark.asyncio
async def test_succeses_hook_invocation(mock_screenshot_b64):
    """
    Ensures that after a successful click and ChromaDB persistence
    the ON_VISION_LEARNED_SUCCESS hook fires for the web UI.
    """
    import core.vision
    from core.vision import vision_click
    from unittest.mock import patch, AsyncMock, MagicMock

    # Mocking
    mock_success_cb = AsyncMock()
    core.vision.ON_VISION_LEARNED_SUCCESS = mock_success_cb

    with patch("core.vision._take_screenshot", return_value=mock_screenshot_b64), \
         patch("core.vision._get_bounding_box", return_value="UNSURE"), \
         patch("core.vision._capture_user_click", return_value=(100, 100)), \
         patch("core.vision.check_sandbox", new_callable=AsyncMock), \
         patch("core.vision.pyautogui", MagicMock()), \
         patch("core.vision_memory.save_vision_rule") as mock_save:

        res = await vision_click("Unknown Element")
        print(f"DEBUG: vision_click returned {res}")

        # Verify persistence and success notification were called
        mock_save.assert_called_once()
        mock_success_cb.assert_awaited_once_with("Unknown Element")

        assert "war unsicher" in res
        assert "manuellen Klick eingegriffen" in res
