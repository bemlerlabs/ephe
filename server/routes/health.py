"""server/routes/health.py – GET /api/health

Extended with hybrid-architecture information:
  - active_tier:  which tier is active right now (offline | fast | power)
  - active_model: which model is being used right now
  - dgx_online:   whether the DGX remote server is reachable
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import uuid
from pathlib import Path

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from core import __version__
from core._version import API_CONTRACT
from core.connectivity_probe import ConnectivityProbe
from core.model_provider import (
    KEY_CHALLENGE_STATUSES,
    get_active_provider,
    key_challenge_reason,
)
from core.model_router import get_router

router = APIRouter(tags=["Health"])

#: Stable for this process; a restart gets a new id.
_INSTANCE_ID = uuid.uuid4().hex
_ROOT = str(Path(__file__).resolve().parents[2])


def _read_git_sha(root: str) -> str:
    """Commit the serving tree is on, or "" outside a checkout.

    The version string cannot tell two builds of the same number apart, and a
    backend nine commits behind posed as current exactly that way; the shell
    and the installer compare this value instead.
    """
    try:
        out = subprocess.run(
            ["git", "-C", root, "rev-parse", "--short=12", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


_GIT_SHA = _read_git_sha(_ROOT)

# Browser-typical user agent for engine probes: WAFs/Cloudflare block
# python default UAs with 403 (finding 2026-10-01: opencode.ai/zen answered the
# urllib probe with 403 while the httpx chat stream ran over the same endpoint
# → the UI showed "engine offline" during live operation). The health probe
# therefore has to present itself like the chat client.
_PROBE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
}


class HealthResponse(BaseModel):
    status: str
    version: str
    # LC-1: identity and wire contract for the desktop shell's ownership check.
    instance_id: str = ""
    pid: int = 0
    root: str = ""
    git_sha: str = ""
    api_contract: int = 0
    owner: str = ""
    ollama: bool
    models: list[str]
    # Hybrid-architecture fields
    active_tier:  str
    active_model: str
    dgx_online:   bool
    active_provider: str
    offline_capable: bool
    requires_internet: bool
    model_installed: bool = True
    detail: str = ""
    engine_online: bool = False
    # W18/A5: a three-valued state instead of just "online yes/no" — the UI
    # thereby shows "busy" honestly (the engine answers, but the probe runs into
    # the timeout: model loading / GPU occupied) apart from "unreachable".
    engine_state: str = "unreachable"
    # The engine answered and refused the credential this process holds (or has
    # none). Not the same fact as "unreachable", and the desktop reuse path reads
    # exactly this field: a backend it did not start cannot be handed a token
    # afterwards, so the only honest action left is to say what was seen.
    engine_key_challenge: bool = False
    # Whether this start can resolve a credential for the active endpoint at all.
    # The surface needs the pair: "no key here" and "your key was rejected" are
    # different actions, and one sentence may not claim the wrong one.
    engine_key_configured: bool = False


async def _quick_ollama_status(base_url: str, model: str) -> tuple[bool, bool, list[str], str]:
    """Fast, non-blocking UI health probe for local/custom Ollama."""
    url = f"{base_url.rstrip('/')}/api/tags"

    def _fetch() -> tuple[bool, bool, list[str], str]:
        try:
            resp = httpx.get(url, timeout=0.75, headers=_PROBE_HEADERS)
            payload = resp.json()
            models = [
                str(item.get("name") or item.get("model") or "")
                for item in payload.get("models", [])
                if item.get("name") or item.get("model")
            ]
            installed = any(name == model or model in name for name in models)
            detail = "connected" if installed else f"model not installed: {model}"
            return True, installed, models, detail
        except Exception as exc:
            return False, False, [], f"ollama offline: {exc}"

    return await asyncio.to_thread(_fetch)


async def check_ollama_connection(model: str) -> tuple[bool, str, list[str]]:
    """Backward-compatible health probe used by tests and older call sites."""
    provider = get_active_provider()
    connected, _installed, models, detail = await _quick_ollama_status(provider.base_url, model)
    return connected, detail, models


# F-02: engine probe for OpenAI-compatible engines (vLLM/SGLang/DGX)
# Before, openai_compatible was not probed AT ALL → UI/health reported
# "offline" while the engine ran (and the other way round). A short TTL cache so
# the 10s health poll does not flood the engine.
_ENGINE_CACHE: dict[str, tuple[float, bool, str, list[str], str, bool]] = {}
_ENGINE_TTL_S = 15.0


async def _quick_engine_status(
    base_url: str, model: str
) -> tuple[bool, str, list[str], str, bool]:
    """Probe {base_url}/models (OpenAI-compatible).

    Returns ``(online, detail, models, state, key_challenge)`` with ``state`` out
    of ``ok`` | ``busy`` | ``unreachable`` — the same three-valued logic as
    ``core.chat._engine_reachable`` (timeout = busy, not offline). The fifth
    field says what the state cannot: the endpoint is up and turned *us* away.
    """
    now = asyncio.get_event_loop().time()
    cached = _ENGINE_CACHE.get(base_url)
    if cached and (now - cached[0]) < _ENGINE_TTL_S:
        return cached[1], cached[2], cached[3], cached[4], cached[5]

    url = f"{base_url.rstrip('/')}/models"
    # W18: no hardcoded access token any more — a key is sent only
    # when the user has set one (EPHE_OPENAI_COMPAT_API_KEY).
    from core.engine_config import engine_api_key_for

    _key = engine_api_key_for(base_url)
    headers = {"Authorization": f"Bearer {_key}"} if _key else {}

    def _fetch() -> tuple[bool, str, list[str], str, bool]:
        try:
            resp = httpx.get(url, timeout=2.0, headers={**_PROBE_HEADERS, **headers})
            if resp.status_code in KEY_CHALLENGE_STATUSES:
                # Measured 2026-10-10 across two processes: a 401 body is valid JSON
                # with no `data`, so this probe read a keyed endpoint as
                # "engine reachable, model not listed" and the surface said
                # "reachable" while every request failed. What the answer speaks
                # about is the credential; the model list was never read.
                return (
                    False,
                    key_challenge_reason(base_url, resp.status_code, bool(_key)),
                    [],
                    "unreachable",
                    True,
                )
            payload = resp.json()
            models = [
                str(item.get("id") or "")
                for item in payload.get("data", [])
                if item.get("id")
            ]
            installed = any(m == model or model in m for m in models)
            detail = "engine reachable" if installed else f"engine reachable, model not listed: {model}"
            return True, detail, models, "ok", False
        except (httpx.TimeoutException, TimeoutError) as exc:
            # Reachable, but the probe runs into the timeout (model loading,
            # GPU occupied) → "busy", NOT "offline"/unreachable.
            return False, f"engine busy (probe timeout): {exc}", [], "busy", False
        except Exception as exc:
            return False, f"engine unreachable: {exc}", [], "unreachable", False

    result = await asyncio.to_thread(_fetch)
    _ENGINE_CACHE[base_url] = (now, *result)
    return result


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Checks whether the server, Ollama and optionally the DGX are reachable.
    Always returns status 200.

    New in v4.1:
      - active_tier:  "offline" | "fast" | "power"
      - active_model: e.g. "gemma4:e4b"
      - dgx_online:   True when the DGX remote server is reachable

    Optimisation: one shared ConnectivityProbe instance for router + DGX check
    avoids duplicate network calls on the same health poll.
    """
    import os

    provider = get_active_provider()
    active_model = provider.model
    connected = False
    model_installed = True
    all_models: list[str] = []
    detail = ""
    dgx_online = False
    engine_online = False
    engine_state = "unreachable"
    key_challenge = False
    active_tier = "offline"

    if provider.provider in {"local_ollama", "custom_ollama"}:
        connected, detail, all_models = await check_ollama_connection(active_model)
        model_installed = any(name == active_model or active_model in name for name in all_models)
        if connected:
            active_tier = "fast" if model_installed else "offline"
        engine_online = connected
        engine_state = "ok" if connected else "unreachable"

    if provider.provider == "openai_compatible":
        # F-02: real engine probe (before: no probe → always "offline")
        engine_online, detail, all_models, engine_state, key_challenge = (
            await _quick_engine_status(provider.base_url, active_model)
        )
        dgx_online = engine_online
        model_installed = any(m == active_model or active_model in m for m in all_models) if all_models else engine_online
        active_tier = "power" if engine_online else "offline"

    if (os.environ.get("EPHE_HEALTH_DEEP")) == "1":
        try:
            shared_probe = ConnectivityProbe(dgx_host=os.environ.get("EPHE_DGX_HOST"))
            router_inst = get_router()
            active_config = await router_inst.resolve()
            active_tier = active_config.tier.value
            active_model = provider.model or active_config.name
            dgx_online = await shared_probe.check_remote()
            connected, model_installed, all_models, detail = await _quick_ollama_status(
                provider.base_url,
                active_model,
            )
        except Exception:
            connected = False
            model_installed = False
            all_models = []
            detail = "deep health check failed"

    ephe_models = [m for m in all_models if active_model in m]

    return HealthResponse(
        status="ok",
        version=__version__,
        instance_id=_INSTANCE_ID,
        pid=os.getpid(),
        root=_ROOT,
        git_sha=_GIT_SHA,
        api_contract=API_CONTRACT,
        owner=os.environ.get("EPHE_BACKEND_OWNER", ""),
        ollama=connected,
        models=ephe_models if ephe_models else ([active_model] if connected else []),
        active_tier=active_tier,
        active_model=active_model,
        dgx_online=dgx_online,
        engine_state=engine_state,
        active_provider=provider.provider,
        offline_capable=provider.offline_capable,
        requires_internet=provider.requires_internet,
        model_installed=model_installed,
        detail=detail,
        engine_online=engine_online,
        engine_key_challenge=key_challenge,
        engine_key_configured=provider.api_key_configured,
    )
