"""server/routes/channels.py – channel admin API (R24, Telegram).

Admin surface for the Telegram channel:

  GET    /api/channels/telegram/status            token configured? poller running?
  POST   /api/channels/telegram/token             store the bot token in the vault (keyring → 0600 file)
  DELETE /api/channels/telegram/token             delete the bot token + stop the poller
  POST   /api/channels/telegram/start             start the long-polling runner (outbound-only)
  POST   /api/channels/telegram/stop              stop the runner
  POST   /api/channels/telegram/pair              build a one-time token + t.me deep link + QR
  GET    /api/channels/telegram/devices           paired Telegram accounts
  DELETE /api/channels/telegram/devices/{user_id} revoke — drops access IMMEDIATELY

The plaintext bot token NEVER leaves the server (masked hints only); the pairing
token is one-time, valid for 10 minutes, and lives only in the QR code handed to
the desktop user. Everything is recorded in the R23 audit (kind="channel").
"""
from __future__ import annotations

import asyncio
import base64
import io
import os
import re
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.audit_log import audit_event
from core.channels.pairing import (
    delete_bot_token,
    load_bot_token,
    load_devices,
    remove_device,
    store_bot_token,
)
from core.channels.pairing_tokens import (
    DEFAULT_TTL_SECONDS,
    PairingLimitError,
    create_pairing_token,
    tokens_path,
)
from core.channels.telegram_bot import (
    FakeTransport,  # noqa: F401  (test export, see telegram_bot)
    HttpxTelegramTransport,
    TelegramChannelRunner,
    SESSIONS_FILENAME,
)

router = APIRouter(prefix="/channels", tags=["Channels"])

_BOT_TOKEN_RE = re.compile(r"^\d{3,}:[A-Za-z0-9_-]{20,}$")

# Runner singleton (one poller per process)

_runner: TelegramChannelRunner | None = None
_runner_task: asyncio.Task | None = None
_bot_username: str | None = None


def _ephe_dir() -> Path:
    return Path(os.environ.get("EPHE_DIR", str(Path.home() / ".ephe")))


def _sessions_path() -> Path:
    return _ephe_dir() / SESSIONS_FILENAME


async def shutdown_channels() -> None:
    """Lifespan-Hook: Poller-Task sauber beenden (server/main.py)."""
    global _runner, _runner_task
    if _runner is not None:
        _runner.stop()
    if _runner_task is not None and not _runner_task.done():
        _runner_task.cancel()
        try:
            await _runner_task
        except (asyncio.CancelledError, Exception):
            pass
    _runner = None
    _runner_task = None
    global _discord_runner, _discord_task
    if _discord_runner is not None:
        _discord_runner.stop()
    if _discord_task is not None and not _discord_task.done():
        _discord_task.cancel()
        try:
            await _discord_task
        except (asyncio.CancelledError, Exception):
            pass
    _discord_runner = None
    _discord_task = None


def reset_for_tests() -> None:
    """Test suture: drop the singleton references (tasks die with the portal loop)."""
    global _runner, _runner_task, _bot_username
    _runner = None
    _runner_task = None
    _bot_username = None


def _is_running() -> bool:
    return bool(_runner_task is not None and not _runner_task.done())


# Schemas


class TokenRequest(BaseModel):
    token: str


class TokenResponse(BaseModel):
    mode: str
    masked: str


class StartResponse(BaseModel):
    running: bool


class PairingResponse(BaseModel):
    deep_link: str
    qr_base64: str
    issued_at: float
    expires_at: float
    ttl_seconds: int


class DeviceEntry(BaseModel):
    user_id: int
    label: str
    paired_at: str


# Helpers


def _qr_base64(payload: str) -> str:
    import qrcode

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _require_token() -> str:
    token = load_bot_token()
    if not token:
        audit_event(
            "channel", tool="telegram_admin", decision="deny",
            status="no_token", detail="telegram action without configured token",
        )
        raise HTTPException(
            status_code=409,
            detail="No bot token configured. Set it up under Settings -> Mobile -> Telegram first.",
        )
    return token


# Routes


@router.get("/telegram/status")
def telegram_status() -> dict:
    token = load_bot_token()
    return {
        "token_configured": bool(token),
        "token_masked": None if not token else _mask_hint(token),
        "running": _is_running(),
        "bot_username": _bot_username,
        "paired_count": len(load_devices(_ephe_dir() / "channel_pairing.json")),
        "session_count": len(_read_sessions()),
        "last_error": _runner.last_error if _runner else None,
    }


def _mask_hint(token: str) -> str:
    tail = token[-4:] if len(token) > 8 else ""
    return f"…{tail} ({len(token)} Zeichen)"


def _read_sessions() -> dict:
    import json

    p = _sessions_path()
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


@router.post("/telegram/token", response_model=TokenResponse)
def save_telegram_token(req: TokenRequest) -> TokenResponse:
    token = req.token.strip()
    if not _BOT_TOKEN_RE.match(token):
        raise HTTPException(
            status_code=422,
            detail="This does not look like a Telegram bot token (format: 123456:ABC-DEF…). "
            "Create a bot with @BotFather and paste the token here.",
        )
    mode = store_bot_token(token)
    audit_event(
        "channel", tool="telegram_admin", decision="allow",
        status="stored", detail="telegram_token_stored",
    )
    tail = token[-4:] if len(token) > 8 else ""
    return TokenResponse(mode=mode, masked=f"…{tail} ({len(token)} Zeichen)")


@router.delete("/telegram/token")
def remove_telegram_token() -> dict:
    delete_bot_token()
    global _bot_username
    _bot_username = None
    if _runner is not None:
        _runner.stop()
    audit_event(
        "channel", tool="telegram_admin", decision="allow",
        status="deleted", detail="telegram_token_deleted",
    )
    return {"ok": True}


@router.post("/telegram/start", response_model=StartResponse)
async def start_telegram() -> StartResponse:
    global _runner, _runner_task
    token = _require_token()
    if _is_running():
        return StartResponse(running=True)

    _runner = TelegramChannelRunner(
        HttpxTelegramTransport(token),
        pairing_path=_ephe_dir() / "channel_pairing.json",
        tokens_path=tokens_path(),
        sessions_path=_sessions_path(),
    )
    _runner_task = asyncio.create_task(_runner.run(), name="telegram-channel-runner")
    audit_event(
        "channel", tool="telegram_admin", decision="allow",
        status="started", detail="telegram_channel_started",
    )
    return StartResponse(running=True)


@router.post("/telegram/stop", response_model=StartResponse)
async def stop_telegram() -> StartResponse:
    global _runner_task
    if _runner is not None:
        _runner.stop()
    if _runner_task is not None and not _runner_task.done():
        _runner_task.cancel()
        try:
            await _runner_task
        except (asyncio.CancelledError, Exception):
            pass
    _runner_task = None
    audit_event(
        "channel", tool="telegram_admin", decision="allow",
        status="stopped", detail="telegram_channel_stopped",
    )
    return StartResponse(running=False)


@router.post("/telegram/pair", response_model=PairingResponse)
async def create_pairing_qr() -> PairingResponse:
    global _bot_username
    token_bot = _require_token()

    if not _bot_username:
        transport = HttpxTelegramTransport(token_bot)
        try:
            _bot_username = await transport.bot_username()
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Telegram bot not reachable ({exc}). Is the token valid and is the network up?",
            ) from exc
    if not _bot_username:
        raise HTTPException(status_code=502, detail="could not determine the bot username (getMe).")

    try:
        token = create_pairing_token(path=tokens_path())
    except PairingLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    now = time.time()
    deep_link = f"https://t.me/{_bot_username}?start={token}"
    audit_event(
        "channel", tool="telegram_admin", decision="allow",
        status="created", detail="telegram_pairing_qr_created",
    )
    return PairingResponse(
        deep_link=deep_link,
        qr_base64=_qr_base64(deep_link),
        issued_at=now,
        expires_at=now + DEFAULT_TTL_SECONDS,
        ttl_seconds=DEFAULT_TTL_SECONDS,
    )


@router.get("/telegram/devices", response_model=list[DeviceEntry])
def list_telegram_devices() -> list[DeviceEntry]:
    return [
        DeviceEntry(user_id=d.user_id, label=d.label, paired_at=d.paired_at)
        for d in load_devices(_ephe_dir() / "channel_pairing.json")
    ]


@router.delete("/telegram/devices/{user_id}")
async def revoke_telegram_device(user_id: int) -> dict:
    devices = {d.user_id for d in load_devices(_ephe_dir() / "channel_pairing.json")}
    if user_id not in devices:
        raise HTTPException(status_code=404, detail="device not found.")
    remove_device(user_id, path=_ephe_dir() / "channel_pairing.json")
    # drop the account's session mapping (immediate disconnect)
    sessions = _read_sessions()
    if str(user_id) in sessions:
        sessions.pop(str(user_id))
        _sessions_path().parent.mkdir(parents=True, exist_ok=True)
        tmp = _sessions_path().with_suffix(".json.tmp")
        import json

        tmp.write_text(json.dumps(sessions, indent=2) + "\n", encoding="utf-8")
        tmp.replace(_sessions_path())
        try:
            _sessions_path().chmod(0o600)
        except OSError:
            pass
    audit_event(
        "channel", tool="telegram_admin", decision="allow",
        status="revoked", detail="telegram_device_revoked",
    )
    return {"ok": True, "user_id": user_id}


# W3d: Discord channel (R24 pattern, 2026-09-09)

from core.channels.discord import (  # noqa: E402
    DiscordChannelRunner,
    HttpxDiscordTransport,
    TOKEN_FILENAME as DISCORD_TOKEN_FILENAME,
)

_DISCORD_TOKEN_RE = re.compile(r"^\d{10,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}$")

_discord_runner: DiscordChannelRunner | None = None
_discord_task: asyncio.Task | None = None


def reset_discord_for_tests() -> None:
    """Test suture: drop the Discord singletons (tasks die with the portal loop)."""
    global _discord_runner, _discord_task
    _discord_runner = None
    _discord_task = None


def _discord_token_path() -> Path:
    return _ephe_dir() / DISCORD_TOKEN_FILENAME


def _load_discord_token() -> str | None:
    p = _discord_token_path()
    if not p.exists():
        return None
    try:
        raw = p.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return raw or None


@router.get("/discord/status")
def discord_status() -> dict:
    token = _load_discord_token()
    return {
        "configured": bool(token),
        "token_masked": None if not token else _mask_hint(token),
        "running": bool(_discord_task is not None and not _discord_task.done()),
        "last_error": _discord_runner.last_error if _discord_runner else None,
        "message": "" if token else "not configured",
    }


@router.post("/discord/token", response_model=TokenResponse)
def save_discord_token(req: TokenRequest) -> TokenResponse:
    token = req.token.strip()
    if not _DISCORD_TOKEN_RE.match(token):
        raise HTTPException(
            status_code=422,
            detail="This does not look like a Discord bot token (format: 143289….abc….ABC). "
            "Create a bot in the Developer Portal and paste the token here.",
        )
    mode = store_bot_token(token, path=_discord_token_path())
    audit_event(
        "channel", tool="discord_admin", decision="allow",
        status="stored", detail="discord_token_stored",
    )
    return TokenResponse(mode=mode, masked=_mask_hint(token))


@router.delete("/discord/token")
def remove_discord_token() -> dict:
    p = _discord_token_path()
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass
    global _discord_runner, _discord_task
    if _discord_runner is not None:
        _discord_runner.stop()
    _discord_runner = None
    _discord_task = None
    audit_event(
        "channel", tool="discord_admin", decision="allow",
        status="deleted", detail="discord_token_deleted",
    )
    return {"ok": True}


@router.post("/discord/start", response_model=StartResponse)
async def start_discord() -> StartResponse:
    global _discord_runner, _discord_task
    token = _load_discord_token()
    if not token:
        raise HTTPException(
            status_code=409,
            detail="No bot token configured. Set it up under Settings -> Mobile -> Discord first.",
        )
    if _discord_task is not None and not _discord_task.done():
        return StartResponse(running=True)
    _discord_runner = DiscordChannelRunner(
        HttpxDiscordTransport(token),
        pairing_path=_ephe_dir() / "channel_pairing.json",
        tokens_path=tokens_path(),
        sessions_path=_ephe_dir() / "discord_sessions.json",
        state_path=_ephe_dir() / "discord_state.json",
    )
    _discord_task = asyncio.create_task(_discord_runner.run(), name="discord-channel-runner")
    audit_event(
        "channel", tool="discord_admin", decision="allow",
        status="started", detail="discord_channel_started",
    )
    return StartResponse(running=True)


@router.post("/discord/stop", response_model=StartResponse)
async def stop_discord() -> StartResponse:
    global _discord_task
    if _discord_runner is not None:
        _discord_runner.stop()
    if _discord_task is not None and not _discord_task.done():
        _discord_task.cancel()
        try:
            await _discord_task
        except (asyncio.CancelledError, Exception):
            pass
    _discord_task = None
    audit_event(
        "channel", tool="discord_admin", decision="allow",
        status="stopped", detail="discord_channel_stopped",
    )
    return StartResponse(running=False)
