"""WS6-37: one honest end-to-end path — install, chat, tool, artifact.

The product's own hops, in order:

1. install  — the project is installed into a fresh virtualenv and the
   installed console script runs, the way ``install.sh`` and CI's
   ``pip install -e`` produce a working ``ephe`` command.
2. chat     — ``POST /api/chat/stream`` on the real FastAPI app.
3. tool     — the model's tool call runs through the real tool loop
   (``core.tools.execute_tool`` -> ``create_svg``) and the real approval gate.
4. artifact — the file the tool wrote is registered in the artifact library
   and comes back out of ``GET /api/artifacts``.

Only the engine client is faked. Route, agent loop, approval gate, tool,
workbench file, artifact store and artifacts API are the shipped code.

The install leg builds a throwaway virtualenv and installs the project with
``pip`` exactly as CI does; it runs once per session and needs the package
index. Set ``EPHE_E2E_SKIP_INSTALL=1`` to skip it — the chat/tool/artifact leg
needs no index.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from core._version import __version__

ROOT = Path(__file__).resolve().parents[2]

# The spine mutates global state (the shipped approval profile) and the install
# leg builds a venv from an *editable* install of the checkout, which writes
# build metadata into the repo. Neither survives eight workers doing it at once,
# so this module runs on a serial leg (release.yml runs the whole set in one
# process) and stands down under xdist.
pytestmark = pytest.mark.skipif(
    bool(os.environ.get("PYTEST_XDIST_WORKER")),
    reason="serial leg only: editable install and global security config race under xdist",
)

TOOL_NAME = "create_svg"
ARTIFACT_FILENAME = "e2e-proof.svg"
SVG_BODY = '<svg xmlns="http://www.w3.org/2000/svg" width="40" height="40"><rect width="40" height="40" fill="red"/></svg>'
FINAL_ANSWER = "Saved the red square as e2e-proof.svg."
SESSION_ID = "e2e-session"


def _install_into_fresh_venv(venv_dir: Path) -> Path:
    """Install the project into a throwaway venv; return the installed script.

    The declared build backend (hatchling, plus ``editables`` for an editable
    build) is installed first, then the project is built with
    ``--no-build-isolation`` so pip does not spin up a throwaway build env and
    re-resolve the backend on every run. ``--no-deps`` keeps runtime
    dependencies out of the throwaway env: ``ephe --version`` does not need
    them, and this leg proves the install contract (packaging and
    console-script wiring).
    """
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv_dir)],
        check=True, capture_output=True, text=True,
    )
    bindir = "Scripts" if os.name == "nt" else "bin"
    py = venv_dir / bindir / "python"
    for args in (
        ["install", "--disable-pip-version-check", "hatchling", "editables"],
        ["install", "--disable-pip-version-check", "--no-deps", "--no-build-isolation", "-e", str(ROOT)],
    ):
        step = subprocess.run([str(py), "-m", "pip", *args], capture_output=True, text=True)
        assert step.returncode == 0, (
            f"`pip {' '.join(args)}` failed (needs the package index):\n"
            f"stdout:\n{step.stdout}\nstderr:\n{step.stderr}"
        )
    return venv_dir / bindir / "ephe"


@pytest.fixture(scope="session")
def installed_ephe(tmp_path_factory) -> Path:
    """The console script of a fresh install of this checkout. Built once."""
    if os.environ.get("EPHE_E2E_SKIP_INSTALL") == "1":
        pytest.skip("EPHE_E2E_SKIP_INSTALL=1")
    return _install_into_fresh_venv(tmp_path_factory.mktemp("e2e-venv"))


def test_install_puts_a_running_ephe_console_script_on_path(installed_ephe: Path):
    """Stage 1 alone, so an install regression names itself."""
    assert installed_ephe.exists(), f"no console script installed at {installed_ephe}"
    result = subprocess.run([str(installed_ephe), "--version"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"ephe {__version__}"


def _response(content: str = "", tool_calls=None):
    from core.model_provider import (
        ProviderChatResponse, ProviderFunctionCall, ProviderMessage, ProviderToolCall,
    )

    calls = None
    if tool_calls:
        calls = [
            ProviderToolCall(function=ProviderFunctionCall(name=name, arguments=args))
            for name, args in tool_calls
        ]
    return ProviderChatResponse(message=ProviderMessage(content=content, tool_calls=calls))


class _Engine:
    """A model that calls one tool, then answers. No network, no LLM."""

    def __init__(self):
        self.calls: list[dict] = []
        self._responses = [
            _response(content="", tool_calls=[(TOOL_NAME, {"svg_code": SVG_BODY, "filename": ARTIFACT_FILENAME})]),
            _response(content=FINAL_ANSWER, tool_calls=None),
        ]

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        return self._responses[idx]

    async def aclose(self):
        return None


def _server_events(body: str) -> list[dict]:
    events: list[dict] = []
    for line in body.splitlines():
        if not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload:
            events.append(json.loads(payload))
    return events


def _first(events: list[dict], **match) -> dict | None:
    return next((e for e in events if all(e.get(k) == v for k, v in match.items())), None)


def _wire_fake_engine(monkeypatch, engine: "_Engine") -> None:
    """Replace only the engine client, at the seam core.chat reads at call time."""
    from core.model_provider import DEFAULT_OLLAMA_BASE_URL, ModelProviderConfig

    provider = ModelProviderConfig(
        provider="local_ollama", model="e2e-model", base_url=DEFAULT_OLLAMA_BASE_URL,
        label="E2E", offline_capable=True, requires_internet=False,
    )

    async def _passthrough(p):
        return p

    import core.chat as chat_mod
    import server.routes.chat as route_mod

    monkeypatch.setattr(chat_mod, "build_provider_client", lambda *a, **k: engine)
    monkeypatch.setattr(chat_mod, "get_active_provider", lambda: provider)
    monkeypatch.setattr(chat_mod, "resolve_active_with_failover", _passthrough)
    monkeypatch.setattr(route_mod, "get_active_provider", lambda: provider)


def _run_turn(client) -> list[dict]:
    """One real SSE turn; returns the parsed server events."""
    resp = client.post("/api/chat/stream", json={
        "message": "Draw a red square and save it as an SVG.",
        "model": "e2e-model",
        "session_id": SESSION_ID,
        "mode": "agent",
        "autonomous": True,
    })
    assert resp.status_code == 200, resp.text
    return _server_events(resp.text)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """The real app. Only the engine client is replaced."""
    monkeypatch.setenv("EPHE_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    # This fixture writes the shipped "session" approval profile below, and the writer
    # resolves that file through core.engine_config.CONFIG_DIR — a module constant bound at
    # import, so EPHE_CONFIG_DIR alone does not move it. Without this the suite writes the
    # profile into the user's real ~/.ephe, which tests/test_home_isolation.py refuses
    # (correctly) as soon as a full run arms it: the setup errors and the turn that follows
    # asserts against a profile that was never saved. Same shape as
    # tests/conftest.py::chosen_engine.
    import core.engine_config as _engine_config

    _config_dir = tmp_path / "ephe-home"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(_config_dir))
    monkeypatch.setattr(_engine_config, "CONFIG_DIR", _config_dir, raising=False)

    _wire_fake_engine(monkeypatch, _Engine())

    # A session allowed to write without a per-file dialog: the shipped
    # "session" approval profile. The turn still runs the real gate.
    from core.security_config import save_security_config
    save_security_config(approval_profile="session")

    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as c:
        yield c


def test_e2e_chat_runs_a_tool_and_registers_its_artifact(client):
    """Stages 2-4: an SSE turn drives the real tool loop; the file lands in the library."""
    events = _run_turn(client)

    answer = "".join(e.get("data", "") for e in events if e.get("type") == "chunk")
    assert FINAL_ANSWER in answer, f"answer not streamed; events={events}"
    assert _first(events, type="done") is not None, "stream never sent done"

    assert _first(events, type="tool_start", tool=TOOL_NAME) is not None, events
    assert _first(events, type="tool_done", tool=TOOL_NAME) is not None, events

    file_result = _first(events, type="file_result", file_type="svg")
    assert file_result is not None, events
    artifact_id = file_result.get("id")
    assert artifact_id, f"no artifact id on the file_result event: {file_result}"

    out_path = Path(file_result["path"])
    assert out_path.is_file(), f"tool reported {out_path}, nothing there"
    assert SVG_BODY in out_path.read_text(encoding="utf-8")

    listed = client.get("/api/artifacts", params={"session_id": SESSION_ID}).json()
    ids = {row["id"] for row in listed["artifacts"]}
    assert artifact_id in ids, f"{artifact_id} not in library: {listed}"

    detail = client.get(f"/api/artifacts/{artifact_id}")
    assert detail.status_code == 200
    assert detail.json()["kind"] == "svg"


def test_e2e_install_chat_tool_artifact(tmp_path, monkeypatch, installed_ephe: Path):
    """The whole spine in one test: install, chat, tool, artifact."""
    version = subprocess.run([str(installed_ephe), "--version"], capture_output=True, text=True)
    assert version.returncode == 0 and version.stdout.strip() == f"ephe {__version__}"

    monkeypatch.setenv("EPHE_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_OFFLINE", "1")
    # The approval profile below lands in the config dir, and that path is the
    # module constant core.engine_config.CONFIG_DIR rather than the env var — see the
    # `client` fixture above for why writing it into the real ~/.ephe fails the run.
    import core.engine_config as _engine_config

    _config_dir = tmp_path / "ephe-home"
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(_config_dir))
    monkeypatch.setattr(_engine_config, "CONFIG_DIR", _config_dir, raising=False)
    _wire_fake_engine(monkeypatch, _Engine())

    from core.security_config import save_security_config
    save_security_config(approval_profile="session")

    from fastapi.testclient import TestClient
    from server.main import create_app

    with TestClient(create_app()) as c:
        events = _run_turn(c)

        assert _first(events, type="tool_done", tool=TOOL_NAME) is not None, events
        file_result = _first(events, type="file_result", file_type="svg")
        assert file_result and file_result.get("id"), events
        assert Path(file_result["path"]).is_file()

        detail = c.get(f"/api/artifacts/{file_result['id']}")
        assert detail.status_code == 200
        assert detail.json()["kind"] == "svg"
