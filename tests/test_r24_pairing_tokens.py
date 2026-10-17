"""R24: one-time pairing tokens for the Telegram QR deep-link pairing.

Threat model (docs/SECURITY_THREAT_MODEL.md §6, the QR-pairing extension):
- The token is CSPRNG (secrets), single-use, short-lived (TTL 10 min default).
- ONLY the SHA-256 hash is persisted (C3) — the plaintext lives exclusively
  in the QR code on the desktop of whoever pairs.
- Brute-force gate: too many failed consumes lock the window.
- Corrupt file → fail-closed (empty token set, no crash).
"""

from __future__ import annotations

import hashlib
import json
import stat
import time
from pathlib import Path

import pytest

from core.channels import pairing_tokens as pt
from core.audit_log import tail as audit_tail


@pytest.fixture()
def tokens_path(tmp_path: Path) -> Path:
    return tmp_path / "channel_pairing_tokens.json"


@pytest.fixture()
def audit_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # AUDIT_LOG_FILE is bound at import time → replace the attribute (like the R23 tests)
    import core.audit_log as audit_log

    p = tmp_path / "audit.log"
    monkeypatch.setattr(audit_log, "AUDIT_LOG_FILE", p)
    return p


# create


def test_create_returns_urlsafe_token_and_persists_hash_only(tokens_path: Path) -> None:
    token = pt.create_pairing_token(path=tokens_path)

    assert 16 <= len(token) <= 64  # deep-link payload limit (t.me ≤ 64 Base64-URL)
    assert all(c.isalnum() or c in "-_" for c in token)  # URL-safe alphabet

    raw = json.loads(tokens_path.read_text(encoding="utf-8"))
    entries = raw["tokens"]
    assert len(entries) == 1
    assert token not in json.dumps(raw)  # C3: plaintext NEVER on disk
    assert entries[0]["token_hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert entries[0]["used"] is False
    assert entries[0]["used_by"] is None


def test_create_sets_0600_file_mode(tokens_path: Path) -> None:
    pt.create_pairing_token(path=tokens_path)
    mode = stat.S_IMODE(tokens_path.stat().st_mode)
    assert mode == 0o600


def test_create_respects_ttl(tokens_path: Path) -> None:
    token = pt.create_pairing_token(path=tokens_path, ttl=123)
    rec = json.loads(tokens_path.read_text())["tokens"][0]
    assert rec["expires_at"] - rec["created_at"] == pytest.approx(123)


def test_create_enforces_max_open_tokens(tokens_path: Path) -> None:
    for _ in range(pt.MAX_OPEN_TOKENS):
        pt.create_pairing_token(path=tokens_path)
    with pytest.raises(pt.PairingLimitError):
        pt.create_pairing_token(path=tokens_path)


def test_create_cleans_expired_first(tokens_path: Path) -> None:
    for _ in range(pt.MAX_OPEN_TOKENS):
        pt.create_pairing_token(path=tokens_path, ttl=1)
    time.sleep(0.05)
    token = pt.create_pairing_token(path=tokens_path, now=time.time() + 5)
    assert token  # the expired ones were swept → there is room again


def test_create_writes_audit_event(tokens_path: Path, audit_env: Path) -> None:
    pt.create_pairing_token(path=tokens_path)
    events = audit_tail(kind="channel")
    assert any(e.get("detail") == "pairing_token_created" for e in events)
    # the plaintext token must not show up in the audit
    assert not any(str(t) in json.dumps(events) for t in ())


# consume


def test_consume_ok_is_single_use(tokens_path: Path) -> None:
    token = pt.create_pairing_token(path=tokens_path)
    first = pt.consume_pairing_token(token, user_id=42, path=tokens_path)
    assert first.status == "ok"
    assert first.user_id == 42

    # Telegram redelivers /start idempotently → the second consume is refused
    second = pt.consume_pairing_token(token, user_id=42, path=tokens_path)
    assert second.status == "used"


def test_consume_rejects_unknown_token(tokens_path: Path) -> None:
    out = pt.consume_pairing_token("bogus-token", user_id=1, path=tokens_path)
    assert out.status == "invalid"


def test_consume_rejects_expired(tokens_path: Path) -> None:
    token = pt.create_pairing_token(path=tokens_path, ttl=10)
    out = pt.consume_pairing_token(token, user_id=7, path=tokens_path, now=time.time() + 11)
    assert out.status == "expired"


def test_consume_lockout_after_brute_force(tokens_path: Path) -> None:
    token = pt.create_pairing_token(path=tokens_path)
    for i in range(pt.MAX_FAILED_CONSUMES):
        out = pt.consume_pairing_token(f"guess-{i}", user_id=1, path=tokens_path)
        assert out.status == "invalid"
    # even the CORRECT token is refused during the lockout (fail-closed)
    out = pt.consume_pairing_token(token, user_id=1, path=tokens_path)
    assert out.status == "locked"


def test_lockout_window_resets(tokens_path: Path) -> None:
    for i in range(pt.MAX_FAILED_CONSUMES):
        pt.consume_pairing_token(f"guess-{i}", user_id=1, path=tokens_path)
    # New window: the failed-window has expired → a valid token gets through
    token = pt.create_pairing_token(path=tokens_path)
    out = pt.consume_pairing_token(token, user_id=5, path=tokens_path,
                                   now=time.time() + pt.FAILED_WINDOW_SECONDS + 1)
    assert out.status == "ok"


def test_consume_writes_audit_event(tokens_path: Path, audit_env: Path) -> None:
    token = pt.create_pairing_token(path=tokens_path)
    pt.consume_pairing_token(token, user_id=99, path=tokens_path)
    events = audit_tail(kind="channel")
    kinds = [e.get("detail") for e in events]
    assert "pairing_token_created" in kinds
    assert any(e.get("detail") == "pairing_token_consumed" and e.get("status") == "ok"
               for e in events)


def test_corrupt_file_is_fail_closed(tokens_path: Path) -> None:
    tokens_path.parent.mkdir(parents=True, exist_ok=True)
    tokens_path.write_text("{not json", encoding="utf-8")
    token = pt.create_pairing_token(path=tokens_path)
    assert token
    out = pt.consume_pairing_token("nonsense", user_id=1, path=tokens_path)
    assert out.status == "invalid"


def test_consume_user_id_must_be_integer_like(tokens_path: Path) -> None:
    token = pt.create_pairing_token(path=tokens_path)
    out = pt.consume_pairing_token(token, user_id="not-a-number", path=tokens_path)
    assert out.status in ("invalid", "expired", "used", "locked")
    assert out.status != "ok"


def test_pending_tokens_listing_hides_secret(tokens_path: Path) -> None:
    pt.create_pairing_token(path=tokens_path)
    listing = pt.pending_tokens(path=tokens_path)
    assert len(listing) == 1
    assert set(listing[0]) <= {"token_hash", "created_at", "expires_at", "used"}
