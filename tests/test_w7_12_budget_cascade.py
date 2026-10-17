"""W7-12 — the budget cascade: the DECLARED ladder equals what the loop enforces.

The R37/R43 cascade is documented as ONE schema in `core/ephe_plan.py`. The
2026-10 declaration was stale: it declared `MAX_TOOL_ITERATIONS = 10` (casual)
and a coding class of 25, while the loop already enforced 25 casual / 40 coding
/ 40 cap — and the arithmetic line `40 = 2×(10+8+2)` was a formula nobody
enforced. Nothing failed, because no test ever compared the declaration against
the enforcement.

So these tests read BOTH sides — the declared ladder and the enforcing
constants (never a literal) — and require them to agree, for the chat tool loop
and for the execution cell's own output budget. A change to a constant that the
declaration does not follow fails here; that is the point.
"""
from __future__ import annotations

import re

# the chat tool-round rounds, read from the enforcer


def _declared_ladder() -> dict[str, int]:
    """The ladder as the module docstring declares it, keyed by its level marker."""
    from core import ephe_plan

    doc = ephe_plan.__doc__ or ""
    out: dict[str, int] = {}
    for line in doc.splitlines():
        match = re.match(r"\s*level\s+(\S+)\s+.+?=\s*(\d+)\b", line)
        if match:
            out[match.group(1)] = int(match.group(2))
    return out


def _ephe_coding_budget() -> int:
    """The coding class' declared budget — where the route reads it from."""
    from server.routes.chat import EPHE_TOOL_BUDGET

    return EPHE_TOOL_BUDGET


def test_declared_ladder_matches_the_enforced_constants():
    """GIVEN the cascade declared in the ephe_plan docstring
    WHEN each level is read against the constant that enforces it
    THEN they agree — the declaration is not a second, staler table."""
    from core.chat import MAX_TOOL_ITERATIONS, TOOL_BUDGET_HARD_CAP
    from core.ephe_plan import MAX_PLAN_STEPS, MAX_REPAIRS_PER_STEP

    declared = _declared_ladder()
    assert set(declared) == {"1", "2", "3", "3'", "4"}, (
        f"the ladder lost or gained a level: {sorted(declared)} — every declared "
        f"level must be one a reader can check against a constant"
    )
    assert declared["1"] == MAX_PLAN_STEPS
    assert declared["2"] == MAX_REPAIRS_PER_STEP
    assert declared["3"] == MAX_TOOL_ITERATIONS  # 25, never the stale 10 (R46)
    assert declared["3'"] == _ephe_coding_budget()
    assert declared["4"] == TOOL_BUDGET_HARD_CAP


def test_budget_cascade_is_the_enforcement_it_declares():
    """GIVEN `budget_cascade()`, the machine-readable form of the ladder
    WHEN its values are read against the enforcer
    THEN every level is the enforcing constant, not a copy of it."""
    from core.chat import MAX_TOOL_ITERATIONS, TOOL_BUDGET_HARD_CAP, clamp_tool_budget
    from core.ephe_plan import (
        MAX_PLAN_STEPS,
        MAX_REPAIRS_PER_STEP,
        budget_cascade,
    )

    cascade = budget_cascade()
    assert cascade == {
        "plan_steps": MAX_PLAN_STEPS,
        "repairs_per_step": MAX_REPAIRS_PER_STEP,
        "tool_rounds": MAX_TOOL_ITERATIONS,
        "tool_rounds_hard_cap": TOOL_BUDGET_HARD_CAP,
    }
    # The casual level the ladder declares IS the default the loop applies.
    assert clamp_tool_budget(None) == cascade["tool_rounds"]
    assert clamp_tool_budget(cascade["tool_rounds_hard_cap"]) == cascade["tool_rounds_hard_cap"]


def test_the_coding_class_runs_at_the_budget_it_declares():
    """GIVEN the /ephe coding class declares its tool budget
    WHEN the loop clamps that value
    THEN it survives unchanged — a declared budget the cap silently lowers is a
    declaration the product does not keep."""
    from core.chat import TOOL_BUDGET_HARD_CAP, clamp_tool_budget

    coding = _ephe_coding_budget()
    assert coding <= TOOL_BUDGET_HARD_CAP, (
        f"the coding class declares {coding}, above the hard cap {TOOL_BUDGET_HARD_CAP}: "
        f"the loop would clamp it and the declaration would lie"
    )
    assert clamp_tool_budget(coding) == coding


def test_cascade_is_monotonic():
    """GIVEN the four levels in their documented order
    WHEN their sizes are compared
    THEN no level caps the next one below itself."""
    from core.chat import TOOL_BUDGET_HARD_CAP, clamp_tool_budget
    from core.ephe_plan import MAX_PLAN_STEPS, MAX_REPAIRS_PER_STEP

    assert 1 <= MAX_REPAIRS_PER_STEP <= MAX_PLAN_STEPS
    assert clamp_tool_budget(None) <= TOOL_BUDGET_HARD_CAP
    # A repair budget of 0 would hand off on the first failure without trying;
    # the plan documents at least one attempt per step.
    assert MAX_REPAIRS_PER_STEP >= 1


# the execution cell's own budget


def test_the_execution_cell_enforces_the_budget_it_declares():
    """GIVEN the cell budget `core/cell_output.py` declares to the settings card,
    `ephe doctor` and the status page
    WHEN the value `core/cell_boot.py` enforces inside the cell is read
    THEN it is the same number — the report cannot carry a cap the cell does not
    apply (the `report == enforced` rule of `core/cell_policy.py`)."""
    from core import cell_boot, cell_output

    assert cell_boot.FORWARD_BYTES == cell_output.GUEST_FORWARD_BYTES
    assert cell_boot.TEE_CAP_BYTES == cell_output.GUEST_TEE_CAP_BYTES
    # The forwarded worst case (both streams plus its marker) stays under the wall
    # that used to kill the guest on its own print.
    assert cell_output.GUEST_FORWARD_BYTES * 2 + 4096 < cell_output.SINK_CEILING_BYTES


def test_the_cell_policy_publishes_the_numbers_the_cell_enforces():
    """GIVEN the policy snapshot the panel shows
    WHEN it is compared with what the boot enforces and what the sink caps
    THEN the published cap is the enforced cap — no panel shows a number the cell
    does not hold to."""
    from core import cell_boot, cell_output, cell_policy

    policy = cell_policy.policy_snapshot()
    assert policy["output_cap_bytes"] == cell_output.OUTPUT_CAP_BYTES
    assert policy["guest_forward_bytes"] == cell_boot.FORWARD_BYTES
    assert policy["guest_tee_cap_bytes"] == cell_boot.TEE_CAP_BYTES
    assert policy["guest_forward_bytes"] < policy["sink_ceiling_bytes"]
