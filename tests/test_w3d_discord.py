"""W3d (2026-09-09): Discord channel (R24 pattern) + Telegram live setup.

Every bot-API call runs through a mocked transport (no network). Keyring stub
as in test_r24_channels_routes.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import core.channels.pairing as pairing
import server.routes.channels as channels


@pytest.fixture(autouse=True)
def _hermetic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("EPHE_DIR", str(tmp_path / "ephe"))
    monkeypatch.setattr(pairing, "_store_keyring", lambda token: False)
    monkeypatch.setattr(pairing, "_load_keyring", lambda: None)
    monkeypatch.setattr(pairing, "_delete_keyring", lambda: None)
    return tmp_path / "ephe"


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    import os

    os.environ["EPHE_MEMORY_DIR"] = os.environ["EPHE_MEMORY_DIR"] = str(tmp_path / "chroma_db")
    os.environ["EPHE_PROFILE_PATH"] = os.environ["EPHE_PROFILE_PATH"] = str(tmp_path / "user_profile.json")
    os.environ["EPHE_CORRECTIONS_PATH"] = os.environ["EPHE_CORRECTIONS_PATH"] = str(tmp_path / "corrections.md")
    os.environ["EPHE_FEEDBACK_DIR"] = os.environ["EPHE_FEEDBACK_DIR"] = str(tmp_path)
    os.environ["EPHE_SKILLS_DIR"] = os.environ["EPHE_SKILLS_DIR"] = str(tmp_path / "skills")
    from server.main import create_app

    with TestClient(create_app()) as c:
        yield c
    channels.reset_for_tests()
    channels.reset_discord_for_tests()


VALID_BOT = "1432891234567890123.aB3dEf-GhIjK.1234567890abcdefgh"


class TestDiscordRoutes:

    def test_status_without_token_is_honest_not_configured(self, client):
        resp = client.get("/api/channels/discord/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["configured"] is False
        assert body["running"] is False
        assert body["message"] == "not configured"

    def test_save_token_masks_and_persists_file_0600(self, client, _hermetic):
        resp = client.post("/api/channels/discord/token", json={"token": VALID_BOT})
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] in ("file_0600", "keyring")
        assert VALID_BOT not in resp.text
        assert body["masked"].startswith("…")

    def test_invalid_token_shape_rejected_422(self, client):
        resp = client.post("/api/channels/discord/token", json={"token": "kurz"})
        assert resp.status_code == 422

    def test_delete_token_then_status_unconfigured(self, client):
        client.post("/api/channels/discord/token", json={"token": VALID_BOT})
        client.delete("/api/channels/discord/token")
        body = client.get("/api/channels/discord/status").json()
        assert body["configured"] is False

    def test_start_without_token_409(self, client):
        resp = client.post("/api/channels/discord/start")
        assert resp.status_code == 409


@pytest.mark.asyncio
async def test_handle_message_pairing_and_answer_roundtrip(tmp_path: Path) -> None:
    """G: start-token batch + follow-up message W: handle_message T: pairing + guard-wrap + echo back."""
    from core.channels.pairing_tokens import create_pairing_token
    from core.channels.discord import DiscordChannelRunner, FakeDiscordTransport

    pp = tmp_path / "pairing.json"
    tp = tmp_path / "tokens.json"
    token = create_pairing_token(path=tp)
    transport = FakeDiscordTransport([])
    answered: list = []

    async def answer(session_id: str, text: str) -> str:
        answered.append(text)
        return f"echo:{text}"

    runner = DiscordChannelRunner(
        transport,
        answer=answer,
        pairing_path=pp,
        tokens_path=tp,
        sessions_path=tmp_path / "sessions.json",
        state_path=tmp_path / "state.json",
    )
    await runner.handle_message(
        {"id": "1", "channel_id": "10", "author": {"id": "42", "username": "u"}, "content": f"start {token}"}
    )
    await runner.handle_message(
        {"id": "2", "channel_id": "10", "author": {"id": "42", "username": "u"}, "content": "hallo"}
    )
    assert len(answered) == 1, "genau eine Pipeline-Antwort erwartet"
    assert "hallo" in answered[0]
    assert transport.sent, "Antwort wurde nicht zurueckgesendet"
    assert any("echo:" in c for _, c in transport.sent)


@pytest.mark.asyncio
async def test_run_loop_drains_batch_and_stops_clean(tmp_path: Path) -> None:
    """G: fake with a 1-message batch W: run() until drained + stop() T: channel discovery, no hang."""
    import asyncio

    from core.channels.discord import DiscordChannelRunner, FakeDiscordTransport

    transport = FakeDiscordTransport([
        {"id": "7", "channel_id": "33", "author": {"id": "42", "username": "u"}, "content": "ping"},
    ])
    runner = DiscordChannelRunner(
        transport,
        answer=_noop_answer,
        pairing_path=tmp_path / "pairing.json",
        tokens_path=tmp_path / "tokens.json",
        sessions_path=tmp_path / "sessions.json",
        state_path=tmp_path / "state.json",
    )
    task = asyncio.create_task(runner.run())
    await runner.wait_until_drained()
    runner.stop()
    await asyncio.wait_for(task, timeout=5)
    assert runner._channel_ids == ["33"]


async def _noop_answer(session_id: str, text: str) -> str:
    return "ok"
