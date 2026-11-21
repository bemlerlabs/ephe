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

A declared plan strategy (PLAN-P1). The step budget and the step vocabulary are no longer
only this module's constants: a bundle may declare `capabilities.planner` and
`plan_strategy()` resolves it here, where the constructors used to read `MAX_PLAN_STEPS`
directly. The kernel keeps the ceiling — a declared budget may only tighten the plan —
and it keeps the loop, the repair budget and the abort, which no strategy can move.

Pure logic, no I/O. The react_loop (/ephe) drives it; render()/progress()
feed the chat stream and the status popover.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from enum import Enum

#: The kernel's own plan sources. A manifest may not take either id, and the contract
#: module beside this file reads the same two names (`BUILTIN_STRATEGY_IDS`).
from core.plugin_planner_contract import (
    BUILTIN_STRATEGY_IDS as KERNEL_STRATEGY_IDS,
)
from core.plugin_planner_contract import PlanStrategy

logger = logging.getLogger(__name__)

MAX_PLAN_STEPS = 8
MIN_PLAN_STEPS = 4
MAX_REPAIRS_PER_STEP = 2

#: The plan strategy the kernel uses when nothing is declared: the model writes the
#: `## Plan` block and every step carries a title.
KERNEL_STRATEGY_ID = "checklist"
KERNEL_PLAN_STRATEGY = PlanStrategy(
    strategy_id=KERNEL_STRATEGY_ID, step_budget=MAX_PLAN_STEPS
)
#: Env seam: an explicit choice among declared strategies, or `checklist` to keep the
#: kernel's own while a bundle is active.
ENV_PLAN_STRATEGY = "EPHE_PLAN_STRATEGY"


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


def plan_strategy() -> PlanStrategy:
    """The plan strategy this process builds plans under.

    Resolution, in one order: an explicit `EPHE_PLAN_STRATEGY` pin, then the one
    strategy an active bundle declares, then the kernel's own. A declared strategy
    answers only while its bundle is active. A contested id answers like an unknown one,
    and two bundles that declare different dialects contradict each other, so neither of
    them governs. Every refusal falls back to the kernel strategy, so no plugin can stop
    a turn from planning.
    """
    pinned = (os.environ.get(ENV_PLAN_STRATEGY) or "").strip().lower()
    if pinned == KERNEL_STRATEGY_ID:
        return KERNEL_PLAN_STRATEGY
    try:
        from core import plugin_runtime

        table = plugin_runtime.plan_strategies()
    except Exception:  # noqa: BLE001 — a broken portfolio never blocks a plan
        logger.warning("planner: the plugin portfolio could not be read; kernel plan stays")
        return KERNEL_PLAN_STRATEGY
    if not table.claims:
        if pinned:
            logger.warning(
                "planner: ignoring %s=%r — no plugin declares a plan strategy",
                ENV_PLAN_STRATEGY,
                pinned,
            )
        return KERNEL_PLAN_STRATEGY
    if pinned:
        claim = table.get(pinned)
        if claim is None:
            why = (
                f" — {table.conflict_reason(pinned)}"
                if pinned in table.contested
                else " — no plugin declares it"
            )
            logger.warning(
                "planner: ignoring %s=%r%s", ENV_PLAN_STRATEGY, pinned, why
            )
            return KERNEL_PLAN_STRATEGY
        return _active_strategy(claim, pinned=True) or KERNEL_PLAN_STRATEGY
    if not table.contested and len(table.claims) == 1:
        return _active_strategy(table.claims[0], pinned=False) or KERNEL_PLAN_STRATEGY
    if table.contested:
        logger.warning(
            "planner: strategy %s is claimed by more than one plugin; "
            "the kernel's own plan stays",
            ", ".join(repr(strategy_id) for strategy_id in table.contested),
        )
        return KERNEL_PLAN_STRATEGY
    logger.warning(
        "planner: %d plan strategies are declared and contradict each other; "
        "the kernel's own plan stays",
        len(table.claims),
    )
    return KERNEL_PLAN_STRATEGY


def _active_strategy(claim: PlanStrategy, *, pinned: bool) -> PlanStrategy | None:
    """The claim while its bundle is active; None (and a note) when it is switched off."""
    from core import plugin_runtime

    if plugin_runtime.is_plugin_active(claim.plugin_id):
        return claim
    log = logger.warning if pinned else logger.debug
    log(
        "planner: strategy %r is declared by plugin %r, which is switched off",
        claim.strategy_id,
        claim.plugin_id,
    )
    return None


def _step_budget(strategy: PlanStrategy) -> int:
    """The declared budget inside the kernel's window — a handed-in strategy included."""
    return max(1, min(strategy.step_budget, MAX_PLAN_STEPS))


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
    #: The declared strategy the plan was built under; the kernel's own by default.
    strategy: PlanStrategy = field(default_factory=lambda: KERNEL_PLAN_STRATEGY)

    # Construction

    @classmethod
    def from_titles(
        cls, titles: list[str], strategy: PlanStrategy | None = None
    ) -> "EphePlan":
        clean = [t.strip() for t in titles if t and t.strip()]
        if not clean:
            raise ValueError("EphePlan needs at least one step")
        active = strategy or plan_strategy()
        return cls(
            steps=[EpheStep(title=t) for t in clean[: _step_budget(active)]],
            strategy=active,
        )

    @classmethod
    def from_markdown(
        cls, markdown: str, strategy: PlanStrategy | None = None
    ) -> "EphePlan":
        """Extracts steps from a plan checklist ('- [ ] title'); a step the model
        already finished ('[x]') comes in as done. A step line cut off mid-write
        parses as a shorter title, so a streaming answer never loses the block."""
        plan = cls.try_from_markdown(markdown, strategy=strategy)
        if plan is None:
            raise ValueError("no plan checklist ('- [ ] …') in the text")
        return plan

    @classmethod
    def try_from_markdown(
        cls, markdown: str, strategy: PlanStrategy | None = None
    ) -> "EphePlan" | None:
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
        active = strategy or plan_strategy()
        return cls(steps=steps[: _step_budget(active)], strategy=active)

    @classmethod
    def from_ledger(
        cls, rows: list[dict], strategy: PlanStrategy | None = None
    ) -> "EphePlan | None":
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
        active = strategy or plan_strategy()
        plan = cls(steps=steps[: _step_budget(active)], strategy=active)
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
