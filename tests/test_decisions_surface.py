"""The frozen decision surface — the names, the four verbs and the record.

core/decisions.py is the interface the later waves consume (interface before
consumer, plan rule 3), and its consumer side lands after this file, so the
interface is pinned first, the way tests/test_w3_68_api_contract_frozen.py pins
the /api routes. FROZEN_SURFACE names every public export and is compared for
exact equality against the module's __all__; a star-import must bind those names
and nothing else. A rename therefore shows up as the added/removed pair it is,
instead of hiding inside an add and a delete that nets the same total.

To move the surface, change FROZEN_SURFACE in the same commit and say why. An
addition reds this file on purpose: that is the review.
"""
from __future__ import annotations

import dataclasses
import inspect

import pytest

from core import decisions

#: Every public export of core/decisions.py, sorted. This is the contract.
FROZEN_SURFACE: tuple[str, ...] = (
    "Decision",
    "DecisionEngineUnavailable",
    "DecisionError",
    "ENV_ENGINE_KEY",
    "ENV_ENGINE_MODEL",
    "ENV_ENGINE_URL",
    "EngineAdapter",
    "LocalScorer",
    "MAX_ENGINE_OPTIONS",
    "achoose",
    "ajudge",
    "aroute",
    "ascore",
    "choose",
    "engine_config",
    "is_engine_configured",
    "judge",
    "resolve_backend",
    "route",
    "score",
)

#: The four question shapes: each verb and its async twin.
VERBS: tuple[tuple[str, str], ...] = (
    ("choose", "achoose"),
    ("score", "ascore"),
    ("route", "aroute"),
    ("judge", "ajudge"),
)

#: The two backend name strings a record may carry in ``Decision.backend``.
BACKEND_NAMES: frozenset[str] = frozenset({"local", "engine"})

#: ``Decision``'s fields in declaration order; positional readers break on a
#: reorder, so the order is frozen with the names.
RECORD_FIELDS: tuple[str, ...] = (
    "verb",
    "state",
    "options",
    "chosen",
    "confidence",
    "distribution",
    "backend",
    "cost_seconds",
    "reversal",
    "fallback_reason",
)

_ROUTE_CALL = ("retry after the timeout", {"fail": "abort", "retry": "try again"})


@pytest.fixture(autouse=True)
def _no_engine_env(monkeypatch):
    for name in (
        decisions.ENV_ENGINE_URL,
        decisions.ENV_ENGINE_MODEL,
        decisions.ENV_ENGINE_KEY,
    ):
        monkeypatch.delenv(name, raising=False)


def _sync(verb: str) -> decisions.Decision:
    if verb == "route":
        return decisions.route(*_ROUTE_CALL)
    if verb == "judge":
        return decisions.judge("the request timed out")
    return getattr(decisions, verb)("retry after the timeout", ["fail", "retry"])


async def _async(verb: str) -> decisions.Decision:
    if verb == "route":
        return await decisions.aroute(*_ROUTE_CALL)
    if verb == "judge":
        return await decisions.ajudge("the request timed out")
    return await getattr(decisions, "a" + verb)(
        "retry after the timeout", ["fail", "retry"]
    )


def _without_cost(record: decisions.Decision) -> decisions.Decision:
    return dataclasses.replace(record, cost_seconds=0.0)


def test_the_public_surface_is_exactly_the_frozen_one():
    declared = set(decisions.__all__)
    frozen = set(FROZEN_SURFACE)
    added, removed = sorted(declared - frozen), sorted(frozen - declared)
    assert not added and not removed, (
        f"core/decisions.py surface changed: added {added}, removed {removed}. "
        "Update FROZEN_SURFACE in the same commit and say why."
    )


def test_the_surface_is_a_duplicate_free_tuple():
    assert isinstance(decisions.__all__, tuple)
    assert len(set(decisions.__all__)) == len(decisions.__all__)


def test_star_import_binds_the_frozen_surface_and_nothing_else():
    namespace: dict = {}
    exec("from core.decisions import *", namespace)
    bound = {name for name in namespace if not name.startswith("__")}
    assert bound == set(FROZEN_SURFACE)


def test_every_frozen_name_resolves_on_the_module():
    missing = [name for name in FROZEN_SURFACE if not hasattr(decisions, name)]
    assert missing == []


@pytest.mark.parametrize("verb, async_verb", VERBS)
def test_each_verb_has_its_named_async_twin(verb, async_verb):
    assert inspect.iscoroutinefunction(getattr(decisions, async_verb))


@pytest.mark.parametrize("verb, async_verb", VERBS)
def test_each_verb_stamps_its_own_name_in_the_record(verb, async_verb):
    record = _sync(verb)
    assert record.verb == verb
    assert record.backend in BACKEND_NAMES


@pytest.mark.parametrize("verb, async_verb", VERBS)
async def test_async_twin_returns_the_same_record(verb, async_verb):
    assert _without_cost(await _async(verb)) == _without_cost(_sync(verb))


def test_judge_is_the_binary_shape():
    record = decisions.judge("the request timed out")
    assert record.options == ("no", "yes")
    assert {option for option, _ in record.distribution} == {"no", "yes"}


def test_backend_names_are_the_frozen_vocabulary():
    assert decisions.LocalScorer.name in BACKEND_NAMES
    assert decisions.EngineAdapter.name in BACKEND_NAMES
    assert decisions.LocalScorer.name != decisions.EngineAdapter.name


def test_the_record_carries_exactly_the_frozen_fields():
    fields = tuple(field.name for field in dataclasses.fields(decisions.Decision))
    assert fields == RECORD_FIELDS


def test_the_record_is_immutable():
    record = decisions.choose("pick a path", ["left", "right"])
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.chosen = "left"


def test_distribution_covers_the_caller_option_set():
    options = ("retry", "fail", "redirect")
    record = decisions.choose("HTTP 404 on the API", list(options))
    assert record.options == options
    assert {option for option, _ in record.distribution} == set(options)


def test_chosen_and_confidence_are_the_top_of_the_distribution():
    record = decisions.choose("GPU OOM, the batch is too large", ["grow", "reduce"])
    assert record.distribution[0] == (record.chosen, record.confidence)
    probs = [probability for _, probability in record.distribution]
    assert probs == sorted(probs, reverse=True)
    assert sum(probs) == pytest.approx(1.0)


def test_a_single_option_decides_itself():
    record = decisions.choose("anything", ["only"])
    assert record.chosen == "only"
    assert dict(record.distribution) == pytest.approx({"only": 1.0})
