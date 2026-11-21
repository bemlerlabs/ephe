"""The engine-down sentence names the engine the turn really dialled.

``OllamaNotReachableError`` is the transport-down bucket of *every* provider: a
refused connect is a refused connect, and a remote OpenAI-compatible engine
raises the same class a local Ollama turn does. Read by class name alone, each
of those failures was answered with "start it: ollama serve" — a sentence about
software the reader is not running, which reads as a broken app.

One test per surface, each red on the sentence that named Ollama and green on
the sentence that names the engine that is actually down:

  * ``POST /chat`` (the REST route),
  * the ``/swarm`` command handler,
  * the ``/goal`` command handler,
  * the TUI streaming worker,
  * the TUI swarm worker,
  * the skill self-test (``core/skills.py``).

The local engine keeps its pinned Ollama hint — ``OllamaNotReachableError`` from
a local turn still says so (``tests/test_chat_stream_errors.py`` and
``tests/test_goal_command_surface.py`` hold that side).
"""
from __future__ import annotations

import asyncio
import time

import pytest
from fastapi import HTTPException

from core.chat import OllamaNotReachableError
from core.model_provider import ModelProviderConfig
from server.routes import chat as chat_route

REMOTE_URL = "http://engine.test:18080/v1"


def _remote_provider() -> ModelProviderConfig:
    """An OpenAI-compatible engine on an endpoint that is not Ollama."""
    return ModelProviderConfig(
        provider="openai_compatible",
        model="remote-model",
        base_url=REMOTE_URL,
        label="Remote E2E",
        offline_capable=False,
        requires_internet=True,
    )


def _assert_names_the_endpoint(msg: str) -> None:
    """The one invariant every surface owes the reader."""
    assert "ollama" not in msg.lower(), msg
    assert REMOTE_URL in msg, msg


# the server route: POST /chat

@pytest.mark.asyncio
async def test_rest_route_names_the_remote_engine_that_did_not_answer(monkeypatch):
    """GIVEN a REST turn on a remote engine
    WHEN its transport fails with the shared class
    THEN the 503 detail names that endpoint and never Ollama."""
    monkeypatch.setattr(chat_route, "get_active_provider", _remote_provider)

    async def _boom(**_kwargs):
        raise OllamaNotReachableError()

    monkeypatch.setattr(chat_route, "react_loop", _boom)
    req = chat_route.ChatRequest(message="ping")
    with pytest.raises(HTTPException) as caught:
        await chat_route.chat(req)
    assert caught.value.status_code == 503
    _assert_names_the_endpoint(caught.value.detail)


# the /swarm command handler

@pytest.mark.asyncio
async def test_swarm_handler_names_the_remote_engine(monkeypatch):
    """GIVEN /swarm on a remote engine
    WHEN the swarm raises the shared transport class
    THEN the error frame names that endpoint and never Ollama."""
    monkeypatch.setattr(chat_route, "get_active_provider", _remote_provider)

    async def _boom(**_kwargs):
        raise OllamaNotReachableError()

    monkeypatch.setattr("core.swarm_v2.run_swarm_v2", _boom)
    frames: list[dict] = []
    handled = await chat_route._run_swarm_command(
        "/swarm analyse the build logs", "remote-model", frames.append
    )
    assert handled is True
    errors = [f for f in frames if f.get("type") == "error"]
    assert len(errors) == 1, frames
    _assert_names_the_endpoint(errors[0]["msg"])


# the /goal command handler

@pytest.mark.asyncio
async def test_goal_handler_names_the_remote_engine(monkeypatch):
    """GIVEN /goal on a remote engine
    WHEN the loop raises the shared transport class
    THEN the error frame names that endpoint and never Ollama."""
    monkeypatch.setattr(chat_route, "get_active_provider", _remote_provider)

    class _Raiser:
        def __init__(self, **kwargs) -> None:
            pass

        async def run(self, goal):
            raise OllamaNotReachableError()

    monkeypatch.setattr("core.goal_loop.GoalRunner", _Raiser)

    async def _confirm(question: str, payload: dict) -> bool:
        return True

    frames: list[dict] = []
    handled = await chat_route._run_goal_command(
        "/goal fix the failing test", "remote-model", frames.append, _confirm
    )
    assert handled is True
    errors = [f for f in frames if f.get("type") == "error"]
    assert len(errors) == 1, frames
    _assert_names_the_endpoint(errors[0]["msg"])


# the TUI: both workers

def _capture_system_messages(monkeypatch) -> list[str]:
    """Every ChatView.AddSystemMessage body the TUI posts, in order."""
    from ui.widgets import ChatView

    seen: list[str] = []
    original = ChatView.on_chat_view_add_system_message

    def _record(self, event) -> None:
        seen.append(event.text)
        original(self, event)

    monkeypatch.setattr(ChatView, "on_chat_view_add_system_message", _record)
    return seen


def _isolate(monkeypatch, tmp_path) -> None:
    """Point the TUI away from the real home: sessions, memory, profile."""
    import core.session as session_module

    session_dir = tmp_path / "sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(session_module, "SESSION_DIR", session_dir)
    monkeypatch.setattr(session_module, "SESSION_FILE", session_dir / "default.json")
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    monkeypatch.setenv("EPHE_OFFLINE", "1")


def _stand_down_startup(app, monkeypatch) -> None:
    """Stand down the two startup workers that would touch the network."""

    async def noop() -> None:
        return None

    monkeypatch.setattr(app, "_async_check_connection", noop)
    monkeypatch.setattr(app, "_async_init_mcp", noop)


async def _wait_for(predicate, pilot, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await pilot.pause(0.05)
    return predicate()


def test_tui_stream_worker_names_the_remote_engine(tmp_path, monkeypatch):
    """GIVEN a TUI dialling a remote endpoint
    WHEN the streaming worker hits the shared transport class
    THEN the chat banner names that endpoint and never Ollama."""
    _isolate(monkeypatch, tmp_path)
    seen = _capture_system_messages(monkeypatch)

    async def _boom(**_kwargs):
        raise OllamaNotReachableError()

    monkeypatch.setattr("ui.app.react_loop", _boom)

    from ui.app import EpheApp

    app = EpheApp(model="remote-model", reset=True, api_url=REMOTE_URL)

    async def run() -> None:
        _stand_down_startup(app, monkeypatch)
        async with app.run_test(size=(90, 28)) as pilot:
            await pilot.pause()
            app._pending_history = [{"role": "user", "content": "ping"}]
            app._stream_response()
            assert await _wait_for(lambda: seen, pilot), app._session

    asyncio.run(run())
    assert seen, "the worker posted no system message"
    _assert_names_the_endpoint("\n".join(seen))


def test_tui_swarm_worker_names_the_remote_engine(tmp_path, monkeypatch):
    """GIVEN a TUI dialling a remote endpoint
    WHEN the swarm worker hits the shared transport class
    THEN the chat banner names that endpoint and never Ollama."""
    _isolate(monkeypatch, tmp_path)
    seen = _capture_system_messages(monkeypatch)

    async def _boom(**_kwargs):
        raise OllamaNotReachableError()

    monkeypatch.setattr("ui.app.run_swarm_v2", _boom)

    from ui.app import EpheApp

    app = EpheApp(model="remote-model", reset=True, api_url=REMOTE_URL)

    async def run() -> None:
        _stand_down_startup(app, monkeypatch)
        async with app.run_test(size=(90, 28)) as pilot:
            await pilot.pause()
            app._run_swarm("analyse the build logs")
            assert await _wait_for(lambda: seen, pilot), app._session

    asyncio.run(run())
    assert seen, "the swarm worker posted no system message"
    _assert_names_the_endpoint("\n".join(seen))


# the skill self-test

SKILL_UNDER_TEST = """\
# web-researcher

**Trigger**: /research
**Description**: a routed skill with a self-test.
**Tools**: web_search

## System Prompt

Answer short and use the web_search tool for current facts.

## Test

**Input**: what is the current weather
**Expect Tool**: web_search
"""


@pytest.mark.asyncio
async def test_skill_self_test_names_the_remote_engine(tmp_path, monkeypatch):
    """GIVEN a skill self-test dialling a remote engine
    WHEN its transport fails with the shared class
    THEN the result message names that endpoint and never Ollama."""
    monkeypatch.setattr("core.model_provider.get_active_provider", _remote_provider)

    async def _boom(**_kwargs):
        raise OllamaNotReachableError()

    monkeypatch.setattr("core.chat.chat_with_tools", _boom)

    from core.skills import SkillLoader

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "web-researcher.md").write_text(SKILL_UNDER_TEST, encoding="utf-8")
    loader = SkillLoader(skills_dir=skills_dir)

    result = await loader.run_test("web-researcher")
    assert result.passed is False, result
    _assert_names_the_endpoint(result.message)


def _local_provider() -> ModelProviderConfig:
    """The local Ollama engine — its transport failure may say Ollama."""
    return ModelProviderConfig(
        provider="local_ollama",
        model="local-model",
        base_url="http://127.0.0.1:11434",
        label="Local Ollama",
        offline_capable=True,
        requires_internet=False,
    )


@pytest.mark.asyncio
async def test_skill_self_test_keeps_the_local_ollama_hint(tmp_path, monkeypatch):
    """GIVEN a skill self-test dialling the local engine
    WHEN its transport fails with the shared class
    THEN the result message still says Ollama — that engine really is local."""
    monkeypatch.setattr("core.model_provider.get_active_provider", _local_provider)

    async def _boom(**_kwargs):
        raise OllamaNotReachableError()

    monkeypatch.setattr("core.chat.chat_with_tools", _boom)

    from core.skills import SkillLoader

    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "web-researcher.md").write_text(SKILL_UNDER_TEST, encoding="utf-8")
    loader = SkillLoader(skills_dir=skills_dir)

    result = await loader.run_test("web-researcher")
    assert result.passed is False, result
    assert "Ollama" in result.message, result.message
