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
itself: the verifier tries every key of the requested class and never maps a
key back to a `kid`. Nothing in this module treats `kid` as an authorization.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import base64
import json
import os
import threading
from pathlib import Path
from typing import Any, Callable

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from core.plugin_manifest import SIG_FILENAME  # noqa: F401 — re-exported single source
from core.plugin_store import config_root

SIG_ALG = "ES256"
PINS_FILENAME = "plugin-signatures.json"

#: Test/production seam for the enable gate: returns trusted public PEMs.
TRUSTED_KEYS_LOADER: Callable[[], list[bytes]] | None = None

_PINS_LOCK = threading.Lock()


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


FIRST_PARTY = "first-party"
USER = "user"


def load_trusted_keys_with_class(extra_dir: Path | None = None) -> list[tuple[bytes, str]]:
    """Trusted keys with the class they were installed as; the class is not a label
    a signature can choose."""
    if TRUSTED_KEYS_LOADER is not None:
        loaded = list(TRUSTED_KEYS_LOADER())
        return [tuple(item) if isinstance(item, tuple) else (item, USER) for item in loaded]
    keys: list[tuple[bytes, str]] = []
    first_party = Path(__file__).resolve().parent.parent / "plugins" / "first-party.pub.pem"
    if first_party.is_file():
        keys.append((first_party.read_bytes(), FIRST_PARTY))
    base = Path(extra_dir) if extra_dir is not None else config_root() / "trusted-keys"
    if base.is_dir():
        for f in sorted(base.glob("*.pub.pem")):
            keys.append((f.read_bytes(), USER))
    return keys


def trusted_pems_for_class(trust_class: str | None) -> list[bytes]:
    """Keys of one class. A named class with no keys returns none: never all keys."""
    if trust_class is None:
        return load_trusted_public_keys()
    return [pem for pem, cls in load_trusted_keys_with_class() if cls == trust_class]


def verify_plugin_dir(
    plugin_dir: Path,
    record: dict[str, Any],
    trusted_public_pems: list[bytes] | None = None,
    *,
    trust_class: str | None = None,
    require_dir_name: bool = True,
) -> tuple[bool, str]:
    """Verify a signature record against the CURRENT directory content.

    Returns (ok, reason). Reasons: drift (content changed), identity
    (record does not match the manifest), signature (crypto failure),
    no_trusted_key, stray signature record."""
    from core.plugin_manifest import dir_sha256, load_manifest

    plugin_dir = Path(plugin_dir)
    if not isinstance(record, dict) or not record.get("signature"):
        return False, "no signature record"
    # A rollback backup is named `.previous-<name>`; only that caller may skip
    # the directory-name rule, so the enable gate keeps it.
    manifest, err = load_manifest(plugin_dir, require_dir_name=require_dir_name)
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
    keys = trusted_public_pems or []
    if trust_class is not None:
        keys = trusted_pems_for_class(trust_class)
    if not keys:
        return False, f"no_trusted_key for class {trust_class}" if trust_class else "no_trusted_key"
    for pem in keys:
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


def pins_path() -> Path:
    return config_root() / PINS_FILENAME


def _read_pins() -> dict[str, dict[str, Any]]:
    try:
        raw = json.loads(pins_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    plugins = raw.get("plugins") if isinstance(raw, dict) else None
    if not isinstance(plugins, dict):
        return {}
    return {
        str(name): dict(pin)
        for name, pin in plugins.items()
        if isinstance(pin, dict)
    }


def load_pin(name: str) -> dict[str, Any] | None:
    """The last verified signature identity for `name`, or None."""
    pin = _read_pins().get(str(name))
    return dict(pin) if isinstance(pin, dict) else None


def record_pin(
    name: str, record: dict[str, Any], *, trust_class: str | None = None
) -> None:
    """Persist the identity a verified record carried.

    The record lives inside the plugin directory and can be deleted by the same
    user; the pin lives in the config directory and survives that deletion. It
    is not a second signature check, it makes a lost record visible. The class
    the artifact was verified under is part of that identity: a rollback later
    verifies against that class alone.
    """
    if not isinstance(record, dict) or not record.get("sha256"):
        return
    pin = {
        "name": str(record.get("name") or name),
        "version": str(record.get("version") or ""),
        "sha256": str(record.get("sha256")),
        "kid": str(record.get("kid") or ""),
    }
    with _PINS_LOCK:
        pins = _read_pins()
        if trust_class:
            pin["trust_class"] = str(trust_class)
        pins[str(name)] = pin
        _write_pins(pins)


def clear_pin(name: str) -> None:
    with _PINS_LOCK:
        pins = _read_pins()
        if str(name) in pins:
            pins.pop(str(name), None)
            _write_pins(pins)


def _write_pins(pins: dict[str, dict[str, Any]]) -> None:
    path = pins_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(
                {"version": 1, "plugins": pins},
                handle,
                ensure_ascii=False,
                indent=2,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def signature_check_enabled() -> bool:
    """Deep setting `plugins.plugin_signature_check` (default True)."""
    from core.settings_schema import deep_bool

    return deep_bool("plugins.plugin_signature_check")


def _signature_file(plugin_id: str) -> Path | None:
    from core.plugin_manifest import BUILTIN_PLUGINS_ROOT, SIG_FILENAME

    for base in (config_root() / "plugins", BUILTIN_PLUGINS_ROOT):
        candidate = base / plugin_id / SIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


def verify_enable(plugin_id: str) -> tuple[bool, str]:
    """The enable-time gate for every surface, HTTP and CLI alike.

    Returns (ok, reason). A record that existed at install but is now missing is
    refused through the pin written by the last successful verification; a
    malformed record is a coded refusal, not an exception.
    """
    if not signature_check_enabled():
        return True, ""
    sig_file = _signature_file(plugin_id)
    if sig_file is None:
        if load_pin(plugin_id) is not None:
            return False, "signature_record_missing"
        return True, ""
    try:
        record = json.loads(sig_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, f"signature_invalid: record is not readable ({type(exc).__name__})"
    from core.plugin_lockfile import trust_class_for

    # Enabling is the other verification call site: without the recorded class,
    # a user-class key could enable an artifact the pin calls first-party.
    trust_class = trust_class_for(plugin_id, sig_file.parent)
    ok, reason = verify_plugin_dir(
        sig_file.parent, record, trust_class=trust_class
    )
    if not ok:
        return False, reason
    try:
        record_pin(plugin_id, record, trust_class=trust_class)
    except OSError:
        pass
    return True, ""
