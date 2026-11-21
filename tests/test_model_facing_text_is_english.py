"""The text the engine is instructed with is English (root AGENTS.md, "English in the tree").

Five builders spoke German at the model, and two of them mixed it into an otherwise English
sentence, so the mixing was visible inside the prompt itself. Each test calls the builder and
reads what the model would receive. The words below are ASCII-folded on purpose — that is how
the builders wrote them ("uebergeben", "vollstaendig"), so the fold is part of what is pinned.
Example *content* stays German where it is user data: the guard is about our labels.
"""
from __future__ import annotations

import asyncio
import re
import types
from unittest.mock import patch

from core import cell_output
from core.feedback import FeedbackExample, FeedbackStore
from core.goal_loop import GoalRunner
from core.react import reflect

GERMAN = re.compile(
    r"\b(uebergeben|vollstaendig|gesichert|verloren|abholbar|Koerper|Beispiel|Frage|Antwort"
    r"|Pruefbefehl|schlug fehl|Aenderungen|naechsten|Minimum-Aenderung|Byte)\b"
)


def _assert_english(text: str) -> None:
    hit = GERMAN.search(text)
    assert hit is None, f"model-facing text carries German ({hit.group(0)!r}): {text!r}"


def test_excerpt_spokes_the_cut_in_english() -> None:
    """The truncation marker lands in the tool result, so the model reads it verbatim."""
    data = b"x" * (cell_output.OUTPUT_CAP_BYTES + 500)

    partial, truncated = cell_output.excerpt(data, "stdout.log", total=len(data) + 1000, start=0)
    assert truncated
    _assert_english(partial)
    assert "bytes not delivered" in partial and "are lost" in partial
    # The span is the half that makes the journal retrievable without guessing.
    assert "bytes 0..10500 in /work/stdout.log" in partial

    whole, truncated = cell_output.excerpt(data, "stdout.log", total=len(data), start=0)
    assert truncated
    _assert_english(whole)
    assert "complete —" in whole


def test_loss_lines_speaks_both_halves_in_english() -> None:
    """`cpython_report` appends these lines to the run report the model is handed."""
    shorted = {
        "stdout_bytes": 1000,
        "stdout_log_bytes": 400,
        "stdout_log_start": 0,
        "stdout": "abc",
    }
    line = cell_output.loss_lines(shorted)[0]
    _assert_english(line)
    assert "bytes produced" in line and "bytes secured" in line and "bytes gone" in line

    secured = {
        "stdout_bytes": 1000,
        "stdout_log_bytes": 1000,
        "stdout_log_start": 0,
        "stdout": "abc",
    }
    line = cell_output.loss_lines(secured)[0]
    _assert_english(line)
    assert "fully secured" in line and "retrievable in this session" in line


def test_the_few_shot_labels_are_english(tmp_path) -> None:
    """The example pair is user data and may stay German; the label around it is ours."""
    example = FeedbackExample(prompt="Wie spaet ist es?", response="Dreizehn Uhr.")
    with patch.object(FeedbackStore, "get_good_examples", return_value=[example]):
        text = FeedbackStore(base_dir=tmp_path).to_few_shot_string()

    _assert_english(text)
    assert "Example 1:" in text and "Prompt:" in text and "Response:" in text


def test_the_reflexion_prompt_is_english_throughout() -> None:
    """One label of eight English words was German inside the same prompt string."""
    captured: dict[str, object] = {}

    class _Client:
        async def chat(self, **kwargs):
            captured["messages"] = kwargs["messages"]
            return types.SimpleNamespace(message=types.SimpleNamespace(content="REVISION: no"))

    with patch("core.react._resolve_provider", return_value={}), patch(
        "core.react.build_provider_client", return_value=_Client()
    ), patch("core.react._native_thinking_kwargs", return_value={}):
        result = asyncio.run(reflect("Es ist dreizehn Uhr.", "Wie spaet ist es?", "some-model"))

    assert result.status != "provider_error"
    prompt = captured["messages"][1]["content"]  # type: ignore[index]
    _assert_english(prompt)
    assert prompt.startswith("Question: ") and "Answer to evaluate:" in prompt


def test_the_goal_loop_asks_for_the_next_edit_in_english() -> None:
    """The repair instruction the loop feeds back after a failed check is model context."""
    last_user_message: list[str] = []

    async def fake_chat(*, model, history, on_chunk, on_phase=None, turn_id=""):
        last_user_message.append(history[-1]["content"])
        return "the patch is in"

    async def fake_execute(name, args, policy):
        return "1 failed"

    with patch("core.chat.chat_with_tools", fake_chat), patch(
        "core.tools.registry.execute_tool", fake_execute
    ):
        result = asyncio.run(
            GoalRunner(model="m", check_command="pytest -q", max_turns=2).run("make the suite pass")
        )

    assert not result.success
    _assert_english(last_user_message[-1])
    assert "The check command 'pytest -q' failed:" in last_user_message[-1]
    assert "Correct the changes" in last_user_message[-1]
