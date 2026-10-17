"""WA-10 — the vision module's inference and sandbox paths (core/vision.py).

Item 9 of docs/COVERAGE_GAPS_2026-10-11.md left core/vision.py at 55%: the
screen-grab fallback, the bounding-box inference and the sandbox gate were not
exercised because the GUI libraries are absent. These tests stand in for the
model client and the screenshot, so the parse/refuse branches run without a
display, a camera or an engine.
"""
from __future__ import annotations

import asyncio
import base64
import importlib.util
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import core.vision as vision_mod
from core.vision import (
    SandboxConfirmationRequired,
    _get_bounding_box,
    _take_screenshot,
    check_sandbox,
    set_sandbox_confirm_cb,
    set_vision_learned_success_cb,
    set_vision_learning_cb,
    vision_click,
    vision_type,
)


def _install_generate(monkeypatch, *, text=None, error=None):
    """Point the module's ollama client at a canned response; return the call log."""
    calls: dict = {}

    async def generate(**kwargs):
        calls.update(kwargs)
        if error is not None:
            raise error
        return {"response": text}

    monkeypatch.setattr(vision_mod.ollama, "AsyncClient", lambda: SimpleNamespace(generate=generate))
    return calls


@pytest.fixture(autouse=True)
def _reset_vision_callbacks():
    """The vision ContextVars outlive a test; the module resets the sandbox one, not these two."""
    for setter in (set_sandbox_confirm_cb, set_vision_learning_cb, set_vision_learned_success_cb):
        setter(None)
    yield
    for setter in (set_sandbox_confirm_cb, set_vision_learning_cb, set_vision_learned_success_cb):
        setter(None)


# SandboxConfirmationRequired: the refusal carries what it refused


def test_sandbox_confirmation_required_holds_the_tool_and_args():
    exc = SandboxConfirmationRequired("vision_click", {"target_description": "Save"})
    assert exc.tool_name == "vision_click"
    # super().__init__ resets BaseException.args to the message tuple; the dict
    # stays on the instance as the constructor argument it was given.
    assert "vision_click" in str(exc)


# check_sandbox: approve, deny, or demand confirmation


@pytest.mark.asyncio
async def test_check_sandbox_passes_when_the_callback_approves():
    async def approve(_name, _args):
        return True

    set_sandbox_confirm_cb(approve)
    await check_sandbox("vision_click", {"target_description": "Save"})  # must not raise


@pytest.mark.asyncio
async def test_check_sandbox_aborts_when_the_callback_denies():
    async def deny(_name, _args):
        return False

    set_sandbox_confirm_cb(deny)
    with pytest.raises(Exception, match="Action aborted by User Intervention"):
        await check_sandbox("vision_click", {"target_description": "Save"})


@pytest.mark.asyncio
async def test_check_sandbox_raises_confirmation_required_without_a_callback():
    # The conftest clears the request-scoped callback before each test.
    with pytest.raises(SandboxConfirmationRequired) as excinfo:
        await check_sandbox("vision_type", {"text": "hi", "press_enter": False})
    assert excinfo.value.tool_name == "vision_type"


@pytest.mark.asyncio
async def test_check_sandbox_falls_back_to_the_legacy_global(monkeypatch):
    calls = []

    async def legacy(_name, _args):
        calls.append(_name)
        return True

    monkeypatch.setattr(vision_mod, "ON_SANDBOX_CONFIRM", legacy)
    await check_sandbox("vision_click", {"target_description": "Save"})
    assert calls == ["vision_click"]


# callback setters pin the request-scoped ContextVars


def test_set_sandbox_confirm_cb_stores_the_callback():
    sentinel = object()
    set_sandbox_confirm_cb(sentinel)
    assert vision_mod._sandbox_cb_var.get() is sentinel


def test_set_vision_learning_cb_stores_the_callback():
    sentinel = object()
    set_vision_learning_cb(sentinel)
    assert vision_mod._vision_learning_var.get() is sentinel


def test_set_vision_learned_success_cb_stores_the_callback():
    sentinel = object()
    set_vision_learned_success_cb(sentinel)
    assert vision_mod._vision_learned_var.get() is sentinel


# _take_screenshot degrades cleanly without mss


def test_take_screenshot_names_the_missing_library(monkeypatch):
    monkeypatch.setattr(vision_mod, "mss", None)
    with pytest.raises(RuntimeError, match="mss library not installed"):
        _take_screenshot()


# _get_bounding_box: the parse contract


@pytest.fixture
def vision_model(monkeypatch):
    monkeypatch.setenv("EPHE_VISION_MODEL", "vision-test:1b")


def test_bounding_box_returns_the_normalized_tuple(monkeypatch, vision_model):
    calls = _install_generate(monkeypatch, text="[0.1, 0.2, 0.3, 0.4]")
    box = asyncio.run(_get_bounding_box("BASE64", "Save"))
    assert box == pytest.approx((0.1, 0.2, 0.3, 0.4))
    assert calls["model"] == "vision-test:1b"
    assert calls["options"] == {"temperature": 0.0}
    assert calls["images"] == ["BASE64"]


def test_bounding_box_honours_unsure(monkeypatch, vision_model):
    _install_generate(monkeypatch, text="I am not sure, UNSURE")
    assert asyncio.run(_get_bounding_box("BASE64", "Save")) == "UNSURE"


def test_bounding_box_strips_a_json_fence(monkeypatch, vision_model):
    _install_generate(monkeypatch, text="```json\n[0.0, 0.0, 1.0, 1.0]\n```")
    assert asyncio.run(_get_bounding_box("BASE64", "Save")) == pytest.approx((0.0, 0.0, 1.0, 1.0))


def test_bounding_box_strips_a_bare_fence(monkeypatch, vision_model):
    _install_generate(monkeypatch, text="```\n[0.5, 0.5, 0.5, 0.5]\n```")
    assert asyncio.run(_get_bounding_box("BASE64", "Save")) == pytest.approx((0.5, 0.5, 0.5, 0.5))


@pytest.mark.parametrize("answer", ["[1, 2, 3]", '{"x": 1}', "42"])
def test_bounding_box_rejects_a_shape_that_is_not_a_box(monkeypatch, vision_model, answer):
    _install_generate(monkeypatch, text=answer)
    assert asyncio.run(_get_bounding_box("BASE64", "Save")) is None


def test_bounding_box_wraps_a_parse_error_as_a_readable_runtime_error(monkeypatch, vision_model):
    _install_generate(monkeypatch, text="the button is on the left somewhere")
    with pytest.raises(RuntimeError, match="local vision model not ready"):
        asyncio.run(_get_bounding_box("BASE64", "Save"))


def test_bounding_box_wraps_an_engine_error(monkeypatch, vision_model):
    _install_generate(monkeypatch, error=RuntimeError("connection refused"))
    with pytest.raises(RuntimeError, match="local vision model not ready"):
        asyncio.run(_get_bounding_box("BASE64", "Save"))


def test_bounding_box_sends_the_reference_crop_as_a_second_image(monkeypatch, vision_model):
    calls = _install_generate(monkeypatch, text="[0.0, 0.0, 1.0, 1.0]")
    asyncio.run(_get_bounding_box("BASE64", "Save", reference_crop_b64="REFERENCE"))
    assert calls["images"] == ["BASE64", "REFERENCE"]
    assert "image 2" in calls["prompt"]


def test_bounding_box_falls_back_to_chosen_model(monkeypatch):
    monkeypatch.delenv("EPHE_VISION_MODEL", raising=False)
    calls = _install_generate(monkeypatch, text="[0.0, 0.0, 1.0, 1.0]")

    import core.model_provider as model_provider

    monkeypatch.setattr(model_provider, "chosen_model", lambda _context: "chosen:1b")

    asyncio.run(_get_bounding_box("BASE64", "Save"))
    assert calls["model"] == "chosen:1b"


# GUI entry points degrade to one readable line without the libraries


def test_vision_click_reports_missing_gui_dependencies(monkeypatch):
    monkeypatch.setattr(vision_mod, "pyautogui", None)
    out = asyncio.run(vision_click("Save"))
    assert "[error: GUI automation dependencies" in out


def test_vision_type_reports_missing_gui_dependencies(monkeypatch):
    monkeypatch.setattr(vision_mod, "pyautogui", None)
    out = asyncio.run(vision_type("hello"))
    assert "[error: GUI automation dependencies" in out


# the click/type bodies, driven through a fake desktop


class _FakeGUI:
    """A pyautogui stand-in that runs without a display."""

    class FailSafeException(Exception):
        pass

    def __init__(self, size=(1920, 1080), move_error=None, click_error=None,
                 write_error=None, press_error=None):
        self._size = size
        self._move_error = move_error
        self._click_error = click_error
        self._write_error = write_error
        self._press_error = press_error
        self.moved: list[tuple] = []
        self.clicks = 0
        self.written: list[str] = []
        self.pressed: list[str] = []

    def size(self):
        return self._size

    def moveTo(self, x, y, duration=None):
        if self._move_error is not None:
            raise self._move_error
        self.moved.append((x, y))

    def click(self):
        if self._click_error is not None:
            raise self._click_error
        self.clicks += 1

    def write(self, text, interval=None):
        if self._write_error is not None:
            raise self._write_error
        self.written.append(text)

    def press(self, key):
        if self._press_error is not None:
            raise self._press_error
        self.pressed.append(key)


@pytest.fixture
def desktop(monkeypatch):
    """Install the GUI dependencies and an approving sandbox so the bodies run."""
    async def approve(_name, _args):
        return True

    monkeypatch.setattr(vision_mod, "mss", object())
    monkeypatch.setattr(vision_mod, "Image", object())
    monkeypatch.setattr(vision_mod, "_take_screenshot", lambda: "B64")
    set_sandbox_confirm_cb(approve)
    return monkeypatch


def test_vision_click_presses_the_scaled_center(desktop, monkeypatch):
    gui = _FakeGUI()
    desktop.setattr(vision_mod, "pyautogui", gui)
    desktop.setattr(vision_mod, "_get_bounding_box", _async_return((0.25, 0.25, 0.75, 0.75)))
    import core.vision_memory as memory

    desktop.setattr(memory, "find_vision_rule", lambda _t: None)
    desktop.setattr(memory, "save_vision_rule", lambda *a, **k: None)

    out = asyncio.run(vision_click("Save"))

    assert out == "Clicked on 'Save' successfully."
    assert gui.moved == [(960, 540)]  # center (0.5, 0.5) of 1920x1080
    assert gui.clicks == 1


def test_vision_click_passes_a_learned_rule_as_reference(desktop, monkeypatch):
    gui = _FakeGUI()
    desktop.setattr(vision_mod, "pyautogui", gui)
    seen = {}

    async def _bbox(image, target, reference_crop_b64=None):
        seen["reference"] = reference_crop_b64
        return (0.0, 0.0, 1.0, 1.0)

    desktop.setattr(vision_mod, "_get_bounding_box", _bbox)
    import core.vision_memory as memory

    desktop.setattr(memory, "find_vision_rule", lambda _t: {"base64_crop": "LEARNED"})
    desktop.setattr(memory, "save_vision_rule", lambda *a, **k: None)

    asyncio.run(vision_click("Save"))

    assert seen["reference"] == "LEARNED"


def test_vision_click_falls_back_to_a_human_click_when_unsure(desktop, monkeypatch):
    gui = _FakeGUI()
    desktop.setattr(vision_mod, "pyautogui", gui)
    desktop.setattr(vision_mod, "_get_bounding_box", _async_return("UNSURE"))
    desktop.setattr(vision_mod, "_capture_user_click", _async_return((100, 200)))
    desktop.setattr(vision_mod, "_crop_around", lambda *_a, **_k: "CROP")

    saved = {}
    import core.vision_memory as memory

    desktop.setattr(memory, "find_vision_rule", lambda _t: None)
    desktop.setattr(memory, "save_vision_rule", lambda target, crop, x, y: saved.update(
        target=target, crop=crop, x=x, y=y))

    learned = []

    async def _learn(target):
        learned.append(("asked", target))

    set_vision_learning_cb(_learn)

    succeeded = []

    async def _succeeded(target):
        succeeded.append(target)

    set_vision_learned_success_cb(_succeeded)

    out = asyncio.run(vision_click("Mystery"))

    assert saved == {"target": "Mystery", "crop": "CROP", "x": 100, "y": 200}
    assert learned == [("asked", "Mystery")]
    assert succeeded == ["Mystery"]
    assert "was uncertain" in out and "manual click" in out
    assert gui.clicks == 0


def test_vision_click_reports_an_element_it_cannot_find(desktop):
    desktop.setattr(vision_mod, "pyautogui", _FakeGUI())
    desktop.setattr(vision_mod, "_get_bounding_box", _async_return(None))
    import core.vision_memory as memory

    desktop.setattr(memory, "find_vision_rule", lambda _t: None)

    out = asyncio.run(vision_click("Ghost"))

    assert out == "Error: Element 'Ghost' not found"


def test_vision_click_honours_the_failsafe_brake(desktop):
    gui = _FakeGUI(click_error=_FakeGUI.FailSafeException())
    desktop.setattr(vision_mod, "pyautogui", gui)
    desktop.setattr(vision_mod, "_get_bounding_box", _async_return((0.1, 0.1, 0.9, 0.9)))
    import core.vision_memory as memory

    desktop.setattr(memory, "find_vision_rule", lambda _t: None)

    assert asyncio.run(vision_click("Save")) == "Action aborted by User Intervention"


def test_vision_click_reports_a_click_error(desktop):
    gui = _FakeGUI(move_error=RuntimeError("pointer lost"))
    desktop.setattr(vision_mod, "pyautogui", gui)
    desktop.setattr(vision_mod, "_get_bounding_box", _async_return((0.1, 0.1, 0.9, 0.9)))
    import core.vision_memory as memory

    desktop.setattr(memory, "find_vision_rule", lambda _t: None)

    assert asyncio.run(vision_click("Save")) == "Error on click: pointer lost"


def test_vision_type_writes_text_without_enter(desktop):
    gui = _FakeGUI()
    desktop.setattr(vision_mod, "pyautogui", gui)

    out = asyncio.run(vision_type("hello"))

    assert gui.written == ["hello"]
    assert gui.pressed == []
    assert out == "Text typed successfully."


def test_vision_type_presses_enter_when_asked(desktop):
    gui = _FakeGUI()
    desktop.setattr(vision_mod, "pyautogui", gui)

    asyncio.run(vision_type("hello", press_enter=True))

    assert gui.pressed == ["enter"]


def test_vision_type_honours_the_failsafe_brake(desktop):
    gui = _FakeGUI(write_error=_FakeGUI.FailSafeException())
    desktop.setattr(vision_mod, "pyautogui", gui)

    assert asyncio.run(vision_type("x")) == "Action aborted by User Intervention"


def test_vision_type_reports_a_write_error(desktop):
    gui = _FakeGUI(write_error=RuntimeError("keyboard gone"))
    desktop.setattr(vision_mod, "pyautogui", gui)

    assert asyncio.run(vision_type("x")) == "Error on typing: keyboard gone"


def _async_return(value):
    async def _fn(*_args, **_kwargs):
        return value

    return _fn


# the module-level import guard (core/vision.py: mss + pyautogui + PIL)


def _load_vision_fresh(monkeypatch, *, blocked=()):
    """Run core/vision.py again in a throwaway namespace.

    Each name in ``blocked`` is pinned to ``None`` in ``sys.modules`` so the
    module's own ``import <name>`` raises ImportError, while the already-imported
    copy the rest of the suite uses stays untouched. ``monkeypatch`` restores
    ``sys.modules`` when the test ends.
    """
    for name in blocked:
        monkeypatch.setitem(sys.modules, name, None)
    spec = importlib.util.spec_from_file_location("core._vision_probe", Path(vision_mod.__file__))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mss_import_failure_zeroes_every_gui_global(monkeypatch):
    # The outer guard: mss missing means pyautogui and PIL cannot be trusted either.
    probe = _load_vision_fresh(monkeypatch, blocked=("mss",))
    assert probe.mss is None
    assert probe.pyautogui is None
    assert probe.Image is None


def test_pyautogui_import_failure_leaves_mss_and_image_in_place(monkeypatch):
    # The inner guard catches a broken pyautogui on its own, without discarding what the
    # outer guard loaded. Compared against an unblocked load so the assertion also holds
    # where the optional GUI stack is absent altogether (the CI install has no mss).
    baseline = _load_vision_fresh(monkeypatch)
    probe = _load_vision_fresh(monkeypatch, blocked=("pyautogui",))
    assert probe.pyautogui is None
    assert probe.mss is baseline.mss
    assert probe.Image is baseline.Image


def test_the_headless_display_probe_is_undone(monkeypatch):
    # No DISPLAY: the module borrows ":99" for the pyautogui import and removes it again.
    monkeypatch.delenv("DISPLAY", raising=False)
    _load_vision_fresh(monkeypatch)
    assert "DISPLAY" not in os.environ


def test_the_display_probe_keeps_an_existing_display(monkeypatch):
    # A real DISPLAY is left exactly as it was found.
    monkeypatch.setenv("DISPLAY", ":7")
    _load_vision_fresh(monkeypatch)
    assert os.environ["DISPLAY"] == ":7"


# _take_screenshot: the grab-and-encode body, driven by a fake desktop


_JPEG_BYTES = b"jpeg-bytes"


class _FakeSctImage:
    """What mss.grab() hands back: a .size and a raw .bgra buffer."""

    def __init__(self, size, bgra):
        self.size = size
        self.bgra = bgra


class _FakeMSSSession:
    """A screen-capture session without a screen."""

    def __init__(self, monitor, shot):
        # index 0 is mss's "all monitors" aggregate; monitor 1 is the primary.
        self.monitors = [{"left": 0, "top": 0, "width": 4, "height": 4}, monitor]
        self._shot = shot
        self.grabbed = []
        self.closed = False

    def grab(self, monitor):
        self.grabbed.append(monitor)
        return self._shot

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        self.closed = True
        return False


class _FakeImageModule:
    """The slice of PIL.Image the grab body touches."""

    def __init__(self):
        self.frombytes_calls = []
        self.saved = {}

    def frombytes(self, mode, size, data, decoder, decoder_name):
        self.frombytes_calls.append((mode, size, data, decoder, decoder_name))
        saved = self.saved

        class _Img:
            def save(self, buffer, format=None, quality=None):
                saved.update(format=format, quality=quality)
                buffer.write(_JPEG_BYTES)

        return _Img()


def test_take_screenshot_grabs_and_encodes_the_primary_monitor(monkeypatch):
    monitor = {"left": 0, "top": 0, "width": 2, "height": 2}
    session = _FakeMSSSession(monitor, _FakeSctImage((2, 2), b"\x00\x01\x02\r"))
    image_mod = _FakeImageModule()
    monkeypatch.setattr(vision_mod, "mss", SimpleNamespace(mss=lambda: session))
    monkeypatch.setattr(vision_mod, "Image", image_mod)

    result = _take_screenshot()

    assert session.grabbed == [monitor]  # the primary monitor entry rather than the aggregate
    assert image_mod.frombytes_calls == [("RGB", (2, 2), b"\x00\x01\x02\r", "raw", "BGRX")]
    assert image_mod.saved == {"format": "JPEG", "quality": 85}
    assert session.closed is True
    assert base64.b64decode(result) == _JPEG_BYTES
