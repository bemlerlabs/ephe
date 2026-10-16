"""Ephe — the hybrid router decides a loop step from observables, and never for the user.

One test per branch of `core/model_router.decide_loop_step` / `route_loop_call`, plus the two
invariants the branch list exists to protect: a routed call carries its tier's own endpoint
(the half-switch F4 closed), and switching routing on is not an engine choice — with nothing
persisted and no engine env the resolution stays fail-closed instead of falling back to a
local model.

Given / When / Then, strictly. No test here reads a clock or contacts an endpoint.
"""
from __future__ import annotations

import pytest

from core import model_config, model_router
from core.engine_config import ENGINE_SETUP_HINT, EngineNotConfigured
from core.model_config import ModelTier, get_model_config
from core.model_router import (
    LOOP_READONLY_CALL_LIMIT,
    LOOP_TIER,
    ROUTER_REFUSAL_CODE,
    LoopRoute,
    bind_call,
    decide_loop_step,
    route_loop_call,
    routing_enabled,
)

READ_ONLY = ("read_file", "list_directory", "file_search")


def _step(**overrides):
    args = {
        "tools_used_this_turn": ["read_file"],
        "next_tool": "list_directory",
        "calls_so_far": 1,
        "small_tier_ready": True,
    }
    args.update(overrides)
    return decide_loop_step(**args)


def test_GIVEN_routing_off_WHEN_a_read_only_step_is_decided_THEN_the_active_engine_answers():
    route = route_loop_call(
        active=get_model_config(ModelTier.POWER), enabled=False,
        tools_used_this_turn=READ_ONLY, next_tool="read_file", calls_so_far=0,
    )

    assert route == LoopRoute(None, "router-off")
    assert bind_call(route, get_model_config(ModelTier.POWER)).name == get_model_config(
        ModelTier.POWER).name


def test_GIVEN_a_safe_step_under_the_call_limit_WHEN_decided_THEN_the_small_local_tier_runs_it():
    route = _step(tools_used_this_turn=[], next_tool="read_file", calls_so_far=0)

    assert route.tier is LOOP_TIER
    assert route.reason == "router-loop-readonly"
    assert route.refuse is False


def test_GIVEN_a_state_changing_tool_in_the_turn_WHEN_decided_THEN_the_small_tier_is_not_used():
    for used, nxt in ((["read_file"], "write_file"), (["write_file"], "read_file"),
                      ([], "edit_file"), ([], "run_shell"), ([], "delete_file")):
        route = _step(tools_used_this_turn=used, next_tool=nxt)

        assert route.tier is None, (used, nxt)
        assert route.reason == "router-loop-mutating"


@pytest.mark.parametrize(
    "name", ["totally_unknown_tool", "mcp_something", ""],
)
def test_GIVEN_an_unregistered_tool_name_WHEN_decided_THEN_it_stays_on_the_active_engine(name):
    route = _step(next_tool=name)

    assert route.tier is None
    assert route.reason == "router-loop-unknown-tool"


def test_GIVEN_a_repair_step_WHEN_decided_THEN_the_small_tier_is_skipped():
    assert _step(is_repair=True).reason == "router-loop-repair"


def test_GIVEN_the_step_that_commits_a_file_state_outcome_WHEN_decided_THEN_the_big_tier_closes_it():
    assert _step(closes_file_state=True).reason == "router-loop-synthesis"


def test_GIVEN_the_call_limit_IS_reached_WHEN_decided_THEN_the_turn_leaves_the_small_tier():
    under = _step(calls_so_far=LOOP_READONLY_CALL_LIMIT - 1)
    at = _step(calls_so_far=LOOP_READONLY_CALL_LIMIT)

    assert under.tier is LOOP_TIER
    assert at.tier is None and at.reason == "router-loop-call-limit"


def test_GIVEN_the_small_tier_never_answered_a_real_turn_WHEN_decided_THEN_the_step_refuses():
    route = _step(small_tier_ready=False, fallback_to_active=False)

    assert route.refuse is True
    assert route.reason == ROUTER_REFUSAL_CODE
    assert route.tier is None


def test_GIVEN_the_user_named_the_active_engine_as_fallback_WHEN_the_small_tier_is_unreachable_THEN_it_is_recorded_as_a_fallback():
    route = _step(small_tier_ready=False, fallback_to_active=True)

    assert route.tier is None
    assert route.reason == "router-loop-fallback"
    assert route.refuse is False


def test_GIVEN_routing_on_and_no_engine_chosen_WHEN_a_step_is_routed_THEN_it_fails_closed():
    with pytest.raises(EngineNotConfigured) as raised:
        route_loop_call(
            active=None, enabled=True, tools_used_this_turn=READ_ONLY,
            next_tool="read_file", calls_so_far=0,
        )

    assert "routing" in str(raised.value.args[0]).lower()
    assert raised.value.hint == ENGINE_SETUP_HINT


def test_GIVEN_routing_off_and_no_engine_chosen_WHEN_a_step_is_routed_THEN_the_resolution_is_left_to_the_caller():
    # Turning routing off must not change what an unconfigured machine sees: the fail-closed
    # path stays the one place that raises, and the router stays out of it.
    route = route_loop_call(
        active=None, enabled=False, tools_used_this_turn=READ_ONLY,
        next_tool="read_file", calls_so_far=0,
    )

    assert route == LoopRoute(None, "router-off")


@pytest.mark.parametrize(
    "environ,expected",
    [
        ({}, False),
        ({"EPHE_ENGINE_ROUTING": ""}, False),
        ({"EPHE_ENGINE_ROUTING": "off"}, False),
        ({"EPHE_ENGINE_ROUTING": "0"}, False),
        ({"EPHE_ENGINE_ROUTING": "on"}, True),
        ({"EPHE_ENGINE_ROUTING": "ON"}, True),
        ({"EPHE_ENGINE_ROUTING": " true "}, True),
    ],
)
def test_GIVEN_the_switch_values_WHEN_routing_enabled_is_read_THEN_only_an_explicit_on_turns_it_on(environ, expected):
    assert routing_enabled(environ) is expected


@pytest.fixture()
def separate_hosts(monkeypatch):
    """FAST and POWER on different hosts, the DGX case the invariant is about.

    Without EPHE_DGX_HOST both tiers answer localhost:11434, and a test that compares the
    two endpoints proves nothing on such a machine.

    The teardown restores the three variables ITSELF before the final reload, because
    ``monkeypatch.undo()`` runs only after this finalizer: a reload under the fixture's own
    tags would leave ``core.model_config`` and ``core.model_router`` rebuilt for a host the
    rest of the suite does not run on, and a later test that reads ``get_model_config``
    would inherit the tag (the order-dependence `94-report.md` §18 measured). The final
    reload must see the environment the suite started in.
    """
    import importlib
    import os

    keys = ("EPHE_DGX_HOST", "EPHE_POWER_MODEL", "EPHE_FAST_MODEL")
    original = {key: os.environ.get(key) for key in keys}
    monkeypatch.setenv("EPHE_DGX_HOST", "spark.internal:11434")
    monkeypatch.setenv("EPHE_POWER_MODEL", "gemma4:26b")
    monkeypatch.setenv("EPHE_FAST_MODEL", "gemma4:12b")
    importlib.reload(model_config)
    importlib.reload(model_router)
    try:
        yield model_config, model_router
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        importlib.reload(model_config)
        importlib.reload(model_router)


def test_GIVEN_a_routed_small_tier_call_WHEN_bound_THEN_model_and_endpoint_move_together(separate_hosts):
    config, router = separate_hosts
    fast = config.get_model_config(config.ModelTier.FAST)
    power = config.get_model_config(config.ModelTier.POWER)
    bound = router.bind_call(router.LoopRoute(router.LOOP_TIER, "router-loop-readonly"), active=power)

    assert (bound.name, bound.base_url) == (fast.name, fast.base_url)
    assert bound.base_url != power.base_url


def test_GIVEN_a_return_to_the_active_engine_WHEN_bound_THEN_the_choice_is_untouched(separate_hosts):
    config, router = separate_hosts
    power = config.get_model_config(config.ModelTier.POWER)
    fast = config.get_model_config(config.ModelTier.FAST)
    bound = router.bind_call(router.LoopRoute(None, "router-loop-mutating"), active=power)

    assert (bound.name, bound.base_url) == (power.name, power.base_url)
    assert bound.base_url != fast.base_url
