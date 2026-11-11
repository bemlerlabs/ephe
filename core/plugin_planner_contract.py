"""Ephe — `capabilities.planner`: the plan strategy one manifest declares.

core/plugin_planner_contract.py

A bundle may say how a plan is shaped: the strategy it names, the step budget the plan
may grow to, and the fields each step carries. It says so once, in a version 2 manifest,
and the kernel decides every consequence — `core/ephe_plan.py` resolves the declared
strategy where it used to read its own constant, and a plan built while that bundle is
active is bounded by the declared budget. Nothing here imports plugin code, and nothing
here runs at turn time: a strategy is configuration, so it needs no permission family.

What the kernel keeps. The loop, the repair budget (`MAX_REPAIRS_PER_STEP`), the abort
when the budget is spent, the rendered block and the stream payload are the kernel's
under every strategy. A declared budget may only TIGHTEN the plan: the floor is the
guard's own floor and the ceiling is `MAX_PLAN_STEPS`, both read off `core/ephe_plan.py`
at call time rather than restated here, so a change there cannot leave a stale window
behind. `checklist` and `ledger` are the kernel's plan sources and a manifest may not
take either name.

Why a declared budget may not exceed the ceiling, and may not fall below the floor: the
architect guard tells the model to write four to eight steps (`core/persona.py`). A
strategy asking for more than eight would be cut silently by the same clamp that runs
today, and one asking for fewer than four would contradict the instruction the model was
given in the same turn. Both are refused at load time, where the bundle is still the
thing that is wrong.

Fail-closed rules, in one list: `capabilities` in a version 1 manifest, a `planner`
section that is not an object, an unknown field, a missing or malformed strategy id, an
id the kernel owns, an id past the ceiling, a step budget that is not a whole number or
falls outside the kernel's window, a step schema that is not a list, names a field the
plan core does not carry or names one twice, a schema without `title`, and a blank
description. Each of them quarantines the whole bundle.

What a declared step schema means today: the fields a plan under this strategy is meant
to carry, validated against the kernel's own step vocabulary and recorded on the plan
(`EphePlan.strategy`). The kernel enforces the budget; it does not yet act on a declared
field beyond `title`, and the contract says so instead of implying a reader that does
not exist.

Two bundles that declare one strategy id: neither wins. The scan marks the id contested
and names both claimants; `get` answers None for it, so the resolution falls back the way
it does for an id nobody declared. That is the same answer the tool gate gives a contested
name.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

__all__ = [
    "BUILTIN_STRATEGY_IDS",
    "MAX_STRATEGY_ID_CHARS",
    "PLANNER_FIELDS",
    "PLAN_STEP_FIELDS",
    "PlanStrategy",
    "PlanStrategyTable",
    "planner_claim",
    "scan_plan_strategies",
    "validate_planner",
]

#: Strategy ids the kernel owns; a manifest may not take one. `core/ephe_plan.py`
#: re-exports this set as `KERNEL_STRATEGY_IDS`, so the plan core and the contract read
#: one table instead of two that happen to agree.
BUILTIN_STRATEGY_IDS: frozenset[str] = frozenset({"checklist", "ledger"})
#: The fields a step carries, as `core/ephe_plan.EpheStep` declares them. A strategy may
#: name a subset; `status`, `repairs` and the checkpoint anchor are kernel bookkeeping and
#: stay out of the vocabulary.
PLAN_STEP_FIELDS: tuple[str, ...] = ("title", "evidence", "mutating")
PLANNER_FIELDS: frozenset[str] = frozenset(
    {"strategy", "step_budget", "step_schema", "description"}
)
#: Ceiling on a strategy id: it rides in env, plans and refusal sentences.
MAX_STRATEGY_ID_CHARS = 40

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


@dataclass(frozen=True)
class PlanStrategy:
    """One declared plan strategy, normalized the way the scan and the plan core read it.

    ``plugin_id`` owns the declaration and is what the lifecycle gate asks about; it is
    empty for the kernel's own strategy. ``step_budget`` is already inside the kernel's
    window: the contract refuses anything else, so a plan never has to clamp twice.
    """

    strategy_id: str
    step_budget: int
    step_schema: tuple[str, ...] = ("title",)
    plugin_id: str = ""
    description: str = ""


@dataclass(frozen=True)
class PlanStrategyTable:
    """Every declared strategy over one scan, with the ids two bundles claim."""

    claims: tuple[PlanStrategy, ...] = ()
    contested: tuple[str, ...] = ()
    _reasons: tuple[tuple[str, str], ...] = ()

    def get(self, strategy_id: str) -> PlanStrategy | None:
        """The claim behind one id, or None — contested and unknown answer the same."""
        if strategy_id in self.contested:
            return None
        for claim in self.claims:
            if claim.strategy_id == strategy_id:
                return claim
        return None

    def conflict_reason(self, strategy_id: str) -> str:
        return dict(self._reasons).get(
            strategy_id, f"strategy {strategy_id!r} is claimed by more than one plugin"
        )


def _bounds() -> tuple[int, int, frozenset[str]]:
    """The kernel's step window and its reserved ids, read at call time."""
    from core.ephe_plan import MAX_PLAN_STEPS, MIN_PLAN_STEPS

    return MIN_PLAN_STEPS, MAX_PLAN_STEPS, BUILTIN_STRATEGY_IDS


def _planner_section(manifest: dict) -> dict | None:
    capabilities = manifest.get("capabilities")
    if not isinstance(capabilities, dict):
        return None
    section = capabilities.get("planner")
    return section if isinstance(section, dict) else None


def _check_schema(schema: Any) -> str | None:
    if schema is None:
        return None
    if not isinstance(schema, list) or any(not isinstance(field, str) for field in schema):
        return "capabilities.planner.step_schema: list of step field names expected"
    unknown = sorted(set(schema) - set(PLAN_STEP_FIELDS))
    if unknown:
        return (
            "capabilities.planner.step_schema: unknown step field(s): "
            f"{', '.join(unknown)} ({', '.join(PLAN_STEP_FIELDS)})"
        )
    repeated = sorted({field for field in schema if schema.count(field) > 1})
    if repeated:
        return (
            "capabilities.planner.step_schema: duplicate step field(s): "
            f"{', '.join(repeated)}"
        )
    if "title" not in schema:
        return (
            "capabilities.planner.step_schema: must name 'title' — "
            "a step without a title is not a step"
        )
    return None


def validate_planner(manifest: dict) -> str | None:
    """The `capabilities.planner` contract; called once from the manifest contract."""
    capabilities = manifest.get("capabilities")
    if capabilities is None:
        return None
    if manifest.get("manifest_version") != 2:
        return "capabilities: manifest_version 2 required"
    if not isinstance(capabilities, dict):
        return "capabilities: object expected"
    planner = capabilities.get("planner")
    if planner is None:
        return None
    if not isinstance(planner, dict):
        return "capabilities.planner: object expected"
    unknown_fields = sorted(set(planner) - PLANNER_FIELDS)
    if unknown_fields:
        return f"capabilities.planner: unknown field(s): {', '.join(unknown_fields)}"

    floor, ceiling, reserved = _bounds()
    strategy_id = planner.get("strategy")
    if not isinstance(strategy_id, str) or not _SLUG_RE.match(strategy_id):
        return "capabilities.planner.strategy: lowercase slug expected (a-z0-9-)"
    if len(strategy_id) > MAX_STRATEGY_ID_CHARS:
        return (
            "capabilities.planner.strategy: at most "
            f"{MAX_STRATEGY_ID_CHARS} characters expected"
        )
    if strategy_id in reserved:
        return f"capabilities.planner.strategy: {strategy_id!r} is a kernel strategy id"

    step_budget = planner.get("step_budget", ceiling)
    # `True` is an integer in Python and would read back as a one-step budget.
    if (
        isinstance(step_budget, bool)
        or not isinstance(step_budget, int)
        or not floor <= step_budget <= ceiling
    ):
        if isinstance(step_budget, bool) or not isinstance(step_budget, int):
            return "capabilities.planner.step_budget: a whole number of steps expected"
        return (
            "capabilities.planner.step_budget: "
            f"{step_budget} is outside {floor}..{ceiling} steps"
        )

    schema_error = _check_schema(planner.get("step_schema"))
    if schema_error:
        return schema_error

    description = planner.get("description", "")
    if not isinstance(description, str) or (description and not description.strip()):
        return "capabilities.planner.description: non-empty string expected"
    return None


def planner_claim(manifest: Any) -> PlanStrategy | None:
    """The strategy one validated manifest declares, or None when it declares none."""
    if not isinstance(manifest, dict) or validate_planner(manifest) is not None:
        return None
    planner = _planner_section(manifest)
    if planner is None:
        return None
    _, ceiling, _ = _bounds()
    return PlanStrategy(
        strategy_id=str(planner["strategy"]),
        step_budget=int(planner.get("step_budget", ceiling)),
        step_schema=tuple(planner.get("step_schema") or ("title",)),
        plugin_id=str(manifest.get("name") or ""),
        description=str(planner.get("description") or ""),
    )


def scan_plan_strategies(entries: Iterable[dict]) -> PlanStrategyTable:
    """Claims from one manifest scan (`core.plugin_manifest.scan_plugins`), plus conflicts.

    Takes the entries rather than scanning them, so this module stays below the loader it
    is called from and a caller owns the root it reads.
    """
    claims: list[PlanStrategy] = []
    claimants: dict[str, list[str]] = {}
    for entry in entries:
        manifest = entry.get("manifest")
        if entry.get("error") or not manifest:
            continue
        claim = planner_claim(manifest)
        if claim is None:
            continue
        claims.append(claim)
        claimants.setdefault(claim.strategy_id, []).append(claim.plugin_id)
    contested = tuple(sorted(sid for sid, owners in claimants.items() if len(owners) > 1))
    reasons = tuple(
        (
            sid,
            f"strategy {sid!r} is claimed by "
            + ", ".join(f"{owner!r}" for owner in sorted(claimants[sid])),
        )
        for sid in contested
    )
    return PlanStrategyTable(
        claims=tuple(sorted(claims, key=lambda item: item.strategy_id)),
        contested=contested,
        _reasons=reasons,
    )
