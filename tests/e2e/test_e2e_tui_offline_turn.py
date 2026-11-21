"""WG-44 e2e: the TUI runs a whole turn offline, against a stubbed engine.

The terminal was the last surface without an end-to-end path. This mounts the
real ``EpheApp`` in Textual's test harness, submits a line through the real
input widget, and lets the shipped turn run: ``on_history_input_submitted`` ->
the ``_stream_response`` worker -> ``react_loop`` -> ``chat_with_tools`` ->
the streamed answer -> the chat card -> ``save_session``. Only the engine
client is faked, at the two seams the loop reads at call time (``core.chat``
and ``core.react``); the widget, the worker, the loop, the card and the
session store are the shipped code. No socket is opened.
"""
from __future__ import annotations

import asyncio
import time

from core.model_provider import (
    DEFAULT_OLLAMA_BASE_URL,
    ModelProviderConfig,
    ProviderChatResponse,
    ProviderMessage,
)
from ui.composer import ComposerArea
from ui.widgets import AgentMessageCard

ANSWER = "Offline turn answered by the stub engine."
SECOND_ANSWER = "Second turn still offline."


class _StubEngine:
    """A provider client that answers from a script. No network, no LLM."""

    def __init__(self, answers: list[str]) -> None:
        self.calls: list[dict] = []
        self._answers = answers

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        idx = min(len(self.calls) - 1, len(self._answers) - 1)
        return ProviderChatResponse(message=ProviderMessage(content=self._answers[idx]))

    async def aclose(self) -> None:
        return None


def _provider() -> ModelProviderConfig:
    return ModelProviderConfig(
        provider="local_ollama",
        model="stub-model",
        base_url=DEFAULT_OLLAMA_BASE_URL,
        label="E2E",
        offline_capable=True,
        requires_internet=False,
    )


def _wire_stub_engine(monkeypatch, engine: _StubEngine) -> None:
    """Replace the engine client at the two seams the loop reads at call time."""

    async def _passthrough(p):
        return p

    import core.chat as chat_mod
    import core.react as react_mod

    monkeypatch.setattr(chat_mod, "build_provider_client", lambda *a, **k: engine)
    monkeypatch.setattr(chat_mod, "get_active_provider", _provider)
    monkeypatch.setattr(chat_mod, "resolve_active_with_failover", _passthrough)
    # reflect() builds its own client out of core.react's namespace.
    monkeypatch.setattr(react_mod, "build_provider_client", lambda *a, **k: engine)


def _isolate(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("EPHE_MEMORY_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("EPHE_PROFILE_PATH", str(tmp_path / "profile.json"))
    monkeypatch.setenv("EPHE_OFFLINE", "1")


def _mount(app, monkeypatch) -> None:
    """Stand down the two startup workers that would touch the network."""

    async def noop() -> None:
        return None

    monkeypatch.setattr(app, "_async_check_connection", noop)
    monkeypatch.setattr(app, "_async_init_mcp", noop)


async def _wait_for(predicate, pilot, timeout: float = 10.0) -> bool:
    """Pump the app's loop until the predicate holds or the budget is spent."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await pilot.pause(0.05)
    return predicate()


async def _submit(pilot, app, text: str) -> None:
    """Type into the real input and press Enter, the way a user does."""
    inp = app.query_one("#chat-input", ComposerArea)
    inp.focus()
    inp.value = text
    await pilot.pause()
    await pilot.press("enter")


def _assistant_count(app) -> int:
    return sum(1 for m in app._session if m["role"] == "assistant")


def test_tui_runs_an_offline_turn_and_persists_it(tmp_path, monkeypatch, tmp_session_dir):
    """GIVEN a mounted TUI with a stubbed engine
    WHEN a line is submitted
    THEN the answer streams into the chat card and lands in the session store."""
    _isolate(monkeypatch, tmp_path)
    engine = _StubEngine([ANSWER])
    _wire_stub_engine(monkeypatch, engine)

    from core import multi_session as ms
    from ui.app import EpheApp

    captured: dict = {}

    async def run() -> None:
        app = EpheApp(model="stub-model", reset=False)
        _mount(app, monkeypatch)
        async with app.run_test(size=(100, 30)) as pilot:
            await _submit(pilot, app, "answer one line")
            ok = await _wait_for(
                lambda: app._session and app._session[-1]["role"] == "assistant", pilot
            )
            await pilot.pause()
            assert ok, f"the turn never finished; session={app._session}"
            captured["answer_acc"] = app.query(AgentMessageCard).last()._answer_acc
            captured["session"] = list(app._session)
            captured["session_id"] = app._session_id

    asyncio.run(run())

    assert captured["session"][-1] == {"role": "assistant", "content": ANSWER}
    assert ANSWER in captured["answer_acc"], captured["answer_acc"]

    on_disk = ms.load_messages(captured["session_id"])
    assert on_disk[-1] == {"role": "assistant", "content": ANSWER}, on_disk


def test_tui_second_turn_carries_the_first_answer(tmp_path, monkeypatch, tmp_session_dir):
    """GIVEN one finished turn
    WHEN a second line is submitted
    THEN the engine receives the first answer as conversation context."""
    _isolate(monkeypatch, tmp_path)
    engine = _StubEngine([ANSWER, SECOND_ANSWER])
    _wire_stub_engine(monkeypatch, engine)

    from ui.app import EpheApp

    async def run() -> None:
        app = EpheApp(model="stub-model", reset=False)
        _mount(app, monkeypatch)
        async with app.run_test(size=(100, 30)) as pilot:
            await _submit(pilot, app, "first question")
            assert await _wait_for(lambda: _assistant_count(app) >= 1, pilot), app._session
            await _submit(pilot, app, "second question")
            assert await _wait_for(lambda: _assistant_count(app) >= 2, pilot), app._session

    asyncio.run(run())

    seen = [
        m.get("content")
        for call in engine.calls
        for m in call.get("messages", [])
        if m.get("role") == "assistant"
    ]
    assert ANSWER in seen, f"the first answer was not in the second turn's context: {seen}"
