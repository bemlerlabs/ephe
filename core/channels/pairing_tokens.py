"""Ephe – pairing_tokens: single-use pairing tokens for the Telegram QR (R24).

The cross-device QR pairing flow (like leading AI clients):

  1. The desktop user clicks „Gerät koppeln" (the German product label) → the server  # language-gate: ignore (quoted product label, app/src/locales/de.json:730 telegramConnect — the QR flow is named after what the surface shows)
     generates a CSPRNG token (``secrets.token_urlsafe(24)`` → 32 characters, fits
     into the 64-character deep-link payload limit of t.me).
  2. The QR code contains ``https://t.me/<bot>?start=<token>`` — scanning it opens
     Telegram in the bot chat and delivers ``/start <token>``.
  3. The bot consumes the token ATOMICALLY (single-use, TTL), adds the Telegram
     user ID to the pairing allowlist and confirms on both sides (anti-QR-phishing:
     the user sees in the chat what was paired).

Threat model (docs/SECURITY_THREAT_MODEL.md §6 QR pairing):
- C3: only the SHA-256 hash is persisted — the plaintext lives exactly once
  (in the desktop user's QR) and is never logged or stored.
- Replay: single-use; Telegram re-delivery of ``/start`` is rejected idempotently
  as ``used`` instead of pairing anew.
- Brute force: failed consumes lock the window (fail-closed, even for the correct
  token).
- Corrupt file → empty token set (fail-closed, no crash).
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.audit_log import audit_event

TOKENS_FILENAME = "channel_pairing_tokens.json"
DEFAULT_TTL_SECONDS = 600          # 10 minutes (the Cleeng „PIN-Pair" band of 1–15 min)
MAX_OPEN_TOKENS = 6                # spam cap on open (unused) tokens
MAX_FAILED_CONSUMES = 10           # brute-force lockout threshold
FAILED_WINDOW_SECONDS = 300        # 5-minute window for failed attempts


class PairingLimitError(RuntimeError):
    """Too many open tokens — the rate limit of the QR endpoint (fail-closed)."""


@dataclass(frozen=True)
class ConsumeOutcome:
    """Outcome of a token consumption (human-readable + machine-readable)."""

    status: str  # "ok" | "invalid" | "expired" | "used" | "locked"
    user_id: int | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "ok"


def tokens_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    ephe_dir = Path(os.environ.get("EPHE_DIR", str(Path.home() / ".ephe")))
    return ephe_dir / TOKENS_FILENAME


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _atomic_write_0600(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.parent.chmod(0o700)
    except OSError:
        pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _load(path: Path) -> dict[str, Any]:
    """Loads the token store; missing/corrupt → empty (fail-closed)."""
    if not path.exists():
        return {"tokens": [], "failed": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {"tokens": [], "failed": []}
        raw.setdefault("tokens", [])
        raw.setdefault("failed", [])
        return raw
    except (json.JSONDecodeError, OSError, TypeError):
        return {"tokens": [], "failed": []}


def _sweep_expired(store: dict[str, Any], now: float) -> None:
    """Clears expired tokens + stale failed attempts (in place)."""
    store["tokens"] = [t for t in store["tokens"] if float(t.get("expires_at", 0)) > now]
    window_start = now - FAILED_WINDOW_SECONDS
    store["failed"] = [f for f in store["failed"] if float(f) > window_start]


def create_pairing_token(
    path: Path | None = None,
    ttl: int = DEFAULT_TTL_SECONDS,
    now: float | None = None,
) -> str:
    """Creates a single-use token and returns the plaintext EXACTLY ONCE.

    Only the SHA-256 hash is persisted. Expired tokens are swept before creation;
    the spam cap ``MAX_OPEN_TOKENS`` counts only open (unused, valid) tokens.
    """
    now_v = float(now if now is not None else time.time())
    p = tokens_path(path)
    store = _load(p)
    _sweep_expired(store, now_v)

    if len(store["tokens"]) >= MAX_OPEN_TOKENS:
        audit_event(
            "channel",
            tool="telegram_pairing",
            decision="deny",
            status="rate_limited",
            detail="pairing_token_create_blocked",
        )
        raise PairingLimitError(
            f"Too many open pairing tokens ({MAX_OPEN_TOKENS}) — wait a moment and scan the current QR code again."
        )

    token = secrets.token_urlsafe(24)  # 32 URL-safe characters (≤ the 64 payload limit)
    store["tokens"].append(
        {
            "token_hash": _hash(token),
            "created_at": now_v,
            "expires_at": now_v + float(ttl),
            "used": False,
            "used_by": None,
        }
    )
    _atomic_write_0600(p, store)
    audit_event(
        "channel",
        tool="telegram_pairing",
        decision="allow",
        status="created",
        detail="pairing_token_created",
    )
    return token


def consume_pairing_token(
    token: str,
    user_id: int | str | None,
    path: Path | None = None,
    now: float | None = None,
) -> ConsumeOutcome:
    """Consumes a single-use token atomically (single-use, TTL, lockout).

    ``user_id`` is bound only when ``status == "ok"`` — the Telegram user ID from
    the ``/start`` update is the only source of authority for it.
    """
    now_v = float(now if now is not None else time.time())
    p = tokens_path(path)
    store = _load(p)
    # Sweep only the failure window — do NOT throw tokens away before the lookup,
    # otherwise a just-expired token returns "invalid" instead of "expired".
    window_start = now_v - FAILED_WINDOW_SECONDS
    store["failed"] = [f for f in store["failed"] if float(f) > window_start]

    def _finish(outcome: ConsumeOutcome) -> ConsumeOutcome:
        _atomic_write_0600(p, store)
        audit_event(
            "channel",
            tool="telegram_pairing",
            decision="allow" if outcome.ok else "deny",
            status=outcome.status,
            detail="pairing_token_consumed",
        )
        return outcome

    try:
        uid = int(str(user_id).strip())
    except (TypeError, ValueError):
        return ConsumeOutcome(status="invalid", detail="user_id is not numeric")

    if len(store["failed"]) >= MAX_FAILED_CONSUMES:
        return _finish(ConsumeOutcome(status="locked", detail="Brute-Force-Lockout aktiv"))

    entry = next((t for t in store["tokens"] if t.get("token_hash") == _hash(str(token or ""))), None)
    if entry is None:
        store["failed"].append(now_v)
        return _finish(ConsumeOutcome(status="invalid", detail="Token unbekannt"))

    if entry.get("used"):
        return _finish(ConsumeOutcome(status="used", detail="Token bereits verbraucht"))
    if float(entry.get("expires_at", 0)) <= now_v:
        return _finish(ConsumeOutcome(status="expired", detail="Token abgelaufen"))

    entry["used"] = True
    entry["used_by"] = uid
    entry["used_at"] = now_v
    return _finish(ConsumeOutcome(status="ok", user_id=uid))


def pending_tokens(path: Path | None = None) -> list[dict[str, Any]]:
    """Open (unused, valid) tokens — ONLY hash + timestamps, no secret."""
    p = tokens_path(path)
    store = _load(p)
    _sweep_expired(store, time.time())
    return [
        {
            "token_hash": str(t.get("token_hash", ""))[:12] + "…",
            "created_at": t.get("created_at"),
            "expires_at": t.get("expires_at"),
            "used": bool(t.get("used")),
        }
        for t in store["tokens"]
        if not t.get("used")
    ]


__all__ = [
    "PairingLimitError",
    "ConsumeOutcome",
    "create_pairing_token",
    "consume_pairing_token",
    "pending_tokens",
    "tokens_path",
    "TOKENS_FILENAME",
    "DEFAULT_TTL_SECONDS",
    "MAX_OPEN_TOKENS",
    "MAX_FAILED_CONSUMES",
    "FAILED_WINDOW_SECONDS",
]
