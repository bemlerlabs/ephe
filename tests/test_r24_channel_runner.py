"""R24: Telegram channel runner — QR-pairing E2E, hardening, session mapping.

The full roundtrip WITHOUT a real bot token (transport abstraction):
create the QR token → FakeTransport delivers a ``/start <token>`` update →
device paired → paired message → answer via the injected bridge →
revoke withdraws access immediately. The long-polling hardening (backoff, offset
persistence) runs against the same fake.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import core.multi_session as ms
import core.channels.telegram_bot as tb
from core.channels.pairing import load_pairing, load_devices, remove_device
from core.channels.pairing_tokens import create_pairing_token
from core.channels.telegram_bot import (
    FakeTransport,
    TelegramChannelRunner,
    TelegramUpdate,
)


@pytest.fixture(autouse=True)
def _tmp_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "sessions"
    d.mkdir(parents=True)
    monkeypatch.setattr(ms, "SESSIONS_DIR", d)
    monkeypatch.setattr(ms, "REGISTRY_FILE", d / "registry.json")
    return d


@pytest.fixture()
def channels_dir(tmp_path: Path) -> Path:
    return tmp_path / "channels"


def _update(text: str, user_id: int = 42, chat_id: int | None = None,
            update_id: int = 1, name: str = "Test User") -> TelegramUpdate:
    return TelegramUpdate(
        update_id=update_id,
        chat_id=chat_id if chat_id is not None else user_id,
        user_id=user_id,
        text=text,
        user_name=name,
        message_id=update_id,
    )


def _runner(fake: FakeTransport, channels_dir: Path, answer) -> TelegramChannelRunner:
    return TelegramChannelRunner(
        fake,
        answer=answer,
        pairing_path=channels_dir / "channel_pairing.json",
        tokens_path=channels_dir / "channel_pairing_tokens.json",
        sessions_path=channels_dir / "channel_sessions.json",
        state_path=channels_dir / "channel_state.json",
    )


# Pairing-E2E (QR → /start → Device → Chat → Revoke)


@pytest.mark.asyncio
async def test_qr_start_token_pairs_device_end_to_end(channels_dir: Path) -> None:
    token = create_pairing_token(path=channels_dir / "channel_pairing_tokens.json")
    fake = FakeTransport(updates=[_update(f"/start {token}", update_id=101)])
    sent: list[tuple[int, str]] = []
    called: list[str] = []

    async def answer(session_id: str, text: str) -> str:
        called.append(text)
        return "Antwort"

    runner = _runner(fake, channels_dir, answer)
    await runner.handle_update(fake.pending[0])

    # Allowlist + device metadata
    assert load_pairing(channels_dir / "channel_pairing.json").is_allowed(42)
    devices = load_devices(channels_dir / "channel_pairing.json")
    assert [d.user_id for d in devices] == [42]
    assert devices[0].label == "Test User"

    # Two-sided confirmation (anti QR-phishing): the Telegram message names the account
    assert any("Test User" in t and "42" in t for _, t in fake.sent_messages)
    # The token never appears in plaintext in any reply
    assert all(token not in t for _, t in fake.sent_messages)
    # The session mapping exists
    mapping = json.loads((channels_dir / "channel_sessions.json").read_text())
    assert "42" in mapping and mapping["42"]["session_id"]


@pytest.mark.asyncio
async def test_start_redelivery_is_idempotent(channels_dir: Path) -> None:
    token = create_pairing_token(path=channels_dir / "channel_pairing_tokens.json")
    fake = FakeTransport()

    async def answer(session_id: str, text: str) -> str:
        return "Antwort"

    runner = _runner(fake, channels_dir, answer)
    await runner.handle_update(_update(f"/start {token}", update_id=1))
    await runner.handle_update(_update(f"/start {token}", update_id=2))  # Telegram re-delivery

    assert len(load_devices(channels_dir / "channel_pairing.json")) == 1
    assert any("already paired" in t for _, t in fake.sent_messages)


@pytest.mark.asyncio
async def test_start_with_invalid_token_never_pairs(channels_dir: Path) -> None:
    fake = FakeTransport()

    async def answer(session_id: str, text: str) -> str:
        return "Antwort"

    runner = _runner(fake, channels_dir, answer)
    await runner.handle_update(_update("/start bogus-token", update_id=1))

    assert not load_devices(channels_dir / "channel_pairing.json")
    assert any("invalid" in t.lower() or "expired" in t.lower() for _, t in fake.sent_messages)


@pytest.mark.asyncio
async def test_unknown_user_is_denied_fail_closed(channels_dir: Path) -> None:
    fake = FakeTransport()
    called: list[str] = []

    async def answer(session_id: str, text: str) -> str:
        called.append(text)
        return "Antwort"

    runner = _runner(fake, channels_dir, answer)
    await runner.handle_update(_update("Hallo Bot", user_id=999, update_id=1))

    assert called == []  # never handed on to the engine
    assert any("not paired" in t for _, t in fake.sent_messages)


@pytest.mark.asyncio
async def test_paired_message_reaches_answer_bridge_with_injection_guard(
    channels_dir: Path,
) -> None:
    # pair the device directly (fixture shortcut)
    from core.channels.pairing import add_device

    add_device(42, label="Test User", path=channels_dir / "channel_pairing.json")
    fake = FakeTransport()
    seen: list[str] = []
    session_ids: list[str] = []

    async def answer(session_id: str, text: str) -> str:
        seen.append(text)
        session_ids.append(session_id)
        return "Ping zurück"

    runner = _runner(fake, channels_dir, answer)
    await runner.handle_update(_update("Wie geht es dir?", update_id=7))

    assert len(seen) == 1
    assert tb.UNTRUSTED_OPEN in seen[0]  # the injection-guard wrap is active
    assert "Wie geht es dir?" in seen[0]
    assert session_ids[0]  # a session mapping was assigned
    assert any("Ping zurück" in t for _, t in fake.sent_messages)


@pytest.mark.asyncio
async def test_image_marker_sends_photo_and_strips_marker(channels_dir: Path) -> None:
    from core.channels.pairing import add_device

    add_device(42, label="Test User", path=channels_dir / "channel_pairing.json")
    img = channels_dir / "chart.png"
    img.write_bytes(b"\x89PNG\r\n")
    fake = FakeTransport()

    async def answer(session_id: str, text: str) -> str:
        return f"Hier ist das Bild.\nPNG_FILE:{img}\n"

    runner = _runner(fake, channels_dir, answer)
    await runner.handle_update(_update("Zeichne ein Diagramm", update_id=9))

    assert fake.sent_photos == [img]
    last_text = fake.sent_messages[-1][1]
    assert "PNG_FILE" not in last_text
    assert "Hier ist das Bild." in last_text


@pytest.mark.asyncio
async def test_new_command_resets_channel_session(channels_dir: Path) -> None:
    from core.channels.pairing import add_device

    add_device(42, label="Test User", path=channels_dir / "channel_pairing.json")
    fake = FakeTransport()

    async def answer(session_id: str, text: str) -> str:
        return "ok"

    runner = _runner(fake, channels_dir, answer)
    await runner.handle_update(_update("Erste Frage", update_id=1))
    first_sid = runner.session_for(42)
    await runner.handle_update(_update("/new", update_id=2))
    second_sid = runner.session_for(42)

    assert second_sid and second_sid != first_sid


@pytest.mark.asyncio
async def test_revoke_denies_immediately(channels_dir: Path) -> None:
    from core.channels.pairing import add_device

    add_device(42, label="Test User", path=channels_dir / "channel_pairing.json")
    fake = FakeTransport()
    called: list[str] = []

    async def answer(session_id: str, text: str) -> str:
        called.append(text)
        return "Antwort"

    runner = _runner(fake, channels_dir, answer)
    remove_device(42, path=channels_dir / "channel_pairing.json")

    await runner.handle_update(_update("Noch da?", update_id=3))
    assert called == []
    assert any("not paired" in t for _, t in fake.sent_messages)
    # The session mapping was removed along with it
    assert runner.session_for(42) == ""


# Long-polling hardening


@pytest.mark.asyncio
async def test_run_loop_survives_transport_errors_and_persists_offset(
    channels_dir: Path,
) -> None:
    fake = FakeTransport(
        updates=[_update("/start nope", update_id=501)],
        failures=2,
    )
    errors: list[str] = []

    async def answer(session_id: str, text: str) -> str:
        return "Antwort"

    runner = _runner(fake, channels_dir, answer)
    runner.on_error = errors.append
    runner.backoff_seconds = 0.01  # speed the test up

    task = asyncio.create_task(runner.run())
    await asyncio.wait_for(runner.wait_until_drained(), timeout=5)
    runner.stop()
    await asyncio.wait_for(task, timeout=5)

    assert len(errors) == 2  # survived two transport failures, no exit
    state = json.loads((channels_dir / "channel_state.json").read_text())
    assert state["offset"] == 502  # Telegram convention: next-to-fetch = last_id + 1


@pytest.mark.asyncio
async def test_run_loop_stops_gracefully(channels_dir: Path) -> None:
    fake = FakeTransport(updates=[])

    async def answer(session_id: str, text: str) -> str:
        return "Antwort"

    runner = _runner(fake, channels_dir, answer)
    runner.backoff_seconds = 0.01
    task = asyncio.create_task(runner.run())
    await asyncio.sleep(0.05)
    runner.stop()
    await asyncio.wait_for(task, timeout=5)
    assert task.done() and not task.cancelled()


# Default bridge (the real pipeline wiring)


@pytest.mark.asyncio
async def test_default_bridge_uses_channel_approval_policy(monkeypatch, channels_dir: Path) -> None:
    """The production bridge runs react_loop WITH the channel policy (no mutating
    tool without confirmation) and persists the history."""
    captured: dict = {}

    async def fake_react_loop(**kwargs):
        captured.update(kwargs)
        return "Engine-Antwort"

    monkeypatch.setattr(tb, "react_loop", fake_react_loop)

    sid = ms.create_session("Telegram 42")["id"]
    out = await tb.default_channel_answer(sid, "Frage?")

    assert out == "Engine-Antwort"
    assert captured["approval_policy"] is not None
    assert captured["approval_policy"].auto_approve is False
    assert captured["approval_policy"].interactive is False
    history = ms.load_messages(sid)
    assert [(m["role"], m["content"]) for m in history] == [
        ("user", "Frage?"),
        ("assistant", "Engine-Antwort"),
    ]
