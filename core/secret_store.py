"""Named secrets the user typed in, stored where the machine keeps secrets.

Two modes, both honest about themselves: the OS keyring when its backend is
importable, otherwise an owner-only file under this app's config directory
(mode 0600). The mode is returned to the caller so a surface can say which one
holds the value; a value itself is never returned to a page, logged, or put in
an error message.

What reads them is the one place that needs them: an MCP child process receives
exactly the names its connector declared, merged into the environment it was
already given. There is no "all secrets" accessor for exactly that reason.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from core import engine_config
from core.path_guard import child

#: An environment-variable shape: uppercase, digits, underscores, not starting with a digit.
_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,63}$")
SERVICE = "ephe"
MODE_KEYRING = "keyring"
MODE_FILE = "file_0600"


def _valid(name: str) -> bool:
    return bool(_NAME.fullmatch(str(name or "")))


def is_name(name: str) -> bool:
    """Whether this is shaped like an environment variable name."""
    return _valid(name)


def secrets_dir() -> Path:
    return engine_config.config_root() / "secrets"


def _path(name: str) -> Path | None:
    target = child(secrets_dir(), name, pattern=_NAME)
    return target


def _store_keyring(name: str, value: str) -> bool:
    try:
        import keyring  # optional: absent on a machine without a backend
    except ImportError:
        return False
    try:
        keyring.set_password(SERVICE, name, value)
        return True
    except Exception:  # noqa: BLE001 — no backend is the documented fallback case
        return False


def _load_keyring(name: str) -> str | None:
    try:
        import keyring
    except ImportError:
        return None
    try:
        return keyring.get_password(SERVICE, name)
    except Exception:  # noqa: BLE001
        return None


def _delete_keyring(name: str) -> None:
    try:
        import keyring
    except ImportError:
        return
    try:
        keyring.delete_password(SERVICE, name)
    except Exception:  # noqa: BLE001
        return


def put(name: str, value: str) -> str:
    """Stores one secret and answers with the mode that holds it."""
    if not _valid(name):
        raise ValueError("a secret name is an environment variable name")
    text = str(value or "").strip()
    if not text:
        raise ValueError("the value is empty")
    if _store_keyring(name, text):
        return MODE_KEYRING
    target = _path(name)
    if target is None:
        raise ValueError("a secret name is an environment variable name")
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        target.parent.chmod(0o700)
    except OSError:
        pass
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, target)
        os.chmod(target, 0o600)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return MODE_FILE


def get(name: str) -> str | None:
    if not _valid(name):
        return None
    value = _load_keyring(name)
    if value:
        return value
    target = _path(name)
    if target is None or not target.is_file():
        return None
    try:
        text = target.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return text or None


def delete(name: str) -> None:
    if not _valid(name):
        return
    _delete_keyring(name)
    target = _path(name)
    if target is not None:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass


def mode(name: str) -> str:
    """Which store holds this name, or an empty string when it is not set."""
    if not _valid(name):
        return ""
    if _load_keyring(name):
        return MODE_KEYRING
    target = _path(name)
    if target is not None and target.is_file():
        return MODE_FILE
    return ""


def status(names: list[str]) -> list[dict[str, Any]]:
    """Presence and mode per name — the only shape a page ever sees."""
    out: list[dict[str, Any]] = []
    for name in names:
        if not _valid(name):
            continue
        held = mode(name)
        out.append({"name": name, "present": bool(held), "mode": held})
    return out


def env_for(names: list[str]) -> dict[str, str]:
    """The values for the names a connector declared, for its child process only."""
    out: dict[str, str] = {}
    for name in names:
        value = get(name)
        if value:
            out[name] = value
    return out
