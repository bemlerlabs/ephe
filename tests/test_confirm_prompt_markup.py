"""ConfirmPrompt markup: no orphaned Rich tags (TUI crash protection).

Root cause (screenshot from the user): when the ConfirmPrompt mounted,
the whole TUI crashed with

    MarkupError: closing tag '[/<hex>]' does not match any open tag

The hint line had ONE opening tag before its letter and TWO closing tags —
the second was orphaned. Textual renders the child Static at the first layout
reflow, Rich's markup parser throws, the exception propagates through the
compositor (``_refresh_layout`` → ``reflow`` → ``arrange`` → ``render``) and
kills the app.

These tests make sure that the exact crash path (ConfirmPrompt mount
→ Static render) produces valid Rich markup — otherwise the TUI crashes at the
next unbalanced colour-tag pair. The balance is read generically, so the check
follows the palette constants of ``ui/palette.py`` instead of pinning a colour
value that the surface has since retired.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from rich.markup import render

UI_DIR = Path(__file__).parent.parent / "ui"


def _static_content(widget: Any) -> str:
    """Reads the raw markup string out of a Textual Static.

    Textual 8.x types ``content`` as ``VisualType``; at runtime it is
    the original string (as long as no visual override is set).
    """
    return str(widget.content)


# Target test: exact crash path (ConfirmPrompt mount → Static render)

@pytest.mark.asyncio
async def test_confirm_prompt_composes_without_markup_error():
    """GIVEN a ConfirmPrompt is built with a question containing Rich-sensitive
    special characters (dots, brackets, /, ?, the -rf flag)
    THEN the composed question Static renders WITHOUT MarkupError.

    That is the exact crash path from the screenshot: Textual renders the
    child Static at the layout reflow, Rich throws MarkupError, the app crashes.
    """
    from textual.app import App, ComposeResult
    from textual.widgets import Static

    from ui.widgets import ConfirmPrompt

    # Question with every Rich-sensitive character that really occurs in tool args:
    # round bracket, slash, question mark, hyphen, dot.
    question = "run_shell: rm -rf build/? (target: [build]/out)"
    prompt = ConfirmPrompt(question, tool_name="run_shell")

    class Host(App):
        def compose(self) -> ComposeResult:
            yield prompt

    async with Host().run_test():
        static = prompt.query_one("#confirm-question", Static)
        # Parse the Rich markup: throws MarkupError on orphaned/unbalanced tags.
        render(_static_content(static))


@pytest.mark.asyncio
async def test_confirm_prompt_escapes_user_question():
    """GIVEN the question contains Rich tags as PLAIN TEXT ([shell] etc.)
    THEN they appear in the Static content ESCAPED (\\[) — not as markup.

    Otherwise a tool name carrying [b] could unintentionally inject markup
    or (worse) bring the parser to crashing.
    """
    from textual.app import App, ComposeResult
    from textual.widgets import Static

    from ui.widgets import ConfirmPrompt

    prompt = ConfirmPrompt("run [shell] --target build", tool_name="run_shell")

    class Host(App):
        def compose(self) -> ComposeResult:
            yield prompt

    async with Host().run_test():
        static = prompt.query_one("#confirm-question", Static)
        content = _static_content(static)
        assert "\\[" in content, "question tags are not escaped — markup injection risk"
        render(content)  # escaped → still renders cleanly


# Regression test: the exact bug line (the a=Always hint) at source level

def test_confirm_prompt_hint_line_is_balanced():
    """GIVEN the ConfirmPrompt hint (the y/n/a line) in the source code
    THEN every colour tag on that line is balanced (no orphaned tags) and the
    'a' affordance carries its label, not just a colour.

    The crash from the screenshot: three colour tags on the line, an orphaned
    closing tag at the end of it. The tag shape is read generically — a literal
    hex or a ``{NAME}`` constant of ``ui/palette.py`` — so moving a colour into
    the palette cannot leave this test checking a retired value.
    """
    widgets_src = (UI_DIR / "widgets.py").read_text(encoding="utf-8")
    tag = r"(\{[A-Z_]+\}|#[0-9A-Fa-f]{6})"
    # The a=Always hint: one opening tag, the letter, one matching closing tag.
    match = re.search(r"\[" + tag + r"\](a)\[/\1\][^\"]*", widgets_src)
    assert match, "the a=Always hint line is no longer findable (refactored?)"
    hint = match.group(0)

    opens = re.findall(r"\[" + tag + r"\]", hint)
    closes = re.findall(r"\[/" + tag + r"\]", hint)
    assert opens and opens == closes, (
        f"unbalanced colour tags in the a=Always hint: {opens} opens, {closes} closes"
    )
    assert "Always" in hint, "the 'a' affordance lost its label"
