"""The plan contract: guard, emitter, parser and renderer over one shape.

Four components named a plan and disagreed (work item #92, measured 0 plans in 4 live turns).
Held here are the seams between them: what the emitter writes is what the parser reads, what
the guard instructs is the same block, and the fixture the client parses is that output.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.ephe_plan import (
    MAX_PLAN_STEPS,
    MIN_PLAN_STEPS,
    PLAN_HEADING,
    EphePlan,
    StepStatus,
)
from core.persona import PAGE_OUTPUT_GUARD, PLAN_MODE_GUARD, needs_page_guard

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "app" / "fixtures" / "plan" / "rendered-block.txt"


def _sample() -> EphePlan:
    plan = EphePlan.from_titles(
        [
            "Read the three route files the request names",
            "Add the failing case to the existing test family",
            "Change the handler and keep the response shape",
            "Run the family and report the count",
        ]
    )
    plan.start_current()
    plan.complete_current(ok=True)
    plan.start_current()
    plan.steps[2].mutating = True
    return plan


class TestOneShape:

    def test_rendered_block_parses_back_to_the_same_plan(self):
        """The emitter's own output must feed from_markdown(): the two were different
        dialects (a bare `[x] title` line against a required `- [ ]` bullet)."""
        plan = _sample()
        again = EphePlan.from_markdown(plan.render())
        assert [s.title for s in again.steps] == [s.title for s in plan.steps]
        assert [s.status for s in again.steps] == [s.status for s in plan.steps]

    def test_render_uses_the_heading_the_contract_names(self):
        text = _sample().render()
        assert text.split("\n")[0].startswith(PLAN_HEADING)
        assert all(line.startswith("- [") for line in text.split("\n")[1:])

    def test_the_committed_fixture_is_what_the_emitter_writes(self):
        """app/fixtures/plan/rendered-block.txt is what app/src/lib/planCardModel.ts
        parses. A drift here moves the client's read of every plan."""
        assert FIXTURE.read_text(encoding="utf-8").strip() == _sample().render().strip()

    def test_a_step_line_cut_off_mid_write_keeps_the_block(self):
        plan = EphePlan.try_from_markdown(f"{PLAN_HEADING}\n- [ ] Read the three route fil")
        assert plan is not None
        assert plan.steps[0].title == "Read the three route fil"

    def test_no_block_returns_none_instead_of_raising(self):
        assert EphePlan.try_from_markdown("Plain prose.") is None
        assert EphePlan.try_from_markdown("") is None
        with pytest.raises(ValueError):
            EphePlan.from_markdown("Plain prose.")

    def test_the_ledger_id_does_not_reach_the_title(self):
        plan = EphePlan.from_markdown(
            f"{PLAN_HEADING} · 1/2\n- [x] 1. Read routes\n- [>] 2. Add the case"
        )
        assert [s.title for s in plan.steps] == ["Read routes", "Add the case"]

    def test_every_status_mark_round_trips(self):
        for status in StepStatus:
            plan = EphePlan.from_markdown(f"{PLAN_HEADING}\n- [ ] a\n- [ ] b")
            plan.steps[0].status = status
            parsed = EphePlan.from_markdown(plan.render())
            assert parsed.steps[0].status is status


class TestGuardInstructsTheShape:

    def test_guard_names_the_heading_and_the_checklist_mark(self):
        assert PLAN_HEADING in PLAN_MODE_GUARD
        assert "- [ ]" in PLAN_MODE_GUARD

    def test_guard_bounds_the_step_count_within_the_core_budget(self):
        """A guard promising more steps than the core holds writes a plan that gets cut."""
        assert f"{MIN_PLAN_STEPS} to {MAX_PLAN_STEPS}" in PLAN_MODE_GUARD

    def test_the_example_lines_inside_the_guard_parse_as_a_plan(self):
        """The guard's own example is the contract: if it does not parse, the instruction
        and the parser disagree in the same sentence."""
        block = "\n".join(
            line for line in PLAN_MODE_GUARD.split("\n")
            if line.startswith(PLAN_HEADING) or line.startswith("- [")
        )
        plan = EphePlan.from_markdown(block)
        assert len(plan.steps) >= MIN_PLAN_STEPS, (
            "the guard's own example is shorter than the floor it states, so a model that "
            "copies it writes a set the core would call a sentence"
        )
        short = [s.title for s in plan.steps if len(s.title) < 12]
        assert not short, f"the guard's own example carries a step that names nothing: {short}"

    def test_guard_names_the_shortest_step_it_accepts(self):
        """A step shorter than this names no target, so the block stops being a plan."""
        assert "no step shorter than 12 characters" in PLAN_MODE_GUARD

    def test_guard_forbids_the_numbered_form_the_old_one_demanded(self):
        assert "no numbered lists" in PLAN_MODE_GUARD

    def test_guard_closes_the_question_loop(self):
        """Measured: both plan-mode turns ended on a question and carried no plan."""
        assert "without a plan" in PLAN_MODE_GUARD


class TestLedgerPlan:

    def test_ledger_rows_become_a_plan_with_the_same_statuses(self):
        plan = EphePlan.from_ledger(
            [
                {"id": 1, "title": "Read", "status": "completed"},
                {"id": 2, "title": "Write", "status": "in_progress"},
                {"id": 3, "title": "Test", "status": "pending"},
            ]
        )
        assert plan is not None
        assert plan.as_dict()["done"] == 1
        assert plan.as_dict()["state"] == "running"
        assert [s["status"] for s in plan.as_dict()["steps"]] == ["done", "running", "pending"]

    def test_an_empty_ledger_is_no_plan(self):
        assert EphePlan.from_ledger([]) is None

    def test_the_tool_output_of_the_ledger_is_the_plan_block(self):
        """todo_list prints what the parser reads, so the model echoes one shape."""
        import asyncio

        from core.tools import todo_tools

        todo_tools.reset_todo()
        out = asyncio.run(todo_tools.todo_list(action="set", items="Read routes\nAdd case\nChange\nRun"))
        assert out.startswith(PLAN_HEADING)
        assert len(EphePlan.from_markdown(out).steps) == 4


class TestPageGuidance:

    def test_a_page_request_carries_the_guard(self):
        assert needs_page_guard("I need a landing page for my product")
        assert needs_page_guard("build me a website clone")

    def test_an_unrelated_request_does_not(self):
        for text in (
            "add a test for the parser",
            "what does the left side of this layout mean",
            "sum the csv files",
            "explain the auth middleware",
        ):
            assert not needs_page_guard(text), text

    def test_guard_states_the_countable_floors(self):
        for token in ("<h1>", "1.25", "4.5:1", "390px", "1280px", "four"):
            assert token in PAGE_OUTPUT_GUARD, token

    def test_guard_is_engine_facing_prose(self):
        """The engine reads this; it is machine-facing text and therefore English."""
        assert not re.search(r"[äöüÄÖÜß]", PAGE_OUTPUT_GUARD)


class TestStreamEvent:

    def test_plan_payload_carries_state_and_counts(self):
        payload = _sample().as_dict()
        assert payload["state"] == "running"
        assert (payload["done"], payload["total"]) == (1, 4)
        assert len(payload["steps"]) == 4

    def test_the_route_emits_the_plan_frame_as_the_answer_streams(self):
        """The frame is what makes the steps visible while the answer streams: the block
        grows one line at a time and every distinct state arrives as its own frame."""
        from server.routes.chat import _make_stream_callbacks

        frames: list[dict] = []
        on_chunk, *_ = _make_stream_callbacks(
            frames.append, [], [], "session-x", "turn-1"
        )
        on_chunk("Working now.\n" + PLAN_HEADING + "\n- [ ] Read routes\n")
        on_chunk("- [ ] Add the failing ca")
        on_chunk("se\n- [ ] Run the famil")
        plan_frames = [f for f in frames if f.get("type") == "plan"]
        assert [f["total"] for f in plan_frames] == [1, 2, 3]
        assert plan_frames[-1]["steps"][0]["title"] == "Read routes"
        assert plan_frames[-1]["steps"][2]["title"] == "Run the famil"

    def test_a_repeated_state_emits_no_second_frame(self):
        from server.routes.chat import _make_stream_callbacks

        frames: list[dict] = []
        on_chunk, *_ = _make_stream_callbacks(frames.append, [], [], "session-y", "turn-2")
        on_chunk(PLAN_HEADING + "\n- [ ] Read routes\n- [ ] Add case\n")
        first = len([f for f in frames if f.get("type") == "plan"])
        on_chunk(" trailing words only\nmore prose")
        on_chunk(" and more")
        assert len([f for f in frames if f.get("type") == "plan"]) == first
