"""Provider resolution, engine reachability and the local model catalog.

Split from core/chat.py (2026-10-11). The names stay re-exported from
core.chat; the seams tests patch there (get_active_provider, build_provider_client,
_ollama_async_client) are resolved through the facade at call time.
"""

from __future__ import annotations

import asyncio

from core.model_provider import (
    DEFAULT_OLLAMA_BASE_URL,
    ModelProviderConfig,
    build_engine_provider,
)


def _resolve_provider(
    model: str,
    provider_config: ModelProviderConfig | None,
    api_url: str | None,
) -> ModelProviderConfig:
    """Provider precedence: an explicit config, then a foreign api_url, then the active one.

    - ``provider_config`` wins when given.
    - ``api_url`` selects an OpenAI-compatible engine (e.g. DGX-Spark ds4),
      unless it equals the local Ollama base URL.
    - Otherwise fall back to the active provider (Ollama).
    """
    if provider_config is not None:
        return provider_config
    if api_url and api_url.strip() and api_url.rstrip("/") != DEFAULT_OLLAMA_BASE_URL:
        return build_engine_provider(api_url, model)
    from core.chat import (
        get_active_provider,  # patch seam: tests patch this on core.chat
    )
    return get_active_provider()


async def _engine_reachable(provider: ModelProviderConfig) -> str:
    """Provider-aware engine probe (root-cause fix for a wrong Ollama diagnosis).

    Old: the tool-detect timeout handler ALWAYS probed the local Ollama
    (_ollama_async_client().list()) — for an OpenAI-compatible
    DGX engine that was the wrong engine, the probe ran against
    localhost:11434 and produced the misleading error message
    "Ollama nicht erreichbar".  # language-gate: ignore (verbatim German engine-down message this probe replaced, ui/app.py:356)

    New: the probe follows the active provider and distinguishes three
    states:
    - openai_compatible → GET {base_url}/models (vLLM health endpoint, ~100ms)
    - local/custom_ollama → Ollama .list() (as before)

    Return:
    - "ok"          → the engine answers
    - "busy"        → engine reachable, but the probe itself times out
                      (model loading/GPU occupancy) → "busy", NOT "offline"
    - "unreachable" → connection error/refused → the engine really is down
    """
    if provider.provider == "openai_compatible":
        import httpx

        base = provider.base_url.rstrip("/")
        models_url = f"{base}/models"
        headers = {}
        from core.engine_config import engine_api_key_for

        key = engine_api_key_for(provider.base_url)
        if key:
            headers["Authorization"] = f"Bearer {key}"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(models_url, headers=headers)
                resp.raise_for_status()
            return "ok"
        except (httpx.TimeoutException, asyncio.TimeoutError):
            return "busy"
        except Exception:
            return "unreachable"
    try:
        from core.chat import (
            _ollama_async_client,  # patch seam: tests patch this on core.chat
        )
        client = _ollama_async_client()
        await asyncio.wait_for(client.list(), timeout=3.0)
        return "ok"
    except (asyncio.TimeoutError, TimeoutError):
        return "busy"
    except Exception:
        return "unreachable"


async def list_local_models() -> list[str]:
    """
    Return list of locally available model names.
    Used for onboarding: show user what they have installed.
    Returns [] on any error.
    """
    try:
        from core.chat import (  # patch seam: tests patch these on core.chat
            build_provider_client,
            get_active_provider,
        )
        client = build_provider_client(get_active_provider())
        result = await asyncio.wait_for(client.list(), timeout=3.0)
        names = []
        for m in result.models:
            name = getattr(m, "model", None) or getattr(m, "name", "")
            if name:
                names.append(str(name))
        return names
    except Exception:
        return []


def _model_attr(model: object, name: str, default: object = None) -> object:
    if isinstance(model, dict):
        return model.get(name, default)
    return getattr(model, name, default)


def _model_details(model: object) -> dict:
    details = _model_attr(model, "details", {}) or {}
    if hasattr(details, "model_dump"):
        details = details.model_dump()
    if not isinstance(details, dict):
        details = {}
    return details


def _is_chat_model_option(name: str, details: dict) -> bool:
    family = str(details.get("family") or "").lower()
    families = " ".join(str(item).lower() for item in (details.get("families") or []))
    haystack = f"{name.lower()} {family} {families}"
    blocked = ("embed", "embedding", "nomic-bert", "bge", "e5-", "rerank")
    return bool(name) and not any(token in haystack for token in blocked)


def _format_model_size(size: object) -> str:
    try:
        raw = int(size or 0)
    except (TypeError, ValueError):
        raw = 0
    if raw <= 0:
        return ""
    gib = raw / (1024 ** 3)
    return f"{gib:.1f} GB" if gib >= 1 else f"{raw / (1024 ** 2):.0f} MB"


async def list_local_model_options() -> list[dict]:
    """
    Return local Ollama chat models with UI-friendly metadata.
    Embedding/reranker models are intentionally excluded from chat selection.
    """
    try:
        from core.chat import (  # patch seam: tests patch these on core.chat
            build_provider_client,
            get_active_provider,
        )
        client = build_provider_client(get_active_provider())
        result = await asyncio.wait_for(client.list(), timeout=3.0)
        options: list[dict] = []
        for model_info in getattr(result, "models", []):
            name = str(_model_attr(model_info, "model", None) or _model_attr(model_info, "name", "") or "")
            details = _model_details(model_info)
            if not _is_chat_model_option(name, details):
                continue
            size = _model_attr(model_info, "size", 0)
            parameter_size = str(details.get("parameter_size") or "")
            quantization = str(details.get("quantization_level") or "")
            family = str(details.get("family") or "")
            bits = [bit for bit in (parameter_size, quantization, _format_model_size(size)) if bit]
            options.append(
                {
                    "name": name,
                    "model": name,
                    "label": f"{name} · {' · '.join(bits)}" if bits else name,
                    "family": family,
                    "parameter_size": parameter_size,
                    "quantization": quantization,
                    "size_bytes": int(size or 0),
                    "size_label": _format_model_size(size),
                    "chat_capable": True,
                }
            )
        return sorted(options, key=lambda item: item["name"].lower())
    except Exception:
        return []


async def check_ollama_connection(model: str) -> tuple[bool, str, list[str]]:
    """
    Quick connectivity check. Returns (is_connected, status_message, available_models).
    Safe to call on startup without raising.

        Ollama 0.4+ returns pydantic models instead of dicts.
    """
    try:
        from core.chat import (  # patch seam: tests patch these on core.chat
            build_provider_client,
            get_active_provider,
        )
        client = build_provider_client(get_active_provider())
        result = await asyncio.wait_for(client.list(), timeout=3.0)

        available_names: list[str] = []
        for m in result.models:
            name = getattr(m, "model", None) or getattr(m, "name", "")
            available_names.append(str(name))

        model_pulled = any(model in name for name in available_names)
        if model_pulled:
            return True, f"connected · {model}", available_names
        return True, f"connected · {model} (not pulled)", available_names

    except asyncio.TimeoutError:
        return False, "timeout", []
    except Exception:
        return False, "offline", []


async def check_engine_connection(api_url: str, model: str) -> tuple[bool, str, list[str]]:
    """
    Quick connectivity check for an OpenAI-compatible engine (e.g. DGX-Spark ds4).
    Returns (is_connected, status_message, available_models).

    Root-cause fix: uses the light ``/v1/models`` metadata endpoint (~100ms),
    NOT a full LLM chat request. A 27B model needs 5-15s TTFB for the
    first inference — with a 3s start timeout a chat ping would always be a false
    negative ("not connected"). Health check = metadata, no inference
    (backend architect principle: a light health check, a clear timeout budget).
    """
    import httpx

    # vLLM/DGX URLs often carry a /v1 suffix (e.g. http://host:8000/v1) —
    # the /v1/models endpoint hangs on the base URL (never the /v1 path).
    base = api_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[:-3]
    models_url = f"{base}/v1/models"
    from core.engine_config import engine_api_key_for

    key = engine_api_key_for(api_url)
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(models_url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        available = [m.get("id", "") for m in data.get("data", []) if m.get("id")]
        model_present = any(model in name for name in available)
        if model_present:
            return True, f"connected · {model}", available
        if available:
            # The engine runs, but the active model is not listed → treat it as
            # connected (vLLM lists the loaded model correctly; other
            # server versions may show deviations).
            return True, f"connected · {model} (not listed in /v1/models)", available
        return True, f"connected · {model} (no model list)", []
    except Exception:
        return False, "offline", []
