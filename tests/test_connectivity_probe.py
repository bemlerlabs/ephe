"""
◑ Ephe – test_connectivity_probe.py

TDD tests for core/connectivity_probe.py

Given / When / Then — three levels of depth coverage:
  depth 1: check_local() — the local Ollama check
  depth 2: check_remote() — the DGX check with a timeout
  depth 3: best_available_tier() — automatic tier decision + cache
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# Depth 1: check_local()

class TestCheckLocal:
    """GIVEN check_local() probes the local Ollama server"""

    async def test_returns_true_when_ollama_reachable(self):
        """WHEN the local Ollama answers
        THEN check_local() returns True"""
        from core.connectivity_probe import ConnectivityProbe
        probe = ConnectivityProbe()
        list_response = MagicMock()
        list_response.models = []
        with patch("core.connectivity_probe.ollama.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.list = AsyncMock(return_value=list_response)
            mock_cls.return_value = instance
            result = await probe.check_local()
        assert result is True

    async def test_returns_false_when_connection_refused(self):
        """WHEN Ollama is not running (ConnectionRefusedError)
        THEN check_local() returns False — no exception crash"""
        from core.connectivity_probe import ConnectivityProbe
        probe = ConnectivityProbe()
        with patch("core.connectivity_probe.ollama.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.list.side_effect = ConnectionRefusedError("refused")
            mock_cls.return_value = instance
            result = await probe.check_local()
        assert result is False

    async def test_returns_false_on_timeout(self):
        """WHEN Ollama does not answer (timeout)
        THEN check_local() returns False"""
        from core.connectivity_probe import ConnectivityProbe
        probe = ConnectivityProbe()
        with patch("core.connectivity_probe.ollama.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.list.side_effect = asyncio.TimeoutError()
            mock_cls.return_value = instance
            result = await probe.check_local()
        assert result is False

    async def test_returns_false_on_any_exception(self):
        """WHEN an unknown error occurs
        THEN check_local() returns False (defensive)"""
        from core.connectivity_probe import ConnectivityProbe
        probe = ConnectivityProbe()
        with patch("core.connectivity_probe.ollama.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.list.side_effect = RuntimeError("unexpected!")
            mock_cls.return_value = instance
            result = await probe.check_local()
        assert result is False


# Depth 2: check_remote()

class TestCheckRemote:
    """GIVEN check_remote() probes the remote DGX server"""

    async def test_returns_true_when_dgx_reachable(self):
        """WHEN the DGX host is reachable
        THEN check_remote() returns True"""
        from core.connectivity_probe import ConnectivityProbe
        probe = ConnectivityProbe(dgx_host="192.168.1.50:11434")
        list_response = MagicMock()
        list_response.models = []
        with patch("core.connectivity_probe.ollama.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.list = AsyncMock(return_value=list_response)
            mock_cls.return_value = instance
            result = await probe.check_remote()
        assert result is True

    async def test_returns_false_when_dgx_not_reachable(self):
        """WHEN the DGX host is unreachable (timeout)
        THEN check_remote() returns False"""
        from core.connectivity_probe import ConnectivityProbe
        probe = ConnectivityProbe(dgx_host="dgx.local:11434")
        with patch("core.connectivity_probe.ollama.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.list.side_effect = asyncio.TimeoutError()
            mock_cls.return_value = instance
            result = await probe.check_remote()
        assert result is False

    async def test_returns_false_when_no_dgx_host_configured(self):
        """WHEN no DGX host is configured
        THEN check_remote() returns False immediately (no network call)"""
        from core.connectivity_probe import ConnectivityProbe
        probe = ConnectivityProbe(dgx_host=None)
        with patch("core.connectivity_probe.ollama.AsyncClient") as mock_cls:
            result = await probe.check_remote()
            mock_cls.assert_not_called()
        assert result is False

    async def test_uses_explicit_host_parameter(self):
        """WHEN host='10.0.0.1:11434' is passed directly
        THEN that host is used instead of the configured DGX host"""
        from core.connectivity_probe import ConnectivityProbe
        probe = ConnectivityProbe(dgx_host="default.host:11434")
        list_response = MagicMock()
        list_response.models = []
        captured_host = []
        with patch("core.connectivity_probe.ollama.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.list = AsyncMock(return_value=list_response)
            mock_cls.return_value = instance
            def capture_host(**kwargs):
                captured_host.append(kwargs.get("host", ""))
                return instance
            mock_cls.side_effect = capture_host
            await probe.check_remote(host="10.0.0.1:11434")
        assert any("10.0.0.1:11434" in h for h in captured_host)


# Depth 3: best_available_tier()

class TestBestAvailableTier:
    """GIVEN best_available_tier() picks the best tier automatically"""

    async def test_offline_when_nothing_available(self):
        """GIVEN local Ollama + DGX both unreachable
        WHEN best_available_tier() is called
        THEN it returns ModelTier.OFFLINE"""
        from core.connectivity_probe import ConnectivityProbe
        from core.model_config import ModelTier
        probe = ConnectivityProbe()
        with patch.object(probe, "check_local", return_value=False), \
             patch.object(probe, "check_remote", return_value=False):
            tier = await probe.best_available_tier()
        assert tier == ModelTier.OFFLINE

    async def test_fast_when_only_local_available(self):
        """GIVEN only the local Ollama is reachable
        WHEN best_available_tier() is called
        THEN it returns ModelTier.FAST"""
        from core.connectivity_probe import ConnectivityProbe
        from core.model_config import ModelTier
        probe = ConnectivityProbe()
        with patch.object(probe, "check_local", return_value=True), \
             patch.object(probe, "check_remote", return_value=False):
            tier = await probe.best_available_tier()
        assert tier == ModelTier.FAST

    async def test_power_when_both_available(self):
        """GIVEN local Ollama + DGX both reachable
        WHEN best_available_tier() is called
        THEN it returns ModelTier.POWER"""
        from core.connectivity_probe import ConnectivityProbe
        from core.model_config import ModelTier
        probe = ConnectivityProbe(dgx_host="dgx.local:11434")
        with patch.object(probe, "check_local", return_value=True), \
             patch.object(probe, "check_remote", return_value=True):
            tier = await probe.best_available_tier()
        assert tier == ModelTier.POWER

    async def test_ttl_cache_prevents_double_network_call(self):
        """GIVEN check_local() was already called
        WHEN check_local() is called again inside the TTL window
        THEN no second network call is made"""
        from core.connectivity_probe import ConnectivityProbe
        probe = ConnectivityProbe()
        call_count = 0

        async def fake_list():
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.models = []
            return resp

        with patch("core.connectivity_probe.ollama.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.list = fake_list
            mock_cls.return_value = instance
            await probe.check_local()
            await probe.check_local()  # second call — should use the cache

        assert call_count == 1, "Cache hat nicht funktioniert — 2 Netzwerkaufrufe!"

    async def test_cache_invalidated_after_ttl(self):
        """GIVEN the TTL cache has expired (simulated)
        WHEN check_local() is called again
        THEN a new network call is made"""
        from core.connectivity_probe import ConnectivityProbe
        probe = ConnectivityProbe()

        # Mark the cache as expired manually
        probe._local_cache_result = True
        probe._local_cache_time = 0.0  # epoch = always expired

        call_count = 0
        resp = MagicMock()
        resp.models = []
        with patch("core.connectivity_probe.ollama.AsyncClient") as mock_cls:
            instance = AsyncMock()
            instance.list = AsyncMock(return_value=resp)
            mock_cls.return_value = instance
            await probe.check_local()
            call_count = instance.list.call_count

        assert call_count == 1, "Nach TTL-Ablauf sollte neu geprüft werden"
