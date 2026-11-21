"""
◑ Ephe – TDD: EphePlan (round I3, the coding-agent core)

Given / When / Then – strictly.

Purpose: the Ephe agent works tasks off as a PLAN — steps with status,
a hard step budget (max. 8), a repair budget per step (max. 2
repair attempts after a failed self-verification), checkpoint markers
before every writing step. Pure logic, no I/O — the react_loop and the
CLI consume it; the status popover later shows x/y progress.
"""
from __future__ import annotations

import pytest

from core.ephe_plan import (
    MAX_PLAN_STEPS,
    MAX_REPAIRS_PER_STEP,
    EphePlan,
    EpheStep,
    StepStatus,
)


class TestEphePlanCreation:

    def test_given_titles_when_created_then_steps_pending_and_index_0(self):
        """G: step titles W: EphePlan.from_titles T: all pending, current=0"""
        plan = EphePlan.from_titles(["Dateien lesen", "Patch schreiben", "Tests laufen"])
        assert plan.current == 0
        assert [s.status for s in plan.steps] == [StepStatus.PENDING] * 3
        assert [s.title for s in plan.steps] == ["Dateien lesen", "Patch schreiben", "Tests laufen"]

    def test_given_too_many_titles_when_created_then_capped_at_budget(self):
        """G: 12 steps W: creation T: capped at MAX_PLAN_STEPS (loop guard)"""
        plan = EphePlan.from_titles([f"Schritt {i}" for i in range(12)])
        assert len(plan.steps) == MAX_PLAN_STEPS

    def test_given_empty_titles_when_created_then_value_error(self):
        """G: no steps W: creation T: ValueError (fail honestly)"""
        with pytest.raises(ValueError):
            EphePlan.from_titles([])


class TestEphePlanProgression:

    def test_given_running_plan_when_step_verified_then_advance(self):
        """G: step 0 running W: complete_current(ok=True) T: step done, current=1"""
        plan = EphePlan.from_titles(["a", "b"])
        plan.start_current()
        plan.complete_current(ok=True)
        assert plan.steps[0].status == StepStatus.DONE
        assert plan.current == 1

    def test_given_failed_step_when_repair_budget_left_then_stays_with_repairs(self):
        """G: verification failed, 0 repairs W: complete_current(ok=False)
        T: the step stays RUNNING, repairs=1, current unchanged"""
        plan = EphePlan.from_titles(["a", "b"])
        plan.start_current()
        plan.complete_current(ok=False)
        assert plan.current == 0
        assert plan.steps[0].status == StepStatus.RUNNING
        assert plan.steps[0].repairs == 1

    def test_given_repair_budget_exhausted_when_failed_again_then_plan_failed(self):
        """G: MAX_REPAIRS_PER_STEP repairs used up W: fail once more
        T: Plan.status=failed (an honest hand-over instead of an endless loop)"""
        plan = EphePlan.from_titles(["hart", "b"])
        plan.start_current()
        for _ in range(MAX_REPAIRS_PER_STEP):
            plan.complete_current(ok=False)
        plan.complete_current(ok=False)
        assert plan.status == "failed"

    def test_given_last_step_done_when_completed_then_plan_done(self):
        """G: the last step W: complete_current(ok=True) T: Plan.status=done"""
        plan = EphePlan.from_titles(["a"])
        plan.start_current()
        plan.complete_current(ok=True)
        assert plan.status == "done"

    def test_given_mutating_step_when_started_then_checkpoint_marker(self):
        """G: a writing step (mutating=True) W: start_current
        T: checkpoint_before=True (the rollback anchor before writing)"""
        plan = EphePlan.from_titles(["lesen", "patchen"])
        plan.steps[1].mutating = True
        plan.start_current()
        plan.complete_current(ok=True)   # step 0 ("lesen") is done
        plan.start_current()             # step 1 ("patchen", mutating) starts
        assert plan.steps[0].checkpoint_before is False
        assert plan.steps[1].checkpoint_before is True


class TestEphePlanRendering:

    def test_given_plan_when_rendered_then_checklist_with_marks(self):
        """G: plan with done/running/pending W: render T: [x]/[>]/[ ] markers + progress x/y"""
        plan = EphePlan.from_titles(["lesen", "patchen", "testen"])
        plan.start_current()
        plan.complete_current(ok=True)   # step 0 done -> current=1
        plan.start_current()
        text = plan.render()
        assert "1/3" in text
        assert "[x] lesen" in text
        assert "[>] patchen" in text
        assert "[ ] testen" in text

    def test_given_plan_when_progress_called_then_done_and_total(self):
        """G: 1 of 2 done W: progress T: (1, 2) — for the status popover"""
        plan = EphePlan.from_titles(["a", "b"])
        plan.steps[0].status = StepStatus.DONE
        assert plan.progress() == (1, 2)

    def test_given_plan_markdown_when_parsed_then_steps_extracted(self):
        """G: model output with a plan checklist W: EphePlan.from_markdown
        T: steps from '- [ ] <title>' lines, the budget applies"""
        md = (
            "## Plan\n"
            "- [ ] Dateien lesen\n"
            "- [x] Schon erledigt\n"
            "- [ ] Patch schreiben\n"
        )
        plan = EphePlan.from_markdown(md)
        assert [s.title for s in plan.steps] == ["Dateien lesen", "Schon erledigt", "Patch schreiben"]
        assert plan.steps[1].status == StepStatus.DONE

    def test_given_markdown_without_plan_when_parsed_then_value_error(self):
        """G: text without a checklist W: from_markdown T: ValueError"""
        with pytest.raises(ValueError):
            EphePlan.from_markdown("Kein Plan hier, nur Prosa.")
