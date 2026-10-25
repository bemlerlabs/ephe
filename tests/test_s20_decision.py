"""S20: the guided decision provider reads its confidence from the decoder.

Six of these port the behaviour of the prototype that lived outside the repo
(classify, score, route, multi-token options, binary judge, stable order); the
rest pin what the product needs on top: no invented confidence, the option
limit, a timeout that fails closed, a cache, redaction before the state leaves
the process, a switch that is off by default, and an approval primitive that
can never act as an approval gate.

No network: every test drives a transport that returns a recorded decoder
response.
"""
from __future__ import annotations

import json

import pytest

from core import decision_provider as dp


def _reply(label: str, pairs: dict[str, float], *, content: str | None = None, usage=None) -> dict:
    """One recorded completion: the choice token plus its top_logprobs."""
    top = [{"token": option, "logprob": logprob} for option, logprob in pairs.items()]
    entries = [
        {
            "token": label,
            "logprob": max(pairs.values()),
            "top_logprobs": top,
        }
    ]
    return {
        "choices": [
            {
                "message": {"content": json.dumps({"label": label}) if content is None else content},
                "logprobs": {"content": entries},
            }
        ],
        "usage": usage or {"prompt_tokens": 40, "completion_tokens": 4, "total_tokens": 44},
    }


class Recorder:
    def __init__(self, replies: list[dict] | None = None, error: Exception | None = None):
        self.replies = list(replies or [])
        self.error = error
        self.calls: list[tuple[str, dict, dict, float]] = []

    def __call__(self, url, headers, payload, timeout):
        self.calls.append((url, headers, payload, timeout))
        if self.error is not None:
            raise self.error
        return self.replies.pop(0)


def _provider(recorder: Recorder, **kwargs) -> dp.DecisionProvider:
    target = dp.EngineTarget(
        provider="openai_compatible",
        model="test-model",
        endpoint="https://engine.example/v1",
        api_key="sk-test-0123456789",
    )
    return dp.DecisionProvider(target=target, transport=recorder, **kwargs)


def test_classify_returns_a_valid_label_and_a_distribution():
    recorder = Recorder([_reply("retry", {"retry": -0.2, "fail": -2.1, "redirect": -4.0})])
    result = _provider(recorder).decide("error", "HTTP 404 on /v1/models", ["retry", "fail", "redirect"])

    assert set(result) == {"label", "confidence", "distribution", "degraded", "provider"}
    assert result["label"] == "retry"
    assert 0.0 <= result["confidence"] <= 1.0
    assert abs(sum(item["prob"] for item in result["distribution"]) - 1.0) < 0.01
    assert result["degraded"] is None


def test_score_ranks_every_option_with_separation():
    recorder = Recorder([_reply("reduce_batch", {"reduce_batch": -0.1, "reduce_context": -2.4, "fail": -6.0})])
    result = _provider(recorder).decide(
        "score", "GPU OOM during batch inference", ["reduce_batch", "reduce_context", "fail"]
    )

    probs = [item["prob"] for item in result["distribution"]]
    assert len(probs) == 3
    assert probs == sorted(probs, reverse=True)
    assert probs[0] > probs[-1]
    assert abs(sum(probs) - 1.0) < 0.01


def test_route_picks_one_of_the_named_routes():
    recorder = Recorder([_reply("retry_shorter", {"retry_shorter": -0.3, "fail": -3.0, "compress": -5.0})])
    result = _provider(recorder).decide(
        "routing", "timeout after 120s on large context", ["retry_shorter", "fail", "compress"]
    )
    assert result["label"] in {"retry_shorter", "fail", "compress"}


def test_a_multi_token_option_appears_in_label_and_distribution():
    recorder = Recorder([_reply("retry", {"retry": -0.4, "fail": -2.9, "compress": -4.2})])
    result = _provider(recorder).decide(
        "routing", "timeout after 120s", ["retry_shorter", "fail_hard", "compress_context"]
    )

    assert result["label"] == "retry_shorter"
    options = {item["option"] for item in result["distribution"]}
    assert result["label"] in options


def test_the_binary_judge_answers_yes_or_no():
    recorder = Recorder([_reply("yes", {"yes": -0.1, "no": -3.0})])
    result = dp.judge("The status 404 means Not Found.", provider=_provider(recorder))

    assert result["label"] in {"yes", "no"}
    assert 0.0 <= result["confidence"] <= 1.0


def test_option_order_does_not_change_the_request_or_the_label():
    first = Recorder([_reply("retry", {"retry": -0.2, "fail": -2.4, "redirect": -4.1})])
    second = Recorder([_reply("retry", {"retry": -0.2, "fail": -2.4, "redirect": -4.1})])

    a = _provider(first, cache_ttl=0).decide("error", "503 after 3 attempts", ["retry", "fail", "redirect"])
    b = _provider(second, cache_ttl=0).decide("error", "503 after 3 attempts", ["redirect", "retry", "fail"])

    assert a["label"] == b["label"]
    assert {i["option"]: i["prob"] for i in a["distribution"]} == {
        i["option"]: i["prob"] for i in b["distribution"]
    }
    assert first.calls[0][2]["messages"] == second.calls[0][2]["messages"]


def test_no_logprobs_yields_no_confidence_and_names_the_degradation():
    response = {
        "choices": [{"message": {"content": json.dumps({"label": "fail"})}}],
    }
    result = _provider(Recorder([response])).decide("error", "engine gone", ["retry", "fail"])

    assert result["label"] == "fail"
    assert result["confidence"] is None
    assert result["degraded"] == "no_logprobs"
    assert result["distribution"] == []


def test_invalid_json_falls_back_to_the_decoder_and_says_so():
    reply = _reply("retry", {"retry": -0.2, "fail": -2.0}, content="not json at all")
    result = _provider(Recorder([reply])).decide("error", "engine gone", ["retry", "fail"])

    assert result["label"] == "retry"
    assert result["degraded"] == "invalid_json"


def test_the_option_limit_is_255():
    options = [f"option-{i}" for i in range(256)]
    assert _provider(Recorder([])).decide("score", "state", options) is None

    allowed = [f"option-{i}" for i in range(255)]
    recorder = Recorder([_reply("option-0", {"option-0": -0.1, "option-254": -8.0})])
    assert _provider(recorder).decide("score", "state", allowed) is not None


class _RefusingOnce:
    def __init__(self, status: int, body: str, reply: dict):
        self.status = status
        self.body = body
        self.reply = reply
        self.payloads: list[dict] = []

    def __call__(self, _url, _headers, payload, _timeout):
        self.payloads.append(payload)
        if len(self.payloads) == 1:
            raise dp.EngineRefusal(self.status, self.body)
        return self.reply


def test_an_engine_without_logprobs_answers_without_confidence():
    transport = _RefusingOnce(
        400,
        '{"error":"logprobs is not supported for this model"}',
        {"choices": [{"message": {"content": json.dumps({"label": "fail"})}}]},
    )
    result = _provider(transport).decide("error", "engine gone", ["retry", "fail"])

    assert result["label"] == "fail"
    assert result["confidence"] is None
    assert result["degraded"] == "no_logprobs"
    assert len(transport.payloads) == 2
    assert "logprobs" not in transport.payloads[1]
    assert "top_logprobs" not in transport.payloads[1]


def test_a_refusal_that_is_not_about_logprobs_is_not_retried():
    transport = _RefusingOnce(400, '{"error":"bad request"}', {})
    assert _provider(transport).decide("error", "state", ["retry", "fail"]) is None
    assert len(transport.payloads) == 1


def test_a_timeout_or_transport_error_returns_none():
    provider = _provider(Recorder(error=TimeoutError("engine too slow")))
    assert provider.decide("error", "state", ["retry", "fail"]) is None


def test_the_cache_answers_a_repeated_question_without_a_second_call():
    recorder = Recorder([_reply("retry", {"retry": -0.1, "fail": -3.0})])
    provider = _provider(recorder)

    first = provider.decide("error", "same state", ["retry", "fail"])
    second = provider.decide("error", "same state", ["fail", "retry"])

    assert first == second
    assert len(recorder.calls) == 1


def test_an_expired_cache_entry_is_refetched(monkeypatch):
    recorder = Recorder(
        [
            _reply("retry", {"retry": -0.1, "fail": -3.0}),
            _reply("retry", {"retry": -0.1, "fail": -3.0}),
        ]
    )
    provider = _provider(recorder, cache_ttl=0.01)
    now = [100.0]
    monkeypatch.setattr(dp.time, "monotonic", lambda: now[0])

    provider.decide("error", "same state", ["retry", "fail"])
    now[0] += 1.0
    provider.decide("error", "same state", ["retry", "fail"])

    assert len(recorder.calls) == 2


def test_credentials_are_masked_before_the_state_leaves_the_process():
    recorder = Recorder([_reply("retry", {"retry": -0.1, "fail": -2.0})])
    state = (
        "Authorization: Bearer ghp_abcdefghijklmnop\n"
        "api_key=sk-live-9876543210\n"
        "see https://user:secret@example.test/v1"
    )
    _provider(recorder).decide("error", state, ["retry", "fail"])

    sent = json.dumps(recorder.calls[0][2])
    for secret in ("ghp_abcdefghijklmnop", "sk-live-9876543210", "user:secret"):
        assert secret not in sent
    assert "[redacted]" in sent


def test_the_switch_is_off_by_default(monkeypatch):
    monkeypatch.delenv("EPHE_CONFIG_DIR", raising=False)
    monkeypatch.setattr(dp, "deep_bool", lambda _key: False)
    assert dp.is_enabled() is False
    assert dp.decide("error", "state", ["retry", "fail"]) is None


def test_the_approval_primitive_cannot_act_as_the_approval_gate():
    names = {name.lower() for name in dp.__all__}
    assert not any(word in name for name in names for word in ("approve_", "allow_tool", "bypass"))
    assert not hasattr(dp, "approve_tool")

    recorder = Recorder([_reply("allow", {"allow": -0.1, "ask": -2.0, "deny": -4.0})])
    result = dp.recommend_approval("rm -rf build", provider=_provider(recorder))
    assert result["label"] in dp.APPROVAL_LABELS


def test_the_data_notice_names_whether_the_state_leaves_the_device():
    local = dp.data_notice(
        provider=dp.DecisionProvider(
            target=dp.EngineTarget(
                provider="local_ollama", model="m", endpoint="http://127.0.0.1:11434"
            )
        )
    )
    remote = dp.data_notice(
        provider=dp.DecisionProvider(
            target=dp.EngineTarget(provider="openai_compatible", model="m", endpoint="https://engine.example/v1")
        )
    )

    assert local["leaves_device"] is False
    assert local["engine"] == "local_ollama/m"
    assert remote["leaves_device"] is True
    assert remote["engine"] == "openai_compatible/m"


def test_the_switch_is_registered_and_off(tmp_path, monkeypatch):
    from core.settings_schema import SCHEMA

    meta = SCHEMA["advanced.decision_layer"]
    assert meta["type"] == "bool"
    assert meta["default"] is False

    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path))
    assert dp.is_enabled() is False


def test_the_request_pins_the_decoder_settings():
    recorder = Recorder([_reply("retry", {"retry": -0.1, "fail": -2.0})])
    _provider(recorder).decide("error", "state", ["retry", "fail"])

    payload = recorder.calls[0][2]
    assert payload["temperature"] == 0.0
    assert payload["max_tokens"] == 32
    assert payload["logprobs"] is True
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["top_logprobs"] <= dp.TOP_LOGPROBS_CAP


@pytest.mark.parametrize("kind", ["", "approve", "anything"])
def test_an_unknown_kind_is_refused(kind):
    assert _provider(Recorder([])).decide(kind, "state", ["a", "b"]) is None
