"""Wave 2 / B1 — the bounded custom-instruction layer.

The user's standing words enter the prompt as their own named, provenance-marked
stage: after the constant protocol and ahead of the project's files, capped with an
explicit truncation marker, absent when empty. The same block is what `/api/context/stages`
reports, so the display cannot drift from what the model reads.
"""
from __future__ import annotations

import pytest

from core.chat_prompt import (
    CUSTOM_INSTRUCTIONS_MAX,
    assemble_system_prompt,
    custom_instructions_block,
)
from core.settings_schema import normalize_field, save_deep_settings

KEY = "chat.custom_instructions"


def _store(text: str | None) -> None:
    fields: dict[str, object] = {} if text is None else {KEY: text}
    assert save_deep_settings({"chat": fields})


class TestTheBlock:
    def test_empty_stays_absent(self):
        _store(None)
        assert custom_instructions_block() is None
        prompt = assemble_system_prompt(model="m")
        assert "Custom instructions" not in prompt

    def test_provenance_names_the_user_as_the_author(self):
        _store("Answer in short sentences.")
        block = custom_instructions_block()
        assert block is not None
        assert block.startswith("## Custom instructions")
        assert "the user's own words" in block.split("\n", 1)[0]
        assert block.rstrip().endswith("Answer in short sentences.")

    def test_over_the_cap_is_marked_not_silently_cut(self):
        _store("x" * (CUSTOM_INSTRUCTIONS_MAX + 25))
        block = custom_instructions_block() or ""
        assert "… truncated (" in block
        assert f"{CUSTOM_INSTRUCTIONS_MAX} of {CUSTOM_INSTRUCTIONS_MAX + 25} chars shown" in block
        # The body itself stops at the cap; only the marker follows it.
        body = block.split("\n\n", 1)[1]
        assert body.startswith("x" * CUSTOM_INSTRUCTIONS_MAX)

    def test_whitespace_only_counts_as_empty(self):
        _store("   \n\t ")
        assert custom_instructions_block() is None


class TestThePosition:
    def test_custom_instructions_sit_before_the_workspace_rules(self):
        prompt = assemble_system_prompt(
            model="m",
            custom_instructions_ctx="CUSTOM-BLOCK",
            workspace_rules_ctx="WORKSPACE-BLOCK",
            profile_ctx="PROFILE-BLOCK",
        )
        assert prompt.index("CUSTOM-BLOCK") < prompt.index("WORKSPACE-BLOCK")
        assert prompt.index("WORKSPACE-BLOCK") < prompt.index("PROFILE-BLOCK")

    def test_the_same_settings_produce_the_same_bytes(self):
        _store("Be brief.")
        first = assemble_system_prompt(model="m", custom_instructions_ctx=custom_instructions_block())
        second = assemble_system_prompt(model="m", custom_instructions_ctx=custom_instructions_block())
        assert first == second


class TestTheStore:
    def test_a_stored_value_beyond_the_cap_reaches_the_prompt_and_is_marked(self):
        # The editor stops at the limit; a hand-edited settings.json does not, and the
        # reader is where the cut becomes visible instead of silent.
        oversize = "y" * (CUSTOM_INSTRUCTIONS_MAX + 40)
        stored = normalize_field(KEY, oversize)
        assert stored == oversize
        _store(oversize)
        block = custom_instructions_block() or ""
        assert "… truncated (" in block

    def test_the_stage_route_reports_it(self):
        _store("Stage me.")
        from server.routes.context import context_stages

        answer = context_stages()
        names = [stage["name"] for stage in answer["stages"]]
        assert "custom_instructions" in names
        stage = next(s for s in answer["stages"] if s["name"] == "custom_instructions")
        assert stage["chars"] > 0
        assert "Stage me." in stage["preview"]

    def test_the_route_stays_quiet_when_the_layer_is_empty(self):
        _store(None)
        from server.routes.context import context_stages

        names = [stage["name"] for stage in context_stages()["stages"]]
        assert "custom_instructions" not in names
