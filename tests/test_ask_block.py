"""The AskUserQuestion block read by the terminal (finding #66).

`core/persona.py` offers the model the block convention beside the `ask_user` tool, and the
browser has parsed it since J6. The terminal printed it, so the reader met a question in its
wire format. These tests hold both halves of the fix: the parse keeps the JSON off the screen
and survives the shapes the model really writes, and what it cannot read stays visible —
silence would be the quieter loss.
"""
from __future__ import annotations

import json

from core.ask_block import parse_spec, split_block

BLOCK = {
    "question": "Which report should the summary lead with?",
    "options": [
        {"label": "Revenue first", "description": "the board asked for it"},
        {"label": "Churn first"},
    ],
    "recommendation": "Revenue first",
    "multiSelect": True,
}


def fenced(text: str) -> str:
    return "Here is the choice:\n\n```json\n" + text + "\n```\n"


class TestParseSpec:
    def test_a_fenced_block_becomes_a_question(self):
        spec = parse_spec(fenced(json.dumps(BLOCK)))
        assert spec is not None
        assert spec["question"].startswith("Which report")
        assert [one["label"] for one in spec["options"]] == ["Revenue first", "Churn first"]
        assert spec["options"][0]["description"] == "the board asked for it"
        assert spec["recommendation"] == "Revenue first"
        assert spec["multi_select"] is True

    def test_options_written_as_plain_strings(self):
        spec = parse_spec(fenced('{"question": "Which one?", "options": ["a", "b"]}'))
        assert spec is not None
        assert [one["label"] for one in spec["options"]] == ["a", "b"]

    def test_a_bare_block_is_found(self):
        spec = parse_spec('Sure — {"question": "Which one?", "options": ["a", "b"]} — tell me')
        assert spec is not None
        assert spec["question"] == "Which one?"

    def test_a_trailing_comma_is_tolerated(self):
        spec = parse_spec(fenced('{"question": "Which one?", "options": ["a", "b",],}'))
        assert spec is not None

    def test_one_option_is_not_a_question(self):
        assert parse_spec(fenced('{"question": "Which one?", "options": ["only"]}')) is None

    def test_a_json_block_about_something_else_is_left_alone(self):
        text = fenced('{"path": "a.py", "diff": "+1"}')
        assert parse_spec(text) is None


class TestSplitBlock:
    def test_the_block_leaves_the_answer_text(self):
        text = fenced(json.dumps(BLOCK))
        cleaned, spec = split_block(text)
        assert spec is not None
        assert cleaned == "Here is the choice:"
        assert "question" not in cleaned

    def test_an_unreadable_block_stays_visible(self):
        text = fenced('{"question": "Which one?", "options": ["only one"]}')
        cleaned, spec = split_block(text)
        assert spec is None
        assert cleaned == text.strip("\n") or "only one" in cleaned

    def test_text_without_any_block_passes_through(self):
        cleaned, spec = split_block("nothing to ask here")
        assert (cleaned, spec) == ("nothing to ask here", None)

    def test_an_empty_answer_is_not_a_crash(self):
        assert split_block("") == ("", None)
        assert parse_spec("") is None
