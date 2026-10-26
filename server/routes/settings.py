"""server/routes/settings.py – GET/POST /api/settings

Single source of truth for the PWA settings.

Why: the frontend (ChatInput, SettingsPanel) calls `getSettings()` →
`GET /api/settings`. That route did not exist before → 404 →
`catch(() => {})` swallowed the error → the hardcoded `gemma4:e4b`
stayed as the active model even though the engine (CLI/`engine.json`)
was using Qwen/DGX.

This endpoint returns the **actively configured** model from
`get_active_provider()` (which reads `engine.json` + env) — exactly the
engine that `ephe tui` / `ephe start` runs on. The PWA therefore always
shows the same model as the CLI (one source).

POST /api/settings applies a provider choice (via
`set_active_provider`, persisted in engine.json) and returns the new
active model.
"""
from __future__ import annotations

import asyncio
import logging
from urllib.parse import urlparse
import json
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.model_provider import (
    ProviderSetupError,
    get_active_provider,
    set_active_provider,
    validate_provider_type,
)
from core.engine_config import (
    OPENAI_COMPAT,
    EngineChoice,
    clear_engine_config,
    load_engine_config,
    save_engine_config,
    store_engine_api_key,
)
from core.security_config import load_security_config
from server.refusals import Refused

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Settings"])


class ProviderSettings(BaseModel):
    type: str
    endpoint: str | None = None
    api_key: str | None = None
    model: str | None = None


class SettingsRequest(BaseModel):
    provider: ProviderSettings | None = None
    memory_enabled: bool | None = None
    language: str | None = None
    # F: workspace/project folder — the shell/file tools work inside it (like an
    # editor workspace). None/empty = the previous behaviour (server cwd).
    workspace_dir: str | None = None
    # R44 (P4) / R4-A1: since the workbench no longer a birthplace, but the saved
    # adoption target (POST /artifacts/{id}/adopt). Empty = ask for the target;
    # an existing folder object is required.
    output_dir: str | None = None
    # Wave 5 (setting depth): generation parameters (temperature, top_p,
    # max_tokens, tool_budget, context_window, memory_max_entries). None =
    # unchanged (the existing block stays). Hard validated → 422.
    generation: dict | None = None
    # Wave 6 (deep settings): section register from the deep schema
    # (core.settings_schema). None = unchanged. Hard validated → 422.
    sections: dict | None = None


def _active_provider_dict() -> dict:
    """Maps the active provider into the frontend shape (AppSettings.provider).

    The key itself never travels. The screen has to know whether one is stored and how it
    ends, which is what the image section already answers with `has_api_key` /
    `api_key_hint`; a GET that returns the secret puts it into every proxy log, browser
    devtools panel and screen share on the network the product is reachable from.
    """
    active = get_active_provider()
    key = os.environ.get("EPHE_OPENAI_COMPAT_API_KEY", "")
    return {
        "type": active.provider,
        "endpoint": active.base_url,
        "api_key_configured": bool(key),
        "api_key_hint": key[-4:] if len(key) >= 4 else "",
        "model": active.model,
    }


def _workspace_dir_dict() -> str | None:
    """Reports the active workspace (persisted engine.json, validated)."""
    from core.engine_config import get_workspace_dir, load_engine_config

    persisted = load_engine_config()
    if persisted and persisted.workspace_dir:
        return persisted.workspace_dir
    # No persisted workspace → show the server cwd as the effective value
    return get_workspace_dir()


def _output_dir_dict() -> str | None:
    """Reports the active output path (engine.json > EPHE_OUTPUT_DIR > None)."""
    from core.engine_config import get_output_dir

    return get_output_dir()


def _generation_dict() -> dict:
    """Active generation parameters (env precedence > engine.json > default).

    Wave 2/B4: the non-numeric options join the payload when they are set, so the
    settings surface can show what the request will actually carry.
    """
    from core.engine_config import read_generation_options, read_generation_values

    values: dict = dict(read_generation_values())
    for key, value in read_generation_options().items():
        if value:
            values[key] = value
    return values


def _generation_meta_dict() -> dict:
    """Bounds AND explanation of the generation block, from one source.

    I3-3: the limits had been typed into the client ('0–2'), the truth lived in
    GENERATION_BOUNDS. I3-9: the matching text travels along, so the card shows six
    explained dials instead of six puzzling number fields. max=None means
    'no upper bound' — passed through exactly like that.
    """
    from core.engine_config import GENERATION_BOUNDS
    from core.settings_hints import GENERATION_HINTS

    meta: dict[str, dict] = {}
    for key, (default, low, high) in GENERATION_BOUNDS.items():
        hint = GENERATION_HINTS.get(key)
        meta[key] = {"default": default, "min": low, "max": high}
        if hint is not None:
            meta[key]["hint"], meta[key]["hintEn"] = hint
    return meta


@router.get("/settings")
async def get_settings() -> dict:
    """Returns the active settings (single source of truth)."""
    return {
        "provider": _active_provider_dict(),
        "memory_enabled": os.environ.get("EPHE_MEMORY_ENABLED", "1") != "0",
        "language": os.environ.get("EPHE_LANGUAGE", "de"),
        "workspace_dir": _workspace_dir_dict(),
        "output_dir": _output_dir_dict(),
        # M2: approval profile for the composer badge (strict|session|autonomous).
        "approval_profile": load_security_config().approval_profile,
        # Wave 5: generation depth (temperature/top_p/max_tokens/tool_budget/
        # context_window/memory_max_entries) — more levers for the user.
        "generation": _generation_dict(),
        # I3-3/I3-9: the bounds and explanation belonging to it — display, clamping and
        # client text from one source, not from three typed-in ones.
        "generation_meta": _generation_meta_dict(),
        # Wave 6: deep section register (deep schema, persisted).
        "deep": _deep_view_dict(),
    }


def _deep_view_dict() -> list[dict]:
    """Aggregated deep view: schema + persistence + defaults, presented compactly.

    I3-6: the blocked MCP counter is gone — the field was no dial but a
    gauge that overwrote the user value on every GET. MCP servers are shown and
    configured in the MCP area (GET/PUT /api/settings/mcp).
    """
    from core.settings_schema import deep_view

    return deep_view()


@router.post("/settings")
async def update_settings(req: SettingsRequest) -> dict:
    """Applies a provider choice and returns the new active model.

    Persisted in engine.json (via set_active_provider) — so CLI and PWA
    keep the same engine (one source).
    """
    if req.provider is not None:
        try:
            provider_type = validate_provider_type(req.provider.type)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        key = ""
        if provider_type == "openai_compatible" and req.provider.api_key:
            key = req.provider.api_key.strip()
            if key:
                os.environ["EPHE_OPENAI_COMPAT_API_KEY"] = key

        try:
            set_active_provider(
                provider=provider_type,
                model=req.provider.model,
                base_url=req.provider.endpoint,
            )
        except ProviderSetupError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        if key:
            # The env copy answers this process only; the stored copy is what the
            # next start reads, so it is bound to the engine that just validated.
            from core.engine_config import EngineChoice

            active = get_active_provider()
            store_engine_api_key(
                key,
                engine=EngineChoice(
                    provider=active.provider,
                    model=active.model,
                    api_url=active.base_url,
                ),
            )

    if req.memory_enabled is not None:
        os.environ["EPHE_MEMORY_ENABLED"] = "1" if req.memory_enabled else "0"
    if req.language:
        os.environ["EPHE_LANGUAGE"] = req.language
    if req.workspace_dir is not None or req.output_dir is not None:
        # F: set or clear the workspace — validated (must be an existing dir).
        # R44 (P4): output_dir as the second folder entry of the same file —
        # one read-modify-write block, so the two fields cannot
        # overwrite each other in the same POST.
        # Module alias instead of a from-import — a from-import here would
        # make save_engine_config & Co. local variables for the ENTIRE function
        # (UnboundLocalError in the provider persist block, silently swallowed).
        import core.engine_config as _ec

        try:
            wd = (
                _ec.validate_workspace_dir(req.workspace_dir)
                if req.workspace_dir is not None
                else None
            )
            od = (
                _ec.validate_output_dir(req.output_dir)
                if req.output_dir is not None
                else None
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        base = _ec.load_engine_config() or _ec.EngineChoice(
            provider=get_active_provider().provider,
            model=get_active_provider().model,
            api_url=get_active_provider().base_url,
        )
        _ec.save_engine_config(_ec.EngineChoice(
            provider=base.provider,
            model=base.model,
            api_url=base.api_url,
            # Empty input = explicit reset back to the default.
            workspace_dir=wd if req.workspace_dir is not None else base.workspace_dir,
            output_dir=od if req.output_dir is not None else base.output_dir,
        ))

    # Wave 5: persist the generation block (read-modify-write through the
    # core helper). Hard validated — outside the bounds → 422.
    if req.generation is not None:
        from core.engine_config import (
            EngineChoice as _EC,
            validate_generation,
        )
        import core.engine_config as _ec

        try:
            gen = validate_generation(req.generation)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        base = _ec.load_engine_config() or _EC(
            provider=get_active_provider().provider,
            model=get_active_provider().model,
            api_url=get_active_provider().base_url,
        )
        _ec.save_engine_config(_EC(
            provider=base.provider,
            model=base.model,
            api_url=base.api_url,
            workspace_dir=base.workspace_dir,
            output_dir=base.output_dir,
            generation=gen,
        ))

    # Wave 6: persist the deep section register (settings.json).
    # Hard validated — range violation / bad toggle choice → 422.
    if req.sections is not None:
        from core.settings_schema import validate_sections, save_deep_settings
        try:
            merged = validate_sections(req.sections)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if not save_deep_settings(merged):
            raise Refused("settings_register_unwritable")

    # Persistence: engine.json is the shared source for CLI + PWA.
    # set_active_provider() is session-local only — without save_engine_config
    # the CLI would use the old engine again on the next start
    # (two sources instead of one).
    if req.provider is not None:
        # R20-SSOT: persistence only through the core helper (same path as
        # PUT /api/model/provider) — api_url is kept for remote providers.
        from core.engine_config import persist_engine_choice

        active = get_active_provider()
        try:
            persist_engine_choice(active.provider, active.model, active.base_url)
        except Exception:
            pass
        # W19: with a chosen engine the skip marker is obsolete — the chat
        # opens, the gate will show the chat directly from now on.
        # (Persistence is best-effort; the session-local choice still applies.)
        _clear_setup_skip()

    return {
        "provider": _active_provider_dict(),
        "memory_enabled": os.environ.get("EPHE_MEMORY_ENABLED", "1") != "0",
        "language": os.environ.get("EPHE_LANGUAGE", "de"),
        "workspace_dir": _workspace_dir_dict(),
        "output_dir": _output_dir_dict(),
        # M2: approval profile for the composer badge (strict|session|autonomous).
        "approval_profile": load_security_config().approval_profile,
        "generation": _generation_dict(),
    }


# Setup status (the PWA first-run gate)
# Root cause: on first start the PWA never knew whether an engine had
# already been chosen — which is why it showed the old Tauri-only onboarding wizard
# (check_ollama via IPC), which never ran in the browser. /api/setup/status is
# the single source of truth for "does the user need the engine choice?".


def _setup_skip_file():
    """Marker file for "deliberately skipped setup" (W19 skip option)."""
    import core.engine_config as _ec

    return _ec.config_root() / "setup.json"


#: Max remembered endpoints in the history (recent-first, deduplicated).
_ENDPOINT_HISTORY_MAX = 8


def _endpoint_history_file():
    """Persisted list of the OpenAI-compatible endpoints reached last."""
    import core.engine_config as _ec

    return _ec.config_root() / "endpoints.json"


def _load_endpoint_history() -> list[str]:
    """Recently seen OpenAI-compatible URLs (recent-first); empty when there are none."""
    try:
        raw = json.loads(_endpoint_history_file().read_text(encoding="utf-8"))
    except Exception:
        return []
    items = raw.get("endpoints") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        return []
    return [str(u).strip() for u in items if isinstance(u, str) and str(u).strip()]


def _remember_endpoint(url: str) -> None:
    """Writes the endpoint into the history recent-first (deduplicated, capped)."""
    url = (url or "").strip().rstrip("/")
    if not url:
        return
    hist = _load_endpoint_history()
    norm = {u.rstrip("/") for u in hist}
    if url.rstrip("/") in norm:
        # already known — just pull it to the front.
        hist = [url] + [u for u in hist if u.rstrip("/") != url.rstrip("/")]
    else:
        hist = [url] + hist
    hist = hist[:_ENDPOINT_HISTORY_MAX]
    try:
        f = _endpoint_history_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"endpoints": hist}), encoding="utf-8")
    except Exception:
        pass


def _setup_skipped() -> bool:
    try:
        return bool(json.loads(_setup_skip_file().read_text(encoding="utf-8")).get("skipped"))
    except Exception:
        return False


def _clear_setup_skip() -> None:
    try:
        _setup_skip_file().unlink(missing_ok=True)
    except Exception:
        pass


#: Base URL sources for the OpenAI-compatible engine (DGX Spark / vLLM). The
#: deployment environment already carries the real URL; no separate entry needed.
_OPENAI_BASE_URL_ENV: tuple[str, ...] = (
    "EPHE_OPENAI_COMPAT_BASE_URL",
    "ANTHROPIC_BASE_URL",
    "OPENAI_BASE_URL",
    "VLLM_BASE_URL",
)
#: Default ports a vLLM-/OpenAI-compatible service typically occupies
#: (sibling fallback, when the env port does not serve /v1/models).
#: The usual ports of local and in-network inference servers. ONE list for both
#: paths: the loopback scan of this machine (``_setup_candidates``) and the
#: probing of known hosts (\`_probe_openai_auto\`). Two lists were two
#: truths — 8888 (vLLM on the DGX Spark) was only in one, 30000 (SGLang)
#: and 1234 (LM Studio) in the other.
#:
#: Only a host already named somewhere (engine.json,
#: env, history) or loopback gets probed. Never a network. The hint names a
#: likelihood, not a result: what is recognised is an OpenAI-compatible endpoint,
#: not the software behind it (vLLM, SGLang, TensorRT-LLM, LM Studio, llama.cpp
#: and new servers of the same kind are all meant here).
_ENGINE_PORTS: tuple[tuple[int, str, str], ...] = (
    (8000, "vllm", "typisch für vLLM / TensorRT-LLM"),
    (8888, "vllm_dgx", "typisch für vLLM (DGX-Spark-Default)"),
    (30000, "sglang", "typisch für SGLang"),
    (1234, "lm_studio", "typisch für LM Studio"),
    (8080, "llama_cpp", "typisch für llama.cpp-Server"),
    (4000, "litellm", "typisch für LiteLLM-Proxy"),
    (5000, "", ""),
)

#: Port list as strings — the sibling fallback needs URLs, not numbers.
_VLLM_STD_PORTS: tuple[str, ...] = tuple(str(port) for port, _code, _hint in _ENGINE_PORTS)
#: Port -> (code, sentence), so that even a hit THE LONG WAY ROUND (host without a
#: port or the wrong port) can say what the found port typically stands for. The code
#: is the machine half, the sentence stays what an old client and the log read; the
#: wording a user sees lives in `app/src/locales/{de,en}.json` under
#: `setup.portHint.<code>`. Same split as `core.reason.Reason`.
_PORT_HINT: dict[str, tuple[str, str]] = {
    str(port): (code, hint) for port, code, hint in _ENGINE_PORTS
}


def _port_hint(port: object) -> tuple[str, str]:
    """(code, sentence) for a port, both empty where the port says nothing."""
    return _PORT_HINT.get(str(port or ""), ("", ""))


def _dgx_host_url(raw: str) -> str | None:
    """Converts `EPHE_DGX_HOST` (host, host:port or a full URL) into a candidate URL.

    The value already lives in the core (core/model_config.py, core/model_router.py,
    server/routes/health.py) — only the setup scanning did not know it. Whoever set
    their Spark address once does not have to type it a second time.
    """
    host = (raw or "").strip()
    if not host:
        return None
    if host.startswith(("http://", "https://")):
        return host if host.rstrip("/").endswith("/v1") else host.rstrip("/") + "/v1"
    return f"http://{host}/v1"


def _first_env(names: tuple[str, ...]) -> str:
    """First non-empty environment VARIABLE from ``names`` (priority order)."""
    for name in names:
        val = (os.environ.get(name) or "").strip()
        if val:
            return val
    return ""


def _setup_candidates() -> list[dict[str, str | None]]:
    """All engine candidates due for the auto scan, deduplicated.

    Sources in priority order: the persisted ``engine.json`` (the URL the user
    actually stored, e.g. DGX Spark), the local Ollama default and
    the env base URLs of the three providers. That way onboarding always has
    the correct, configured URL prefilled — not just the default.
    """
    out: list[dict[str, str | None]] = []
    seen: set[str] = set()

    def _add(
        provider: str,
        url: str | None,
        code: str = "",
        hint: str = "",
        sweep: bool = False,
    ) -> None:
        url = (url or "").strip() or None
        key = f"{provider}|{(url or '').rstrip('/')}"
        if not provider or key in seen:
            return
        seen.add(key)
        entry: dict[str, str | None] = {"provider": provider, "url": url}
        if hint:
            entry["hint"] = hint
            entry["hint_code"] = code
        if sweep:
            entry["sweep"] = True
        out.append(entry)

    persisted = load_engine_config()
    if persisted is not None:
        _add(persisted.provider, persisted.api_url or None)
    # OpenAI-compatible endpoints reached last (e.g. DGX Spark), even
    # after the active engine was switched to another provider.
    for hist_url in _load_endpoint_history():
        _add("openai_compatible", hist_url)
    # Environment-carried engines before the implicit default: the deployment
    # environment already carries the real DGX/vLLM URL (e.g. ANTHROPIC_BASE_URL),
    # without the user having to store it separately.
    _add("openai_compatible", _first_env(_OPENAI_BASE_URL_ENV))
    # I4-2: the host once set on this machine (DGX Spark and the like) counts too —
    # without a port the sibling scan finds the right one in the probe path.
    _add("openai_compatible", _dgx_host_url(os.environ.get("EPHE_DGX_HOST", "")))
    _add("custom_ollama", _first_env(("EPHE_CUSTOM_OLLAMA_BASE_URL",)))
    _add("local_ollama", _first_env(("EPHE_LOCAL_OLLAMA_BASE_URL",)))
    # I4-1: find local engine servers nobody has stored — the machine
    # is already running one, Ephe just did not know. Loopback, pure discovery.
    for port, code, hint in _ENGINE_PORTS:
        _add("openai_compatible", f"http://127.0.0.1:{port}/v1", code, hint, sweep=True)
    # implicit local Ollama default last (only when nothing else is set).
    _add("local_ollama", None)
    return [c for c in out if c["url"] or c["provider"] == "local_ollama"]


async def _probe_openai_auto(url: str, allow_siblings: bool = True) -> dict[str, object]:
    """OpenAI-compatible probe, optionally with a sibling-port fallback.

    When the environment names a URL whose port does not serve the ``/v1/models``
    list (typical for proxy/port deviations), the same host is probed on the
    usual vLLM ports and the first responding combination is
    returned.

    I4-1: for the candidates of the loopback scan this is off. They are
    themselves the port list — the fallback would have merged all seven onto the one
    responding port, and a hit on :8000 would have carried 'typisch für SGLang'.  # language-gate: ignore (quotes a shipped port-hint string, see settings.py:393)
    """
    from core.model_probe import probe_openai_compatible, resolve_probe_key

    ok, models, detail, state = await probe_openai_compatible(url, None)
    source = resolve_probe_key(url)[1]
    if ok and models:
        _remember_endpoint(url)
        return {
            "url": url,
            "reachable": True,
            "models": models,
            "detail": detail,
            "state": "ok",
            "key_source": source,
        }
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        port = str(parsed.port or "")
        scheme = parsed.scheme or "http"
    except Exception:
        host, port, scheme = "", "", "http"
    if host and allow_siblings:
        for cand_port in _VLLM_STD_PORTS:
            if cand_port == port:
                continue
            alt = f"{scheme}://{host}:{cand_port}/v1"
            ok2, models2, detail2, state2 = await probe_openai_compatible(alt, None)
            if ok2 and models2:
                _remember_endpoint(alt)
                alt_code, alt_hint = _port_hint(cand_port)
                return {
                    "url": alt,
                    "reachable": True,
                    "models": models2,
                    "detail": detail2,
                    "state": "ok",
                    "hint": alt_hint,
                    "hint_code": alt_code,
                    "key_source": resolve_probe_key(alt)[1],
                }
    near_code, near_hint = _port_hint(urlparse(str(url)).port)
    return {
        "url": url,
        "reachable": bool(ok),
        "models": models or [],
        "detail": detail,
        "state": state,
        "hint": near_hint,
        "hint_code": near_code,
        "key_source": source,
    }


def _engine_choice_is_complete(choice: EngineChoice | None) -> bool:
    """A persisted choice counts as configured only when it can produce a provider.

    openai_compatible without an endpoint is a half-written choice: the provider
    resolver cannot build it, so the gate must show the setup page instead of a
    chat that can only report Disconnected.
    """
    if choice is None or not str(choice.model or "").strip():
        return False
    if choice.provider == OPENAI_COMPAT and not str(choice.api_url or "").strip():
        return False
    return True


def _setup_provider_dict() -> dict:
    """Active engine + reachability status for the setup UI.

    R25 (perceived latency, 2026-10-14): the reachability half of this answer used to cost a
    fresh upstream round trip on *every* call — measured on the real engine, the
    synchronous `_probe_remote` (GET {engine}/v1/models, new TLS handshake each time)
    took 316-533 ms while `_setup_candidates()` beside it took 0.1 ms. That number sat on
    the PWA's first-paint path, because the app gated its first render on this route.

    The answer is a discovery aid. `configured`/`skipped` come from the local engine.json and
    do not change under the user's hands, and the live engine truth has its own home in
    `GET /api/health` (measured 3-14 ms, polled every 10 s). So the probe result is memoised
    for `_SETUP_PROBE_TTL_S` — a reload, a second mount or a route change no longer re-pays
    it, and the app stops waiting on an upstream round trip to be told something a file
    already says.
    """
    persisted = load_engine_config()
    active = get_active_provider()
    provider = persisted.provider if persisted else active.provider
    model = persisted.model if (persisted and persisted.model) else active.model
    url = persisted.api_url if persisted else (active.base_url if active.provider == "openai_compatible" else None)
    reachable, available_models = _probe_memoised(provider, url)
    complete = _engine_choice_is_complete(persisted)
    # T2: a stored key for another engine keeps the setup screen open. The state is
    # re-read on every call, so re-entering the key or restoring the bound engine
    # clears it here.
    from core.engine_config import engine_key_repair_state

    repair = engine_key_repair_state()
    if repair is not None:
        complete = False
    incomplete = persisted is not None and not complete
    return {
        "configured": complete,
        # A deliberate skip with no engine at all still opens the chat (which
        # stays fail-closed). A half-written persisted engine is different: it
        # leaves nothing usable to skip to, so the setup page stays reachable.
        "skipped": _setup_skipped() and not incomplete,
        "provider": provider,
        "model": model,
        "url": url,
        "reachable": reachable,
        "available_models": available_models,
        "candidates": _setup_candidates(),
        "repair": repair,
    }


#: How long an engine probe keeps its answer for the setup status.
#:
#: Bound to the same order as the app's own engine poll (10 s, see `chat/model.ts`), so the
#: cached value is never staler than the reading the shell already shows in its status bar.
#: It exists to collapse *repeats*: `_setup_skipped()`/`configured` are read fresh on every
#: call.
_SETUP_PROBE_TTL_S = 10.0
_setup_probe_cache: dict[str, tuple[float, bool, list[str]]] = {}


def _probe_memoised(provider: str, url: str | None) -> tuple[bool, list[str]]:
    """`_probe_local`/`_probe_remote` behind a TTL — the 320 ms round trip, once."""
    import time

    key = f"{provider}|{url or ''}"
    now = time.monotonic()
    hit = _setup_probe_cache.get(key)
    if hit is not None and now - hit[0] < _SETUP_PROBE_TTL_S:
        return hit[1], hit[2]
    if provider in ("local_ollama", "custom_ollama"):
        reachable, models = _probe_local(provider, url)
    elif provider == "openai_compatible" and url:
        reachable, models = _probe_remote(url)
    else:
        return False, []
    _setup_probe_cache[key] = (now, reachable, list(models))
    return reachable, models


def _probe_local(provider: str, url: str | None):
    """Synchronous Ollama probe (for the status call without an async context)."""
    import urllib.request

    base = (url or ("http://127.0.0.1:11434" if provider == "local_ollama" else "")).strip()
    if base and not base.startswith(("http://", "https://")):
        base = f"http://{base}"
    base = base.rstrip("/")
    try:
        with urllib.request.urlopen(f"{base}/api/tags", timeout=4.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        names = [str(m.get("name") or "") for m in data.get("models", []) if m.get("name")]
        return True, names
    except Exception:
        return False, []


def _probe_remote(url: str):
    """Synchronous OpenAI-compatible probe (GET /v1/models)."""
    import urllib.request

    base = url.strip().rstrip("/")
    if not base.startswith(("http://", "https://")):
        base = f"http://{base}"
    if base.endswith("/v1"):
        base = base[:-3]
    headers = {}
    from core.engine_config import engine_api_key_for

    key = engine_api_key_for(url)
    if key:
        headers["Authorization"] = f"Bearer {key}"
    try:
        req = urllib.request.Request(f"{base}/v1/models", headers=headers)
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ids = [str(m.get("id") or "") for m in data.get("data", []) if m.get("id")]
        return True, ids
    except Exception:
        return False, []


@router.get("/setup/status")
def get_setup_status() -> dict:
    """Reports whether the user has already chosen an engine.

    configured=True  → engine.json exists → the PWA goes straight into the chat.
    configured=False → the PWA shows the engine choice (end-user choice).
    reachable/available_models are a bonus: the PWA can offer the detected
    models directly as a choice (e.g. all local Ollama models).

    R25: deliberately a **sync** handler. The body is a synchronous urllib probe on a cold
    cache (see `_probe_memoised`), and as an `async def` that probe ran on the event loop —
    so one app load froze every other in-flight request for the probe's 320 ms, a streamed
    answer included. FastAPI runs a `def` handler in the threadpool instead, which is what
    a blocking probe needs.
    """
    return _setup_provider_dict()


@router.get("/setup/detect")
async def detect_setup_engines() -> dict:
    """Parallel auto scan of all engine candidates (Ollama + OpenAI-compatible).

    P3 (2026-09-15): one scan over all known endpoints — the persisted
    ``engine.json``, the local Ollama default, env URLs. Per candidate it returns
    ``{provider, url, reachable, models, state}`` and the index of the first
    reachable candidate with at least one model. No persist, no
    pull — pure discovery. Drives the re-scan button of the setup page.
    """
    from core.model_probe import probe_ollama

    candidates = _setup_candidates()

    async def _one(cand: dict) -> dict:
        provider = str(cand.get("provider") or "")
        url = cand.get("url")
        # The port hint ("typisch für …") stays with the hit — the setup line  # language-gate: ignore (quotes the shipped hint text settings.py:393 really sends)
        # thereby says what the user probably has running, without asserting it.
        hint = str(cand.get("hint") or "")
        code = str(cand.get("hint_code") or "")
        if provider in ("local_ollama", "custom_ollama"):
            ok, models, detail, state = await probe_ollama(url)
            return {
                "provider": provider,
                "url": url,
                "reachable": bool(ok),
                "models": models,
                "detail": detail,
                "state": state,
                "hint": hint,
                "hint_code": code,
            }
        if provider == "openai_compatible" and url:
            res = await _probe_openai_auto(str(url), allow_siblings=not cand.get("sweep"))
            return {
                "provider": provider,
                "url": res["url"],
                "reachable": res["reachable"],
                "models": res["models"],
                "detail": res["detail"],
                "state": res["state"],
                "hint": hint or str(res.get("hint") or ""),
                "hint_code": code or str(res.get("hint_code") or ""),
                "key_source": res.get("key_source"),
            }
        return {
            "provider": provider,
            "url": url,
            "reachable": False,
            "models": [],
            "detail": "no url",
            "state": "unreachable",
            "hint": hint,
            "hint_code": code,
        }

    detected = list(await asyncio.gather(*[_one(c) for c in candidates])) if candidates else []
    first = next(
        (i for i, r in enumerate(detected) if r["reachable"] and r["models"]),
        -1,
    )
    return {"candidates": candidates, "detected": detected, "first_reachable": first}


@router.post("/setup/skip")
async def skip_setup() -> dict:
    """W19: deliberately skip onboarding — no silent engine default.

    The user gets into the PWA (the chat stays fail-closed: /api/chat answers
    409 setup_required until an engine is chosen), and the setup gate
    does not come back on reloads. The setup page when called again: reachable at
    any time through the engine chip menu.
    """
    import datetime as _dt

    f = _setup_skip_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(
        json.dumps({"skipped": True, "skipped_at": _dt.datetime.now(_dt.timezone.utc).isoformat()}),
        encoding="utf-8",
    )
    return {"configured": False, "skipped": True}


@router.post("/setup/reset")
async def reset_setup() -> dict:
    """Deletes the engine choice (engine.json) — the user chooses again.

    Session-locally the current provider stays active until a new one is chosen.
    The skip marker falls away with it: after the reset the gate decides again.
    """
    clear_engine_config()
    _clear_setup_skip()
    return {"configured": False, "skipped": False}


# R16: image endpoint settings (settings UI → image.json)

class ImageSettingsRequest(BaseModel):
    base_url: str = ""
    model: str = ""
    # api_key=None → keep the existing key; "" → delete (UI semantics).
    api_key: str | None = None


def _image_settings_payload() -> dict:
    from core.image_config import load_image_config

    cfg = load_image_config()
    return {
        "base_url": cfg.base_url,
        "model": cfg.model,
        "has_api_key": bool(cfg.api_key),
        # Never the plaintext key — only a hint about WHICH key is set.
        "api_key_hint": f"…{cfg.api_key[-4:]}" if len(cfg.api_key) >= 4 else ("gesetzt" if cfg.api_key else ""),
    }


@router.get("/settings/image")
async def get_image_settings() -> dict:
    return _image_settings_payload()


@router.put("/settings/image")
async def update_image_settings(request: ImageSettingsRequest) -> dict:
    from core.image_config import save_image_config

    try:
        save_image_config(
            base_url=request.base_url,
            model=request.model,
            api_key=request.api_key,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _image_settings_payload()


@router.post("/settings/image/test")
async def test_image_endpoint() -> dict:
    """Cheap probe of the effective image endpoint: GET {base}/models.

    "reachable" means: an OpenAI-compatible server answers — no proof
    that images can be generated. That costs a real generation;
    the honest answer to it stays the first generate_image run.
    """
    import httpx

    from core.tools.image_tools import _image_endpoint

    base, key, _ = _image_endpoint()
    if not base:
        return {"reachable": False, "models": [], "base_url_used": "", "detail": "Kein Endpunkt konfiguriert"}
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, connect=4.0)) as client:
            resp = await client.get(f"{base.rstrip('/')}/models", headers=headers)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        # The exception is for the log below. The surface gets a fixed sentence.
        logger.warning("image endpoint probe failed: %s", exc, exc_info=True)
        return {"reachable": False, "models": [], "base_url_used": base, "detail": "endpoint not reachable"}
    models = [item.get("id", "") for item in (data or {}).get("data", []) if isinstance(item, dict)]
    return {"reachable": True, "models": models, "base_url_used": base, "detail": "OK"}


# R18: voice settings (TTS engine/STT) → voice.json

class VoiceSettingsRequest(BaseModel):
    tts_engine: str | None = None
    piper_voice: str | None = None
    edge_voice: str | None = None
    stt_model: str | None = None
    stt_language: str | None = None
    stt_allow_download: bool | None = None


def _voice_settings_payload() -> dict:
    from core.voice_config import load_voice_config, piper_binary_available, list_installed_piper_voices
    from core.transcribe import model_is_cached

    cfg = load_voice_config()
    return {
        "tts_engine": cfg.tts_engine,
        "piper_voice": cfg.piper_voice,
        "edge_voice": cfg.edge_voice,
        "stt_model": cfg.stt_model,
        "stt_language": cfg.stt_language,
        # The download consent and whether the model it would fetch is already
        # here — a surface shows the switch next to what is still missing.
        "stt_allow_download": cfg.stt_allow_download,
        "stt_model_cached": model_is_cached(cfg.stt_model),
        "piper_available": piper_binary_available(),
        "installed_piper_voices": list_installed_piper_voices(),
    }


@router.get("/settings/voice")
async def get_voice_settings() -> dict:
    return _voice_settings_payload()


@router.put("/settings/voice")
async def update_voice_settings(request: VoiceSettingsRequest) -> dict:
    from core.voice_config import save_voice_config

    payload = {k: v for k, v in request.model_dump().items() if v is not None}
    try:
        save_voice_config(**payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _voice_settings_payload()


# R23: the /settings/security route, carrying the approval profile and the shell sandbox

class SecuritySettingsRequest(BaseModel):
    approval_profile: str | None = None
    sandbox_enabled: bool | None = None
    # Wave 2/B3: categories the user wants a prompt for every time. Only the two
    # that auto-run are accepted, and an absent list leaves the stored one alone.
    ask_categories: list[str] | None = None


def _security_settings_payload() -> dict:
    from core.security_config import load_security_config

    cfg = load_security_config()
    return {
        "approval_profile": cfg.approval_profile,
        "sandbox_enabled": cfg.sandbox_enabled,
        "ask_categories": list(cfg.ask_categories),
    }


@router.get("/settings/security")
async def get_security_settings() -> dict:
    return _security_settings_payload()


@router.put("/settings/security")
async def update_security_settings(request: SecuritySettingsRequest) -> dict:
    from core.security_config import save_security_config

    try:
        save_security_config(
            approval_profile=request.approval_profile,
            sandbox_enabled=request.sandbox_enabled,
            ask_categories=request.ask_categories,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _security_settings_payload()


# R23 error path: secrets do not belong in user-visible errors.


# R28: Agent Identity — persona editor

class PersonaUpdateRequest(BaseModel):
    text: str


@router.get("/settings/persona")
async def get_persona() -> dict:
    """Current agent persona (identity stays generated — persona is editable)."""
    from core.persona import persona_source, load_persona_for_editor

    return {"source": persona_source(), "text": load_persona_for_editor()}


@router.put("/settings/persona")
async def put_persona(req: PersonaUpdateRequest) -> dict:
    from core.persona import (
        load_persona_for_editor,
        persona_source,
        write_persona,
    )

    if len(req.text) > 8_000:
        raise HTTPException(status_code=413, detail="Persona exceeds 8000 characters.")
    try:
        write_persona(req.text)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    return {"source": persona_source(), "text": load_persona_for_editor()}


# R40 (Z44): MCP server attachment (settings UI → mcp.json; env has precedence)

class McpSettingsRequest(BaseModel):
    servers: list[str] = []


_ALLOWED_MCP_PREFIXES = ("http://", "https://", "stdio:")


def _mcp_settings_payload() -> dict:
    from core.mcp_config import load_mcp_servers
    from core.tools.mcp_client import mcp_tool_names

    servers, source = load_mcp_servers()
    return {"servers": servers, "source": source, "tools": mcp_tool_names()}


@router.get("/settings/mcp")
async def get_mcp_settings() -> dict:
    return _mcp_settings_payload()


@router.put("/settings/mcp")
async def put_mcp_settings(req: McpSettingsRequest) -> dict:
    """Persists the server list and re-syncs the remote tools.

    Only the spec formats http(s)://… / stdio:… (the parse_server mirror); otherwise 422.
    """
    from core.mcp_config import init_mcp_from_config, save_mcp_servers

    for entry in req.servers:
        if not str(entry).startswith(_ALLOWED_MCP_PREFIXES):
            raise HTTPException(
                status_code=422,
                detail=f"MCP spec must start with http://, https:// or stdio: (got '{entry}').",
            )
    save_mcp_servers(list(req.servers))
    await init_mcp_from_config(specs=list(req.servers))
    return _mcp_settings_payload()


# Wave E1: code execution — the effective cell policy (read-only)

@router.get("/settings/code-exec")
async def get_code_exec_policy() -> dict:
    """What the runtime REALLY enforces when the model executes Python.

    Read-only and secret-free (only caps, version, license, measured cost):
    the settings page may not assert anything `core.cpython_cell` does not write
    into its WASIConfig — report == enforced, the numbers come from
    `core.cell_policy`. The opt-out path is called `EPHE_CODE_EXEC=kernel` and
    stays what it is: unsandboxed.
    """
    from core import cell_policy

    return cell_policy.policy_snapshot()
