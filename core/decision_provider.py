"""Guided decision provider: one decoder position answers the option set.

The request names the option set, the engine returns ``top_logprobs`` for the
position that commits to a label, and the distribution over the options is read
from that one position. The engine half lives in ``core.decision_engine``; this
module owns the switch, the cache and the five primitives.

The provider is off unless ``advanced.decision_layer`` is set, and every failure
returns ``None``: a decision that cannot be measured is not replaced with a
number.

The approval primitive returns a recommendation for a surface to display.
Approving a tool call stays in ``core.tools.approval``; no function here takes
or returns an approval verdict.
"""

from __future__ import annotations

import json
import time
from collections import OrderedDict
from typing import Sequence

from core.decision_engine import (
    EngineRefusal,
    EngineTarget,
    branch_pairs,
    chat_url,
    httpx_transport,
    label_from_json,
    mentions_logprobs,
    ranked,
    redact_state,
    resolved_target,
)
from core.engine_config import engine_key_fingerprint
from core.settings_schema import deep_bool

__all__ = (
    "APPROVAL_LABELS",
    "DECISION_SETTING",
    "ERROR_LABELS",
    "KINDS",
    "MAX_OPTIONS",
    "DecisionProvider",
    "classify_error",
    "data_notice",
    "decide",
    "is_enabled",
    "judge",
    "recommend_approval",
    "route_skill",
    "score_options",
)

#: Off by default; the switch is the only path to a module-level decision.
DECISION_SETTING = "advanced.decision_layer"

#: One branch position carries at most one token per option.
MAX_OPTIONS = 255
TOP_LOGPROBS_CAP = 20

DEFAULT_TIMEOUT = 10.0
DEFAULT_CACHE_TTL = 30.0
DEFAULT_CACHE_SIZE = 64

APPROVAL_LABELS = ("allow", "ask", "deny")
ERROR_LABELS = ("retry", "retry_shorter", "fail", "compress")
JUDGE_LABELS = ("no", "yes")

KINDS = frozenset({"approval", "error", "routing", "score", "judge"})


def _copy_result(result: dict) -> dict:
    return {
        "label": result["label"],
        "confidence": result["confidence"],
        "distribution": [dict(item) for item in result["distribution"]],
        "degraded": result["degraded"],
        "provider": result["provider"],
    }


class DecisionProvider:
    """Reads the option distribution from one sampled position."""

    def __init__(
        self,
        *,
        target: EngineTarget | None = None,
        endpoint: str = "",
        model: str = "",
        api_key: str = "",
        provider: str = "engine",
        timeout: float = DEFAULT_TIMEOUT,
        cache_ttl: float = DEFAULT_CACHE_TTL,
        cache_size: int = DEFAULT_CACHE_SIZE,
        transport=None,
    ) -> None:
        if target is None:
            if not endpoint or not model:
                raise ValueError("a decision provider needs an endpoint and a model")
            target = EngineTarget(
                provider=provider, model=model, endpoint=endpoint, api_key=api_key
            )
        self.target = target
        self.timeout = timeout
        self.cache_ttl = cache_ttl
        self.cache_size = cache_size
        self.transport = transport or httpx_transport
        self.last_usage: dict = {}
        self._cache: OrderedDict = OrderedDict()

    @classmethod
    def from_config(cls, **kwargs) -> "DecisionProvider | None":
        target = resolved_target()
        if target is None:
            return None
        try:
            return cls(target=target, **kwargs)
        except Exception:
            return None

    @property
    def name(self) -> str:
        return self.target.name

    def _payload(self, kind: str, state: str, options: Sequence[str]) -> dict:
        listing = ", ".join(json.dumps(option, ensure_ascii=False) for option in options)
        return {
            "model": self.target.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You classify one state into exactly one label from the enum. "
                        "Return a JSON object with the single key label."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Task: {kind} decision.\nState: {state}\n"
                        f"Enum: [{listing}]\n"
                        'Return JSON: {"label": <one enum value>}'
                    ),
                },
            ],
            "temperature": 0.0,
            "max_tokens": 32,
            "response_format": {"type": "json_object"},
            "logprobs": True,
            "top_logprobs": min(len(options) + 2, TOP_LOGPROBS_CAP),
        }

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.target.api_key:
            headers["Authorization"] = f"Bearer {self.target.api_key}"
        return headers

    def _cache_key(self, kind: str, state: str, options: Sequence[str]) -> tuple:
        return (
            kind,
            state,
            tuple(options),
            self.target.name,
            self.target.endpoint,
        )

    def _cache_get(self, key: tuple) -> dict | None:
        if self.cache_ttl <= 0 or self.cache_size <= 0:
            return None
        entry = self._cache.get(key)
        if entry is None:
            return None
        stamp, result = entry
        if time.monotonic() - stamp > self.cache_ttl:
            self._cache.pop(key, None)
            return None
        self._cache.move_to_end(key)
        return _copy_result(result)

    def _cache_put(self, key: tuple, result: dict) -> None:
        if self.cache_ttl <= 0 or self.cache_size <= 0:
            return
        self._cache[key] = (time.monotonic(), result)
        self._cache.move_to_end(key)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)

    def _parse(self, data: object, options: Sequence[str]) -> dict | None:
        if not isinstance(data, dict):
            return None
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        choice = choices[0]
        if not isinstance(choice, dict):
            return None
        message = choice.get("message")
        content = message.get("content") if isinstance(message, dict) else ""
        label = label_from_json(content, options)
        logprobs = choice.get("logprobs")
        entries = logprobs.get("content") if isinstance(logprobs, dict) else None
        entries = entries or []
        pairs = branch_pairs(entries, options) if entries else {}
        if not pairs:
            if label is None:
                return None
            return {
                "label": label,
                "confidence": None,
                "distribution": [],
                "degraded": "no_logprobs" if not entries else "unmatched_logprobs",
                "provider": self.name,
            }
        ranking = ranked(pairs, options)
        if not ranking:
            return None
        degraded = None
        if label is None:
            label = ranking[0][0]
            degraded = "invalid_json"
        confidence = next((prob for option, prob in ranking if option == label), 0.0)
        return {
            "label": label,
            "confidence": confidence,
            "distribution": [
                {"option": option, "prob": prob} for option, prob in ranking
            ],
            "degraded": degraded,
            "provider": self.name,
        }

    def decide(
        self, kind: str, state: str, options: Sequence[str]
    ) -> dict | None:
        self.last_usage = {}
        if kind not in KINDS:
            return None
        try:
            raw = tuple(str(option) for option in options)
        except (TypeError, ValueError):
            return None
        if not raw or len(raw) > MAX_OPTIONS:
            return None
        if any(not option.strip() for option in raw):
            return None
        if len(set(raw)) != len(raw):
            return None
        ordered = tuple(sorted(raw))
        redacted = redact_state(state)
        key = self._cache_key(kind, redacted, ordered)
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        payload = self._payload(kind, redacted, ordered)
        url = chat_url(self.target.endpoint)
        try:
            data = self.transport(url, self._headers(), payload, self.timeout)
        except EngineRefusal as refusal:
            # An engine without logprob support rejects the request outright.
            # The label is still measurable; the confidence is not, so the retry
            # drops the two logprob keys and the parse reports `no_logprobs`.
            if refusal.status not in (400, 422) or not mentions_logprobs(refusal.body):
                return None
            bare = {
                key_name: value
                for key_name, value in payload.items()
                if key_name not in ("logprobs", "top_logprobs")
            }
            try:
                data = self.transport(url, self._headers(), bare, self.timeout)
            except Exception:
                return None
        except Exception:
            return None
        result = self._parse(data, ordered)
        if result is None:
            return None
        usage = data.get("usage") if isinstance(data, dict) else None
        self.last_usage = dict(usage) if isinstance(usage, dict) else {}
        self._cache_put(key, result)
        return _copy_result(result)


_SHARED_PROVIDER: DecisionProvider | None = None
_SHARED_KEY: tuple | None = None


def _shared_provider() -> DecisionProvider | None:
    global _SHARED_PROVIDER, _SHARED_KEY
    target = resolved_target()
    if target is None:
        return None
    key = (
        target.provider,
        target.model,
        target.endpoint,
        engine_key_fingerprint(target.api_key) if target.api_key else "",
    )
    if _SHARED_PROVIDER is None or _SHARED_KEY != key:
        _SHARED_PROVIDER = DecisionProvider(target=target)
        _SHARED_KEY = key
    return _SHARED_PROVIDER


def is_enabled() -> bool:
    try:
        return deep_bool("advanced.decision_layer")
    except Exception:
        return False


def decide(
    kind: str, state: str, options: Sequence[str], *, provider=None
) -> dict | None:
    """One decision, or ``None`` when the switch is off or the engine cannot answer.

    An explicit provider serves tests and measurement and bypasses the switch;
    the module-level path obeys ``advanced.decision_layer``.
    """
    if provider is not None:
        return provider.decide(kind, state, options)
    if not is_enabled():
        return None
    selected = _shared_provider()
    if selected is None:
        return None
    return selected.decide(kind, state, options)


def recommend_approval(state: str, *, provider=None) -> dict | None:
    return decide("approval", state, APPROVAL_LABELS, provider=provider)


def classify_error(state: str, *, provider=None) -> dict | None:
    return decide("error", state, ERROR_LABELS, provider=provider)


def route_skill(state: str, options: Sequence[str], *, provider=None) -> dict | None:
    return decide("routing", state, options, provider=provider)


def score_options(state: str, options: Sequence[str], *, provider=None) -> dict | None:
    return decide("score", state, options, provider=provider)


def judge(state: str, *, provider=None) -> dict | None:
    return decide("judge", state, JUDGE_LABELS, provider=provider)


def data_notice(provider=None) -> dict:
    """Where the state goes under the active engine, for the settings surface.

    The row's own text names both cases; this is the dynamic half a surface can
    show next to it. No engine configured means the flow is unknown, not local.
    """
    target = provider.target if isinstance(provider, DecisionProvider) else resolved_target()
    if target is None:
        return {
            "setting": DECISION_SETTING,
            "enabled": is_enabled(),
            "engine": "",
            "leaves_device": None,
        }
    return {
        "setting": DECISION_SETTING,
        "enabled": is_enabled(),
        "engine": target.name,
        "leaves_device": target.leaves_device,
    }
