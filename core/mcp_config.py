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


def load_mcp_servers() -> tuple[list[str], str]:
    """Effective server list + source ('env' | 'file' | 'none')."""
    import os

    env_raw = (os.environ.get("EPHE_MCP_SERVERS") or "").strip()
    if env_raw:
        servers = [part.strip() for part in env_raw.split(",") if part.strip()]
        if servers:
            return servers, "env"
    try:
        raw = json.loads(mcp_config_path().read_text(encoding="utf-8"))
        entries = raw.get("servers") if isinstance(raw, dict) else None
        if isinstance(entries, list):
            servers = [str(e).strip() for e in entries if str(e).strip()]
            if servers:
                return servers, "file"
    except Exception:
        pass
    return [], "none"


def save_mcp_servers(servers: list[str], path=None) -> list[str]:
    """Atomic write (0600). Returns the list as it was stored."""
    cleaned = [str(s).strip() for s in (servers or []) if str(s).strip()]
    target = path or mcp_config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.parent.chmod(0o700)
    except OSError:
        pass
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps({"servers": cleaned}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(target)
    try:
        target.chmod(0o600)
    except OSError:
        pass
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
    set_mcp_servers(specs)
    try:
        return list(await sync_mcp_tools())
    except Exception:
        return []
