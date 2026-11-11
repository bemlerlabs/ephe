"""Characterisation — the plan core as it behaves today, before the planner seam.

Green before `capabilities.planner` existed and green after it: every assertion here is
a promise the seam must not move. The seam's own tests are
`tests/test_plugin_planner_strategy.py`, and the surface contract the render block owes
its four readers is `tests/test_plan_surface_contract.py`.

Held here: the step budget is the kernel ceiling, a step carries the same four reader
fields, the repair budget aborts the whole plan, and the rendered block plus the SSE
payload stay byte-for-byte what the client already parses.
"""
from __future__ import annotations

from core.ephe_plan import (
    MAX_PLAN_STEPS,
    MAX_REPAIRS_PER_STEP,
    MIN_PLAN_STEPS,
    PLAN_HEADING,
    EphePlan,
    StepStatus,
)


def _titles(count: int) -> list[str]:
    return [f"Step {index} names the file it changes" for index in range(count)]


class TestStepBudgetIsTheKernelCeiling:
    def test_a_short_plan_keeps_every_step(self):
        plan = EphePlan.from_titles(_titles(3))
        assert len(plan.steps) == 3
        assert plan.current == 0
        assert [step.status for step in plan.steps] == [StepStatus.PENDING] * 3

    def test_titles_carry_no_step_id_and_keep_their_order(self):
        plan = EphePlan.from_titles(["1. Read the route", "Write the case"])
        assert [step.title for step in plan.steps] == ["1. Read the route", "Write the case"]

    def test_blank_titles_are_dropped(self):
        plan = EphePlan.from_titles(["Read", "   ", "", "Write"])
        assert [step.title for step in plan.steps] == ["Read", "Write"]

    def test_more_titles_than_the_budget_are_cut_at_the_ceiling(self):
        plan = EphePlan.from_titles(_titles(12))
        assert len(plan.steps) == MAX_PLAN_STEPS

    def test_markdown_steps_are_cut_at_the_same_ceiling(self):
        block = PLAN_HEADING + "\n" + "\n".join(f"- [ ] {t}" for t in _titles(10))
        plan = EphePlan.from_markdown(block)
        assert len(plan.steps) == MAX_PLAN_STEPS

    def test_ledger_rows_are_cut_at_the_same_ceiling(self):
        rows = [{"id": i, "title": f"Row {i}", "status": "pending"} for i in range(10)]
        plan = EphePlan.from_ledger(rows)
        assert plan is not None
        assert len(plan.steps) == MAX_PLAN_STEPS

    def test_the_documented_ladder_is_the_enforced_one(self):
        assert MAX_PLAN_STEPS == 8
        assert MIN_PLAN_STEPS == 4
        assert MAX_REPAIRS_PER_STEP == 2
        assert MIN_PLAN_STEPS < MAX_PLAN_STEPS


class TestStepShapeIsUnchanged:
    def test_a_finished_mark_step_comes_in_done(self):
        plan = EphePlan.from_markdown(f"{PLAN_HEADING}\n- [ ] Read\n- [x] Done already")
        assert [step.status for step in plan.steps] == [
            StepStatus.PENDING,
            StepStatus.DONE,
        ]

    def test_a_numbered_ledger_prefix_is_not_part_of_the_title(self):
        plan = EphePlan.from_markdown(f"{PLAN_HEADING} · 1/2\n- [x] 1. Read routes\n- [ ] 2. Add")
        assert [step.title for step in plan.steps] == ["Read routes", "Add"]

    def test_one_checklist_line_without_a_heading_is_not_a_plan(self):
        assert EphePlan.try_from_markdown("- [ ] Read the router") is None

    def test_two_checklist_lines_without_a_heading_still_parse(self):
        plan = EphePlan.try_from_markdown("- [ ] Read the router\n- [ ] Add the case")
        assert plan is not None
        assert len(plan.steps) == 2

    def test_no_block_answers_none_while_the_strict_reader_raises(self):
        assert EphePlan.try_from_markdown("Plain prose, no plan.") is None
        try:
            EphePlan.from_markdown("Plain prose, no plan.")
        except ValueError:
            pass
        else:  # pragma: no cover - the raise is the promise
            raise AssertionError("from_markdown must raise when there is no plan block")

    def test_ledger_statuses_map_to_the_four_plan_statuses(self):
        plan = EphePlan.from_ledger(
            [
                {"id": 1, "title": "Read", "status": "completed"},
                {"id": 2, "title": "Write", "status": "in_progress"},
                {"id": 3, "title": "Test", "status": "pending"},
                {"id": 4, "title": "Drop", "status": "cancelled"},
            ]
        )
        assert plan is not None
        assert [step.status for step in plan.steps] == [
            StepStatus.DONE,
            StepStatus.RUNNING,
            StepStatus.PENDING,
            StepStatus.CANCELLED,
        ]
        assert plan.status == "running"

    def test_an_empty_ledger_is_no_plan(self):
        assert EphePlan.from_ledger([]) is None


class TestRepairBudgetIsTheKernelAbort:
    def test_a_failed_step_stays_while_the_repair_budget_lasts(self):
        plan = EphePlan.from_titles(["Read", "Write"])
        plan.start_current()
        for _ in range(MAX_REPAIRS_PER_STEP):
            plan.complete_current(ok=False)
        assert plan.current == 0
        assert plan.steps[0].status == StepStatus.RUNNING
        assert plan.steps[0].repairs == MAX_REPAIRS_PER_STEP
        assert plan.status == "running"

    def test_the_repair_past_the_budget_fails_the_whole_plan(self):
        plan = EphePlan.from_titles(["Read", "Write"])
        plan.start_current()
        for _ in range(MAX_REPAIRS_PER_STEP + 1):
            plan.complete_current(ok=False)
        assert plan.steps[0].status == StepStatus.FAILED
        assert plan.status == "failed"

    def test_a_verified_step_advances(self):
        plan = EphePlan.from_titles(["Read", "Write"])
        plan.start_current()
        plan.complete_current(ok=True)
        assert plan.steps[0].status == StepStatus.DONE
        assert plan.current == 1

    def test_the_last_step_verified_completes_the_plan(self):
        plan = EphePlan.from_titles(["Read"])
        plan.start_current()
        plan.complete_current(ok=True)
        assert plan.status == "done"


class TestCheckpointAnchor:
    def test_a_writing_step_gets_its_rollback_anchor(self):
        plan = EphePlan.from_titles(["Read", "Write"])
        plan.steps[1].mutating = True
        plan.start_current()
        plan.complete_current(ok=True)
        plan.start_current()
        assert plan.steps[1].checkpoint_before is True
        assert plan.steps[1].checkpoint_snapshot == {}

    def test_a_read_step_gets_no_anchor(self):
        plan = EphePlan.from_titles(["Read"])
        plan.start_current()
        assert plan.steps[0].checkpoint_before is False


class TestRenderedBlockAndPayload:
    def test_the_rendered_block_is_the_same_text_the_client_parses(self):
        plan = EphePlan.from_titles(["Read the router", "Add the case"])
        plan.start_current()
        plan.complete_current(ok=True)
        plan.start_current()
        assert plan.render() == (
            f"{PLAN_HEADING} · 1/2\n- [x] Read the router\n- [>] Add the case"
        )

    def test_the_stream_payload_keeps_its_four_keys(self):
        plan = EphePlan.from_titles(["Read", "Write"])
        plan.start_current()
        assert plan.as_dict() == {
            "state": "running",
            "done": 0,
            "total": 2,
            "steps": [
                {"title": "Read", "status": "running"},
                {"title": "Write", "status": "pending"},
            ],
        }

    def test_a_step_that_runs_but_is_not_current_renders_pending(self):
        plan = EphePlan.from_titles(["Read", "Write"])
        plan.steps[0].status = StepStatus.RUNNING
        plan.steps[1].status = StepStatus.RUNNING
        plan.current = 1
        assert "- [ ] Read" in plan.render()
        assert "- [>] Write" in plan.render()
