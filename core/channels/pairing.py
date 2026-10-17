"""◑ Ephe – channel pairing + bot-token vault (Sprint3-G2).

Threat-model references (docs/SECURITY_THREAT_MODEL.md §6):

- **C1 / S3 (spoofing):** pairing = a static allowlist of Telegram user IDs.
  Default-empty = the bot answers NOBODY until a device was paired explicitly.
  No dynamic pairing via a Telegram message (that would itself be a
  spoofing vector channel).
- **C3 / T1+I2 (tampering / information disclosure):** the bot token is stored in
  the OS keyring preferably; the fallback is a 0600 file under ``~/.ephe``
  (consistent with ``core.engine_config``). Never-in-plaintext rule: the token is
  never persisted in logs, repr() or the pairing config.
- **C4 (trust boundary):** outbound-only transport — the channel opens NO inbound
  port; the only outbound is the Telegram API transport itself.

Conservative defaults: no auto-approval for channel sessions (reuse of the P0-1
gate from ``core.tools.approval``).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from core.tools.approval import ApprovalPolicy

# Paths (convention: ~/.ephe, 0700/0600 — see core/engine_config)

EPHE_DIR_NAME = ".ephe"
PAIRING_FILENAME = "channel_pairing.json"
TOKEN_FILENAME = "channel_token.key"

#: Keyring service/entry name (deterministic across platforms).
KEYRING_SERVICE = "ephe"
KEYRING_USERNAME = "telegram_channel_bot_token"

# Pairing-Allowlist (C1 / S3)


@dataclass(frozen=True)
class PairingConfig:
    """Static pairing allowlist of Telegram user IDs.

    Default-empty is the safe default policy: without an explicitly paired user ID
    the channel answers nobody's messages.
    """

    allowed_user_ids: frozenset = frozenset()

    def is_allowed(self, user_id: int | str | None) -> bool:
        """True only when ``user_id`` is explicitly in the allowlist.

        Accepts int and numeric strings (Telegram delivers either, depending on the
        call path). Any other value (including None/empty) → False.
        """
        if user_id is None:
            return False
        try:
            uid = int(str(user_id).strip())
        except (TypeError, ValueError):
            return False
        return uid in self.allowed_user_ids

    def add_user(self, user_id: int) -> "PairingConfig":
        """Creates a new config with the additional user ID (frozen → copy)."""
        return PairingConfig(allowed_user_ids=self.allowed_user_ids | {int(user_id)})


def _ephe_dir() -> Path:
    return Path(os.environ.get("EPHE_DIR", Path.home() / EPHE_DIR_NAME))


def pairing_path(path: Path | None = None) -> Path:
    return path or (_ephe_dir() / PAIRING_FILENAME)


@dataclass(frozen=True)
class PairedDevice:
    """A paired Telegram account with display metadata (R24 devices UI)."""

    user_id: int
    label: str = ""
    paired_at: str = ""  # ISO-8601


def _read_raw(path: Path | None) -> dict:
    """Reads the pairing file raw; missing/corrupt → empty (fail-closed)."""
    p = pairing_path(path)
    if not p.exists():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (json.JSONDecodeError, OSError, TypeError):
        return {}


def _write_raw(path: Path | None, payload: dict) -> Path:
    """Persists raw atomically with 0700/0600 (T1/I2). Contains no secrets (C3)."""
    p = pairing_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.parent.chmod(0o700)
    except OSError:
        pass  # best effort (e.g. Windows) — the file mode stays in effect
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)  # atomic write (T2 convention, core/engine_config)
    try:
        p.chmod(0o600)
    except OSError:
        pass
    return p


def _raw_ids(raw: dict) -> set[int]:
    ids = raw.get("allowed_user_ids", [])
    try:
        return {int(x) for x in ids}
    except (TypeError, ValueError):
        return set()


def load_pairing(path: Path | None = None) -> PairingConfig:
    """Loads the pairing config; a missing/empty file → default-empty.

    Corrupt file → default-empty (fail-closed, not fail-open).
    """
    raw = _read_raw(path)
    try:
        return PairingConfig(allowed_user_ids=frozenset(_raw_ids(raw)))
    except (TypeError, ValueError):
        return PairingConfig()


def save_pairing(config: PairingConfig, path: Path | None = None) -> Path:
    """Persists the pairing config atomically with 0700/0600 (T1/I2).

    Contains EXCLUSIVELY user IDs + device metadata — no secrets (C3).
    Existing device entries are kept (add_device/remove_device are the only
    write API for ``devices``).
    """
    raw = _read_raw(path)
    raw["allowed_user_ids"] = sorted(config.allowed_user_ids)
    raw.setdefault("devices", {})
    return _write_raw(path, raw)


def add_device(
    user_id: int,
    label: str = "",
    path: Path | None = None,
    paired_at: str | None = None,
) -> None:
    """Adds a Telegram account to the allowlist + device list (atomically).

    Called by the runner after a successful token consumption — the user ID comes
    from the Telegram update, and so does the label (display name).
    """
    from datetime import datetime, timezone

    raw = _read_raw(path)
    ids = _raw_ids(raw)
    ids.add(int(user_id))
    raw["allowed_user_ids"] = sorted(ids)
    devices = raw.setdefault("devices", {})
    devices[str(int(user_id))] = {
        "label": (label or "")[:80],
        "paired_at": paired_at or datetime.now(timezone.utc).isoformat(),
    }
    _write_raw(path, raw)


def remove_device(user_id: int, path: Path | None = None) -> None:
    """REVOKES access immediately: allowlist + device entry (revoke)."""
    raw = _read_raw(path)
    ids = _raw_ids(raw)
    ids.discard(int(user_id))
    raw["allowed_user_ids"] = sorted(ids)
    raw.setdefault("devices", {}).pop(str(int(user_id)), None)
    _write_raw(path, raw)


def load_devices(path: Path | None = None) -> list[PairedDevice]:
    """Paired devices (for the settings devices panel)."""
    raw = _read_raw(path)
    devices = raw.get("devices", {})
    out: list[PairedDevice] = []
    if isinstance(devices, dict):
        for key, meta in devices.items():
            try:
                uid = int(key)
            except (TypeError, ValueError):
                continue
            meta = meta if isinstance(meta, dict) else {}
            out.append(
                PairedDevice(
                    user_id=uid,
                    label=str(meta.get("label", "")),
                    paired_at=str(meta.get("paired_at", "")),
                )
            )
    return sorted(out, key=lambda d: d.user_id)


# Bot token vault (C3 / T1+I2)


def _store_keyring(token: str) -> bool:
    """Tries to store the token in the OS keyring (Linux SecretService /
    macOS Keychain). Returns False when no keyring backend is available."""
    try:
        import keyring  # optional: the dependency is only missing on the fallback path
    except ImportError:
        return False
    try:
        keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, token)
        return True
    except Exception:
        return False


def _load_keyring() -> str | None:
    try:
        import keyring
    except ImportError:
        return None
    try:
        return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        return None


def _token_file() -> Path:
    return _ephe_dir() / TOKEN_FILENAME


def store_bot_token(token: str, path: Path | None = None) -> str:
    """Stores the bot token: keyring preferred, fallback a 0600 file.

    The return value is the storage mode used (``"keyring"`` / ``"file_0600"``) —
    for logging/status messages. The token itself is NEVER returned, logged or
    repr()-ized (``mask_token``).
    """
    if not token or not token.strip():
        raise ValueError("bot token is empty — pairing refused (fail-closed).")
    if _store_keyring(token):
        return "keyring"
    p = path or _token_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        p.parent.chmod(0o700)
    except OSError:
        pass
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(token.strip() + "\n", encoding="utf-8")
    tmp.replace(p)
    try:
        p.chmod(0o600)
    except OSError:
        pass
    return "file_0600"


def load_bot_token(path: Path | None = None) -> str | None:
    """Reads the bot token (keyring first, then the 0600 file). None = not set."""
    value = _load_keyring()
    if value:
        return value
    p = path or _token_file()
    if p.exists():
        text = p.read_text(encoding="utf-8").strip()
        return text or None
    return None


def _delete_keyring() -> None:
    """Deletes the keyring entry (best effort; missing backend → silently ok)."""
    try:
        import keyring
    except ImportError:
        return
    try:
        keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
    except Exception:
        pass


def delete_bot_token(path: Path | None = None) -> None:
    """Removes the bot token from the keyring AND the 0600 file (config reset/revoke)."""
    _delete_keyring()
    p = path or _token_file()
    try:
        p.unlink(missing_ok=True)
    except OSError:
        pass


def mask_token(token: str | None) -> str:
    """Displayable token mask for logs and status messages (C3 / I1).

    Shows only the length + the last 4 characters; never the plaintext.
    """
    if not token:
        return "(not set)"
    t = token.strip()
    if len(t) <= 6:
        return f"({len(t)} chars)"
    return f"…{t[-4:]} ({len(t)} chars)"


# Channel approval policy (C2 / E2, reusing the P0-1 gate)


def channel_approval_policy() -> ApprovalPolicy:
    """Conservative approval policy for channel sessions (release bar).

    Channel messages are NEVER interactive (no TTY) and NEVER
    auto-approved: mutating tools are declined conservatively without explicit,
    channel-side confirmation (``request_approval`` → the deny branch).
    SAFE tools (read-only) stay untouched — the same gate logic as
    CLI/PWA, no new mechanism.
    """
    return ApprovalPolicy(
        auto_approve=False,
        dry_run=False,
        declined=False,
        on_confirm=None,
        interactive=False,
    )


__all__ = [
    "PairingConfig",
    "PairedDevice",
    "load_pairing",
    "save_pairing",
    "add_device",
    "remove_device",
    "load_devices",
    "store_bot_token",
    "load_bot_token",
    "delete_bot_token",
    "mask_token",
    "channel_approval_policy",
    "KEYRING_SERVICE",
    "KEYRING_USERNAME",
    "PAIRING_FILENAME",
    "TOKEN_FILENAME",
]
