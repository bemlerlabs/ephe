"""W3-61: the two-machine path — a client process against a serve process.

`ephe serve` exists so another machine's agent CLI can drive the engine over a
socket. This test makes that boundary real. The serve side runs in its own
interpreter (``serve_two_machine_leg.py``, a uvicorn host of the shipped
``create_openai_app``) and the client side is this pytest process, reaching it over
a loopback TCP port. Nothing is shared in memory, so a value that arrives here is a
value that crossed the wire.

The client drives the wire two ways: raw httpx against the OpenAI shapes, and the
shipped Ephe consumer (``_fetch_served_models`` and ``OpenAICompatibleAsyncClient``
from ``core.model_provider``) — the code an Ephe on the second machine runs when it
is pointed at a served engine.

The engine behind the serve seam is a deterministic stand-in, because the test host
runs no Ollama. The routes, middleware, SSE framing and the auth gate are shipped.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
LEG = Path(__file__).with_name("serve_two_machine_leg.py")


def _load_leg():
    """Import the serve leg for its two shared constants, without running it.

    A second copy of CHUNKS or the model id would drift from the program the test
    actually starts, and both sides would stop agreeing silently.
    """
    spec = importlib.util.spec_from_file_location("serve_two_machine_leg", LEG)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_LEG = _load_leg()
MODEL = _LEG.DEFAULT_MODEL
FULL = "".join(_LEG.CHUNKS)

#: The token both protected requests carry. `ephe serve --lan` mints one per run;
#: a fixed test value is fine because the app never stores it.
TOKEN = "w3-61-access-token"

#: A cold leg imports the server package before uvicorn binds. The deadline is the
#: wall clock a two-machine pairing may take before the client gives up.
READY_TIMEOUT_S = 40.0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _leg_env(home: Path) -> dict[str, str]:
    """The child environment: this checkout on the path, every write under `home`.

    EPHE_CONFIG_DIR points at the tmp dir so the leg cannot pick up an engine.json
    from the developer's real ``~/.ephe``; the served app must be the stand-in.
    """
    env = dict(os.environ)
    env.update(
        {
            "PYTHONPATH": str(REPO_ROOT),
            "EPHE_OFFLINE": "1",
            "EPHE_CONFIG_DIR": str(home),
            "EPHE_SESSIONS_DIR": str(home / "sessions"),
        }
    )
    return env


class Serve:
    """One serve process on loopback, started from its own interpreter.

    ``base`` is the engine root (``http://127.0.0.1:<port>``); the OpenAI paths hang
    off ``/v1``. ``stop`` terminates the child and waits, so a leaked port cannot
    make the next leg flaky.
    """

    def __init__(self, workdir: Path, *, token: str = "") -> None:
        self.port = _free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.token = token
        self._log_path = workdir / f"serve-{self.port}.log"
        self._log = self._log_path.open("w", encoding="utf-8")
        self.proc = subprocess.Popen(
            [
                sys.executable,
                str(LEG),
                "--port",
                str(self.port),
                "--model",
                MODEL,
                "--token",
                token,
            ],
            cwd=str(REPO_ROOT),
            env=_leg_env(workdir),
            stdout=self._log,
            stderr=subprocess.STDOUT,
        )

    def headers(self) -> dict[str, str]:
        return {"X-Auth-Token": self.token} if self.token else {}

    def wait_ready(self) -> None:
        """Poll the wire until the served app answers, or the child dies.

        A TCP connect alone would pass before the app has built its routes; the probe
        is the real ``/v1/models`` request, and a 401 counts as up when a token is set.
        """
        deadline = time.monotonic() + READY_TIMEOUT_S
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise AssertionError(
                    f"serve leg exited before it was ready\n{self.log()}"
                )
            try:
                response = httpx.get(
                    f"{self.base}/v1/models", headers=self.headers(), timeout=1.0
                )
                if response.status_code in (200, 401):
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.15)
        raise AssertionError(f"serve leg never answered on {self.base}\n{self.log()}")

    def stop(self) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:  # pragma: no cover — hang guard
                self.proc.kill()
                self.proc.wait(timeout=20)
        self._log.close()

    def log(self) -> str:
        self._log.flush()
        try:
            return self._log_path.read_text(encoding="utf-8")
        except OSError:  # pragma: no cover — log lives for the fixture's lifetime
            return ""


@pytest.fixture(scope="module")
def served(tmp_path_factory):
    """A tokenless serve, the shipped ``ephe serve`` default on loopback."""
    instance = Serve(tmp_path_factory.mktemp("serve-plain"))
    instance.wait_ready()
    yield instance
    instance.stop()


@pytest.fixture(scope="module")
def served_token(tmp_path_factory):
    """A token-protected serve, the shape a LAN pairing hands a second machine."""
    instance = Serve(tmp_path_factory.mktemp("serve-token"), token=TOKEN)
    instance.wait_ready()
    yield instance
    instance.stop()


def test_the_serve_side_answers_from_a_separate_process(tmp_path):
    """A serve started as its own program answers on the wire, then stops.

    The pid check separates this from the WG-49 in-process app; the 200 after the
    request shows the answering process is still the child, and the post-stop poll
    shows the socket died with it.
    """
    instance = Serve(tmp_path)
    try:
        instance.wait_ready()
        assert instance.proc.pid != os.getpid()
        response = httpx.get(f"{instance.base}/v1/models", timeout=5.0)
        assert response.status_code == 200, instance.log()
        assert instance.proc.poll() is None
    finally:
        instance.stop()
    assert instance.proc.poll() is not None


def test_models_list_over_the_wire_matches_the_openai_model_list_shape(served_token):
    response = httpx.get(
        f"{served_token.base}/v1/models", headers=served_token.headers(), timeout=5.0
    )
    assert response.status_code == 200, served_token.log()
    body = response.json()
    assert body["object"] == "list"
    assert [item["id"] for item in body["data"]] == [MODEL]
    for item in body["data"]:
        assert item["object"] == "model"
        assert item["owned_by"] == "ephe"
        assert isinstance(item["created"], int)


def test_non_stream_completion_matches_the_openai_chat_completion_shape(served_token):
    response = httpx.post(
        f"{served_token.base}/v1/chat/completions",
        headers=served_token.headers(),
        json={"model": MODEL, "messages": [{"role": "user", "content": "hello"}]},
        timeout=15.0,
    )
    assert response.status_code == 200, served_token.log()
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["id"].startswith("chatcmpl-")
    assert isinstance(body["created"], int)
    assert body["model"] == MODEL
    choice = body["choices"][0]
    assert choice["index"] == 0
    assert choice["finish_reason"] == "stop"
    assert choice["message"] == {"role": "assistant", "content": FULL}
    usage = body["usage"]
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
    assert isinstance(usage["usage_estimated"], bool)
    assert response.headers["X-Model-Provider"] == "ephe"
    assert response.headers["X-Model-Name"] == MODEL


def test_stream_over_the_wire_emits_openai_sse_chunks_and_the_done_sentinel(
    served_token,
):
    with httpx.stream(
        "POST",
        f"{served_token.base}/v1/chat/completions",
        headers=served_token.headers(),
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": "hello"}],
            "stream": True,
        },
        timeout=15.0,
    ) as response:
        assert response.status_code == 200, served_token.log()
        assert response.headers["content-type"].startswith("text/event-stream")
        raw = "".join(response.iter_text())

    frames = [
        line.removeprefix("data:").strip()
        for line in raw.splitlines()
        if line.startswith("data:")
    ]
    assert frames[-1] == "[DONE]"
    deltas = [json.loads(frame) for frame in frames[:-1] if frame and frame != "[DONE]"]
    for delta in deltas:
        assert delta["object"] == "chat.completion.chunk"
    text = "".join(
        delta["choices"][0]["delta"].get("content", "")
        for delta in deltas
        if delta.get("choices")  # the trailing usage frame carries choices=[]
    )
    assert text == FULL


def test_a_call_without_the_token_is_refused_with_the_openai_error_envelope(
    served_token,
):
    response = httpx.get(f"{served_token.base}/v1/models", timeout=5.0)
    assert response.status_code == 401, served_token.log()
    body = response.json()
    assert body["error"]["code"] == "auth_error"
    assert body["error"]["request_id"]
    assert response.headers.get("x-request-id")

    wrong = httpx.get(
        f"{served_token.base}/v1/models",
        headers={"X-Auth-Token": "not-the-token"},
        timeout=5.0,
    )
    assert wrong.status_code == 401


def test_the_shipped_ephe_client_reaches_the_served_engine(served):
    """The second machine's own code path: discover the engine, then run a turn.

    ``_fetch_served_models`` is the client the onboarding uses to read a remote
    engine's model list; ``OpenAICompatibleAsyncClient`` is what Ephe builds when it
    is pointed at an OpenAI-compatible endpoint. Both run here against the serve
    process over the socket, with no shared state.
    """
    from core._cli_common import _fetch_served_models
    from core.model_provider import OpenAICompatibleAsyncClient

    base_v1 = f"{served.base}/v1"
    assert _fetch_served_models(base_v1) == [MODEL]

    client = OpenAICompatibleAsyncClient(base_url=base_v1, api_key="")

    async def _one_shot() -> str:
        reply = await client.chat(
            model=MODEL, messages=[{"role": "user", "content": "hello"}]
        )
        return reply.message.content

    async def _streamed() -> str:
        stream = await client.chat(
            model=MODEL, messages=[{"role": "user", "content": "hello"}], stream=True
        )
        parts = []
        async for frame in stream:
            parts.append(frame["message"].get("content", ""))
        return "".join(parts)

    assert asyncio.run(_one_shot()) == FULL
    assert asyncio.run(_streamed()) == FULL
