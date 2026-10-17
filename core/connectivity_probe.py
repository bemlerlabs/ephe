"""
◑ Ephe – Connectivity Probe
core/connectivity_probe.py

Checks within at most PROBE_TIMEOUT seconds whether local Ollama and/or
the DGX remote server are reachable.

Contains a TTL cache (CACHE_TTL seconds) so that rapid successive calls
do not produce network overhead.

Ephe – Bad Liebenzell, Black Forest
"""
from __future__ import annotations

import asyncio
import time

import ollama

from core.model_config import ModelTier

PROBE_TIMEOUT: float = 2.0   # seconds until timeout
CACHE_TTL:     float = 10.0  # seconds the cache stays valid


class ConnectivityProbe:
    """
    Checks the reachability of local Ollama and the DGX remote server.

    Example:
        probe = ConnectivityProbe(dgx_host="192.168.1.50:11434")
        tier  = await probe.best_available_tier()
        # → ModelTier.POWER when the DGX is reachable
    """

    def __init__(self, dgx_host: str | None = None) -> None:
        self._dgx_host = dgx_host

        # TTL cache for check_local
        self._local_cache_result: bool | None = None
        self._local_cache_time:   float       = 0.0

        # TTL cache for check_remote
        self._remote_cache_result: bool | None = None
        self._remote_cache_time:   float       = 0.0

    # Local Ollama

    async def check_local(self) -> bool:
        """
        Checks whether the local Ollama server is reachable.
        The result is cached for CACHE_TTL seconds.

        Returns:
            True when reachable, False on any error.
        """
        now = time.monotonic()
        if (
            self._local_cache_result is not None
            and (now - self._local_cache_time) < CACHE_TTL
        ):
            return self._local_cache_result

        result = await self._probe_host(host=None)  # None = localhost default
        self._local_cache_result = result
        self._local_cache_time   = now
        return result

    # Remote / DGX

    async def check_remote(self, host: str | None = None) -> bool:
        """
        Checks whether a remote Ollama server (e.g. DGX) is reachable.
        Uses the host parameter or the configured DGX host.
        The result is cached for CACHE_TTL seconds.

        Args:
            host: optional override, e.g. "10.0.0.1:11434"

        Returns:
            True when reachable, False when unconfigured or on error.
        """
        effective_host = host or self._dgx_host
        if not effective_host:
            return False  # No DGX configured → False right away

        now = time.monotonic()
        # Use the cache only for the configured default host
        if host is None:
            if (
                self._remote_cache_result is not None
                and (now - self._remote_cache_time) < CACHE_TTL
            ):
                return self._remote_cache_result

        result = await self._probe_host(host=effective_host)

        if host is None:
            self._remote_cache_result = result
            self._remote_cache_time   = now

        return result

    # Tier decision

    async def best_available_tier(self) -> ModelTier:
        """
        Decides the best available tier automatically:
          - POWER   when DGX + local are reachable
          - FAST    when only local is reachable
          - OFFLINE when nothing is reachable

        Returns:
            ModelTier: the best available tier
        """
        local_ok  = await self.check_local()
        remote_ok = await self.check_remote()

        if local_ok and remote_ok:
            return ModelTier.POWER
        if local_ok:
            return ModelTier.FAST
        return ModelTier.OFFLINE

    # Internal helper

    async def _probe_host(self, host: str | None) -> bool:
        """
        Runs the actual Ollama .list() call.

        Args:
            host: None for localhost, otherwise "ip:port"

        Returns:
            True on success, False on any error.
        """
        try:
            if host:
                client = ollama.AsyncClient(host=f"http://{host}")
            else:
                client = ollama.AsyncClient()

            await asyncio.wait_for(client.list(), timeout=PROBE_TIMEOUT)
            return True
        except Exception:
            return False
