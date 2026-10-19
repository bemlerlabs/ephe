"""The engine probes: what an endpoint answers about itself, and with which token.

Split out of `server/routes/model_provider.py` on 2026-10-18 (the route is the HTTP
shape; this is the network half). Two rules live here and nowhere else: the Ollama and
OpenAI-compatible checks are metadata requests, never chat turns, and the token a probe
authenticates with is resolved by `resolve_probe_key` in one order that the surface
reports back as `key_source`.
"""
from __future__ import annotations

import httpx
from pathlib import Path

from core.model_metadata import names_of


async def probe_ollama(base_url: str | None) -> tuple[bool, list[str], str, str]:
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


def mirror_api_key(base_url: str, home: Path | None = None) -> str | None:
    """Key fallback from the configs of the detected tools (read-only, local).

    Root cause: the probe only had EPHE_OPENAI_COMPAT_API_KEY — a user whose key
    lived in another tool's auth file (subscription/free plan) still got HTTP 401.
    The models.dev-shaped cache maps provider-id → api-URL, and that tool's
    auth.json holds the key per provider-id.

    Scope, owner decision 2026-10-10: this is the only remaining read of that store
    and it authenticates a `/models` probe, nothing else. The engine itself stopped
    falling back to it the same day (engine_api_key_for);
    a chat turn is keyed by the env variable or `~/.ephe/engine.key` or not at all.

    Kept, owner decision 2026-10-18: onboarding is where it pays — a user who has a
    working subscription next to Ephe sees their models instead of a 401 — and the
    same decision requires that the surface says so. `resolve_probe_key` reports it as
    ``foreign`` and nothing here stores, copies or logs the token.
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


def resolve_probe_key(
    base_url: str | None, supplied: str | None = None, home: Path | None = None
) -> tuple[str | None, str]:
    """The token a probe would use for this endpoint, and which source it came from.

    ``given`` — the key that came with this request, ``own`` — Ephe's own store
    (`EPHE_OPENAI_COMPAT_API_KEY`, the keychain, `~/.ephe/engine.key`), ``foreign`` — the
    onboarding mirror, ``none``. ``foreign`` is said out loud because "your key worked" and
    "a key we found next to it worked" are two answers, and only the first means the engine
    still answers after onboarding: a chat turn reads ``own`` and nothing else. One order in
    one function, so a surface asking before the probe gets the source the probe acts on.
    """
    given = (supplied or "").strip()
    if given:
        return given, "given"
    from core.engine_config import engine_api_key_for

    own = engine_api_key_for(base_url, home=home)
    if own:
        return own, "own"
    borrowed = mirror_api_key(base_url or "", home=home)
    if borrowed:
        return borrowed, "foreign"
    return None, "none"


async def probe_openai_models(
    base_url: str, api_key: str | None
) -> tuple[bool, list[object], str, str]:
    """OpenAI-compatible engine check: GET {base}/v1/models, entries as the engine wrote them.

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
    api_key, _source = resolve_probe_key(base_url, api_key)
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base}/v1/models", headers=headers)
            resp.raise_for_status()
            data = resp.json()
        entries = (data.get("data", []) if isinstance(data, dict) else []) or []
        if not isinstance(entries, list):
            entries = []
        count = len(names_of(entries))
        return True, entries, f"{base} reachable · {count} model(s)", "ok"
    except httpx.TimeoutException:
        return False, [], f"{base} did not answer in time (busy)", "busy"
    except httpx.HTTPStatusError as exc:
        return False, [], f"{base} responds with HTTP {exc.response.status_code}", "unreachable"
    except Exception:
        return False, [], f"{base} not reachable", "unreachable"


async def probe_openai_compatible(base_url: str, api_key: str | None) -> tuple[bool, list[str], str, str]:
    """The id list alone — the shape every existing caller and test double already holds."""
    ok, entries, detail, state = await probe_openai_models(base_url, api_key)
    return ok, names_of(entries), detail, state
