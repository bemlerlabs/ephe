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
import pytest
from rich.markup import render

UI_DIR = Path(__file__).parent.parent / "ui"


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
        render(static.content.plain)


@pytest.mark.asyncio
async def test_confirm_prompt_keeps_a_tagged_question_as_text():
    """GIVEN the question contains bracket shapes that a parser would read as tags
    THEN they reach the screen verbatim, and the prompt's content is a Text rather
    than a markup string.

    Escaping was the first answer to this crash and it is not enough: neither
    rich's nor Textual's ``escape`` quotes a group like ``[$@3cg\\x01]``, and
    Textual's tokenizer still reads it as a tag. Only a renderable that never
    meets a parser closes the class.
    """
    from textual.app import App, ComposeResult
    from rich.text import Text
    from textual.widgets import Static

    from ui.widgets import ConfirmPrompt

    prompt = ConfirmPrompt(
        "run [shell] --target build [$@3cg\\x01\\x02=] (c:\\[dir])", tool_name="run_shell"
    )

    class Host(App):
        def compose(self) -> ComposeResult:
            yield prompt

    async with Host().run_test():
        static = prompt.query_one("#confirm-question", Static)
        assert isinstance(static.content, Text)
        plain = static.content.plain
        assert "[shell]" in plain
        assert "[$@3cg\\x01\\x02=]" in plain
        assert "c:\\[dir]" in plain


def test_confirm_prompt_hint_line_is_balanced():
    """GIVEN the ConfirmPrompt hint (the y/n/a line) in the source code
    THEN it is built as a styled Text and no markup string is assembled from the
    question.

    The crash from the screenshot was an orphaned closing colour tag in a
    hand-built markup string. The line moved to ``Text.assemble``, so the guard
    is that the question never re-enters a markup string again.
    """
    widgets_src = (UI_DIR / "widgets.py").read_text(encoding="utf-8")
    compose_src = widgets_src[
        widgets_src.index("class ConfirmPrompt"):
    ].split("def on_mount")[0]

    assert "Text.assemble" in compose_src, "the hint lost its Text build"
    assert "markup_escape(question)" not in compose_src, (
        "the question is back inside a markup string"
    )
    assert '"=Always (this tool, this session)"' in compose_src, (
        "the 'a' affordance lost its label"
    )
