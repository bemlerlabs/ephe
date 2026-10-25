"""The engine side of the decision layer: target, transport and distribution.

`core.decision_provider` owns the decision API (switch, primitives, cache); this
module owns the parts that talk to an engine — resolving the user's configured
target, redacting a state before it leaves the process, building the request
URL, and turning one recorded position's `top_logprobs` into a ranked
distribution. Splitting the two keeps each file inside the repository's size
wall and puts every network-adjacent line in one place.
"""

from __future__ import annotations

import ipaddress
import json
import math
import os
import re
from dataclasses import dataclass, field
from typing import Mapping, Sequence
from urllib.parse import urlparse

from core.engine_config import (
    config_root,
    engine_api_key_for,
    engine_window_name,
    resolve_engine_choice,
)

__all__ = (
    "EngineRefusal",
    "EngineTarget",
    "branch_pairs",
    "chat_url",
    "endpoint_is_local",
    "httpx_transport",
    "label_from_json",
    "match_option",
    "mentions_logprobs",
    "ranked",
    "redact_state",
    "resolved_target",
)

_SECRET_PATTERNS = (
    re.compile(r"(?i)(\bauthorization\b\s*[:=]\s*)(?:bearer\s+)?[^\s,;\"']+"),
    re.compile(
        r"(?i)(\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|token|secret|"
        r"password|passwd|pwd)\b\s*[:=]\s*)([\"']?)([^\s,;\"'}]+)"
    ),
    re.compile(r"\bsk-[A-Za-z0-9_-]{6,}\b"),
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{10,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{8,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{12,}\b"),
    re.compile(r"(://)[^/\s:@]+:[^/\s@]+@"),
)


@dataclass(frozen=True)
class EngineTarget:
    """Where a decision request goes; the key is kept out of repr."""

    provider: str
    model: str
    endpoint: str
    api_key: str = field(default="", repr=False)
    pricing: Mapping[str, float] = field(default_factory=dict, repr=False)

    @property
    def local(self) -> bool:
        return endpoint_is_local(self.endpoint)

    @property
    def leaves_device(self) -> bool:
        return not self.local

    @property
    def name(self) -> str:
        return engine_window_name(self.provider, self.model)


class EngineRefusal(RuntimeError):
    """The engine answered with a status that is not 200; the body names why."""

    def __init__(self, status: int, body: str) -> None:
        super().__init__(f"engine answered HTTP {status}: {body[:200]}")
        self.status = status
        self.body = body


def endpoint_is_local(endpoint: str) -> bool:
    """True only for a loopback endpoint: the process and the engine share a host."""
    host = (urlparse(str(endpoint or "")).hostname or "").strip().lower()
    if not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def redact_state(state: str) -> str:
    """Masks credential-shaped text before the state leaves the process."""
    text = str(state or "")
    text = _SECRET_PATTERNS[0].sub(r"\1[redacted]", text)
    text = _SECRET_PATTERNS[1].sub(
        lambda match: f"{match.group(1)}{match.group(2)}[redacted]", text
    )
    for pattern in _SECRET_PATTERNS[2:-1]:
        text = pattern.sub("[redacted]", text)
    return _SECRET_PATTERNS[-1].sub(r"\1[redacted]@", text)


def _target_from_choice(choice) -> EngineTarget | None:
    provider = str(getattr(choice, "provider", "") or "").strip()
    model = str(getattr(choice, "model", "") or "").strip()
    if not provider or not model:
        return None
    endpoint = str(getattr(choice, "api_url", "") or "").strip()
    if not endpoint:
        env_name = {
            "openai_compatible": "EPHE_OPENAI_COMPAT_BASE_URL",
            "custom_ollama": "EPHE_CUSTOM_OLLAMA_BASE_URL",
            "local_ollama": "EPHE_LOCAL_OLLAMA_BASE_URL",
        }.get(provider, "")
        endpoint = (os.environ.get(env_name) or "").strip() if env_name else ""
    if not endpoint and provider == "local_ollama":
        from core.model_provider import DEFAULT_OLLAMA_BASE_URL

        endpoint = DEFAULT_OLLAMA_BASE_URL
    if not endpoint:
        return None
    pricing = getattr(choice, "pricing", None)
    return EngineTarget(
        provider=provider,
        model=model,
        endpoint=endpoint,
        api_key=engine_api_key_for(endpoint),
        pricing=dict(pricing) if isinstance(pricing, dict) else {},
    )


def resolved_target() -> EngineTarget | None:
    """The user's configured engine, or None when none is configured."""
    try:
        # config_root() reads EPHE_CONFIG_DIR at call time. The resolver's default
        # path binds that root at import, which would make a test harness read ~/.ephe.
        choice = resolve_engine_choice(config_root() / "engine.json")
    except Exception:
        return None
    if choice is None:
        return None
    try:
        return _target_from_choice(choice)
    except Exception:
        return None


def chat_url(endpoint: str) -> str:
    raw = endpoint.rstrip("/")
    if raw.endswith("/chat/completions"):
        return raw
    if raw.endswith("/v1"):
        return f"{raw}/chat/completions"
    return f"{raw}/v1/chat/completions"


def httpx_transport(url: str, headers: dict, payload: dict, timeout: float) -> dict:
    import httpx

    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, headers=headers, json=payload)
    if response.status_code != 200:
        raise EngineRefusal(response.status_code, response.text)
    return response.json()


def mentions_logprobs(body: str) -> bool:
    return "logprob" in str(body or "").lower()


def match_option(token: str, options: Sequence[str]) -> str | None:
    """Map a raw top-logprob token to the option it begins.

    The first token of a multi-token option is a prefix of it, so both directions
    match; the longest option wins so `fail` cannot shadow `fail_hard`.
    """
    text = str(token or "").strip().strip('"').strip()
    if not text:
        return None
    if text in options:
        return text
    candidates = [
        option for option in options if text.startswith(option) or option.startswith(text)
    ]
    return max(candidates, key=len) if candidates else None


def branch_pairs(entries: Sequence, options: Sequence[str]) -> dict[str, float]:
    """The logprob pairs at the position that commits to an option."""
    fallback: dict[str, float] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        pairs: dict[str, float] = {}
        for candidate in entry.get("top_logprobs") or []:
            if not isinstance(candidate, dict):
                continue
            option = match_option(candidate.get("token", ""), options)
            if option is None or option in pairs:
                continue
            try:
                pairs[option] = float(candidate["logprob"])
            except (KeyError, TypeError, ValueError):
                continue
        own = match_option(entry.get("token", ""), options)
        if own is not None and pairs:
            return pairs
        if len(pairs) > len(fallback):
            fallback = pairs
    return fallback


def ranked(pairs: Mapping[str, float], options: Sequence[str]) -> list[tuple[str, float]]:
    """Softmax over the pairs, every declared option present, sorted desc."""
    top = max(pairs.values())
    weights = {option: math.exp(logprob - top) for option, logprob in pairs.items()}
    total = sum(weights.values())
    if total <= 0.0:
        return []
    probs = {option: weight / total for option, weight in weights.items()}
    for option in options:
        probs.setdefault(option, 0.0)
    return sorted(
        ((option, round(prob, 6)) for option, prob in probs.items()),
        key=lambda item: (-item[1], item[0]),
    )


def label_from_json(content: object, options: Sequence[str]) -> str | None:
    if not isinstance(content, str) or not content.strip():
        return None
    try:
        parsed = json.loads(content)
    except (TypeError, ValueError):
        return None
    if not isinstance(parsed, dict):
        return None
    value = parsed.get("label")
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value in options else None
