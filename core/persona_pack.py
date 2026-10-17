"""The portable form of a persona: one JSON document, integrity-checked, optionally signed.

A persona is one markdown file, so sharing it means handing someone a file that
carries its own identity and integrity. A persona pack is a single
self-describing JSON document:

    {
      "format": "ephe-persona", "version": 1,
      "name": "marvin", "title": "Marvin", "description": "…", "author": "…",
      "created": "2026-10-11T00:00:00Z",
      "persona": "<markdown>", "persona_sha256": "<hex>",
      "signature": {"alg": "ES256", "kid": "…", "signature": "<base64>"}
    }

`build_pack` / `export_current` produce one; `dumps` is deterministic so two
identical packs share bytes; `import_pack` validates the pack FAIL-CLOSED and
writes `~/.ephe/persona.md` through the same atomic, capped, 0600 writer the
editor uses (`core.persona.write_persona`) — never overwriting an existing
persona unless the caller asks.

The signature reuses the plugin trust machinery object-for-object
(core/plugin_signing.py: RFC 8785 canonical JSON + ES256 over every field but
`signature`), so a persona pack verifies against the same
`~/.ephe/trusted-keys/*.pub.pem` anchors as a plugin or skill pack. Verify
NEVER throws: any problem is `(False, reason)`.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from core.persona import PERSONA_MAX_CHARS, _strip_marker, load_persona_for_editor, persona_path, write_persona
from core.plugin_signing import SIG_ALG, canonical_json, sign, verify  # noqa: F401 — reused RFC 8785 + ES256 machinery

FORMAT = "ephe-persona"
VERSION = 1
PACK_SUFFIX = ".ephe-persona.json"

NAME_MAX_CHARS = 64
TITLE_MAX_CHARS = 120
DESCRIPTION_MAX_CHARS = 280
AUTHOR_MAX_CHARS = 120
CREATED_MAX_CHARS = 40

#: Every field a v1 reader knows. An unknown key is refused: the version gate
#: runs FIRST, so a future v2 pack is rejected on its version before keys are
#: judged and this strictness never blocks a legitimate newer pack.
KNOWN_FIELDS = frozenset(
    {"format", "version", "name", "title", "description", "author", "created", "persona", "persona_sha256", "signature"}
)

_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class PersonaPackError(ValueError):
    """A pack could not be built, parsed or imported. Message is the reason."""


def slugify(text: str) -> str:
    """A pack/filename slug: lowercase, non-alphanumeric runs folded to '-'."""
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def _canonical_body(text: str) -> str:
    """The persona text as stored and hashed: marker stripped, ends trimmed.

    The `[persona]` assembly marker is an internal artifact (core.persona); a
    pack never carries it and a pack's hash always covers this canonical form.
    """
    return _strip_marker(text or "").strip()


def persona_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _signed_view(pack: dict[str, Any]) -> dict[str, Any]:
    """Everything the signature covers: every field but the signature itself."""
    return {k: v for k, v in pack.items() if k != "signature"}


def _cap(value: Any, limit: int, field: str) -> str:
    text = str(value or "").strip()
    if len(text) > limit:
        raise PersonaPackError(f"{field} too long ({len(text)} > {limit} chars)")
    return text


def build_pack(
    text: str,
    *,
    name: str | None = None,
    title: str = "",
    description: str = "",
    author: str = "",
    created: str = "",
) -> dict[str, Any]:
    """Build a shareable pack from persona markdown.

    `name` is the stable slug (filename identity); when omitted it is derived
    from `title`. The persona body is canonicalized and hashed, so the pack is
    self-checking before it ever leaves the machine."""
    body = _canonical_body(text)
    if not body:
        raise PersonaPackError("empty persona")
    if len(body) > PERSONA_MAX_CHARS:
        raise PersonaPackError(f"persona too large ({len(body)} > {PERSONA_MAX_CHARS} chars)")

    meta: dict[str, str] = {}
    for key, value, limit in (
        ("title", title, TITLE_MAX_CHARS),
        ("description", description, DESCRIPTION_MAX_CHARS),
        ("author", author, AUTHOR_MAX_CHARS),
        ("created", created, CREATED_MAX_CHARS),
    ):
        text_value = _cap(value, limit, key)
        if text_value:
            meta[key] = text_value

    slug = slugify(name or "") or slugify(title)
    if not slug:
        raise PersonaPackError("name required (give a name or a title)")
    if len(slug) > NAME_MAX_CHARS:
        raise PersonaPackError(f"name too long ({len(slug)} > {NAME_MAX_CHARS} chars)")

    pack: dict[str, Any] = {
        "format": FORMAT,
        "version": VERSION,
        "name": slug,
        "persona": body,
        "persona_sha256": persona_sha256(body),
    }
    pack.update(meta)
    return pack


def export_current(*, name: str | None = None, title: str = "", description: str = "", author: str = "") -> dict[str, Any]:
    """Build a pack from the persona this Ephe currently serves."""
    return build_pack(load_persona_for_editor(), name=name, title=title, description=description, author=author)


def dumps(pack: dict[str, Any]) -> str:
    """Canonical, sorted-key, indented JSON — deterministic file bytes.

    Uses the same RFC 8785 key ordering as the signature, so a pack's on-disk
    text and the payload a verifier recomputes agree field for field."""
    return json.dumps(_sorted(pack), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _sorted(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sorted(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [_sorted(v) for v in value]
    return value


def filename(pack: dict[str, Any]) -> str:
    return f"{pack.get('name') or 'persona'}{PACK_SUFFIX}"


def _normalize(raw: Any) -> tuple[dict[str, Any] | None, str]:
    """Validate and canonicalize a pack. Returns (pack, "") or (None, reason)."""
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            raw = json.loads(raw)
        except (ValueError, UnicodeDecodeError):
            return None, "invalid json"
    if not isinstance(raw, dict):
        return None, "not a json object"

    unknown = sorted(set(raw) - KNOWN_FIELDS)
    if unknown:
        return None, f"unknown field: {unknown[0]}"

    if raw.get("format") != FORMAT:
        return None, "not an ephe persona pack"
    version = raw.get("version")
    if isinstance(version, bool) or not isinstance(version, int) or version != VERSION:
        return None, f"unsupported pack version: {version!r}"

    raw_name = raw.get("name")
    if not isinstance(raw_name, str) or not _NAME_RE.match(raw_name):
        return None, f"bad name: {raw_name!r}"
    pack: dict[str, Any] = {"format": FORMAT, "version": VERSION, "name": raw_name}
    try:
        for key, limit in (
            ("title", TITLE_MAX_CHARS),
            ("description", DESCRIPTION_MAX_CHARS),
            ("author", AUTHOR_MAX_CHARS),
            ("created", CREATED_MAX_CHARS),
        ):
            value = _cap(raw.get(key, ""), limit, key)
            if value:
                pack[key] = value
    except PersonaPackError as exc:
        return None, str(exc)

    body = _canonical_body(str(raw.get("persona") or ""))
    if not body:
        return None, "empty persona"
    if len(body) > PERSONA_MAX_CHARS:
        return None, f"persona too large ({len(body)} > {PERSONA_MAX_CHARS} chars)"
    digest = persona_sha256(body)
    if raw.get("persona_sha256") != digest:
        return None, "integrity: persona hash mismatch"
    pack["persona"] = body
    pack["persona_sha256"] = digest
    if "signature" in raw:
        if not isinstance(raw["signature"], dict):
            return None, "bad signature record"
        pack["signature"] = raw["signature"]
    return pack, ""


def load(raw: Any) -> dict[str, Any]:
    """A refusal raises; there is no half-read pack to hand on."""
    pack, reason = _normalize(raw)
    if reason:
        raise PersonaPackError(reason)
    assert pack is not None
    return pack


def validate(raw: Any) -> tuple[bool, str]:
    """(ok, reason) — never throws, the shape a caller checks before importing."""
    _, reason = _normalize(raw)
    return reason == "", reason


def import_pack(raw: Any, *, overwrite: bool = False) -> dict[str, Any]:
    """Validate a pack and write its persona to `~/.ephe/persona.md`.

    Additive by default: an existing persona is kept and a `PersonaPackError`
    reports it, unless `overwrite=True`."""
    pack = load(raw)
    body = pack["persona"]
    path = persona_path()
    if not overwrite:
        try:
            existing = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            existing = ""
        if existing.strip():
            raise PersonaPackError("persona already exists (import with overwrite=True to replace it)")
    write_persona(body)
    return {
        "imported": True,
        "name": pack["name"],
        "title": pack.get("title", ""),
        "chars": len(body),
        "persona_sha256": pack["persona_sha256"],
        "path": str(path),
    }


def sign_pack(pack: dict[str, Any], private_pem: bytes, kid: str = "first-party") -> dict[str, Any]:
    """Return a copy of the pack carrying an ES256 signature over every field
    but `signature`. The pack must be valid before it is signed."""
    normalized = load(pack)
    payload = _signed_view(normalized)
    signature = {"alg": SIG_ALG, "kid": kid, "signature": sign(payload, private_pem)}
    return {**normalized, "signature": signature}


def verify_pack(pack: Any, trusted_public_pems: list[bytes]) -> tuple[bool, str]:
    """Verify a pack's signature against the current content. Never throws.

    Reasons: not an ephe persona pack / integrity / bad signature record,
    unsupported algorithm, no_trusted_key, signature not from a trusted key."""
    if not isinstance(pack, dict):
        return False, "not a json object"
    normalized, reason = _normalize(pack)
    if reason:
        return False, reason
    assert normalized is not None
    record = normalized.get("signature")
    if not isinstance(record, dict) or not record.get("signature"):
        return False, "no signature record"
    if record.get("alg") != SIG_ALG:
        return False, "unsupported algorithm"
    if not trusted_public_pems:
        return False, "no_trusted_key"
    payload = _signed_view(normalized)
    for pem in trusted_public_pems:
        if verify(payload, str(record["signature"]), pem):
            return True, ""
    return False, "signature not from a trusted key"
