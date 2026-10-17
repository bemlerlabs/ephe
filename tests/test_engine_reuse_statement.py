"""Two processes, one truth: a backend that was not started with the token has to say so.

The measured gap (2026-10-10, the same day as `~/.ephe/engine.key`'s first slice): a
valid owner-only key file was in place, the desktop app started, found :8765 already
served, took the reuse branch (`app/src-tauri/src/backend.rs`) and the running
backend — started without any `EPHE_` variable — went on reporting
`engine_state: "ok"` with `detail: "engine reachable, model not listed"` while its
engine answered every request with 401. A reuse branch cannot hand a token to a
process it did not start (an environment is fixed at exec), so the one thing it can
do is ask that process what it sees. `app/src-tauri/src/backend.rs::statement()`
reads the field these tests pin.

Both processes are real here: a stub engine on loopback and a `run_server.py` on an
ephemeral port. A TestClient would run the same interpreter with the same environment
and prove nothing about the spawn/reuse split.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tests.subprocess_env import hermetic_env

import pytest

ROOT = subprocess.run(
    [sys.executable, "-c", "import pathlib;print(pathlib.Path.cwd().resolve())"],
    capture_output=True, text=True, check=True,
).stdout.strip()

TOKEN = "stub-token-only-this-endpoint-accepts"


class _Engine(BaseHTTPRequestHandler):
    """OpenAI-compatible /models that demands a bearer token."""

    key = TOKEN
    seen: list[str] = []

    def do_GET(self):  # noqa: N802 - http.server's name
        auth = self.headers.get("Authorization") or ""
        type(self).seen.append(auth)
        wanted = f"Bearer {type(self).key}"
        if auth == wanted:
            body = b'{"data":[{"id":"stub-model"}]}'
            status = 200
        else:
            body = b'{"error":{"message":"missing bearer token"}}'
            status = 401
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


def _free_port() -> int:
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


@pytest.fixture()
def engine():
    handler = type("BoundEngine", (_Engine,), {"seen": []})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_address[1]}/v1"
    try:
        yield url, handler
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture()
def backend_factory(engine, tmp_path):
    """Start a real backend with a clean environment, reap it in every case."""
    engine_url, _handler = engine
    (tmp_path / "engine.json").write_text(
        json.dumps({"provider": "openai_compatible", "model": "stub-model", "api_url": engine_url}),
        encoding="utf-8",
    )
    processes: list[subprocess.Popen] = []
    err_logs: list = []

    def start(**extra_env) -> int:
        port = _free_port()
        env = hermetic_env(
            PATH=os.environ.get("PATH", ""),
            HOME=str(tmp_path),
            EPHE_CONFIG_DIR=str(tmp_path),
            **extra_env,
        )
        # The child's stderr is kept rather than thrown away: an interpreter that dies at exec
        # leaves nothing but that text, and a bare exit code has cost this suite four rounds of
        # guessing (run 38070085068, three Linux legs, `code 127` with no reason attached).
        err_file = (tmp_path / f"backend-{port}.err").open("wb")
        proc = subprocess.Popen(
            [sys.executable, "run_server.py", "--port", str(port), "--host", "127.0.0.1"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=err_file,
        )
        processes.append(proc)
        err_logs.append((proc, err_file))
        for _ in range(120):
            time.sleep(0.5)
            try:
                _health(port)
                return port
            except Exception:
                if proc.poll() is not None:
                    err_file.flush()
                    detail = (tmp_path / f"backend-{port}.err").read_bytes().decode(
                        "utf-8", "replace").strip()[-400:]
                    raise RuntimeError(
                        f"backend exited early with code {proc.returncode}: {detail or 'no output'}"
                    )
        raise RuntimeError("backend did not come up")

    try:
        yield start
    finally:
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
        for proc in processes:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        for _proc, handle in err_logs:
            handle.close()


def _health(port: int) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=5) as response:
        return json.loads(response.read())


def test_a_backend_started_without_the_token_says_its_engine_refused_it(
    backend_factory, engine
):
    """The reuse case, in one process pair: no credential, endpoint demands one."""
    _url, handler = engine
    port = backend_factory()
    body = _health(port)

    assert body["active_provider"] == "openai_compatible"
    assert body["engine_online"] is False
    assert body["engine_key_challenge"] is True
    assert body["engine_key_configured"] is False
    assert "~/.ephe/engine.key" in body["detail"]
    assert "EPHE_OPENAI_COMPAT_API_KEY" in body["detail"]
    assert handler.seen and set(handler.seen) == {""}, "the probe went out without a header"


def test_the_same_endpoint_is_reachable_once_the_start_carries_the_token(
    backend_factory, engine
):
    """The spawn case: what the desktop branch does with the key file's content."""
    _url, handler = engine
    port = backend_factory(EPHE_OPENAI_COMPAT_API_KEY=TOKEN)
    body = _health(port)

    assert body["engine_online"] is True
    assert body["engine_key_challenge"] is False
    assert body["engine_key_configured"] is True
    assert body["engine_state"] == "ok"
    assert f"Bearer {TOKEN}" in handler.seen


def test_the_two_starts_leave_the_difference_in_the_environment_only(
    backend_factory, engine
):
    """The statement is the only channel: the field is boolean and never carries
    the token, so the desktop reuse branch can read it without sending anything."""
    _url, _handler = engine
    port = backend_factory()
    body = _health(port)
    assert isinstance(body["engine_key_challenge"], bool)
    assert TOKEN not in json.dumps(body), "no secret may leave the health document"
