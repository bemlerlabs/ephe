"""What a capture says about itself, and the shipped claim it has to match.

The sentence this file exists over was in `docs/SECURITY_AND_PRIVACY.md` until it was
corrected here: "Shell, screenshot and GUI actions require explicit approval". Measured
against this tree, two of those three were true and one was not. Shell goes through the
shell confirm callback; `vision_click`/`vision_type` call `core.vision.check_sandbox`,
which raises when no approval channel is wired — that is a promise with teeth. A screen
capture had none: `take_screenshot` sits in `SELF_GATED_TOOLS`, the chat path reads that
set as "may run without a dialog", and the tool never asked for itself.

Two ways to close that gap were open. Putting the desktop gate in front of every capture
would answer the doc and stop every vision flow that has no dialog wired, so the honest
resolution taken here is the narrower one: the doc says what the code does, and the code
makes the run legible — the card states the scope it captured, with the frame's own
geometry read back off the file, so "I can see what it did" starts at the capture instead
of at a summary of it.

The pairing tests are what keep this from rotting in either direction: a claim about
asking is checked against the gate that would ask, and a claim about scope is checked
against the line the tool returns.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DOC = REPO / "docs" / "SECURITY_AND_PRIVACY.md"

from core.tools.system_tools import CAPTURE_SCOPE, take_screenshot  # noqa: E402


@pytest.fixture
def image_dir(tmp_path):
    d = tmp_path / "images"
    d.mkdir()
    return d


def write_a_frame(path: Path, width: int = 1234, height: int = 567) -> None:
    """A real PNG, so the geometry the answer states is read off bytes that exist."""
    from PIL import Image

    Image.new("RGB", (width, height), (8, 30, 90)).save(path, format="PNG")


def doc_row(heading: str) -> str:
    for line in DOC.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"| {heading} |"):
            return line
    return ""


# 1. the capture states its scope


@pytest.mark.asyncio
async def test_a_screen_capture_names_the_scope_it_took(image_dir, monkeypatch):
    """GIVEN a capture that produced a frame WHEN the answer is read
    THEN it states whole screen, the size on disk, and where the file was left."""
    from core.tools import system_tools

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("EPHE_IMAGE_DIR", str(image_dir))

    def fake_run(argv, **_kwargs):
        write_a_frame(Path(argv[-1]), width=1234, height=567)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(system_tools.subprocess, "run", fake_run)
    result = await take_screenshot()

    assert CAPTURE_SCOPE in result
    assert "1234x567" in result, "the scope line must carry the frame's own geometry"
    assert "no window and no page crop" in result
    assert "/images/" in result and "![Screenshot]" in result


@pytest.mark.asyncio
async def test_a_page_capture_says_it_is_a_page_and_not_the_screen(monkeypatch, image_dir):
    """The other scope in the same product: a rendered page, sized from the page object.

    Stating it costs no round trip — `viewport_size` is a property of the page, so the
    scope line cannot become the reason a capture got slower.
    """
    from core.browser import _page_capture_scope
    from core.tools import browser_tools

    class FakePage:
        viewport_size = {"width": 1280, "height": 800}

    assert "page viewport 1280x800" == _page_capture_scope(FakePage())

    class FakeManager:
        async def screenshot(self, session="default"):
            import base64

            return base64.b64encode(b"jpeg-bytes").decode("ascii")

        def capture_scope(self, session="default"):
            return "page viewport 1280x800"

    monkeypatch.setattr(browser_tools, "_get_browser_manager", lambda: FakeManager())
    monkeypatch.setenv("EPHE_IMAGE_DIR", str(image_dir))

    out = await browser_tools.browser_screenshot()
    assert "page viewport 1280x800" in out
    assert "no window and no screen" in out
    assert out.startswith("SCREENSHOT_FILE:"), "the frame stays a findable artifact"


def test_a_page_with_no_reportable_viewport_still_states_its_scope():
    """An unreadable size is a missing number, not a missing claim about what was taken."""
    from core.browser import _page_capture_scope

    class NoViewport:
        viewport_size = None

    assert _page_capture_scope(NoViewport()) == "page viewport (size unread)"


@pytest.mark.asyncio
async def test_an_unreadable_frame_does_not_cancel_the_capture(image_dir, monkeypatch):
    """The scope line is a header read; a file the reader cannot open must not eat the run."""
    from core.tools import system_tools

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setenv("EPHE_IMAGE_DIR", str(image_dir))

    def fake_run(argv, **_kwargs):
        Path(argv[-1]).write_bytes(b"not a png")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(system_tools.subprocess, "run", fake_run)
    result = await take_screenshot()

    assert "size unreadable" in result
    assert "![Screenshot]" in result
    assert "Screenshot failed" not in result


# 2. the doc and the gate are checked together


@pytest.mark.parametrize("name", ["take_screenshot", "browser_screenshot"])
def test_what_the_doc_calls_an_unasked_capture_the_gate_confirms(name):
    """The row says a capture runs without asking; the classification has to agree.

    Read together, the two are a contract. Kept apart, they are the bug this commit
    fixed: a shipped privacy claim describing a dialog nobody wrote.
    """
    from core.tools.approval import chat_tool_requires_confirm

    row = doc_row("Screen capture")
    assert "runs without asking" in row, row
    assert chat_tool_requires_confirm(name) is False, name


def test_the_approval_row_withdraws_the_capture_dialog_promise():
    """The corrected row speaks of shell and desktop control, and of nothing else."""
    row = doc_row("Tool approval")
    assert row and "approval" in row
    for withdrawn in ("screenshot", "screen capture"):
        assert withdrawn not in row.lower(), f"the row promises {withdrawn!r} again"


def test_the_desktop_half_still_asks_through_its_own_callback(monkeypatch):
    """The claim the row keeps, checked against the mechanism that makes it true.

    With no approval channel wired, `check_sandbox` raises instead of acting: explicit
    approval is what the row says, and a row that meant it needed a way to fail closed.
    """
    import asyncio

    import core.vision as vision

    class NoChannel:
        """A context with nothing wired: reads None, and survives the fixture teardown."""

        def get(self):
            return None

        def set(self, _value):
            return None

    monkeypatch.setattr(vision, "_sandbox_cb_var", NoChannel())
    monkeypatch.setattr(vision, "ON_SANDBOX_CONFIRM", None, raising=False)

    async def act():
        with pytest.raises(vision.SandboxConfirmationRequired):
            await vision.check_sandbox("vision_click", {"target_description": "x"})

    asyncio.run(act())
