"""Ephe — Plugin signing (Extensions wave E4b)
core/plugin_signing.py

ES256 (SECP256R1) signatures over a canonical-JSON payload, binding a plugin
identity to its exact directory content:

    payload = {"alg": "ES256", "kid": …, "name": …, "version": …, "sha256": <dir hash>}
    signature = base64( ECDSA-P256-SHA256( canonical_json(payload) ) )

canonical_json is the RFC 8785 subset relevant to manifest payloads (sorted
keys, no whitespace, UTF-8, no floats in the payload).

The signature record lives INSIDE the plugin directory as
`ephe-plugin.sig.json` and is EXCLUDED from the directory hash (see
plugin_manifest.dir_sha256) — so signing does not change the hash it signs.
That exclusion is by file NAME, so a second record hidden in a subdirectory
would escape the hash entirely: `verify_plugin_dir` refuses any package that
carries one.

Trust anchors: every PEM passed by the caller (the enable gate injects the
trusted-key loader; tests use ephemeral keys). Verify NEVER throws — any
problem is `False` plus a reason.

`kid` is signed, therefore unforgeable, but it is only what the signer called
itself: the verifier tries every trusted key and never maps a key back to a
`kid`. Nothing in this module treats `kid` as an authorization.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Callable

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from core.plugin_manifest import SIG_FILENAME  # noqa: F401 — re-exported single source
from core.plugin_store import config_root

SIG_ALG = "ES256"

#: Test/production seam for the enable gate: returns trusted public PEMs.
TRUSTED_KEYS_LOADER: Callable[[], list[bytes]] | None = None


def canonical_json(payload: dict[str, Any]) -> bytes:
    """RFC 8785 subset: recursively sorted keys, no whitespace, UTF-8.
    Deterministic for str/int/bool/None/list/dict payloads (no floats)."""
    return json.dumps(_sorted(payload), ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _sorted(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sorted(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [_sorted(v) for v in value]
    return value


def generate_keypair() -> tuple[bytes, bytes]:
    """(private_pem, public_pem) — SECP256R1, PKCS8/SubjectPublicKeyInfo."""
    key = ec.generate_private_key(ec.SECP256R1())
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return priv, pub


def sign(payload: dict[str, Any], private_pem: bytes) -> str:
    key = serialization.load_pem_private_key(private_pem, password=None)
    sig = key.sign(canonical_json(payload), ec.ECDSA(hashes.SHA256()))
    return base64.b64encode(sig).decode("ascii")


def verify(payload: dict[str, Any], signature_b64: str, public_pem: bytes) -> bool:
    """Fail-closed and fail-soft: any problem → False (never raises)."""
    try:
        pub = serialization.load_pem_public_key(public_pem)
        sig = base64.b64decode(signature_b64, validate=True)
        pub.verify(sig, canonical_json(payload), ec.ECDSA(hashes.SHA256()))
        return True
    except Exception:  # noqa: BLE001 — verification must never throw
        return False


def _stray_signature_records(plugin_dir: Path) -> list[Path]:
    """Signature records below the plugin root.

    `dir_sha256` excludes the signature file NAME at any depth (so signing does
    not change the hash it signs). The same exclusion makes a second record
    hidden in a subdirectory invisible to the signature — content there is not
    covered by any key. Such a package is refused rather than trusted."""
    root = Path(plugin_dir)
    return [p for p in sorted(root.rglob(SIG_FILENAME)) if p.parent != root]


def sign_plugin_dir(plugin_dir: Path, private_pem: bytes, kid: str = "first-party") -> dict[str, Any]:
    """Sign a plugin directory and write the signature record inside it.

    The record binds name+version (from the manifest) to the directory hash
    computed WITHOUT the signature file itself. A directory that already hides
    a record in a subdirectory is not signable — it would be unverifiable."""
    from core.plugin_manifest import dir_sha256, load_manifest

    plugin_dir = Path(plugin_dir)
    manifest, err = load_manifest(plugin_dir)
    if err or manifest is None:
        raise ValueError(f"cannot sign invalid plugin: {err}")
    stray = _stray_signature_records(plugin_dir)
    if stray:
        raise ValueError(f"cannot sign plugin with a nested {SIG_FILENAME}: {stray[0]}")
    payload = {
        "alg": SIG_ALG,
        "kid": kid,
        "name": manifest["name"],
        "version": manifest["version"],
        "sha256": dir_sha256(plugin_dir),
    }
    record = {**payload, "signature": sign(payload, private_pem)}
    (plugin_dir / SIG_FILENAME).write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


def verify_plugin_dir(plugin_dir: Path, record: dict[str, Any], trusted_public_pems: list[bytes]) -> tuple[bool, str]:
    """Verify a signature record against the CURRENT directory content.

    Returns (ok, reason). Reasons: drift (content changed), identity
    (record does not match the manifest), signature (crypto failure),
    no_trusted_key, stray signature record."""
    from core.plugin_manifest import dir_sha256, load_manifest

    plugin_dir = Path(plugin_dir)
    if not isinstance(record, dict) or not record.get("signature"):
        return False, "no signature record"
    manifest, err = load_manifest(plugin_dir)
    if err or manifest is None:
        return False, f"invalid plugin: {err}"
    stray = _stray_signature_records(plugin_dir)
    if stray:
        return False, f"stray {SIG_FILENAME} below the plugin root is not covered by the hash: {stray[0]}"
    if record.get("name") != manifest["name"] or record.get("version") != manifest["version"]:
        return False, "identity mismatch"
    if record.get("alg") != SIG_ALG:
        return False, "unsupported algorithm"
    current = dir_sha256(plugin_dir)
    if record.get("sha256") != current:
        return False, f"drift: directory changed after signing (recorded {str(record.get('sha256'))[:12]}…, now {current[:12]}…)"
    payload = {k: record[k] for k in ("alg", "kid", "name", "version", "sha256") if k in record}
    if not trusted_public_pems:
        return False, "no_trusted_key"
    for pem in trusted_public_pems:
        if verify(payload, str(record["signature"]), pem):
            return True, ""
    return False, "signature not from a trusted key"


def load_trusted_public_keys(extra_dir: Path | None = None) -> list[bytes]:
    """Trusted public PEMs: the seam (if set), the repo first-party key (if
    present) and `~/.ephe/trusted-keys/*.pub.pem` (scanned by DEFAULT)."""
    if TRUSTED_KEYS_LOADER is not None:
        return list(TRUSTED_KEYS_LOADER())
    pems: list[bytes] = []
    first_party = Path(__file__).resolve().parent.parent / "plugins" / "first-party.pub.pem"
    if first_party.is_file():
        pems.append(first_party.read_bytes())
    base = Path(extra_dir) if extra_dir is not None else config_root() / "trusted-keys"
    if base.is_dir():
        for f in sorted(base.glob("*.pub.pem")):
            pems.append(f.read_bytes())
    return pems


def signature_check_enabled() -> bool:
    """Deep setting `plugins.plugin_signature_check` (default True)."""
    from core.settings_schema import deep_bool

    return deep_bool("plugins.plugin_signature_check")
