"""Template tools: copy only what the shipped provenance can prove."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

PLUGIN = Path(__file__).resolve().parents[1]
PROVENANCE = PLUGIN / "templates" / "PROVENANCE.json"
_CDN = re.compile(r"cdn\.jsdelivr\.net|unpkg\.com|cdnjs\.cloudflare\.com|fonts\.googleapis\.com|static\.heygen\.ai")


def _entries() -> list[dict]:
    return json.loads(PROVENANCE.read_text(encoding="utf-8"))["templates"]


def _entry(template_id: str) -> dict | None:
    return next((e for e in _entries() if e["id"] == template_id), None)


def ephe_template_list() -> str:
    lines = [f"{e['id']} ({e['kind']}, {e['licence']})" for e in _entries()]
    return "Local templates:\n" + "\n".join(lines)


def ephe_template_apply(template_id: str, destination: str) -> str:
    entry = _entry(template_id)
    if entry is None:
        return f"[tool-error 'ephe_template_apply': unknown template {template_id!r}]"
    folder = PLUGIN / "templates" / entry["id"]
    source = folder / entry["file"]
    licence = folder / entry["licence_file"]
    if not licence.is_file():
        return f"[tool-error 'ephe_template_apply': licence file missing for {template_id!r}]"
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != entry["sha256"]:
        return f"[tool-error 'ephe_template_apply': sha256 mismatch for {template_id!r}]"
    body = source.read_text(encoding="utf-8", errors="replace")
    if _CDN.search(body):
        return f"[tool-error 'ephe_template_apply': cdn reference in {template_id!r}]"
    target = Path(destination).expanduser()
    target.mkdir(parents=True, exist_ok=True)
    (target / entry["file"]).write_bytes(source.read_bytes())
    (target / entry["licence_file"]).write_bytes(licence.read_bytes())
    return f"Applied {template_id} to {target} with {entry['licence_file']}"
