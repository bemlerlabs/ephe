"""Model provider API for offline-first and advanced opt-in providers."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.chat import list_local_model_options, list_local_models
from core.model_probe import probe_ollama, probe_openai_models, resolve_probe_key
from core.engine_config import window_from_model_entry
from core.model_metadata import bare_metadata, metadata_by_id, model_details, names_of
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


@router.post("/model/providers/probe")
async def probe_model_provider(req: ProviderProbeRequest) -> dict:
    """Detects an engine and lists its models — without installing anything.

    GIVEN the user enters an Ollama or OpenAI-compatible endpoint
    WHEN  POST /api/model/providers/probe
    THEN  200 + { reachable, models, detail, state, model_details } (empty list = not
          reachable or no models) — the PWA builds the selection from it.
          ``state`` is the three-valued ok | busy | unreachable, so the UI can
          tell "the engine is not answering in time" from "the engine is
          down". ``model_details`` is aligned with ``models`` and holds only what the
          endpoint sent; an Ollama name alone is all-null metadata, never a guess.
    """
    provider = req.provider.strip()
    details: list[dict] = []
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
                    "model_details": [],
                }
        ok, models, detail, state = await probe_ollama(url)
        probed = url
        # /api/tags supplies names. /api/show per model would be one request per model
        # on the setup path, so the metadata of an Ollama list stays unknown.
        details = [{"id": name, **bare_metadata()} for name in models]
    elif provider == "openai_compatible":
        ok, entries, detail, state = await probe_openai_models(req.base_url or "", req.api_key)
        models = names_of(entries)
        details = model_details(entries)
        probed = req.base_url or ""
    else:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown provider '{provider}'. Allowed: local_ollama, custom_ollama, openai_compatible.",
        )
    answer: dict = {
        "reachable": ok,
        "models": models,
        "detail": detail,
        "state": state,
        "model_details": details,
    }
    # S3: an endpoint that states `supports_tools: false` is remembered for this
    # process, so the next turn is built without the array instead of asking again
    # and taking the refusal (core/model_capability.py).
    if ok:
        from core.model_capability import note_metadata

        note_metadata(probed, details)
    if provider == "openai_compatible":
        # Which token the probe above authenticated with. `foreign` is the one case the
        # setup line has to say out loud — see resolve_probe_key.
        answer["key_source"] = resolve_probe_key(req.base_url, req.api_key)[1]
    return answer


# Context window per (base_url, model) — an engine restart with a different
# max_model_len is practically a backend restart; a TTL would be YAGNI.
_CONTEXT_WINDOW_CACHE: dict[tuple[str, str], int] = {}


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
        for entry in data.get("data", []):
            if not isinstance(entry, dict) or entry.get("id") != active.model:
                continue
            window = window_from_model_entry(entry)
            if window:
                _CONTEXT_WINDOW_CACHE[key] = window
                return window
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
        ok, entries, _, _ = await probe_openai_models(active.base_url, None)
        if ok:
            known = metadata_by_id(entries)
            from core.model_capability import note_metadata

            note_metadata(active.base_url, list(known.values()))
            local_model_options = []
            for identifier in names_of(entries):
                record = dict(known.get(identifier, bare_metadata()))
                # An option's `name` is the tag a request sends; the entry's own display
                # name belongs to `label`, which is what the list already renders.
                display = record.pop("name", None)
                local_model_options.append(
                    {"name": identifier, "label": display or identifier, **record}
                )
    if local_model_options:
        # One shape for every host: an Ollama list carries sizes and families, not a
        # window or a price, and those fields read as unknown rather than missing.
        local_model_options = [{**bare_metadata(), **item} for item in local_model_options]
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
