"""Updater checks for the release checklist: feed wiring and the signing key.

Both read the same `tauri.conf.json` updater block and stay in their own module
so `release_checklist.py` does not cross the repository's 400-line ceiling.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

TAURI_CONF = "app/src-tauri/tauri.conf.json"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def feed_status(root: Path) -> tuple[str, str]:
    try:
        conf = _read_json(root / TAURI_CONF)
    except (OSError, ValueError):
        return "SKIP", f"cannot read {TAURI_CONF}"
    updater = conf.get("plugins", {}).get("updater", {})
    pubkey = updater.get("pubkey")
    endpoints = updater.get("endpoints") or []
    if not pubkey or not endpoints:
        return "WARN", "updater pubkey or endpoints empty; the feed would be dead"
    return "PASS", f"{len(endpoints)} endpoint(s), pubkey set"


def _configured_pubkey(root: Path) -> str:
    try:
        conf = _read_json(root / TAURI_CONF)
    except (OSError, ValueError):
        return ""
    return str(conf.get("plugins", {}).get("updater", {}).get("pubkey") or "").strip()


def signing_status(root: Path, key_path: str | None = None) -> tuple[str, str]:
    """A private key only counts when its public half is the configured updater key.

    Existence alone is a false green: a key whose public half differs from
    `plugins.updater.pubkey` signs a bundle the client refuses. The check also
    names a matching sibling so a stale default path is one line to diagnose.
    """
    key = key_path or os.environ.get("EPHE_UPDATER_KEY") or str(Path.home() / ".tauri" / "ephe.key")
    path = Path(key)
    if not path.is_file():
        return "WARN", f"{key} missing; the local signed build cannot run"
    expected = _configured_pubkey(root)
    if not expected:
        return "PASS", "signing key present; updater pubkey is not configured"
    public = Path(f"{path}.pub")
    if not public.is_file():
        return "WARN", f"{public} missing; the key cannot be matched to the updater pubkey"
    actual = public.read_text(encoding="utf-8", errors="replace").strip()
    if actual == expected:
        return "PASS", "signing key matches the updater pubkey"
    matches = sorted(
        candidate.name
        for candidate in path.parent.glob("*.pub")
        if candidate.is_file()
        and candidate.read_text(encoding="utf-8", errors="replace").strip() == expected
    )
    hint = f"; a matching key is {', '.join(matches)}" if matches else ""
    return "WARN", f"{path.name} does not match the updater pubkey{hint}"
