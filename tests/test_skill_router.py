"""Skill routing through the decision layer — the routing eval case.

The fuzzy tier of SkillLoader.resolve_for_message used to pick a skill with a
bare argmax. It now routes through core.decisions.route() (core.skill_router),
so the pick is a recorded Decision. This file proves two things:

* the choice is actually made by the decision layer (a spy on
  core.decisions.route sees the call, and the returned skill is the layer's
  chosen option); and
* the layer still routes to the right skill for a corpus of messages, and still
  declines (no skill) below the 2.0 confidence floor.

Given / When / Then.
"""
from __future__ import annotations

import pytest

from core import decisions, skill_router
from core.skills import BUILTIN_SKILLS_DIR, SkillLoader


@pytest.fixture(autouse=True)
def _offline_engine(monkeypatch):
    """No engine configured: the offline verdict backend must be the one that runs."""
    monkeypatch.delenv(decisions.ENV_ENGINE_URL, raising=False)
    monkeypatch.delenv(decisions.ENV_ENGINE_MODEL, raising=False)


@pytest.fixture(scope="module")
def loader():
    sl = SkillLoader(builtin_dir=BUILTIN_SKILLS_DIR)
    sl._clear_cache()
    return sl


# The routing corpus: message -> the skill the fuzzy tier must resolve to.
ROUTING_CASES = [
    ("schreibe tests fuer die parser funktion", "test-writer"),  # language-gate: ignore (quoted German utterance under test)
    ("write unit tests for the parser", "test-writer"),
    ("debug den fehler im stack trace", "debugger"),
    ("ich brauche ein pitch deck fuer investor", "deck-creator"),  # language-gate: ignore (quoted German utterance under test)
    ("refactor den code sauber", "refactor-helper"),
    ("erklaere mir wie ein diff funktioniert", "explain-expert"),
]

# Below the 2.0 floor: no skill routes, but the decision that declined is still real.
NO_ROUTE_CASES = [
    "hello there",
    "compare two frameworks and give pros and cons",
    "translate this text into spanish",
]


class TestDecisionLayerIsTheMechanism:

    def test_fuzzy_route_calls_decision_layer(self, loader, monkeypatch):
        """G: a fuzzy message W: route_for_message T: core.decisions.route is called
        and its chosen option is the returned skill."""
        calls = []
        real = decisions.route

        def spy(state, routes, **kwargs):
            calls.append((state, tuple(routes.keys()), kwargs))
            return real(state, routes, **kwargs)

        monkeypatch.setattr(decisions, "route", spy)
        message = "debug den fehler im stack trace"
        route = loader.route_for_message(message)

        assert len(calls) == 1
        state, options, _ = calls[0]
        assert state == message
        assert route.skill is not None
        assert route.skill.name in options
        assert route.decision is not None
        assert route.decision.chosen == route.skill.name

    def test_decision_is_recorded_and_offline(self, loader):
        """G: a fuzzy message W: route_for_message T: a well-formed offline Decision."""
        route = loader.route_for_message("debug den fehler im stack trace")
        decision = route.decision

        assert decision is not None
        assert decision.verb == "route"
        assert decision.backend == "skill-tfidf"
        assert decision.fallback_reason == ""
        assert decision.cost_seconds >= 0.0
        # The legal option set is recorded, in full, and carries the winner.
        assert decision.chosen in decision.options
        assert len(decision.options) > len(ROUTING_CASES)
        # The distribution is ranked and sums to ~1.
        assert decision.distribution[0][0] == decision.chosen
        assert abs(sum(p for _, p in decision.distribution) - 1.0) < 1e-6

    def test_resolve_for_message_delegates_to_the_route(self, loader):
        """G: resolve_for_message W: any message T: exactly route_for_message(...).skill."""
        for message, _ in ROUTING_CASES:
            route = loader.route_for_message(message)
            assert loader.resolve_for_message(message) is route.skill


class TestRoutingCorpus:

    @pytest.mark.parametrize("message,expected", ROUTING_CASES)
    def test_message_routes_to_expected_skill(self, loader, message, expected):
        """G/W/T: the corpus message resolves to its skill through the layer."""
        route = loader.route_for_message(message)
        assert route.skill is not None and route.skill.name == expected
        # And the public resolver agrees.
        assert loader.resolve_for_message(message).name == expected

    @pytest.mark.parametrize("message", NO_ROUTE_CASES)
    def test_low_confidence_declines_but_records(self, loader, message):
        """G: a message with no confident match W: route_for_message
        T: no skill, yet a Decision that names the below-floor winner."""
        route = loader.route_for_message(message)
        assert route.skill is None
        assert route.decision is not None
        assert route.decision.verb == "route"
        assert route.decision.chosen in route.decision.options

    def test_deterministic_intent_tier_is_not_a_decision(self, loader):
        """G: an explicit verb+artifact W: route_for_message T: skill pinned by the
        rule, no Decision (a rule match is not a choice)."""
        route = loader.route_for_message("erstelle ein PDF aus diesen Daten: a; b")  # language-gate: ignore (quoted German utterance under test)
        assert route.skill is not None and route.skill.trigger == "/pdf"
        assert route.decision is None


class TestSeams:

    def test_verdict_backend_reproduces_the_legacy_argmax(self, loader):
        """G: the same candidates W: SkillVerdictBackend.score T: the top-scoring
        candidate keeps the most mass (the old argmax, unchanged)."""
        candidates = [
            skill_router.RouteCandidate(skill=s, score=score, phrase=phrase)
            for s, score, phrase in [
                (loader.resolve_trigger("/pdf"), 3.0, 1),
                (loader.resolve_trigger("/deck"), 5.0, 0),
                (loader.resolve_trigger("/chart"), 5.0, 2),
            ]
        ]
        backend = skill_router.SkillVerdictBackend(candidates)
        probs = backend.score("x", [c.skill.name for c in candidates])
        # /chart ties /deck on score but wins the phrase tie-break.
        assert max(probs, key=probs.get) == loader.resolve_trigger("/chart").name

    def test_no_candidates_makes_no_decision(self, loader):
        """G: an empty option set W: route_skills T: no skill and no Decision
        (nothing to decide is not a decision)."""
        route = skill_router.route_skills("anything", [])
        assert route.skill is None
        assert route.decision is None

    def test_backend_is_injectable(self, loader):
        """G: an alternative backend W: route_skills T: the layer obeys it — the
        engine seam, without touching core/skills.py."""
        candidates = [
            skill_router.RouteCandidate(skill=loader.resolve_trigger("/pdf"), score=0.0),
            skill_router.RouteCandidate(skill=loader.resolve_trigger("/deck"), score=9.0),
        ]

        class StubBackend:
            name = "stub"

            def score(self, state, options):
                return {option: (1.0 if option == "pdf-creator" else 0.0) for option in options}

        route = skill_router.route_skills("x", candidates, backend=StubBackend())
        assert route.skill is not None and route.skill.name == "pdf-creator"
        assert route.decision is not None and route.decision.backend == "stub"
