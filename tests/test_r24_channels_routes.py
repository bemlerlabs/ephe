"""R24: channel admin routes — token vault, start/stop, QR pairing, devices/revoke.

Every bot API contact goes through a mocked transport (no network, no real
bot token). The keyring is patched (never touch the real keychain).
"""

from __future__ import annotations

import base64
import json
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import core.channels.pairing as pairing
import server.routes.channels as channels
from core.channels.pairing import add_device, load_devices
from core.channels.pairing_tokens import create_pairing_token
from core.channels.telegram_bot import FakeTransport


@pytest.fixture(autouse=True)
def _hermetic_channels(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Never touch the real profile for pairing/token/state files or the keyring."""
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


VALID_TOKEN = ":".join(["123456789", "A" * 35])  # fake, test-only; split so scanners see no token


class TestTokenVault:
    def test_store_token_persists_0600_without_secret_in_response(self, client, tmp_path):
        resp = client.post("/api/channels/telegram/token", json={"token": VALID_TOKEN})
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] in ("file_0600", "keyring")
        assert VALID_TOKEN not in resp.text  # C3: the plaintext is never returned

        p = tmp_path / "ephe" / "channel_token.key"
        assert p.exists()
        assert stat.S_IMODE(p.stat().st_mode) == 0o600
        assert p.read_text().strip() == VALID_TOKEN

    def test_store_rejects_non_token_shaped_input(self, client):
        resp = client.post("/api/channels/telegram/token", json={"token": "hallo-welt"})
        assert resp.status_code == 422

    def test_delete_token_removes_secret_and_stops_runner(self, client, tmp_path):
        client.post("/api/channels/telegram/token", json={"token": VALID_TOKEN})
        resp = client.delete("/api/channels/telegram/token")
        assert resp.status_code == 200
        assert not (tmp_path / "ephe" / "channel_token.key").exists()
        status = client.get("/api/channels/telegram/status").json()
        assert status["token_configured"] is False


class TestStatusAndLifecycle:
    def test_status_without_token(self, client):
        body = client.get("/api/channels/telegram/status").json()
        assert body["token_configured"] is False
        assert body["running"] is False
        assert body["paired_count"] == 0

    def test_start_requires_token(self, client):
        resp = client.post("/api/channels/telegram/start")
        assert resp.status_code == 409

    def test_start_and_stop_with_token(self, client, monkeypatch):
        client.post("/api/channels/telegram/token", json={"token": VALID_TOKEN})
        monkeypatch.setattr(
            channels, "HttpxTelegramTransport", lambda token: FakeTransport()
        )
        resp = client.post("/api/channels/telegram/start")
        assert resp.status_code == 200
        assert resp.json()["running"] is True

        stop = client.post("/api/channels/telegram/stop")
        assert stop.status_code == 200
        assert stop.json()["running"] is False


class TestPairingQR:
    def test_pair_requires_token(self, client):
        resp = client.post("/api/channels/telegram/pair")
        assert resp.status_code == 409

    def test_pair_returns_deep_link_and_png_qr(self, client, monkeypatch):
        client.post("/api/channels/telegram/token", json={"token": VALID_TOKEN})

        class _Transport(FakeTransport):
            async def bot_username(self):
                return "ephe_bot"

        monkeypatch.setattr(
            channels, "HttpxTelegramTransport", lambda token: _Transport()
        )
        resp = client.post("/api/channels/telegram/pair")
        assert resp.status_code == 200
        body = resp.json()

        assert body["deep_link"].startswith("https://t.me/ephe_bot?start=")
        payload = body["deep_link"].split("start=")[1]
        assert 16 <= len(payload) <= 64
        png = base64.b64decode(body["qr_base64"])
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert body["ttl_seconds"] >= 300
        assert body["expires_at"] > body["issued_at"]

    def test_pair_rate_limited_after_max_open_tokens(self, client, monkeypatch, tmp_path):
        client.post("/api/channels/telegram/token", json={"token": VALID_TOKEN})

        class _Transport(FakeTransport):
            async def bot_username(self):
                return "ephe_bot"

        monkeypatch.setattr(
            channels, "HttpxTelegramTransport", lambda token: _Transport()
        )
        from core.channels import pairing_tokens as pt

        ephe_dir = tmp_path / "ephe"
        for _ in range(pt.MAX_OPEN_TOKENS):
            create_pairing_token(path=ephe_dir / "channel_pairing_tokens.json")
        resp = client.post("/api/channels/telegram/pair")
        assert resp.status_code == 429


class TestDevicesAndRevoke:
    def test_list_and_revoke(self, client, tmp_path):
        add_device(42, label="Test User", path=tmp_path / "ephe" / "channel_pairing.json")
        listing = client.get("/api/channels/telegram/devices").json()
        assert listing == [{"user_id": 42, "label": "Test User", "paired_at": listing[0]["paired_at"]}]

        resp = client.delete("/api/channels/telegram/devices/42")
        assert resp.status_code == 200
        assert load_devices(tmp_path / "ephe" / "channel_pairing.json") == []
        assert client.get("/api/channels/telegram/devices").json() == []

    def test_revoke_unknown_device_is_404(self, client):
        assert client.delete("/api/channels/telegram/devices/999").status_code == 404


class TestAuditTrail:
    def test_admin_actions_are_audited(self, client, monkeypatch, tmp_path):
        import core.audit_log as audit_log

        monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", tmp_path / "audit.log")
        client.post("/api/channels/telegram/token", json={"token": VALID_TOKEN})
        add_device(42, label="Test User", path=tmp_path / "ephe" / "channel_pairing.json")
        client.delete("/api/channels/telegram/devices/42")

        entries = audit_log.tail(limit=50, kind="channel")
        details = [e.get("detail") for e in entries]
        assert "telegram_token_stored" in details
        assert "telegram_device_revoked" in details
        # No plaintext token in the audit trail
        assert all(VALID_TOKEN not in json.dumps(e) for e in entries)


class TestTokenHintHoldsNoSecret:
    """The hint the settings card shows is the public id of the bot, and no part of the
    credential.

    A bot token IS the credential for that bot, and `/api/channels/*/status` answers a
    plain GET — the one request a page in the user's browser can make against a localhost
    server. The hint used to be the token's last four characters plus its length, which
    is a partial copy of the secret handed to whoever asked."""

    TELEGRAM_TOKEN = ":".join(["987654321", "B" * 35])  # fake, test-only; split for scanners
    DISCORD_TOKEN = "123456789012345678.abcdef.XXXXX-_yz12"

    def test_telegram_status_hint_names_the_public_id(self, client):
        """GIVEN a Telegram bot token is stored
        THEN the hint is the public numeric bot id, which is what a user reads to
        confirm the right bot is configured."""
        client.post("/api/channels/telegram/token", json={"token": self.TELEGRAM_TOKEN})

        body = client.get("/api/channels/telegram/status").json()

        assert body["token_configured"] is True
        assert body["token_masked"] == "bot 987654321"

    def test_telegram_status_hint_carries_no_token_material(self, client):
        """GIVEN the same stored token
        THEN no run of it, its tail, or its length appears anywhere in the answer —
        today the answer carried `…BBBB (44 Zeichen)`, a partial copy of the credential."""
        client.post("/api/channels/telegram/token", json={"token": self.TELEGRAM_TOKEN})

        resp = client.get("/api/channels/telegram/status")

        secret = self.TELEGRAM_TOKEN.split(":", 1)[1]
        assert secret[-4:] not in resp.text
        assert secret[:4] not in resp.text
        assert str(len(self.TELEGRAM_TOKEN)) not in resp.text
        assert secret not in resp.text

    def test_storing_a_token_answers_with_the_status_hint(self, client):
        """GIVEN the card shows one hint after storing and another after a reload
        THEN both are the same string — the two sites used to format the hint
        independently, and only one of them was changed by any later fix."""
        stored = client.post("/api/channels/telegram/token", json={"token": self.TELEGRAM_TOKEN})

        status = client.get("/api/channels/telegram/status").json()

        assert stored.json()["masked"] == status["token_masked"]

    def test_discord_status_hint_names_the_public_app_id(self, client):
        """GIVEN a Discord bot token is stored
        THEN the hint is the public application id from the token's first segment."""
        client.post("/api/channels/discord/token", json={"token": self.DISCORD_TOKEN})

        body = client.get("/api/channels/discord/status").json()

        assert body["configured"] is True
        assert body["token_masked"] == "bot 123456789012345678"

    def test_discord_status_hint_carries_no_token_material(self, client):
        """GIVEN the same stored Discord token
        THEN neither secret segment, nor a run of either, nor the length is in the
        answer."""
        client.post("/api/channels/discord/token", json={"token": self.DISCORD_TOKEN})

        resp = client.get("/api/channels/discord/status")

        segments = self.DISCORD_TOKEN.split(".")
        for segment in segments[1:]:
            assert segment not in resp.text
            assert segment[:4] not in resp.text
        assert str(len(self.DISCORD_TOKEN)) not in resp.text

    def test_two_tokens_without_a_public_part_answer_the_same_neutral_hint(self):
        """GIVEN two configurations whose tokens carry nothing the hint may repeat
        THEN both answer one neutral line: nothing this route prints singles out which
        credential is stored, which is the point of not deriving a hint from it."""
        from server.routes.channels import _mask_hint

        first = _mask_hint("!!not-a-public-id!!..secret-material")
        second = _mask_hint("!!not-a-public-id!!..other-material")

        assert first == second == "token stored"
        assert "secret" not in first and "other" not in second
