"""QD-015 Z: a capped turn is an offer, not a dead end — and the model knows
which tree it is working in before the first tool call.
"""

from __future__ import annotations

from core.chat import (
    CONTINUE_TURN_ROUNDS,
    MAX_TOOL_ITERATIONS,
    TOOL_BUDGET_HARD_CAP,
    budget_continue_frame,
)
from core.chat_prompt import _workspace_anchor


class TestBudget:
    def test_the_project_default_is_the_chat_class_default(self):
        from core.engine_config import GENERATION_BOUNDS

        assert MAX_TOOL_ITERATIONS == 25
        assert GENERATION_BOUNDS["tool_budget"][0] == MAX_TOOL_ITERATIONS

    def test_the_continuation_adds_ten_rounds_to_the_cap_it_read(self):
        frame = budget_continue_frame(25)
        assert frame == {
            "type": "budget",
            "action": "continue_turn",
            "cap": 25,
            "extra": CONTINUE_TURN_ROUNDS,
        }
        assert CONTINUE_TURN_ROUNDS == 10

    def test_the_frame_never_names_a_cap_above_the_hard_cap(self):
        assert budget_continue_frame(999)["cap"] == TOOL_BUDGET_HARD_CAP
        assert budget_continue_frame(None)["cap"] == MAX_TOOL_ITERATIONS
        # 0 means "unset", not "no rounds" — clamp_tool_budget keeps the class default.
        assert budget_continue_frame(0)["cap"] == MAX_TOOL_ITERATIONS


class TestWorkspaceAnchor:
    def test_the_block_names_the_active_project_with_its_absolute_path(self, monkeypatch, tmp_path):
        from core import workspace_rules

        monkeypatch.setattr(workspace_rules, "resolve_workspace_dir", lambda: str(tmp_path))
        block = _workspace_anchor()
        assert block is not None
        assert "## Active workspace" in block
        assert tmp_path.name in block
        assert str(tmp_path.resolve()) in block

    def test_no_workspace_means_no_block(self, monkeypatch):
        from core import workspace_rules

        monkeypatch.setattr(workspace_rules, "resolve_workspace_dir", lambda: "")
        assert _workspace_anchor() is None

    def test_the_block_lands_in_the_assembled_prompt(self):
        from core.chat_prompt import assemble_system_prompt

        block = "## Active workspace\nName: demo\nPath: /tmp/demo"
        prompt = assemble_system_prompt(model="m", workspace_ctx=block)
        assert block in prompt
