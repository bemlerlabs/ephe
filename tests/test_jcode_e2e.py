"""
◑ Ephe – Phase 3 Item 14: JCode/Codex/OpenCode as consumer of the engine (e2e)
tests/test_jcode_e2e.py

Proves the OpenAI interop demonstration: a real coding CLI binary (jcode, Rust)
consumes the local Ephe serve engine through its /v1 API.

Deterministic & offline:
  - The engine runs on a fake backend (no real Ollama/DS4 needed).
    The fake client always returns "Hello from the Black Forest".
  - jcode is isolated with a temp $HOME (writes $HOME/.jcode/config.toml,
    the user config stays untouched) and pointed as an OpenAI-compatible profile
    at the local engine (jcode provider add ephe).
  - jcode run → the answer must contain the fake engine content → proof that the
    answer came from the Ephe engine, not from a real model.

Skip when jcode is not installed (CI-friendly, like the Ollama skips).
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from unittest.mock import patch
from urllib.request import urlopen

import pytest
import uvicorn

from server.openai import create_openai_app

CHUNKS = ["Hello", " from", " the", " Black", " Forest"]
FULL = "".join(CHUNKS)

pytestmark = pytest.mark.skipif(
    shutil.which("jcode") is None, reason="jcode (Rust coding CLI) nicht installiert"
)


class FakeClient:
    """Replaces build_provider_client: always returns the same engine answer."""

    def chat(self, model, messages, stream):  # noqa: ARG002
        async def _gen():
            for chunk in CHUNKS:
                yield {"message": {"content": chunk}}

        return _gen()


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_ready(port: int, timeout: float = 15.0) -> None:
    """Polls until the engine's /v1/models endpoint answers."""
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            with urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=2) as resp:  # noqa: S310
                if resp.status == 200:
                    return
        except Exception as exc:  # noqa: BLE001
            last_err = exc
        time.sleep(0.1)
    raise AssertionError(f"Engine nicht bereit auf Port {port}: {last_err}")


def _start_engine(port: int):
    """Starts the serve engine as a real uvicorn server with a fake backend."""
    # Patch the module attribute → takes effect across threads (engine runs in the thread).
    patcher = patch("server.openai.build_provider_client", lambda *a, **k: FakeClient())
    patcher.start()
    app = create_openai_app()  # no token → localhost bind only

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    _wait_ready(port)
    return server, thread, patcher


def _jcode(args, home: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOME"] = home  # jcode reads $HOME/.jcode → temp, the user config stays clean
    return subprocess.run(
        ["jcode", *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _contains_engine_marker(text: str) -> bool:
    """Searches the jcode answer recursively for the fake engine marker."""
    if "Black Forest" in text:
        return True
    try:
        return _walk(json.loads(text))
    except Exception:  # noqa: BLE001
        return False


def _walk(node) -> bool:
    if isinstance(node, str):
        return "Black Forest" in node
    if isinstance(node, dict):
        return any(_walk(v) for v in node.values())
    if isinstance(node, list):
        return any(_walk(v) for v in node)
    return False


def test_jcode_consumes_engine_e2e():
    """jcode (Rust coding CLI) consumes the Ephe engine as an OpenAI consumer."""
    port = _free_port()
    server, server_thread, patcher = _start_engine(port)
    tmp_home = tempfile.mkdtemp(prefix="jcode-e2e-")
    try:
        base_url = f"http://127.0.0.1:{port}/v1"

        # 1) Point jcode, as an OpenAI-compatible profile, at the local engine
        add = _jcode(
            [
                "provider",
                "add",
                "ephe",
                "--base-url",
                base_url,
                "--model",
                "gemma4:12b",
                "-p",
                "openai-compatible",
            ],
            tmp_home,
        )
        assert add.returncode == 0, f"provider add fehlgeschlagen:\n{add.stderr}"

        # 2) One real `run` against the engine
        run = _jcode(
            ["run", "Antworte in einem Wort: Wo liegt der Schwarzwald?", "--provider-profile", "ephe", "--json"],
            tmp_home,
        )
        assert run.returncode == 0, f"jcode run fehlgeschlagen:\n{run.stderr}"

        # 3) Proof: the answer came from the Ephe engine (fake marker), not
        #    from a real/remote model.
        assert _contains_engine_marker(run.stdout), (
            "jcode-Antwort enthält nicht den Engine-Marker 'Black Forest' — "
            "Antwort kam nicht von der lokalen Ephe Engine.\n"
            f"stdout: {run.stdout[:500]}\nstderr: {run.stderr[:500]}"
        )
    finally:
        server.should_exit = True
        server_thread.join(timeout=5)
        patcher.stop()
        shutil.rmtree(tmp_home, ignore_errors=True)
