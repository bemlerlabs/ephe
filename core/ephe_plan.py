"""core/ephe_plan.py – EphePlan (round I3): the plan core of the Ephe coding agent.

The Ephe agent works tasks as a PLAN: steps with status, a hard
step budget (MAX_PLAN_STEPS) and a repair budget per step
(MAX_REPAIRS_PER_STEP) against endless loops, a checkpoint marker before each
writing step (the rollback anchor), honest failure (status=failed
when the budget is exhausted — hand off to the user instead of simulating).

Budget cascade (R37/R43, documented as ONE schema). The numbers below are the
ENFORCED ones, not a second table: `budget_cascade()` further down is the
machine-readable form and resolves the tool-round levels from the enforcer
(`core.chat`) at call time, so a change there cannot leave a stale ladder behind.
  level 1  MAX_PLAN_STEPS         =  8   – plan steps (checklist length)
  level 2  MAX_REPAIRS_PER_STEP   =  2   – repair attempts per step
  level 3  tool rounds (casual)   = 25   – core/chat.py::MAX_TOOL_ITERATIONS (R46), the clamp default
  level 3' tool rounds (/ephe)    = 40   – server/routes/chat.py::EPHE_TOOL_BUDGET (R37)
  level 4  TOOL_BUDGET_HARD_CAP   = 40   – hard ceiling (all classes), core/chat.py::clamp_tool_budget
Cascade logic: the hard cap is a CEILING that `clamp_tool_budget` enforces, mapping every request into [1, TOOL_BUDGET_HARD_CAP], and the /ephe coding class
sits AT the cap. Every level has a clear, documented ceiling, so an endless loop
in one level cannot block the whole system.

Pure logic, no I/O. The react_loop (/ephe) drives it; render()/progress()
feed the chat stream and the status popover.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

MAX_PLAN_STEPS = 8
MIN_PLAN_STEPS = 4
MAX_REPAIRS_PER_STEP = 2


def budget_cascade() -> dict[str, int]:
    """The declared R37/R43 ladder, read off the ENFORCER — one schema, no second table.

    The tool-round levels come from ``core.chat`` at call time instead of being
    restated here: the 2026-10 ladder declared ``MAX_TOOL_ITERATIONS = 10`` while
    the loop already enforced 25 (and a coding class of 25 while ``/ephe`` already
    ran at 40), and nothing caught the disagreement. Read from the enforcer, the
    declaration is equal to the enforcement by construction; the prose ladder in
    the module docstring is pinned to the same numbers by
    ``tests/test_w7_12_budget_cascade.py``.
    """
    from core.chat import MAX_TOOL_ITERATIONS, TOOL_BUDGET_HARD_CAP

    return {
        "plan_steps": MAX_PLAN_STEPS,
        "repairs_per_step": MAX_REPAIRS_PER_STEP,
        "tool_rounds": MAX_TOOL_ITERATIONS,
        "tool_rounds_hard_cap": TOOL_BUDGET_HARD_CAP,
    }


# The one text shape. The guard instructs it, render() writes it, from_markdown() reads it,
# and app/src/lib/planCardModel.ts renders it — four readers of one contract. The heading is
# a marker the surface replaces with its own translated title, so it stays English in every
# answer language; the step count behind it is optional because a model cannot know it.
PLAN_HEADING = "## Plan"

_CHECKLIST_RE = re.compile(r"^\s*(?:[-*+]\s*)?\[([ >xX!-])\]\s+(.+?)\s*$")
_HEADING_RE = re.compile(r"^\s*(?:#+\s*)?\*{0,2}\s*Plan\s*(?:·\s*\d+\s*/\s*\d+)?\s*\*{0,2}\s*$")
# The ledger prints `2. Title` because the number is the id an update call takes. The
# reader numbers its own rows, so the prefix comes off at the parse.
_STEP_ID_RE = re.compile(r"^\d+[.)]\s+")


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


# One mark per status, in both directions. The counts a reader sees are always derived
# from these marks, never carried alongside them, so a heading and its steps cannot disagree.
_MARK_OF = {
    StepStatus.PENDING: "[ ]",
    StepStatus.RUNNING: "[>]",
    StepStatus.DONE: "[x]",
    StepStatus.FAILED: "[!]",
    StepStatus.CANCELLED: "[-]",
}
_STATUS_OF = {
    " ": StepStatus.PENDING,
    "x": StepStatus.DONE,
    "X": StepStatus.DONE,
    ">": StepStatus.RUNNING,
    "!": StepStatus.FAILED,
    "-": StepStatus.CANCELLED,
}


@dataclass
class EpheStep:
    title: str
    status: StepStatus = StepStatus.PENDING
    """Writing step -> a checkpoint marker before execution."""
    mutating: bool = False
    checkpoint_before: bool = False
    """E3: snapshot mapping {path: content} for this step's rollback.
    Filled before the first writing tool call; on failed -> restore."""
    checkpoint_snapshot: dict[str, str] | None = None
    repairs: int = 0
    """E7: verify_artifact() note from the last completed check (for the stream/popover)."""
    evidence: str = ""


@dataclass
class EphePlan:
    steps: list[EpheStep] = field(default_factory=list)
    current: int = 0
    status: str = "pending"  # pending | running | done | failed

    # Construction

    @classmethod
    def from_titles(cls, titles: list[str]) -> "EphePlan":
        clean = [t.strip() for t in titles if t and t.strip()]
        if not clean:
            raise ValueError("EphePlan needs at least one step")
        return cls(steps=[EpheStep(title=t) for t in clean[:MAX_PLAN_STEPS]])

    @classmethod
    def from_markdown(cls, markdown: str) -> "EphePlan":
        """Extracts steps from a plan checklist ('- [ ] title'); a step the model
        already finished ('[x]') comes in as done. A step line cut off mid-write
        parses as a shorter title, so a streaming answer never loses the block."""
        plan = cls.try_from_markdown(markdown)
        if plan is None:
            raise ValueError("no plan checklist ('- [ ] …') in the text")
        return plan

    @classmethod
    def try_from_markdown(cls, markdown: str) -> "EphePlan" | None:
        """The same parse with no exception: None when the text holds no plan block yet.
        The stream emitter calls it per chunk, where 'not yet' is the common case.
        The heading is the contract; two or more checklist lines without it still parse,
        so an answer that forgets the heading is not the reason the reader sees no plan."""
        steps: list[EpheStep] = []
        headed = False
        for line in (markdown or "").splitlines():
            if _HEADING_RE.match(line.strip()):
                headed = True
                continue
            m = _CHECKLIST_RE.match(line)
            if m:
                steps.append(
                    EpheStep(
                        title=_STEP_ID_RE.sub("", m.group(2).strip()),
                        status=_STATUS_OF.get(m.group(1), StepStatus.PENDING),
                    )
                )
        if not steps or (not headed and len(steps) < 2):
            return None
        return cls(steps=steps[:MAX_PLAN_STEPS])

    @classmethod
    def from_ledger(cls, rows: list[dict]) -> "EphePlan | None":
        """The todo_list ledger (core/tools/todo_tools.py) as a plan: the same four
        statuses, one shape for the reader. None when the ledger is empty."""
        todo_status = {
            "pending": StepStatus.PENDING,
            "in_progress": StepStatus.RUNNING,
            "completed": StepStatus.DONE,
            "cancelled": StepStatus.CANCELLED,
        }
        steps = [
            EpheStep(title=str(r.get("title", "")).strip(),
                     status=todo_status.get(str(r.get("status", "")), StepStatus.PENDING))
            for r in rows
            if str(r.get("title", "")).strip()
        ]
        if not steps:
            return None
        plan = cls(steps=steps[:MAX_PLAN_STEPS])
        if all(s.status == StepStatus.DONE for s in plan.steps):
            plan.status = "done"
        elif any(s.status in (StepStatus.RUNNING, StepStatus.DONE) for s in plan.steps):
            plan.status = "running"
        return plan

    # Progress

    def start_current(self) -> None:
        """Marks the current step as running; writing steps
        get their checkpoint marker (pull the rollback first)."""
        step = self.steps[self.current]
        step.status = StepStatus.RUNNING
        if step.mutating:
            step.checkpoint_before = True
            if step.checkpoint_snapshot is None:
                step.checkpoint_snapshot = {}
        self.status = "running"

    # E3: Checkpoint / Rollback

    def set_checkpoint(self, path: str, content: str) -> None:
        """E3: Stores the pre-write content of a writing step.
        Call it before the first mutating tool call; the snapshot is the
        rollback anchor for complete_current(ok=False)."""
        step = self.steps[self.current]
        if step.checkpoint_snapshot is None:
            step.checkpoint_snapshot = {}
        step.checkpoint_snapshot[path] = content

    def restore_snapshot(self) -> dict[str, str]:
        """E3: Returns the current step's snapshot mapping for the
        rollback (path → content). Empty mapping when there is no checkpoint."""
        step = self.steps[self.current]
        return dict(step.checkpoint_snapshot or {})

    def complete_current(self, ok: bool) -> None:
        """Completes the current step. ok=True → done + advance;
        ok=False → consume the repair budget, on exhaustion failed for the
        WHOLE plan (an honest hand-off instead of an endless loop)."""
        step = self.steps[self.current]
        if ok:
            step.status = StepStatus.DONE
            if self.current + 1 >= len(self.steps):
                self.status = "done"
            else:
                self.current += 1
            return
        step.repairs += 1
        if step.repairs > MAX_REPAIRS_PER_STEP:
            step.status = StepStatus.FAILED
            self.status = "failed"

    # Visibility

    def progress(self) -> tuple[int, int]:
        done = sum(1 for s in self.steps if s.status == StepStatus.DONE)
        return done, len(self.steps)

    def render(self) -> str:
        done, total = self.progress()
        lines = [f"{PLAN_HEADING} · {done}/{total}"]
        for i, s in enumerate(self.steps):
            mark = _MARK_OF[s.status]
            if s.status == StepStatus.RUNNING and i != self.current:
                mark = _MARK_OF[StepStatus.PENDING]
            lines.append(f"- {mark} {s.title}")
        return "\n".join(lines)

    def as_dict(self) -> dict:
        """The SSE payload of the same state (`{"type": "plan", …}` in the chat stream)."""
        done, total = self.progress()
        return {
            "state": self.status,
            "done": done,
            "total": total,
            "steps": [{"title": s.title, "status": s.status.value} for s in self.steps],
        }
