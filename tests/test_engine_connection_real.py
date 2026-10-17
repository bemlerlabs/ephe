"""Engine connection: REAL integration (no mock, no fake).

The root-cause fix under test: check_engine_connection() uses the light
``/v1/models`` metadata endpoint (~100ms) instead of a full LLM chat request.
A 27B model (Qwen 3.8 on vLLM/DGX) needs 5-15s of TTFB for the first
inference — the old chat ping with a 3s timeout was a false
negative on every start → the TUI wrongly showed "is not installed locally".

Rule of this project: deployment readiness = real tests. Therefore:
- Local: a REAL HTTP server (http.server, a real socket on 127.0.0.1)
  with a real /v1/models handler — no mock, no fake client.
- Offline: a REAL connection refusal (a port nothing listens on).
- Live engine: a REAL network call to the vLLM instance configured through the env
  (skip without env configuration or on physical unreachability — otherwise
  it is checked for real). Endpoint/model come from EPHE_DGX_BASE /
  EPHE_DGX_MODEL, so no private hostname sits in the repo.
"""
from __future__ import annotations

import os
import socket
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from core.chat import check_engine_connection

# W18: the live endpoint comes from the env only — the repo holds neither
# a private hostname nor a model literal. No env → SKIP.
LIVE_BASE = (os.environ.get("EPHE_DGX_BASE") or "").strip().rstrip("/")
LIVE_MODEL = (os.environ.get("EPHE_DGX_MODEL") or "").strip()


# Real local HTTP server (real socket, real HTTP stack)

class _ModelsHandler(BaseHTTPRequestHandler):
    """Real /v1/models handler. Recorded paths = the real server page."""

    model_payload: list[str] = ["qwen38-27b-unsloth-nvfp4"]
    recorded_paths: list[str] = []

    def do_GET(self) -> None:  # noqa: N802 (http.server-API)
        type(self).recorded_paths.append(self.path)
        if self.path == "/v1/models":
            import json

            body = json.dumps({"object": "list", "data": [
                {"id": m, "object": "model"} for m in type(self).model_payload
            ]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args) -> None:  # quieter (http.server signature)
        pass


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _start_real_models_server(model_payload: list[str]) -> tuple[HTTPServer, int, list[str]]:
    """Starts a real HTTP server and returns (server, port, recorded)."""
    handler = type(
        "_Handler",
        (_ModelsHandler,),
        {"model_payload": list(model_payload), "recorded_paths": []},
    )
    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    # Real readiness check (real TCP+HTTP) until the server answers.
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=1.0)
            break
        except Exception:
            time.sleep(0.1)
    return server, port, handler.recorded_paths


async def test_real_v1_models_returns_connected_and_model_list():
    """GIVEN a real vLLM server (real HTTP) listing the Qwen model
    WHEN check_engine_connection
    THEN connected=True + the real model list (no mock)."""
    server, port, _ = _start_real_models_server(["qwen38-27b-unsloth-nvfp4"])
    try:
        connected, status, available = await check_engine_connection(
            f"http://127.0.0.1:{port}/v1", "qwen38-27b-unsloth-nvfp4"
        )
    finally:
        server.shutdown()
    assert connected is True
    assert "connected" in status
    assert "qwen38-27b-unsloth-nvfp4" in available


async def test_v1_suffix_stripped_real_server():
    """GIVEN an api_url with the /v1 suffix (typical for vLLM)
    WHEN check
    THEN the REAL server request is /v1/models (not /v1/v1/models)."""
    server, port, recorded = _start_real_models_server(["m1"])
    try:
        connected, _, _ = await check_engine_connection(f"http://127.0.0.1:{port}/v1", "m1")
    finally:
        server.shutdown()
    assert connected is True
    assert "/v1/models" in recorded, f"Server sah: {recorded}"
    assert "/v1/v1/models" not in recorded


async def test_real_server_other_models_still_connected():
    """GIVEN a real server with a different model
    THEN connected=True (engine reachable) + a list for the UI banner."""
    server, port, _ = _start_real_models_server(["other-model"])
    try:
        connected, status, available = await check_engine_connection(
            f"http://127.0.0.1:{port}/v1", "qwen38-27b-unsloth-nvfp4"
        )
    finally:
        server.shutdown()
    assert connected is True
    assert "not listed in /v1/models" in status
    assert available == ["other-model"]


async def test_real_closed_port_is_offline():
    """GIVEN a port where nothing really listens
    THEN connected=False + offline (a real connection refusal)."""
    dead = _free_port()  # not bound → a real refusal
    connected, status, _ = await check_engine_connection(f"http://127.0.0.1:{dead}/v1", "m")
    assert connected is False
    assert status == "offline"


# Real DGX (deployment endpoint, real network call)

def _dgx_reachable(timeout: float = 2.0) -> bool:
    """Real TCP check of whether the configured live engine is physically reachable."""
    from urllib.parse import urlparse

    if not (LIVE_BASE and LIVE_MODEL):
        return False
    parsed = urlparse(LIVE_BASE)
    try:
        with socket.create_connection((parsed.hostname, parsed.port or 8000), timeout=timeout):
            return True
    except Exception:
        return False


async def test_real_engine_v1_models_lists_configured_model():
    """REAL deployment test: the vLLM instance configured through the env has to deliver
    its active model. Skip without env configuration or on physical
    unreachability — that is an infrastructure state, not a test fake."""
    if not _dgx_reachable():
        pytest.skip(
            "Keine Live-Engine konfiguriert/erreichbar — setze EPHE_DGX_BASE + "
            "EPHE_DGX_MODEL (+ EPHE_DGX_KEY) und prüfe den Endpoint."
        )
    connected, status, available = await check_engine_connection(LIVE_BASE, LIVE_MODEL)
    assert connected is True
    assert LIVE_MODEL in available, (
        f"Engine listet das aktive Modell nicht: {available}"
    )
