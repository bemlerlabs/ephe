"""core/decisions.py — the typed decision record and its two backends.

The local backend is the default and is exercised without any engine; the engine
backend is driven through an injected transport, so nothing here opens a socket.
"""

from __future__ import annotations

import dataclasses
import math

import pytest

from core import decisions
from core.decisions import (
    Decision,
    DecisionEngineUnavailable,
    DecisionError,
    EngineAdapter,
    LocalScorer,
    is_engine_configured,
    resolve_backend,
)


@pytest.fixture(autouse=True)
def _no_engine_env(monkeypatch):
    for name in (
        decisions.ENV_ENGINE_URL,
        decisions.ENV_ENGINE_MODEL,
        decisions.ENV_ENGINE_KEY,
    ):
        monkeypatch.delenv(name, raising=False)


def _empty_env() -> dict[str, str]:
    return {}


def _engine_env(
    url: str = "http://engine.local:8000/v1", model: str = "decider"
) -> dict[str, str]:
    return {decisions.ENV_ENGINE_URL: url, decisions.ENV_ENGINE_MODEL: model}


def _without_cost(decision: Decision) -> Decision:
    return dataclasses.replace(decision, cost_seconds=0.0)


def _logprobs_response(pairs: list[tuple[str, float]]) -> dict:
    return {
        "choices": [
            {
                "logprobs": {
                    "content": [
                        {
                            "top_logprobs": [
                                {"token": t, "logprob": math.log(p)} for t, p in pairs
                            ]
                        }
                    ]
                }
            }
        ]
    }


# Backend selection


def test_default_backend_is_local_and_offline():
    assert not is_engine_configured(_empty_env())
    assert isinstance(resolve_backend(env=_empty_env()), LocalScorer)


def test_engine_requires_both_url_and_model():
    assert not is_engine_configured({decisions.ENV_ENGINE_URL: "http://x/v1"})
    assert not is_engine_configured({decisions.ENV_ENGINE_MODEL: "m"})
    assert is_engine_configured(_engine_env())


def test_configured_engine_resolves_to_adapter():
    backend = resolve_backend(env=_engine_env())
    assert isinstance(backend, EngineAdapter)
    assert backend.model == "decider"


def test_explicit_backend_wins_over_env():
    sentinel = LocalScorer()
    assert resolve_backend(sentinel, env=_engine_env()) is sentinel


def test_local_path_never_touches_the_http_client(monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("the offline path must not open the HTTP client")

    monkeypatch.setattr(decisions, "_httpx_transport", boom)
    decision = decisions.choose("state with no engine", ["a", "b"])
    assert decision.backend == "local"


# The decision record


def test_choose_returns_a_well_formed_decision():
    decision = decisions.choose("HTTP 404 on /v1/models", ["retry", "fail", "redirect"])
    assert isinstance(decision, Decision)
    assert decision.verb == "choose"
    assert decision.chosen in decision.options
    assert 0.0 <= decision.confidence <= 1.0
    assert {opt for opt, _ in decision.distribution} == set(decision.options)
    assert abs(sum(p for _, p in decision.distribution) - 1.0) < 1e-9
    probs = [p for _, p in decision.distribution]
    assert probs == sorted(probs, reverse=True)
    assert decision.backend == "local"
    assert decision.cost_seconds >= 0.0
    assert decision.fallback_reason == ""


def test_reversal_is_carried_on_the_record():
    decision = decisions.choose(
        "pick a path", ["left", "right"], reversal="re-open the path"
    )
    assert decision.reversal == "re-open the path"


def test_no_options_is_refused():
    with pytest.raises(DecisionError):
        decisions.choose("a state", [])


# Determinism


def test_same_input_yields_the_same_decision():
    state = "retry after the connection timeout"
    first = decisions.choose(state, ["fail", "retry"])
    second = decisions.choose(state, ["fail", "retry"])
    assert _without_cost(first) == _without_cost(second)


def test_option_order_does_not_change_the_outcome():
    state = "retry after the connection timeout"
    forward = decisions.choose(state, ["fail", "retry"])
    rotated = decisions.choose(state, ["retry", "fail"])
    assert forward.chosen == rotated.chosen == "retry"
    assert dict(forward.distribution) == pytest.approx(dict(rotated.distribution))


def test_overlapping_words_separate_the_distribution():
    decision = decisions.choose(
        "GPU OOM during batch inference, VRAM exhausted",
        ["reduce_batch", "reduce_context", "fail"],
    )
    assert decision.chosen == "reduce_batch"
    assert decision.distribution[0][1] > decision.distribution[-1][1]


def test_no_signal_is_uniform():
    decision = decisions.choose("the sky is blue", ["retry", "fail"])
    probs = [p for _, p in decision.distribution]
    assert probs == pytest.approx([0.5, 0.5])


# The other three verbs


def test_score_ranks_all_options():
    decision = decisions.score("retry after the timeout", ["fail", "retry"])
    assert decision.verb == "score"
    assert len(decision.distribution) == 2
    assert decision.chosen == decision.distribution[0][0]


def test_route_chooses_a_named_handler():
    routes = {"retry_shorter": "retry with a shorter timeout", "fail": "abort"}
    decision = decisions.route("retry after the timeout", routes)
    assert decision.chosen in routes
    assert decision.options == tuple(routes.keys())


def test_judge_is_binary():
    decision = decisions.judge("the request timed out")
    assert set(decision.options) == {"no", "yes"}
    assert decision.chosen in {"no", "yes"}


# The engine backend


def test_engine_distribution_is_read_from_top_logprobs():
    adapter = EngineAdapter(
        base_url="http://engine/v1",
        model="decider",
        transport=lambda url, headers, payload, timeout: _logprobs_response(
            [("A", 0.7), ("B", 0.2), ("C", 0.1)]
        ),
    )
    decision = decisions.choose("pick one", ["alpha", "beta", "gamma"], backend=adapter)
    assert decision.backend == "engine"
    assert decision.chosen == "alpha"
    assert dict(decision.distribution) == pytest.approx(
        {"alpha": 0.7, "beta": 0.2, "gamma": 0.1}
    )


def test_engine_call_carries_the_logprob_shape():
    seen: dict = {}

    def transport(url, headers, payload, timeout):
        seen["url"] = url
        seen["payload"] = payload
        return _logprobs_response([("A", 1.0)])

    adapter = EngineAdapter(
        base_url="http://engine/v1", model="decider", transport=transport
    )
    adapter.score("state", ["only"])
    assert seen["url"] == "http://engine/v1/chat/completions"
    assert seen["payload"]["logprobs"] is True
    assert seen["payload"]["temperature"] == 0.0
    assert seen["payload"]["max_tokens"] == 1
    assert seen["payload"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_missing_logprobs_falls_back_to_local():
    adapter = EngineAdapter(
        base_url="http://engine/v1",
        model="decider",
        transport=lambda *_: {"choices": [{"logprobs": None}]},
    )
    decision = decisions.choose(
        "retry after the timeout", ["fail", "retry"], backend=adapter
    )
    assert decision.backend == "local"
    assert decision.fallback_reason


def test_transport_error_falls_back_and_names_the_reason():
    def transport(*_args):
        raise ConnectionError("connection refused")

    adapter = EngineAdapter(
        base_url="http://engine/v1", model="decider", transport=transport
    )
    decision = decisions.choose(
        "retry after the timeout", ["fail", "retry"], backend=adapter
    )
    assert decision.backend == "local"
    assert "connection refused" in decision.fallback_reason


def test_too_many_options_for_one_token_falls_back():
    adapter = EngineAdapter(
        base_url="http://engine/v1", model="decider", transport=lambda *_: {}
    )
    options = [f"option_{i}" for i in range(decisions.MAX_ENGINE_OPTIONS + 1)]
    decision = decisions.choose("state", options, backend=adapter)
    assert decision.backend == "local"
    assert "window" in decision.fallback_reason


def test_adapter_raises_unavailable_directly():
    adapter = EngineAdapter(
        base_url="http://engine/v1",
        model="decider",
        transport=lambda *_: {"choices": [{"logprobs": {"content": []}}]},
    )
    with pytest.raises(DecisionEngineUnavailable):
        adapter.score("state", ["a", "b"])


# Async wrappers


async def test_async_choose_matches_the_sync_result():
    state = "retry after the connection timeout"
    assert _without_cost(
        await decisions.achoose(state, ["fail", "retry"])
    ) == _without_cost(decisions.choose(state, ["fail", "retry"]))
