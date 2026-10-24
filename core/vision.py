"""
◑ Ephe – Vision & Computer Use
core/vision.py

Executes screenshots and PyAutoGUI click/type commands.
Usable by the agent.
"""
import base64
import json
import math
import os
import asyncio
from contextvars import ContextVar

try:
    import mss
    # pyautogui's mouseinfo dependency crashes if DISPLAY is not set (headless Linux).
    # We guard against both KeyError and Xlib connection errors.
    import os as _os
    _had_display = "DISPLAY" in _os.environ
    if not _had_display:
        _os.environ["DISPLAY"] = ":99"
    try:
        import pyautogui
    except Exception:
        pyautogui = None
    finally:
        if not _had_display:
            _os.environ.pop("DISPLAY", None)
    from PIL import Image
except ImportError:
    mss = None
    pyautogui = None
    Image = None

import ollama

# Sandbox Exceptions
class SandboxConfirmationRequired(Exception):
    def __init__(self, tool_name: str, args: dict):
        self.tool_name = tool_name
        self.args = args
        super().__init__(f"Sandbox confirmation required for: {tool_name}")

# Internals

def _take_screenshot() -> str:
    """Takes a screenshot using mss and returns it as base64."""
    if mss is None:
        raise RuntimeError("mss library not installed.")

    with mss.mss() as sct:
        # Monitor 1 (Main)
        monitor = sct.monitors[1]
        sct_img = sct.grab(monitor)

        # Convert to PIL Image to compress/save to base64
        # MSS returns BGRA. PIL reads mode RGB from 'raw' if we specify BGRX
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        from io import BytesIO
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")


class VisionUnavailable(RuntimeError):
    """No usable vision engine, or one that did not answer in time."""


def _vision_timeout_s() -> float:
    try:
        value = float(os.environ.get("EPHE_VISION_TIMEOUT_S") or 30)
    except (TypeError, ValueError):
        return 30.0
    if not math.isfinite(value) or value <= 0:
        return 30.0
    return max(1.0, value)


async def _get_bounding_box(b64_image: str, target: str, reference_crop_b64: str | None = None) -> tuple[float, float, float, float] | str | None:
    """
    Asks Llama 3.2 Vision for the bounding box of the element.
    Rule 1 applies: when unsure, it returns "UNSURE".
    If the memory holds experience, the reference crop is provided too.
    """
    system_prompt = (
        f"Find the UI element '{target}' on this image. If you are below 95% sure where the button is, or if there are multiple identical buttons, answer ONLY with the word 'UNSURE'.\nOtherwise return exactly the normalized bounding box coordinates [y_min, x_min, y_max, x_max] in the range 0.0 to 1.0 as a strict JSON array. Output absolutely no other text."
    )

    if reference_crop_b64:
        system_prompt += "\nYou received a reference image for this element (image 2). Use it to find the exact variant in image 1."

    images = [b64_image]
    if reference_crop_b64:
        images.append(reference_crop_b64)

    import os
    # Resolution before the call: without a vision model the click path used to
    # send the chosen chat model to a local Ollama and wait for a load that
    # never happens. The refusal names the missing setting instead.
    vision_model = (os.environ.get("EPHE_VISION_MODEL") or "").strip()
    if not vision_model:
        from core.model_provider import chosen_model, get_active_provider

        try:
            provider = get_active_provider().provider
        except Exception:  # noqa: BLE001 — no engine means no vision model
            provider = ""
        if provider == "local_ollama":
            try:
                vision_model = str(chosen_model("the vision call") or "").strip()
            except Exception:  # noqa: BLE001 — a missing role means "none"
                vision_model = ""
    if not vision_model:
        raise VisionUnavailable(
            "browser_click needs a vision engine: set EPHE_VISION_MODEL to a "
            "local vision model"
        )

    client = ollama.AsyncClient()
    try:
        timeout = _vision_timeout_s()
        response = await asyncio.wait_for(
            client.generate(
                model=vision_model,
                prompt=system_prompt,
                images=images,
                options={"temperature": 0.0},
            ),
            timeout=timeout,
        )

        txt = response["response"].strip()
        if "UNSURE" in txt:
            return "UNSURE"

        if txt.startswith("```json"):
            txt = txt.replace("```json", "").replace("```", "").strip()
        elif txt.startswith("```"):
            txt = txt.replace("```", "").strip()

        coords = json.loads(txt)
        if isinstance(coords, list) and len(coords) == 4:
            return (float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3]))
        return None
    except (asyncio.TimeoutError, TimeoutError) as exc:
        raise VisionUnavailable(
            f"vision model did not answer within {timeout:.0f}s "
            "(EPHE_VISION_TIMEOUT_S); browser_click cannot place the element"
        ) from exc
    except Exception as e:
        import logging
        logging.error(f"Vision Parsing Error: {e}")
        raise RuntimeError(f"local vision model not ready or overloaded: {e}")

def _crop_around(b64_image: str, x: int, y: int, size: int = 50) -> str:
    """Creates a 50x50 image crop with OS boundary padding (black pixels)."""
    from PIL import Image
    from io import BytesIO

    img_data = base64.b64decode(b64_image)
    img = Image.open(BytesIO(img_data)).convert("RGB")
    width, height = img.size

    half = size // 2
    left, top, right, bottom = x - half, y - half, x + half, y + half

    cropped = Image.new("RGB", (size, size), (0, 0, 0))

    src_left = max(0, left)
    src_top = max(0, top)
    src_right = min(width, right)
    src_bottom = min(height, bottom)

    if src_left < src_right and src_top < src_bottom:
        crop_actual = img.crop((src_left, src_top, src_right, src_bottom))
        paste_x = src_left - left
        paste_y = src_top - top
        cropped.paste(crop_actual, (paste_x, paste_y))

    buf = BytesIO()
    cropped.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode("utf-8")

async def _capture_user_click() -> tuple[int, int]:
    """Safe mouse listener that throws itself away right after the first click."""
    import pynput
    click_pos = [0, 0]
    ev = asyncio.Event()
    loop = asyncio.get_running_loop()

    def on_click(x, y, button, pressed):
        if pressed and button == pynput.mouse.Button.left:
            click_pos[0], click_pos[1] = int(x), int(y)
            loop.call_soon_threadsafe(ev.set)
            return False # Ends the listener immediately

    def start_listener():
        with pynput.mouse.Listener(on_click=on_click) as listener:
            listener.join()

    await asyncio.to_thread(start_listener)
    await ev.wait()
    return click_pos[0], click_pos[1]


# Sandbox callbacks — ContextVar (T-02/T-03: request-scoped, no module global)

# ContextVars: every asyncio task / every FastAPI request gets
# its own callback scope. No leak between simultaneous requests.
_sandbox_cb_var:       ContextVar = ContextVar('vision_sandbox_cb',        default=None)
_vision_learning_var:  ContextVar = ContextVar('vision_learning_cb',       default=None)
_vision_learned_var:   ContextVar = ContextVar('vision_learned_success_cb', default=None)

# Backwards-compatible properties — so existing code that reads/writes
# ON_SANDBOX_CONFIRM directly keeps working (deprecated, but no breaking change)
@property
def _ON_SANDBOX_CONFIRM_compat(): return _sandbox_cb_var.get()

# New API: setter functions for the request handler (instead of monkey-patching)
def set_sandbox_confirm_cb(cb):
    """Sets the sandbox-confirm callback for the current asyncio context."""
    _sandbox_cb_var.set(cb)

def set_vision_learning_cb(cb):
    """Sets the vision-learning callback for the current asyncio context."""
    _vision_learning_var.set(cb)

def set_vision_learned_success_cb(cb):
    """Sets the vision-learned-success callback for the current asyncio context."""
    _vision_learned_var.set(cb)

# Legacy globals for code compatibility (read from the ContextVar)
# DEPRECATED: assigning to ON_SANDBOX_CONFIRM directly has a global effect.
# Use set_sandbox_confirm_cb() for request-scoped callbacks.
ON_SANDBOX_CONFIRM = None        # Replaced by a ContextVar inside check_sandbox()
ON_VISION_LEARNING = None        # Replaced by a ContextVar inside vision_click()
ON_VISION_LEARNED_SUCCESS = None # Replaced by a ContextVar inside vision_click()

async def check_sandbox(tool_name: str, args: dict):
    # T-03: check the ContextVar first (request-scoped), fall back to the legacy global.
    # Risky desktop-control tools must always have an explicit UI approval path.
    cb = _sandbox_cb_var.get() or ON_SANDBOX_CONFIRM
    if cb:
        approved = await cb(tool_name, args)
        if not approved:
            raise Exception("Action aborted by User Intervention")
    else:
        raise SandboxConfirmationRequired(tool_name, args)


async def vision_click(target_description: str) -> str:
    """Finds a UI element on the primary monitor and clicks it physically."""
    if pyautogui is None or mss is None or Image is None:
        return "[error: GUI automation dependencies (PyAutoGUI, mss, Pillow) are not fully imported.]"

    # 1. BDD rule: wait for confirmation when the sandbox is on
    await check_sandbox("vision_click", {"target_description": target_description})

    # 2. Memory query
    from core.vision_memory import find_vision_rule, save_vision_rule
    ref_rule = find_vision_rule(target_description)
    ref_b64 =  ref_rule["base64_crop"] if ref_rule else None

    # 3. Screenshot & model inference
    b64_img = await asyncio.to_thread(_take_screenshot)
    coords = await _get_bounding_box(b64_img, target_description, ref_b64)

    # 4. BDD rule 1: zero-guessing policy (HITL fallback)
    if coords == "UNSURE":
        # T-03: ContextVar first, then the legacy global
        learning_cb = _vision_learning_var.get() or ON_VISION_LEARNING
        if learning_cb:
            await learning_cb(target_description)

        # The listener blocks asynchronously until the user physically clicks in their UI
        x, y = await _capture_user_click()

        # Compute the crop and learn it (boundary safe, BDD rule 3)
        crop_img_base64 = _crop_around(b64_img, x, y, size=50)
        save_vision_rule(target_description, crop_img_base64, x, y)

        learned_cb = _vision_learned_var.get() or ON_VISION_LEARNED_SUCCESS
        if learned_cb:
            await learned_cb(target_description)

        return f"Element '{target_description}' was uncertain. The user intervened with a manual click, and the system learned the element image for future runs."

    # Failsafe when the element was not found
    if not coords:
        return f"Error: Element '{target_description}' not found"

    y_min, x_min, y_max, x_max = coords

    # Scaling (BDD rule 4)
    screen_width, screen_height = pyautogui.size()

    center_y = y_min + (y_max - y_min) / 2
    center_x = x_min + (x_max - x_min) / 2

    absolute_x = int(center_x * screen_width)
    absolute_y = int(center_y * screen_height)

    # Physical execution
    try:
        await asyncio.to_thread(pyautogui.moveTo, absolute_x, absolute_y, duration=0.5)
        await asyncio.to_thread(pyautogui.click)
        return f"Clicked on '{target_description}' successfully."
    except pyautogui.FailSafeException:
        # BDD rule 3: the human emergency brake
        return "Action aborted by User Intervention"
    except Exception as e:
        return f"Error on click: {e}"


async def vision_type(text: str, press_enter: bool = False) -> str:
    """Types text with the physical keyboard at the current cursor position."""
    if pyautogui is None or mss is None or Image is None:
        return "[error: GUI automation dependencies (PyAutoGUI, mss, Pillow) are not fully imported.]"

    await check_sandbox("vision_type", {"text": text, "press_enter": press_enter})

    try:
        await asyncio.to_thread(pyautogui.write, text, interval=0.03)
        if press_enter:
            await asyncio.to_thread(pyautogui.press, "enter")
        return "Text typed successfully."
    except pyautogui.FailSafeException:
        return "Action aborted by User Intervention"
    except Exception as e:
        return f"Error on typing: {e}"
