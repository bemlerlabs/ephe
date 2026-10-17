"""Ephe – discord: the second channel (R24 pattern, 2026-09-09).

Outbound-only REST polling against the Discord bot API (v10,
https://discord.com/api/v10): no inbound port, no forced cloud dependency.
Same rules as the Telegram run: ``start <token>`` pairs through a one-time
QR token, unknown senders never get a substantive answer, mutating tools
stay behind the approval gate. The plaintext token lives in the 0600 file
or in the keyring; without a token the status says honestly ``not configured``.
"""
from __future__ import annotations

import asyncio
import json
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from core.audit_log import audit_event
from core.channels.injection_guard import guard_channel_message
from core.channels.pairing import (
    add_device,
    load_pairing,
)
from core.channels.pairing_tokens import ConsumeOutcome, consume_pairing_token

ANSWER_FN = Callable[[str, str], Awaitable[str]]

DISCORD_API_BASE = "https://discord.com/api/v10"
LONG_POLL_TIMEOUT_S = 3.0           # a REST poll returns at once; this is only the socket timeout
MAX_BACKOFF_S = 30.0
INITIAL_BACKOFF_S = 0.5
POLL_INTERVAL_S = 0.05
MAX_OUT_MESSAGE_CHARS = 2000
STATE_FILENAME = "discord_state.json"
SESSIONS_FILENAME = "discord_sessions.json"
TOKEN_FILENAME = "discord_token.json"
PAIRING_FILENAME = "channel_pairing.json"


class TransportError(RuntimeError):
    """Network or API error of the transport — the runner survives it with backoff."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _channels_dir_env() -> Path:
    import os

    return Path(os.environ.get("EPHE_DIR", str(Path.home() / ".ephe")))


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


# Transport


class DiscordTransport:
    """Minimal interface: message polling in, text answer out."""

    async def get_me(self) -> str:
        raise NotImplementedError

    async def poll_channel(self, channel_id: str, after: str) -> list[dict]:
        raise NotImplementedError

    async def send(self, channel_id: str, content: str) -> None:
        raise NotImplementedError


class HttpxDiscordTransport(DiscordTransport):
    """Thin httpx client for the Discord bot API (REST, outbound-only)."""

    def __init__(self, token: str, api_base: str = DISCORD_API_BASE) -> None:
        self._token = token.strip()
        self._base = api_base.rstrip("/")

    async def _call(self, method_path: str, payload: dict | None = None) -> Any:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=LONG_POLL_TIMEOUT_S + 5) as client:
                resp = await client.request(
                    "GET" if payload is None else "POST",
                    f"{self._base}{method_path}",
                    json=payload,
                    headers={"Authorization": self._token},
                )
        except (httpx.HTTPError, OSError) as exc:
            raise TransportError(f"Discord API not reachable: {exc}") from exc
        if resp.status_code == 429:
            raise TransportError("rate limited (retry after backoff)")
        if resp.status_code != 200:
            raise TransportError(f"Discord API {method_path} → HTTP {resp.status_code}")
        return resp.json()

    async def get_me(self) -> str:
        data = await self._call("/users/@me")
        return str((data or {}).get("username", ""))

    async def poll_channel(self, channel_id: str, after: str) -> list[dict]:
        data = await self._call(
            f"/channels/{channel_id}/messages?limit=50&after={after}"
        )
        return list(data or [])

    async def send(self, channel_id: str, content: str) -> None:
        await self._call(f"/channels/{channel_id}/messages", {"content": content})


class FakeDiscordTransport(DiscordTransport):
    """Deterministic transport for tests (no network): batch + sent record."""

    def __init__(self, batch: list[dict], username: str = "ephe-fake") -> None:
        self._batch = batch
        self._username = username
        self.sent: list[tuple[str, str]] = []

    async def get_me(self) -> str:
        return self._username

    async def poll_channel(self, channel_id: str, after: str) -> list[dict]:
        out, self._batch = self._batch, []
        return out

    async def send(self, channel_id: str, content: str) -> None:
        self.sent.append((channel_id, content))


# Runner


class DiscordChannelRunner:
    """Asynchronous REST polling runner (asyncio task, outbound-only).

    Offset per channel = the last snowflake (string, monotonic). Stop via stop(),
    errors land in ``last_error``; batch handling follows the Telegram run.
    """

    def __init__(
        self,
        transport: DiscordTransport,
        *,
        answer: ANSWER_FN | None = None,
        pairing_path: Path | None = None,
        tokens_path: Path | None = None,
        sessions_path: Path | None = None,
        state_path: Path | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self.transport = transport
        if answer is None:
            from core.channels.telegram_bot import default_channel_answer

            answer = default_channel_answer
        self.answer = answer
        base = _channels_dir_env()
        self.pairing_path = pairing_path or (base / PAIRING_FILENAME)
        self.tokens_path = tokens_path
        self.sessions_path = sessions_path or (base / SESSIONS_FILENAME)
        self.state_path = state_path or (base / STATE_FILENAME)
        self.on_error = on_error
        self.last_error: str | None = None
        self.started_at: str | None = None
        self.backoff_seconds = INITIAL_BACKOFF_S
        self._offsets: dict[str, str] = {
            str(k): str(v) for k, v in _load_json(self.state_path).items() if k != "updated_at"
        }
        self._sessions: dict[str, dict[str, Any]] = _load_json(self.sessions_path)
        self._stop = asyncio.Event()
        self._drained = asyncio.Event()
        self._channel_ids: list[str] = []

    def register_channels(self, *channel_ids: str) -> None:
        for cid in channel_ids:
            if cid and cid not in self._channel_ids:
                self._channel_ids.append(cid)

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        self.started_at = _now_iso()
        backoff = self.backoff_seconds
        while not self._stop.is_set():
            try:
                seen_any = False
                if not self._channel_ids:
                    first = await self.transport.poll_channel("", "")
                    seen_any = bool(first)
                    await self._process(first)
                    for msg in first:
                        cid = str(msg.get("channel_id", ""))
                        if cid and cid not in self._channel_ids:
                            self._channel_ids.append(cid)
                            max_id = max((str(m.get("id", "")) for m in first if str(m.get("channel_id", "")) == cid), default="")
                            if max_id:
                                self._offsets[cid] = max_id
                    if first:
                        self._persist_state()
                for cid in self._channel_ids:
                    after = self._offsets.get(cid, "")
                    batch = await self.transport.poll_channel(cid, after)
                    if batch:
                        seen_any = True
                        await self._process(batch)
                        max_id = max((str(m.get("id", "")) for m in batch), default=after)
                        if max_id > after:
                            self._offsets[cid] = max_id
                            self._persist_state()
                if seen_any:
                    self._drained.set()
                backoff = self.backoff_seconds
                await asyncio.sleep(POLL_INTERVAL_S)  # keep the timers and friends on the loop from starving
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._surface(str(exc))
                jitter = random.uniform(0, backoff * 0.3)
                try:
                    await asyncio.sleep(backoff + jitter)
                except asyncio.CancelledError:
                    raise
                backoff = min(backoff * 2, MAX_BACKOFF_S)

    async def _process(self, batch: list[dict]) -> None:
        for msg in batch:
            try:
                await self.handle_message(msg)
            except Exception as exc:  # a single update must never kill the loop
                self._surface(f"message {msg.get('id')} failed: {exc}")

    async def wait_until_drained(self) -> None:
        await self._drained.wait()

    def _surface(self, message: str) -> None:
        self.last_error = message
        audit_event(
            "channel", tool="discord_runner", decision="deny",
            status="error", detail=message[:200],
        )
        if self.on_error:
            try:
                self.on_error(message)
            except Exception:
                pass

    def _persist_state(self) -> None:
        payload = {**self._offsets, "updated_at": _now_iso()}
        _atomic_json(self.state_path, payload)

    # Session mapping (like Telegram: one session per user, never interactive)

    def _ensure_session(self, user_id: str, *, fresh: bool = False) -> str:
        from core.multi_session import create_session, get_session

        entry = self._sessions.get(str(user_id))
        if not fresh and entry and get_session(str(entry.get("session_id", ""))):
            return str(entry["session_id"])
        session = create_session(f"Discord {user_id}")
        self._sessions[str(user_id)] = {
            "session_id": session["id"],
            "paired_at": (entry or {}).get("paired_at", _now_iso()),
            "updated_at": _now_iso(),
        }
        _atomic_json(self.sessions_path, self._sessions)
        return session["id"]

    # Message handling

    async def handle_message(self, msg: dict) -> None:
        author = msg.get("author") or {}
        user_id = str(author.get("id", ""))
        channel_id = str(msg.get("channel_id", ""))
        text = str(msg.get("content", "") or "").strip()
        if not user_id:
            return  # no sender → ignore fail-closed

        if text.lower().startswith("start "):
            await self._handle_start(channel_id, user_id, text)
            return

        pairing = load_pairing(self.pairing_path)
        if not pairing.is_allowed(user_id):
            audit_event(
                "channel", tool="discord_message", decision="deny",
                status="unknown_user", detail=f"unpaired discord user {user_id}",
            )
            await self.transport.send(
                channel_id,
                "🔒 This account is not paired with Ephe. Pair it via the QR "
                "code in Ephe settings (Desktop).",
            )
            return

        if not text:
            return
        guarded = guard_channel_message(text)
        session_id = self._sessions.get(user_id, {}).get("session_id") or self._ensure_session(user_id)
        try:
            answer = await self.answer(session_id, guarded.wrapped)
        except Exception as exc:
            self._surface(f"answer failed: {exc}")
            await self.transport.send(
                channel_id, "⚠️ The engine could not answer the request."
            )
            return
        await self.transport.send(channel_id, (answer or "(empty response)")[:MAX_OUT_MESSAGE_CHARS])

    async def _handle_start(self, channel_id: str, user_id: str, text: str) -> None:
        token = text[6:].strip()
        outcome = (
            consume_pairing_token(token, int(user_id), path=self.tokens_path)
            if token
            else ConsumeOutcome(status="invalid", detail="start ohne Token")
        )
        if outcome.ok:
            add_device(int(user_id), label=str((user_id)), path=self.pairing_path)
            self._ensure_session(user_id, fresh=True)
            await self.transport.send(
                channel_id,
                f"✅ Ephe is now paired with Discord account {user_id}. "
                "Just write to me.",
            )
            return
        reason = {
            "used": "this QR code was already paired — nothing to do.",
            "expired": "this QR code has expired — scan the current one again.",
            "locked": "too many attempts — please wait and scan again.",
        }.get(outcome.status, "this QR code is invalid — scan the current one again.")
        audit_event(
            "channel", tool="discord_message", decision="deny",
            status=f"start_{outcome.status}", detail=f"pairing refused for {user_id}",
        )
        await self.transport.send(channel_id, f"ℹ️ {reason}")


__all__ = [
    "DiscordTransport",
    "HttpxDiscordTransport",
    "FakeDiscordTransport",
    "DiscordChannelRunner",
    "TransportError",
    "DISCORD_API_BASE",
    "STATE_FILENAME",
    "SESSIONS_FILENAME",
    "TOKEN_FILENAME",
    "PAIRING_FILENAME",
    "LONG_POLL_TIMEOUT_S",
]
