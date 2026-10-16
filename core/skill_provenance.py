"""Provenance of an installed skill package (R4).

A skill that the user pulled from a URL keeps running in the tool loop afterwards
— the same risk the workbench has answered for files with A0/A3: the statement is
not the path, but where the package came from and whether it is still what was
installed. Before, the source was lost inside the install call; the surface showed
only a name.

The note sits next to the skill (`.ephe-install.json`) and carries a hash over
every file except itself. That is what gets compared: "unchanged since
installation" is a claim that has to stay recomputable.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

RECORD_FILE = ".ephe-install.json"
SCHEMA = 1


def sanitize_origin(raw: str, kind: str) -> str:
    """What ends up on the surface. A download URL can carry a token in the
    query — query, fragment and userinfo do not belong in a note that you
    might photograph and share."""
    value = (raw or "").strip()
    if kind != "url":
        return Path(value).name
    try:
        parts = urlsplit(value)
    except ValueError:
        return ""
    if not parts.scheme or not parts.netloc:
        return ""
    host = parts.netloc.rsplit("@", 1)[-1]
    return f"{parts.scheme}://{host}{parts.path}"


def content_hash(root: Path) -> str:
    """Deterministic hash over every file in the package, the note itself
    excluded (otherwise it would change its own result)."""
    digest = hashlib.sha256()
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.name != RECORD_FILE)
    for path in files:
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"sha256:{digest.hexdigest()}"


def record_install(
    skill_dir: Path,
    *,
    kind: str,
    origin: str,
    version: str,
    pack_id: str = "",
) -> dict[str, Any]:
    clean = sanitize_origin(origin, kind)
    record = {
        "schema": SCHEMA,
        "kind": kind,
        "origin": clean,
        "version": version,
        "pack_id": pack_id,
        "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "content_hash": content_hash(skill_dir),
    }
    (skill_dir / RECORD_FILE).write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return record


def read(skill_dir: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads((skill_dir / RECORD_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def unchanged(skill_dir: Path) -> bool | None:
    """Three answers because there are three states: no package (None), noted
    and identical (True), noted but changed (False)."""
    record = read(skill_dir)
    if not record or not record.get("content_hash"):
        return None
    try:
        return content_hash(skill_dir) == record["content_hash"]
    except OSError:
        return None
