"""Ephe – telegram_bot: channel runner with QR pairing (R24).

Outbound-only long polling against the official Bot API ("no forced cloud
dependency": polling, no inbound port, no external service in between). The
transport is abstracted (``TelegramTransport``) so the full pairing roundtrip
is testable without a real bot token (``FakeTransport``) — the real one is a
thin httpx client.

Message contract (threat model §6):
  - Fail-closed: without an allowlist entry the bot NEVER answers substantively;
    ``/start <token>`` is the only path that can pair an unknown user
    (one-time, short-lived QR token, see pairing_tokens).
  - Every inbound message runs through ``guard_channel_message``
    (prompt-injection defense: the untrusted-data wrap).
  - Channel sessions are NEVER interactive: ``channel_approval_policy`` declines
    mutating tools conservatively without confirmation — the approval gate from
    ``core.tools.approval`` and the R23 audit apply unchanged.
  - PNG artifacts in an answer are sent back as a photo (marker line
    ``PNG_FILE:<path>`` from the standard pipeline).
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable

from core.audit_log import audit_event
from core.channels.injection_guard import (
    UNTRUSTED_DATA_CLOSE as UNTRUSTED_CLOSE,
    UNTRUSTED_DATA_OPEN as UNTRUSTED_OPEN,
    guard_channel_message,
)
from core.channels.pairing import (
    add_device,
    channel_approval_policy,
    load_pairing,
)
from core.channels.pairing_tokens import ConsumeOutcome, consume_pairing_token

# Type import (no cycle: core.react does not import core.channels)
from core.react import react_loop

ANSWER_FN = Callable[[str, str], Awaitable[str]]

TELEGRAM_API_BASE = "https://api.telegram.org"
LONG_POLL_TIMEOUT_S = 15.0          # stop latency ≤ timeout (documented)
MAX_BACKOFF_S = 30.0
INITIAL_BACKOFF_S = 0.5
MAX_OUT_MESSAGE_CHARS = 4000        # Telegram limit 4096 — safety margin
PNG_MARKER_RE = re.compile(r"^PNG_FILE:(.+)$", re.MULTILINE)

STATE_FILENAME = "channel_state.json"       # long-polling offset (restart-safe)
SESSIONS_FILENAME = "channel_sessions.json"  # chat_id → session mapping


class TransportError(RuntimeError):
    """Network or API error of the transport — the runner survives it with backoff."""


# Transport abstraction


@dataclass(frozen=True)
class TelegramUpdate:
    """Normalized message update (only what the channel needs)."""

    update_id: int
    chat_id: int
    user_id: int | None
    text: str
    user_name: str = ""
    message_id: int = 0


class TelegramTransport:
    """Minimal interface: long polling in, messages/photos out."""

    async def get_updates(self, offset: int, timeout_s: float) -> list[TelegramUpdate]:
        raise NotImplementedError

    async def send_message(self, chat_id: int, text: str) -> None:
        raise NotImplementedError

    async def send_photo(self, chat_id: int, path: Path) -> None:
        raise NotImplementedError

    async def bot_username(self) -> str | None:
        raise NotImplementedError


class HttpxTelegramTransport(TelegramTransport):
    """Thin httpx client for the official Bot API (polling)."""

    def __init__(self, token: str, api_base: str = TELEGRAM_API_BASE) -> None:
        self._token = token.strip()
        self._base = f"{api_base.rstrip('/')}/bot{self._token}"
        self._username: str | None = None

    async def _call(self, method: str, payload: dict | None = None) -> dict:
        import httpx

        try:
            async with httpx.AsyncClient(timeout=max(LONG_POLL_TIMEOUT_S + 5, 20.0)) as client:
                resp = await client.post(f"{self._base}/{method}", json=payload)
        except (httpx.HTTPError, OSError) as exc:  # network / timeout / DNS
            raise TransportError(f"Telegram API not reachable: {exc}") from exc
        if resp.status_code == 429:
            retry_after = 5
            try:
                retry_after = int(resp.json().get("parameters", {}).get("retry_after", 5))
            except Exception:
                pass
            raise TransportError(f"rate limited (retry after {retry_after}s)")
        if resp.status_code != 200:
            raise TransportError(f"Telegram-API {method} → HTTP {resp.status_code}")
        data = resp.json()
        if not data.get("ok"):
            raise TransportError(f"Telegram-API {method} → {data.get('description', 'ok=false')}")
        return data.get("result", {})

    async def get_updates(self, offset: int, timeout_s: float) -> list[TelegramUpdate]:
        result = await self._call(
            "getUpdates",
            {
                "offset": offset,
                "timeout": int(timeout_s),
                "allowed_updates": ["message"],
            },
        )
        updates: list[TelegramUpdate] = []
        for raw in result:
            msg = raw.get("message") or {}
            chat = msg.get("chat") or {}
            sender = msg.get("from") or {}
            updates.append(
                TelegramUpdate(
                    update_id=int(raw.get("update_id", 0)),
                    chat_id=int(chat.get("id", 0)),
                    user_id=int(sender["id"]) if sender.get("id") is not None else None,
                    text=str(msg.get("text") or msg.get("caption") or ""),
                    user_name=(sender.get("first_name") or sender.get("username") or ""),
                    message_id=int(msg.get("message_id", 0)),
                )
            )
        return updates

    async def send_message(self, chat_id: int, text: str) -> None:
        # Chunking (Telegram limit 4096) — plain text, no parse_mode
        # (Markdown would be a second injection surface).
        for start in range(0, max(len(text), 1), MAX_OUT_MESSAGE_CHARS):
            await self._call(
                "sendMessage", {"chat_id": chat_id, "text": text[start : start + MAX_OUT_MESSAGE_CHARS]}
            )

    async def send_photo(self, chat_id: int, path: Path) -> None:
        import httpx

        if not path.exists():
            raise TransportError(f"image not found: {path}")
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                with path.open("rb") as fh:
                    resp = await client.post(
                        f"{self._base}/sendPhoto",
                        data={"chat_id": str(chat_id)},
                        files={"photo": (path.name, fh)},
                    )
        except (httpx.HTTPError, OSError) as exc:
            raise TransportError(f"sendPhoto failed: {exc}") from exc
        if resp.status_code != 200 or not resp.json().get("ok"):
            raise TransportError(f"sendPhoto → HTTP {resp.status_code}")

    async def bot_username(self) -> str | None:
        if self._username:
            return self._username
        result = await self._call("getMe", {})
        self._username = result.get("username") or None
        return self._username


class FakeTransport(TelegramTransport):
    """Test transport: injected updates, sent messages/photos.

    Allows the full pairing E2E roundtrip without a real bot token and
    without network. ``failures`` counts TransportErrors at the start of
    ``get_updates`` (backoff test).
    """

    def __init__(
        self,
        updates: list[TelegramUpdate] | None = None,
        failures: int = 0,
    ) -> None:
        self.pending: list[TelegramUpdate] = list(updates or [])
        self.failures = int(failures)
        self.sent_messages: list[tuple[int, str]] = []
        self.sent_photos: list[Path] = []

    async def get_updates(self, offset: int, timeout_s: float) -> list[TelegramUpdate]:
        if self.failures > 0:
            self.failures -= 1
            raise TransportError("fake transport down")
        batch = self.pending
        self.pending = []
        await asyncio.sleep(0)  # fairness for the event loop
        return batch

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent_messages.append((chat_id, text))

    async def send_photo(self, chat_id: int, path: Path) -> None:
        self.sent_photos.append(path)

    async def bot_username(self) -> str | None:
        return "ephe_test_bot"


# Session mapping + offset persistence


def _channels_dir_env() -> Path:
    return Path(os.environ.get("EPHE_DIR", str(Path.home() / ".ephe")))


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Default bridge: channel message → the real Ephe pipeline ──────────────────


async def default_channel_answer(session_id: str, text: str) -> str:
    """Runs a channel message through the same pipeline as the PWA:
    react_loop (tool use + R23 audit) with the channel approval policy
    (mutating tools are declined conservatively without confirmation),
    history via multi_session, auto-memory hook like /chat."""
    from core.model_provider import get_active_provider
    from core.multi_session import load_messages, save_messages
    from core.types import Message
    from core.auto_memory import maybe_store_turn

    provider = get_active_provider()
    history = load_messages(session_id) if session_id else []
    # Message is a TypedDict — so plain dict rows; attribute access
    # (m.role) fails on dicts, indexing is the canonical way.
    context = [
        {"role": m["role"], "content": m["content"]}
        for m in history[-16:]
        if isinstance(m, dict) and m.get("role") and m.get("content") is not None
    ]

    answer = await react_loop(
        question=text,
        model=provider.model,
        context=context,
        provider_config=provider,
        approval_policy=channel_approval_policy(),
        # n1-memory: the channel turn carries its session, so the provenance trail
        # (injected memories) records who ran it — same field the REST call site passes.
        session_id=session_id,
    )
    final = answer or ""

    if session_id:
        save_messages(
            session_id,
            list(history)
            + [Message(role="user", content=text), Message(role="assistant", content=final)],
        )
    maybe_store_turn(text, final)
    return final


def _extract_images(text: str) -> tuple[str, list[Path]]:
    """Pulls the ``PNG_FILE:<path>`` markers out of the answer (photo sending)."""
    paths: list[Path] = []
    for match in PNG_MARKER_RE.finditer(text):
        candidate = Path(match.group(1).strip())
        if candidate.exists() and candidate not in paths:
            paths.append(candidate)
    cleaned = PNG_MARKER_RE.sub("", text)
    return cleaned.strip(), paths


# Runner


class TelegramChannelRunner:
    """Asynchronous long-polling runner (asyncio task, outbound-only).

    Hardening: exponential backoff with jitter on transport errors (no
    exit), update offset persisted (no re-processing after restart),
    stop via ``stop()`` (latency ≤ long-poll timeout), error surface via
    ``on_error``/``last_error`` for the settings UI.
    """

    def __init__(
        self,
        transport: TelegramTransport,
        *,
        answer: ANSWER_FN | None = None,
        pairing_path: Path | None = None,
        tokens_path: Path | None = None,
        sessions_path: Path | None = None,
        state_path: Path | None = None,
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        self.transport = transport
        self.answer = answer or default_channel_answer
        self.pairing_path = pairing_path  # None → ~/.ephe default
        self.tokens_path = tokens_path
        self.sessions_path = sessions_path or (
            _channels_dir_env() / SESSIONS_FILENAME
        )
        self.state_path = state_path or (_channels_dir_env() / STATE_FILENAME)
        self.on_error = on_error
        self.last_error: str | None = None
        self.started_at: str | None = None
        self.backoff_seconds = INITIAL_BACKOFF_S  # test knob (production: backoff)
        self._offset = int(_load_json(self.state_path).get("offset", 0))
        self._stop = asyncio.Event()
        self._drained = asyncio.Event()
        self._sessions: dict[str, dict[str, Any]] = _load_json(self.sessions_path)

    # Lifecycle

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        """Long-polling loop: survives transport errors, terminates only via stop()."""
        self.started_at = _now_iso()
        backoff = self.backoff_seconds
        while not self._stop.is_set():
            try:
                updates = await self.transport.get_updates(
                    self._offset, LONG_POLL_TIMEOUT_S
                )
                for update in updates:
                    try:
                        await self.handle_update(update)
                    except Exception as exc:  # a single update must never kill the loop
                        self._surface(f"Update {update.update_id} failed: {exc}")
                    self._offset = max(self._offset, update.update_id + 1)
                self._persist_state()
                backoff = self.backoff_seconds
                if not self.pending_updates_left():
                    self._drained.set()
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

    async def wait_until_drained(self) -> None:
        """Test/UI helper: waits for one empty poll (batch processed)."""
        await self._drained.wait()

    def pending_updates_left(self) -> int:
        return 0  # FakeTransport hands out one batch; the real API returns batches as a list

    def _surface(self, message: str) -> None:
        self.last_error = message
        audit_event(
            "channel",
            tool="telegram_runner",
            decision="deny",
            status="error",
            detail=message[:200],
        )
        if self.on_error:
            try:
                self.on_error(message)
            except Exception:
                pass

    def _persist_state(self) -> None:
        _atomic_json(self.state_path, {"offset": self._offset, "updated_at": _now_iso()})

    # Session mapping

    def session_for(self, user_id: int) -> str:
        entry = self._sessions.get(str(user_id)) or {}
        return str(entry.get("session_id", ""))

    def _ensure_session(self, user_id: int, *, fresh: bool = False) -> str:
        from core.multi_session import create_session, get_session

        entry = self._sessions.get(str(user_id))
        if not fresh and entry and get_session(str(entry.get("session_id", ""))):
            return str(entry["session_id"])
        session = create_session(f"Telegram {user_id}")
        self._sessions[str(user_id)] = {
            "session_id": session["id"],
            "paired_at": (entry or {}).get("paired_at", _now_iso()),
            "updated_at": _now_iso(),
        }
        _atomic_json(self.sessions_path, self._sessions)
        return session["id"]

    def _drop_session(self, user_id: int) -> None:
        """Revoke cleanup: drop the mapping (session files stay for the UI)."""
        if self._sessions.pop(str(user_id), None) is not None:
            _atomic_json(self.sessions_path, self._sessions)

    # Incoming updates

    async def handle_update(self, update: TelegramUpdate) -> None:
        if update.user_id is None:
            return  # channel posts and similar without a sender — ignore fail-closed

        text = (update.text or "").strip()
        chat_id = update.chat_id
        pairing = load_pairing(self.pairing_path)

        # 1) The ONLY pairing path for unknown users: /start <token>
        if text.lower().startswith("/start"):
            await self._handle_start(update, text)
            return

        # 2) Unknown user → clear refusal, NEVER answer substantively
        if not is_allowed_user(pairing, update.user_id):
            audit_event(
                "channel",
                tool="telegram_message",
                decision="deny",
                status="unknown_user",
                detail=f"message from unpaired telegram user {update.user_id}",
            )
            self._drop_session(update.user_id)  # revoke cleanup (effective immediately)
            await self.transport.send_message(
                chat_id,
                "🔒 This account is not paired with Ephe. "
                "Pair it via the QR code in Ephe settings (Desktop).",
            )
            return

        # 3) Commands
        if text == "/new":
            self._ensure_session(update.user_id, fresh=True)
            await self.transport.send_message(chat_id, "🆕 New session started.")
            return
        if text == "/status":
            sid = self.session_for(update.user_id)
            await self.transport.send_message(
                chat_id,
                f"🟢 Paired as {update.user_name or update.user_id}.\n"
                f"Session: {sid or '(none)'}\nMutating tools need desktop confirmation.",
            )
            return
        if not text:
            return  # sticker/attachment without text — deliberately ignored (documented)

        # 4) message → injection guard → pipeline → answer (+ photo marker)
        guarded = guard_channel_message(text)
        session_id = self.session_for(update.user_id) or self._ensure_session(update.user_id)
        try:
            answer = await self.answer(session_id, guarded.wrapped)
        except Exception as exc:
            self._surface(f"answer failed: {exc}")
            await self.transport.send_message(
                chat_id,
                "⚠️ The engine could not answer the request. "
                "Check on the desktop whether the model is reachable.",
            )
            return

        body, images = _extract_images(answer)
        for image_path in images:
            try:
                await self.transport.send_photo(chat_id, image_path)
            except Exception as exc:
                self._surface(f"sendPhoto failed: {exc}")
        await self.transport.send_message(chat_id, body or "(empty response)")

    async def _handle_start(self, update: TelegramUpdate, text: str) -> None:
        token = text[6:].strip()  # split off the "/start" prefix
        if token:
            outcome = consume_pairing_token(token, update.user_id, path=self.tokens_path)
        else:
            outcome = ConsumeOutcome(status="invalid", detail="/start ohne Token")

        if outcome.ok:
            add_device(update.user_id, label=update.user_name or "", path=self.pairing_path)
            self._ensure_session(update.user_id, fresh=True)
            await self.transport.send_message(
                update.chat_id,
                f"✅ Ephe is now paired with Telegram account "
                f"“{update.user_name or update.user_id}” (ID {update.user_id}).\n"
                f"Just write to me — /new starts a fresh session.",
            )
            return

        # Idempotent against Telegram re-delivery: a clear, non-alarming message
        reason = {
            "used": "this QR code was already paired — nothing to do.",
            "expired": "this QR code has expired — please scan the current QR code again.",
            "locked": "too many attempts — please wait a moment and scan again.",
        }.get(outcome.status, "this QR code is invalid — please scan the current QR code again.")
        audit_event(
            "channel",
            tool="telegram_message",
            decision="deny",
            status=f"start_{outcome.status}",
            detail=f"pairing refused for user {update.user_id}",
        )
        await self.transport.send_message(update.chat_id, f"ℹ️ {reason}")


def is_allowed_user(pairing, user_id: int) -> bool:
    """Small indirection for tests and readability (PairingConfig.is_allowed)."""
    return pairing.is_allowed(user_id)


__all__ = [
    "TelegramUpdate",
    "TelegramTransport",
    "HttpxTelegramTransport",
    "FakeTransport",
    "TelegramChannelRunner",
    "TransportError",
    "default_channel_answer",
    "is_allowed_user",
    "UNTRUSTED_OPEN",
    "UNTRUSTED_CLOSE",
    "STATE_FILENAME",
    "SESSIONS_FILENAME",
    "LONG_POLL_TIMEOUT_S",
]
