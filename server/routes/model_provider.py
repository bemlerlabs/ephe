"""Model provider API for offline-first and advanced opt-in providers."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path

from core.chat import list_local_model_options, list_local_models
from core.model_provider import (
    ProviderSetupError,
    get_active_provider,
    list_provider_options,
    set_active_provider,
    validate_provider_type,
)


router = APIRouter(tags=["Model Provider"])


class ProviderUpdateRequest(BaseModel):
    provider: str
    model: str | None = None
    base_url: str | None = None
    confirm_online: bool = False


class ProviderProbeRequest(BaseModel):
    """Probe request: check the endpoint and list the available models.

    No persist, no setup — pure detection. This is how the PWA can find all
    local/external engines after installation without the user having to type
    commands (user mandate: 'not hardcore, able to pick from a list').
    """

    provider: str  # local_ollama | custom_ollama | openai_compatible
    base_url: str | None = None
    api_key: str | None = None


async def _probe_ollama(base_url: str | None) -> tuple[bool, list[str], str, str]:
    """Ollama protocol check: GET {base}/api/tags (lightweight metadata call).

    Returns ``(reachable, models, detail, state)`` with ``state`` ∈
    ok | busy | unreachable — a timeout is "busy", not "offline" (same semantics
    as ``core.chat._engine_reachable``).
    """
    base = (base_url or "").strip().rstrip("/")
    if not base:
        base = "http://127.0.0.1:11434"
    if "://" not in base:
        base = f"http://{base}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base}/api/tags")
            resp.raise_for_status()
            data = resp.json()
        names = [str(m.get("name") or "") for m in data.get("models", []) if m.get("name")]
        return True, names, f"{base} reachable · {len(names)} model(s)", "ok"
    except httpx.TimeoutException:
        return False, [], f"{base} did not answer in time (busy)", "busy"
    except httpx.HTTPStatusError as exc:
        return False, [], f"{base} responds with HTTP {exc.response.status_code}", "unreachable"
    except Exception:
        return False, [], f"{base} not reachable", "unreachable"


def _mirror_api_key(base_url: str, home: Path | None = None) -> str | None:
    """Key fallback from the configs of the detected tools (read-only, local).

    Root cause: the probe only had EPHE_OPENAI_COMPAT_API_KEY — a user whose key
    lived in another tool's auth file (subscription/free plan) still got HTTP 401.
    The models.dev-shaped cache maps provider-id → api-URL, and that tool's
    auth.json holds the key per provider-id.

    Scope, owner decision 2026-10-10: this is the only remaining read of that store
    and it authenticates a `/models` probe, nothing else. The engine itself stopped
    falling back to it the same day (`core/engine_config.py::engine_api_key_for`);
    a chat turn is keyed by the env variable or `~/.ephe/engine.key` or not at all.
    """
    import json

    h = Path(home) if home is not None else Path.home()
    base_clean = (base_url or "").strip().rstrip("/")
    try:
        cache = h / ".cache" / "opencode" / "models.json"
        auth = h / ".local" / "share" / "opencode" / "auth.json"
        if base_clean and cache.is_file() and auth.is_file():
            catalog = json.loads(cache.read_text(encoding="utf-8"))
            authd = json.loads(auth.read_text(encoding="utf-8"))
            for pid, pv in catalog.items() if isinstance(catalog, dict) else ():
                api = pv.get("api") if isinstance(pv, dict) else None
                if isinstance(api, str) and api.rstrip("/") == base_clean:
                    key = (authd.get(pid) or {}).get("key") if isinstance(authd, dict) else None
                    if isinstance(key, str) and key:
                        return key
    except (OSError, ValueError):
        pass
    return None


async def _probe_openai_compatible(base_url: str, api_key: str | None) -> tuple[bool, list[str], str, str]:
    """OpenAI-compatible engine check: GET {base}/v1/models.

    Root cause (same as check_engine_connection): a metadata endpoint instead of
    a chat request — a reasoning model needs seconds for its first inference,
    /v1/models answers in ~100ms.
    """
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return False, [], "no engine URL given", "unreachable"
    if "://" not in base:
        base = f"http://{base}"
    if base.endswith("/v1"):
        base = base[:-3]
    if not api_key:
        from core.engine_config import engine_api_key_for

        api_key = engine_api_key_for(base_url) or _mirror_api_key(base_url) or None
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base}/v1/models", headers=headers)
            resp.raise_for_status()
            data = resp.json()
        ids = [str(m.get("id") or "") for m in data.get("data", []) if m.get("id")]
        return True, ids, f"{base} reachable · {len(ids)} model(s)", "ok"
    except httpx.TimeoutException:
        return False, [], f"{base} did not answer in time (busy)", "busy"
    except httpx.HTTPStatusError as exc:
        return False, [], f"{base} responds with HTTP {exc.response.status_code}", "unreachable"
    except Exception:
        return False, [], f"{base} not reachable", "unreachable"


@router.post("/model/providers/probe")
async def probe_model_provider(req: ProviderProbeRequest) -> dict:
    """Detects an engine and lists its models — without installing anything.

    GIVEN the user enters an Ollama or OpenAI-compatible endpoint
    WHEN  POST /api/model/providers/probe
    THEN  200 + { reachable, models, detail, state } (empty list = not
          reachable or no models) — the PWA builds the selection from it.
          ``state`` is the three-valued ok | busy | unreachable, so the UI can
          tell "the engine is not answering in time" from "the engine is
          down".
    """
    provider = req.provider.strip()
    if provider in ("local_ollama", "custom_ollama"):
        url = (req.base_url or "").strip()
        if not url:
            if provider == "local_ollama":
                url = "http://127.0.0.1:11434"
            else:
                # R9: a REMOTE Ollama without an endpoint is nothing that was probed.
                # Before, the probe fell back to http://127.0.0.1:11434 and reported
                # "erreichbar · N Modelle" — the models of THIS machine as the answer  # language-gate: ignore (the German probe detail this branch returned until the 2026-10-09 literal wave moved :60 and :121 to English)
                # of the DGX/LAN engine, and the surface let an empty remote entry
                # persist. Exactly the silent default AGENTS.md forbids; an open
                # answer stays open.
                return {
                    "reachable": False,
                    "models": [],
                    "detail": "no engine URL given",
                    "state": "unreachable",
                }
        ok, models, detail, state = await _probe_ollama(url)
    elif provider == "openai_compatible":
        ok, models, detail, state = await _probe_openai_compatible(req.base_url or "", req.api_key)
    else:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown provider '{provider}'. Allowed: local_ollama, custom_ollama, openai_compatible.",
        )
    return {"reachable": ok, "models": models, "detail": detail, "state": state}


# Context window per (base_url, model) — an engine restart with a different
# max_model_len is practically a backend restart; a TTL would be YAGNI.
_CONTEXT_WINDOW_CACHE: dict[tuple[str, str], int] = {}


#: Field names with which OpenAI-compatible servers name their window. vLLM
#: writes `max_model_len`; SGLang and several routers call it
#: `context_length` / `max_context_length`. Measured on the active engine on
#: 2026-10-08: /v1/models answered without any of these fields — then the window
#: stays unknown and the surface says so, instead of guessing.
_WINDOW_FELDER = ("max_model_len", "context_length", "max_context_length")


def fenster_aus_modell(modell: object) -> int | None:
    """The window of one model entry from /v1/models, or None."""
    if not isinstance(modell, dict):
        return None
    for feld in _WINDOW_FELDER:
        wert = modell.get(feld)
        if isinstance(wert, int) and wert > 0:
            return wert
    return None


async def _active_context_window(active) -> int | None:
    """The window of the active OpenAI-compatible engine, from /v1/models.

    Root cause: contextMeter.ts had 8192 hard-coded -> with the 262k vLLM the
    statusbar showed 0%/8192.
    """
    if active.provider != "openai_compatible" or not active.base_url:
        return None
    key = (active.base_url, active.model)
    if key in _CONTEXT_WINDOW_CACHE:
        return _CONTEXT_WINDOW_CACHE[key]
    base = active.base_url.strip().rstrip("/")
    if "://" not in base:
        base = f"http://{base}"
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    from core.engine_config import engine_api_key_for

    api_key = engine_api_key_for(active.base_url)
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{base}/models", headers=headers)
            resp.raise_for_status()
            data = resp.json()
        for m in data.get("data", []):
            if not isinstance(m, dict) or m.get("id") != active.model:
                continue
            fenster = fenster_aus_modell(m)
            if fenster:
                _CONTEXT_WINDOW_CACHE[key] = fenster
                return fenster
    except Exception:
        return None
    return None


@router.get("/model/providers")
async def get_model_providers() -> dict:
    active = get_active_provider()
    local_model_options = await list_local_model_options()
    if not local_model_options and active.provider == "openai_compatible" and active.base_url:
        # OpenAI-compatible engines have no Ollama list(); /v1/models returns the
        # model ids. Root cause: the engine tab fell back to the Ollama fallback
        # list and never showed the active vLLM engine.
        ok, ids, _, _ = await _probe_openai_compatible(active.base_url, None)
        if ok:
            local_model_options = [{"name": i, "label": i} for i in ids]
    return {
        "active": active.to_dict(),
        "providers": list_provider_options(),
        "local_models": await list_local_models(),
        "local_model_options": local_model_options,
        "context_window": await _active_context_window(active),
        # Wave 3 (cost monitor): price table of the active model — USD per
        # 1M tokens, form {"in_per_m": 0.05, "out_per_m": 0.40} (engine.json
        # `pricing`). None = no price maintained → the PWA shows no cost chip
        # (never guess a number).
        "pricing": _active_pricing(),
    }


def _active_pricing() -> dict | None:
    """Price table from engine.json (N8b field `pricing`), None when empty."""
    try:
        from core.engine_config import load_engine_config

        choice = load_engine_config()
        pricing = getattr(choice, "pricing", None) if choice else None
        if isinstance(pricing, dict) and (pricing.get("in_per_m") or pricing.get("out_per_m")):
            return {
                "in_per_m": float(pricing.get("in_per_m") or 0),
                "out_per_m": float(pricing.get("out_per_m") or 0),
            }
    except Exception:
        pass
    return None


@router.put("/model/provider")
async def update_model_provider(req: ProviderUpdateRequest) -> dict:
    try:
        provider = validate_provider_type(req.provider)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    if provider == "openai_compatible" and not req.confirm_online:
        raise HTTPException(
            status_code=409,
            detail="Online/API provider requires explicit confirmation.",
        )

    # Switch invariant (owner requirement, measured 2026-10-09): a switch changes
    # model AND endpoint together, or does not happen at all. Without a base_url,
    # set_active_provider inherits the PREVIOUS endpoint (core F4) — right for a
    # same-endpoint model edit (which POST /api/settings sends the URL for), wrong
    # for a cross-engine switch: the composer's generic 'OpenAI-compatible' preset
    # left base_url=...:8888 (the Spark engine being exited) while the model became
    # 'custom-model', so the next turn addressed the wrong engine. Only the harmless
    # re-confirm — same model on an already-active OpenAI-compatible endpoint — may
    # omit the URL; every other such switch fails closed here instead of
    # half-applying. POST /api/settings keeps its own endpoint and is unaffected.
    if provider == "openai_compatible" and not (req.base_url or "").strip():
        current = get_active_provider()
        target = (req.model or "").strip()
        if not (current.provider == "openai_compatible" and target and target == current.model):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Switching to a different OpenAI-compatible model needs its endpoint "
                    "(base_url); without one the current engine's URL would be reused. "
                    "Pick the engine together with its address."
                ),
            )

    if provider == "local_ollama":
        local_model_options = await list_local_model_options()
        available = {item["name"] for item in local_model_options}
        if req.model and available and req.model not in available:
            raise HTTPException(
                status_code=422,
                detail=f"Local model '{req.model}' is not installed or not a chat model.",
            )

    try:
        active = set_active_provider(
            provider=provider,
            model=req.model,
            base_url=req.base_url,
        )
    except ProviderSetupError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # F3: persist — R20-SSOT: both routes use the same core helper.
    from core.engine_config import persist_engine_choice

    try:
        persist_engine_choice(active.provider, active.model, active.base_url)
    except Exception:
        pass  # best effort, the session selection still applies

    # W19: a chosen engine makes the setup skip obsolete (same semantics as
    # POST /settings — otherwise skipped=true would stay beside configured=true).
    from server.routes.settings import _clear_setup_skip

    _clear_setup_skip()

    return {"active": active.to_dict()}
