"""Ephe Decision — one typed decision, with the option set and the cost attached.

The layer answers four question shapes over a legal option set:

    choose  a single option from a list
    score   the same list, ranked, with the full distribution kept
    route   a choice among named handlers
    judge   a binary answer

A decision is worth recording: the option set that was legal, the one chosen,
what it cost, and how it reverses. ``Decision`` carries all of it, so a caller
that routes, gates or escalates can be audited afterwards; the module itself
decides nothing about the product.

Two backends, and the default is the one that needs nothing:

* ``LocalScorer`` — deterministic, offline, no network. It ranks options by how
  the words of the state overlap the words of each option and returns a uniform
  distribution when nothing overlaps. It is the default, because Ephe is
  offline-first and a decision that must not be a network round trip should not
  become one.

* ``EngineAdapter`` — the decoder branch-point distribution: one sampled position
  answers with the option letter whose ``top_logprobs`` we read back, so a single
  call replaces one call per option. It is opt-in (``EPHE_DECISION_ENGINE_URL``
  plus ``EPHE_DECISION_ENGINE_MODEL``) and capability-probed on every call. When
  the engine is configured but cannot answer, the layer falls back to the local
  scorer and names the reason in ``Decision.fallback_reason`` — a decision never
  silently becomes a different decision, and the backend that produced it is
  always in the record.

The surface consumers build against is the four verbs, the ``Decision`` record,
the two backend classes with their ``name`` values (``local``, ``engine``), and
``__all__``. The guarantees a consumer may rely on: the distribution's keys are
the option set, sorted by descending probability then by option name; ``chosen``
is the first entry and ``confidence`` its probability; the probabilities sum to
1.0; ``options`` keeps the caller's order; and when the engine was configured but
the record says ``backend == "local"``, ``fallback_reason`` names why. Everything
else in this module is internal.
"""

from __future__ import annotations

import asyncio
import math
import os
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

#: The frozen public surface; tests/test_decisions_surface.py is the gate that holds it.
#: A name leaves this tuple only with a documented migration, never a rename in place.
__all__ = (
    "Decision",
    "DecisionEngineUnavailable",
    "DecisionError",
    "EngineAdapter",
    "LocalScorer",
    "ENV_ENGINE_URL",
    "ENV_ENGINE_MODEL",
    "ENV_ENGINE_KEY",
    "MAX_ENGINE_OPTIONS",
    "choose",
    "score",
    "route",
    "judge",
    "achoose",
    "ascore",
    "aroute",
    "ajudge",
    "engine_config",
    "is_engine_configured",
    "resolve_backend",
)

#: The engine path is opt-in by configuration; no host, model or key is compiled in.
ENV_ENGINE_URL = "EPHE_DECISION_ENGINE_URL"
ENV_ENGINE_MODEL = "EPHE_DECISION_ENGINE_MODEL"
ENV_ENGINE_KEY = "EPHE_OPENAI_COMPAT_API_KEY"

#: One position answers at most one letter, so the option set is bounded by the alphabet.
MAX_ENGINE_OPTIONS = 20

_WORD = re.compile(r"[a-z0-9]+")


class DecisionError(ValueError):
    """A decision that cannot be made: no options, or a backend with no answer."""


class DecisionEngineUnavailable(DecisionError):
    """The engine was configured but did not produce a usable distribution."""


@dataclass(frozen=True)
class Decision:
    verb: str
    state: str
    options: tuple[str, ...]
    chosen: str
    confidence: float
    distribution: tuple[tuple[str, float], ...]
    backend: str
    cost_seconds: float
    reversal: str = ""
    fallback_reason: str = ""


class LocalScorer:
    """Deterministic offline scorer: word overlap between state and option."""

    name = "local"

    def score(self, state: str, options: Sequence[str]) -> dict[str, float]:
        state_words = set(_WORD.findall(state.lower()))
        raw: dict[str, float] = {}
        for option in options:
            words = _WORD.findall(option.lower())
            hits = sum(1 for word in words if word in state_words)
            # A whole-option mention is a stronger signal than a shared word.
            whole = (
                1 if option.strip() and option.strip().lower() in state.lower() else 0
            )
            raw[option] = hits + 2 * whole
        return _softmax(raw, options)


class EngineAdapter:
    """Reads the option distribution from one sampled position's ``top_logprobs``.

    ``transport`` is ``(url, headers, payload, timeout) -> response_dict``; the
    default posts over httpx. It is injectable so the parse and the fallback can
    be tested without a server.
    """

    name = "engine"

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        transport=None,
        timeout: float = 15.0,
        top_k: int | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.transport = transport or _httpx_transport
        self.timeout = timeout
        self.top_k = top_k

    def _chat_url(self) -> str:
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        return f"{self.base_url}/chat/completions"

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def score(self, state: str, options: Sequence[str]) -> dict[str, float]:
        options = tuple(options)
        if len(options) > MAX_ENGINE_OPTIONS:
            raise DecisionEngineUnavailable(
                f"{len(options)} options exceed the single-letter window of {MAX_ENGINE_OPTIONS}"
            )
        letters = {_letter(i): option for i, option in enumerate(options)}
        listing = "\n".join(
            f"{_letter(i)}) {option}" for i, option in enumerate(options)
        )
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Answer with exactly one letter naming the best option for the state. "
                        "Output the letter and nothing else."
                    ),
                },
                {"role": "user", "content": f"State: {state}\nOptions:\n{listing}"},
            ],
            "temperature": 0.0,
            "max_tokens": 1,
            "logprobs": True,
            "top_logprobs": self.top_k or len(options),
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            data = self.transport(
                self._chat_url(), self._headers(), payload, self.timeout
            )
        except DecisionEngineUnavailable:
            raise
        except (
            Exception
        ) as exc:  # transport and decode failures are the same refusal here
            raise DecisionEngineUnavailable(f"engine request failed: {exc}") from exc
        return _distribution_from_logprobs(data, letters, options)


def _letter(index: int) -> str:
    return chr(ord("A") + index)


def _softmax(raw: Mapping[str, float], options: Sequence[str]) -> dict[str, float]:
    if not options:
        raise DecisionError("a decision needs at least one option")
    values = [float(raw[o]) for o in options]
    top = max(values)
    weights = [math.exp(v - top) for v in values]
    total = sum(weights)
    return {o: w / total for o, w in zip(options, weights)}


def _distribution_from_logprobs(
    data: Mapping, letters: Mapping[str, str], options: Sequence[str]
) -> dict[str, float]:
    try:
        entries = data["choices"][0]["logprobs"]["content"][0]["top_logprobs"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DecisionEngineUnavailable(
            "engine response carries no top_logprobs"
        ) from exc
    mass: dict[str, float] = {}
    for entry in entries or []:
        token = str(entry.get("token", "")).strip().upper()
        option = letters.get(token)
        if option is None:
            continue
        try:
            mass[option] = mass.get(option, 0.0) + math.exp(
                float(entry.get("logprob", -math.inf))
            )
        except (TypeError, ValueError):
            continue
    total = sum(mass.values())
    if total <= 0.0:
        raise DecisionEngineUnavailable(
            "no option letter among the engine's top logprobs"
        )
    return {option: mass.get(option, 0.0) / total for option in options}


def _httpx_transport(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    import httpx  # imported here so the offline path never loads an HTTP client

    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        raise DecisionEngineUnavailable(f"engine answered HTTP {response.status_code}")
    return response.json()


def engine_config(env: Mapping[str, str] | None = None) -> tuple[str, str, str]:
    """Returns (base_url, model, api_key) from the environment; empty when unset."""
    env = os.environ if env is None else env
    url = (env.get(ENV_ENGINE_URL) or "").strip()
    model = (env.get(ENV_ENGINE_MODEL) or "").strip()
    key = (env.get(ENV_ENGINE_KEY) or "").strip()
    return url, model, key


def is_engine_configured(env: Mapping[str, str] | None = None) -> bool:
    """True only when both the endpoint and the model are set."""
    url, model, _ = engine_config(env)
    return bool(url and model)


def resolve_backend(backend=None, *, env: Mapping[str, str] | None = None):
    """The explicit backend if given, else the engine when configured, else local."""
    if backend is not None:
        return backend
    url, model, key = engine_config(env)
    if url and model:
        return EngineAdapter(base_url=url, model=model, api_key=key)
    return LocalScorer()


def _decide(
    verb: str,
    state: str,
    options: Sequence[str],
    *,
    backend=None,
    reversal: str = "",
) -> Decision:
    options = tuple(options)
    if not options:
        raise DecisionError("a decision needs at least one option")
    scorer = resolve_backend(backend)
    started = time.perf_counter()
    fallback_reason = ""
    try:
        probs = scorer.score(state, options)
    except DecisionEngineUnavailable as exc:
        fallback_reason = str(exc)
        scorer = LocalScorer()
        probs = scorer.score(state, options)
    cost = time.perf_counter() - started
    distribution = tuple(sorted(probs.items(), key=lambda kv: (-kv[1], kv[0])))
    chosen, confidence = distribution[0]
    return Decision(
        verb=verb,
        state=state,
        options=options,
        chosen=chosen,
        confidence=confidence,
        distribution=distribution,
        backend=scorer.name,
        cost_seconds=cost,
        reversal=reversal,
        fallback_reason=fallback_reason,
    )


def choose(
    state: str, options: Sequence[str], *, backend=None, reversal: str = ""
) -> Decision:
    return _decide("choose", state, options, backend=backend, reversal=reversal)


def score(
    state: str, options: Sequence[str], *, backend=None, reversal: str = ""
) -> Decision:
    return _decide("score", state, options, backend=backend, reversal=reversal)


def route(
    state: str, routes: Mapping[str, str], *, backend=None, reversal: str = ""
) -> Decision:
    """Chooses among the keys of ``routes``; the caller resolves the handler."""
    return _decide(
        "route", state, tuple(routes.keys()), backend=backend, reversal=reversal
    )


def judge(state: str, *, backend=None, reversal: str = "") -> Decision:
    return _decide("judge", state, ("no", "yes"), backend=backend, reversal=reversal)


async def achoose(
    state: str, options: Sequence[str], *, backend=None, reversal: str = ""
) -> Decision:
    return await asyncio.to_thread(
        choose, state, options, backend=backend, reversal=reversal
    )


async def ascore(
    state: str, options: Sequence[str], *, backend=None, reversal: str = ""
) -> Decision:
    return await asyncio.to_thread(
        score, state, options, backend=backend, reversal=reversal
    )


async def aroute(
    state: str, routes: Mapping[str, str], *, backend=None, reversal: str = ""
) -> Decision:
    return await asyncio.to_thread(
        route, state, routes, backend=backend, reversal=reversal
    )


async def ajudge(state: str, *, backend=None, reversal: str = "") -> Decision:
    return await asyncio.to_thread(judge, state, backend=backend, reversal=reversal)
