# Local decision layer

`core/decision_provider.py` reads a decision from one decoder position: the
request names the option set, the engine returns `top_logprobs` for the token
that commits to a label, and the distribution over the options is softmaxed from
that position. The mechanism follows the prototype that lived outside the repo;
the code, the engine binding and the failure behaviour are this repository's.

## Boundary

The layer recommends. It never approves. Approving a tool call stays in
`core.tools.approval`; no function here takes or returns an approval verdict,
and the module imports nothing from the approval path. A test asserts that the
public surface carries no approve/bypass entry point.

## Interface

```python
decide(kind, state, options) -> {
    "label": str,            # one of `options`
    "confidence": float | None,
    "distribution": [{"option": str, "prob": float}],  # every option, sorted desc
    "degraded": str | None,  # "no_logprobs" | "unmatched_logprobs" | "invalid_json"
    "provider": str,         # engine window name
} | None
```

`None` on every failure: the switch is off, no engine is configured, the
transport fails, the reply carries no usable label, or the option set is invalid
(empty, blank, duplicate, more than 255).

Primitives: `recommend_approval` (allow/ask/deny), `classify_error` (retry /
retry_shorter / fail / compress), `route_skill`, `score_options`, `judge`
(yes/no).

## Engine binding

The endpoint, model and key come from the user's persisted choice
(`~/.ephe/engine.json`, `ephe configure`) or the explicit `EPHE_MODEL_PROVIDER`
environment, through `core.engine_config`. No host, key or model name is written
in the module. `endpoint_is_local` decides the data-flow half from the URL
(loopback only). The key is kept out of `repr` and is sent only as a bearer
header.

## Decoder settings

`temperature=0`, `max_tokens=32`, `logprobs=true`,
`top_logprobs=min(len(options)+2, 20)`, `response_format={"type":"json_object"}`,
option list sorted before it enters the prompt so the same set produces the same
request. Timeout 10 s, cache 64 entries / 30 s, both bounded and configurable at
construction.

## Failure behaviour

| Engine answer | Result |
|---|---|
| label + logprobs | label, confidence from the distribution, `degraded: null` |
| label, no logprobs | label, `confidence: null`, `degraded: "no_logprobs"` |
| logprobs present, label not in enum | top option as label, `degraded: "invalid_json"` |
| logprobs present, none matches an option | label from JSON if valid, else `None` |
| HTTP 400/422 naming logprobs | one retry without the two logprob keys, then `no_logprobs` |
| any other non-200, timeout, transport error | `None` |
| content truncated before the label (`finish_reason=length`) | `None` |

No confidence is ever invented: when the decoder distribution is missing, the
number is `None` and the caller keeps its existing heuristic.

## Switch

`advanced.decision_layer` in `core/settings_schema.py`, type bool, **default
false**. The reader is `is_enabled()`; the register contract tests
(`test_r58_register_vertrag.py`, `test_settings_surface_is_real.py`,
`test_settings_hints.py`) accept the field, so it renders as a row in the Engine
settings block with its description from `core/settings_hints.py`. The
description states both data flows: a cloud engine sees the state text, a local
one does not. `data_notice()` returns the dynamic half (`engine`,
`leaves_device`) for a surface that wants to show it next to the switch.

Nothing activates the layer silently: `decide()` without an explicit provider
returns `None` while the switch is off.

## Tests

23 tests in `tests/test_s20_decision.py`, all against a recorded transport, no
network. Six port the prototype's behaviour (classify, score, route,
multi-token options, binary judge, stable option order); the rest pin
no-logprobs, logprob refusal, invalid JSON, the 255 limit, timeout, cache and
expiry, redaction, the switch default, the approval boundary, the data notice
and the pinned decoder settings.

## Measurement

`scripts/decision_ab.py` runs 60 authored cases (20 approval, 20 error, 20
routing) and reports accuracy per kind, the false-allow rate, latency, tokens
and cost. It counts an unanswered case as unanswered, never as correct.

Smoke run, 2 cases per kind, against the configured engine
`openai_compatible/deepseek-flash` (2026-10-25):

| kind | answered | correct | accuracy | no_logprobs |
|---|---|---|---|---|
| approval | 0 / 2 | 0 | 0.0 | 0 |
| error | 0 / 2 | 0 | 0.0 | 0 |
| routing | 2 / 2 | 2 | 1.0 | 0 |

Latency on the answered cases: mean 926 ms, max 1167 ms; 318 tokens.

The zero on approval and error is not a wrong label: the reply content was
`{"` — the engine is a reasoning model and the pinned 32-token cap ends the
completion before the JSON label. The provider fails closed (`None`), which is
the correct behaviour and the reason the switch stays off by default. A default
on this engine would need a different max-token budget, and that is an owner
decision, not a lane decision.

## Open

- The full 60-case run on an engine that answers within the token cap.
- A dynamic data notice next to the switch (the static description covers both
  flows today).
- The default-on decision: only after a run where accuracy wins and the
  false-allow rate does not rise.
- The two prototype performance tests (batched prefix reuse, <1 s latency) have
  no product side yet: the provider makes one call per decision.
