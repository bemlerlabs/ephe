"""Ephe — Skill-pack signing (W3-14)

Signed skill packs reuse the plugin trust machinery verbatim
(core/plugin_signing.py): the same RFC 8785 canonical JSON, the same ES256
(SECP256R1) signatures over that canonical form, the same trust anchors
(`~/.ephe/trusted-keys/*.pub.pem` plus the repo first-party key). Where a
plugin binds a *manifest* identity to its directory, a pack binds its
*SKILL.md* identity (name + version) to the exact pack content:

    payload   = {"alg": "ES256", "kid": …, "name": …, "version": …, "sha256": <pack hash>}
    signature = base64( ECDSA-P256-SHA256( canonical_json(payload) ) )

The signature record lives INSIDE the pack directory as
`ephe-skill.sig.json` and is EXCLUDED from the pack hash — signing must not
change the hash it signs (see `plugin_manifest.dir_sha256`). That exclusion is
by file NAME at any depth, so a record hidden in a subdirectory would escape
the hash entirely: `verify_skill_pack` refuses any pack that carries one.

Two more names are excluded from the pack hash: the signature file itself and
the install-time provenance note (`.ephe-install.json`, core/skill_provenance.py).
The note is written AFTER a pack is installed, with a timestamp — including it
would invalidate the signature on every install. Excluded, a signed pack still
verifies once it is on disk.

Verify NEVER throws — any problem is `(False, reason)`, matching
`plugin_signing.verify_plugin_dir`.

`kid` is signed, therefore unforgeable, but it is only what the signer called
itself: the verifier tries every trusted key and never maps a key back to a
`kid`. Nothing here treats `kid` as an authorization.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core import skill_provenance
from core.plugin_manifest import dir_sha256
from core.plugin_signing import (  # noqa: F401 — the reused RFC 8785 + ES256 machinery
    canonical_json,
    sign,
    verify,
)

SIG_ALG = "ES256"

#: The signature record, inside the pack directory (next to SKILL.md).
SIG_FILENAME = "ephe-skill.sig.json"

#: What the pack hash must NOT cover: the signature itself and the provenance
#: note written after install. Both are metadata about the pack, not content.
HASH_EXCLUDED = frozenset({SIG_FILENAME, skill_provenance.RECORD_FILE})


def pack_sha256(skill_dir: Path) -> str:
    """Deterministic hash over the whole pack (sorted relative paths + bytes),
    with the signature record and the provenance note excluded.

    Same construction as `plugin_manifest.dir_sha256`: content-addressed, so a
    drift between what was signed and what sits on disk is recomputable."""
    return dir_sha256(Path(skill_dir), exclude_names=HASH_EXCLUDED)


def identity(skill_dir: Path) -> tuple[str, str] | None:
    """(name, version) as the loader would resolve them for this pack.

    Read through `skills._parse_skill` so the signed identity is EXACTLY the
    one the loader later serves (frontmatter name wins, version defaults to
    "1.0.0"). Returns None when the pack has no readable, valid SKILL.md — an
    invalid pack is not signable and not verifiable."""
    from core.skills import SkillLoadError, _parse_skill  # lazy: avoid an import cycle

    skill_dir = Path(skill_dir)
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return None
    try:
        skill = _parse_skill(skill_dir.name, skill_md.read_text(encoding="utf-8"), skill_dir=skill_dir)
    except SkillLoadError:
        return None
    return skill.name, skill.version


def _stray_signature_records(skill_dir: Path) -> list[Path]:
    """Signature records below the pack root.

    `dir_sha256` excludes the signature file NAME at any depth (so signing does
    not change the hash it signs). The same exclusion makes a second record
    hidden in a subdirectory invisible to the signature — content there is not
    covered by any key. Such a pack is refused rather than trusted."""
    root = Path(skill_dir)
    return [p for p in sorted(root.rglob(SIG_FILENAME)) if p.parent != root]


def read(skill_dir: Path) -> dict[str, Any] | None:
    """The signature record of a pack, or None when there is none/unreadable."""
    try:
        raw = json.loads((Path(skill_dir) / SIG_FILENAME).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def sign_skill_pack(skill_dir: Path, private_pem: bytes, kid: str = "first-party") -> dict[str, Any]:
    """Sign a pack and write `ephe-skill.sig.json` inside it.

    The record binds name+version (from SKILL.md) to the pack hash computed
    WITHOUT the signature file and the provenance note. A pack that already
    hides a record in a subdirectory is not signable — it would be
    unverifiable."""
    skill_dir = Path(skill_dir)
    ident = identity(skill_dir)
    if ident is None:
        raise ValueError(f"cannot sign unreadable skill pack: {skill_dir}")
    stray = _stray_signature_records(skill_dir)
    if stray:
        raise ValueError(f"cannot sign pack with a nested {SIG_FILENAME}: {stray[0]}")
    name, version = ident
    payload = {
        "alg": SIG_ALG,
        "kid": kid,
        "name": name,
        "version": version,
        "sha256": pack_sha256(skill_dir),
    }
    record = {**payload, "signature": sign(payload, private_pem)}
    (skill_dir / SIG_FILENAME).write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return record


def verify_skill_pack(
    skill_dir: Path, record: dict[str, Any], trusted_public_pems: list[bytes]
) -> tuple[bool, str]:
    """Verify a signature record against the CURRENT pack content.

    Returns (ok, reason). Reasons: no signature record, unreadable pack,
    stray signature record, identity mismatch, unsupported algorithm, drift
    (content changed), no_trusted_key, signature (crypto failure)."""
    skill_dir = Path(skill_dir)
    if not isinstance(record, dict) or not record.get("signature"):
        return False, "no signature record"
    ident = identity(skill_dir)
    if ident is None:
        return False, "unreadable skill pack"
    stray = _stray_signature_records(skill_dir)
    if stray:
        return False, f"stray {SIG_FILENAME} below the pack root is not covered by the hash: {stray[0]}"
    name, version = ident
    if record.get("name") != name or record.get("version") != version:
        return False, "identity mismatch"
    if record.get("alg") != SIG_ALG:
        return False, "unsupported algorithm"
    current = pack_sha256(skill_dir)
    if record.get("sha256") != current:
        return (
            False,
            f"drift: pack changed after signing (recorded {str(record.get('sha256'))[:12]}…, now {current[:12]}…)",
        )
    payload = {k: record[k] for k in ("alg", "kid", "name", "version", "sha256") if k in record}
    if not trusted_public_pems:
        return False, "no_trusted_key"
    for pem in trusted_public_pems:
        if verify(payload, str(record["signature"]), pem):
            return True, ""
    return False, "signature not from a trusted key"


def verify_installed(
    skill_dir: Path, trusted_public_pems: list[bytes] | None = None
) -> tuple[bool, str]:
    """Read the pack's record (if any) and verify it.

    A pack without a record is `(False, "no signature record")` — the caller
    decides whether an unsigned pack matters. Trusted keys default to the
    shared loader (`plugin_signing.load_trusted_public_keys`)."""
    record = read(skill_dir)
    if record is None:
        return False, "no signature record"
    if trusted_public_pems is None:
        from core.plugin_signing import load_trusted_public_keys

        trusted_public_pems = load_trusted_public_keys()
    return verify_skill_pack(skill_dir, record, trusted_public_pems)
