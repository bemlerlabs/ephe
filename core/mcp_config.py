"""Ephe – mcp_config: persistent MCP-server list (R40 / Z44).

Priority as with image.json: env (EPHE_MCP_SERVERS, comma-separated) >
~/.ephe/mcp.json. Deliberately its own file (0600, atomic): save_engine_config
throws foreign keys out of engine.json, and the spec strings are no provider
settings. Fail-tolerant: unreadable file => treated as not configured.
"""
from __future__ import annotations

import json

# Resolve through the config-dir helper at CALL time so the file follows EPHE_CONFIG_DIR
# like every other state file. Reading the import-frozen engine_config.CONFIG_DIR instead
# meant a test that set the config dir per test (after import) still wrote mcp.json — and
# its mcp.tmp sibling — into the developer's real ~/.ephe.
from core import engine_config


def mcp_config_path():
    return engine_config.config_root() / "mcp.json"


def _read() -> dict:
    try:
        raw = json.loads(mcp_config_path().read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def load_mcp_servers() -> tuple[list[str], str]:
    """Effective server list + source ('env' | 'file' | 'none')."""
    import os

    env_raw = (os.environ.get("EPHE_MCP_SERVERS") or "").strip()
    if env_raw:
        servers = [part.strip() for part in env_raw.split(",") if part.strip()]
        if servers:
            return servers, "env"
    raw = _read()
    entries = raw.get("servers")
    if isinstance(entries, list):
        servers = [str(e).strip() for e in entries if str(e).strip()]
        if servers:
            return servers, "file"
    return [], "none"


def load_server_env() -> dict[str, list[str]]:
    """Which secrets a connector may receive, keyed by the spec it was added as.

    Declared, not inferred: a server gets the names the user confirmed on its
    card, so one connector's key never reaches another connector's process."""
    raw = _read().get("env")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, list[str]] = {}
    for spec, names in raw.items():
        if isinstance(names, list):
            cleaned = [str(name).strip() for name in names if str(name).strip()]
            if cleaned:
                out[str(spec)] = cleaned
    return out


def save_server_env(spec: str, names: list[str]) -> dict[str, list[str]]:
    """Records the declared names for one connector (empty list forgets it)."""
    current = load_server_env()
    cleaned = [str(name).strip() for name in names if str(name).strip()]
    if cleaned:
        current[str(spec)] = cleaned
    else:
        current.pop(str(spec), None)
    target = mcp_config_path()
    stored = _read().get("servers")
    servers = [str(s).strip() for s in stored if str(s).strip()] if isinstance(stored, list) else []
    _write(target, servers, current)
    return current


def _write(target, servers: list[str], env_map: dict[str, list[str]]) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.parent.chmod(0o700)
    except OSError:
        pass
    tmp = target.with_suffix(".tmp")
    body = {"servers": servers, "env": env_map}
    tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)
    try:
        target.chmod(0o600)
    except OSError:
        pass


def save_mcp_servers(servers: list[str], path=None) -> list[str]:
    """Atomic write (0600). Returns the list as it was stored.

    A connector that is no longer in the list loses its declared names: a
    spec that is gone cannot have a process to hand a secret to."""
    cleaned = [str(s).strip() for s in (servers or []) if str(s).strip()]
    target = path or mcp_config_path()
    env_map = {spec: names for spec, names in load_server_env().items() if spec in cleaned}
    _write(target, cleaned, env_map)
    return cleaned


async def init_mcp_from_config(specs: list[str] | None = None) -> list[str]:
    """One-time wiring: apply the specs + synchronize the remote tools.

    Fail-tolerant: a server error only costs one row in the
    result list, never the whole run. Returns: the registered tool names.
    """
    from core.tools.mcp_client import set_mcp_servers, sync_mcp_tools

    if specs is None:
        specs, _source = load_mcp_servers()
    if not specs:
        return []
    set_mcp_servers(specs, env_map=load_server_env())
    try:
        return list(await sync_mcp_tools())
    except Exception:
        return []
