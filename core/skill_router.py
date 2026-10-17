"""Skill routing through the decision layer (core.decisions).

SkillLoader.resolve_for_message's fuzzy tier ranks every routable skill with a
TF-IDF score over when_to_use + description + trigger, applies the
when_not_to_use veto, and picks the top one. That pick used to be a bare argmax
inside the loop. It now runs through core.decisions.route(), so the choice is a
recorded Decision: the legal option set, the one chosen, the score distribution,
the backend and the cost.

The scorer is injected as the decisions backend (SkillVerdictBackend), so the
offline ranking and the >= 2.0 confidence floor are unchanged, while the engine
branch of the layer (EPHE_DECISION_ENGINE_*) becomes reachable for skill routing
without a change at any call site.
"""
from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from core import decisions

if TYPE_CHECKING:
    from core.skills import Skill

#: F2 confidence floor: below this TF-IDF score a message is not routed.
CONFIDENCE_FLOOR = 2.0

#: Offset that carries the legacy tie-break (phrase hits, then load order) into
#: the score the layer ranks. It is far below any real TF-IDF gap.
_TIE_EPSILON = 1e-9

#: The engine reads one letter per option, so its option window is bounded.
_ENGINE_WINDOW = decisions.MAX_ENGINE_OPTIONS


@dataclass(frozen=True)
class RouteCandidate:
    """One routable skill with the scores the loader computed for it."""

    skill: Skill
    score: float
    phrase: int = 0


@dataclass(frozen=True)
class SkillRoute:
    """The skill a message routed to, and the decision that picked it.

    ``decision`` is None for the deterministic tiers (trigger, factory/artifact
    intent, named tool) — a rule match is not a choice. The fuzzy tier always
    returns one, including when the result is "no skill" below the floor.
    """

    skill: Skill | None
    decision: decisions.Decision | None = None


class SkillVerdictBackend:
    """decisions backend: the loader's TF-IDF ranking, as a distribution."""

    name = "skill-tfidf"

    def __init__(self, candidates: Sequence[RouteCandidate]) -> None:
        self._rank = {c.skill.name: i for i, c in enumerate(candidates)}
        self._score = {c.skill.name: float(c.score) for c in candidates}
        self._phrase = {c.skill.name: int(c.phrase) for c in candidates}

    def score(self, state: str, options: Sequence[str]) -> dict[str, float]:
        # Legacy priority: highest TF-IDF, then most direct when_to_use hits,
        # then load order. The order is folded into the value as a sub-floor
        # offset, so the layer's argmax reproduces the old loop exactly.
        ordered = sorted(
            options,
            key=lambda o: (-self._score.get(o, 0.0), -self._phrase.get(o, 0), self._rank.get(o, 0)),
        )
        raw = {
            option: self._score.get(option, 0.0) - pos * _TIE_EPSILON
            for pos, option in enumerate(ordered)
        }
        return _softmax(raw, options)


def _softmax(raw: Mapping[str, float], options: Sequence[str]) -> dict[str, float]:
    if not options:
        raise decisions.DecisionError("a decision needs at least one option")
    values = [float(raw[o]) for o in options]
    top = max(values)
    weights = [math.exp(v - top) for v in values]
    total = sum(weights)
    return {o: w / total for o, w in zip(options, weights)}


def route_skills(
    message: str,
    candidates: Sequence[RouteCandidate],
    *,
    floor: float = CONFIDENCE_FLOOR,
    backend=None,
    reversal: str = "",
) -> SkillRoute:
    """Route a message to one of ``candidates`` through core.decisions.route().

    Returns the chosen skill and the Decision that chose it. When the layer's
    choice scores below ``floor`` no skill routes (the caller falls back to the
    model), but the Decision is still returned so a non-route is auditable too.

    With no candidates there is nothing to decide, so no Decision is made.
    """
    if not candidates:
        return SkillRoute(None)

    by_name = {c.skill.name: c for c in candidates}
    names = list(by_name)
    effective = backend
    if effective is None and decisions.is_engine_configured():
        # The engine answers with one letter per option: hand it the strongest
        # window only. Its own fallback to the local scorer is the layer's.
        if len(names) > _ENGINE_WINDOW:
            names = sorted(names, key=lambda n: -by_name[n].score)[:_ENGINE_WINDOW]
    else:
        effective = effective or SkillVerdictBackend(candidates)

    decision = decisions.route(
        message, {name: name for name in names}, backend=effective, reversal=reversal
    )
    chosen = by_name[decision.chosen]
    # The floor is a TF-IDF contract; the engine's choice is the engine's own.
    if decision.backend == SkillVerdictBackend.name and chosen.score < floor:
        return SkillRoute(None, decision)
    return SkillRoute(chosen.skill, decision)
