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
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from core.plugin_manifest import (  # noqa: F401 — SIG_FILENAME is re-exported
    SIG_FILENAME,
    VERIFY_FILENAME,
)
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
    sig = key.sign(canonical_json(payload), ec.ECDSA(hashes.SHA256(), deterministic_signing=True))
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


#: Files the verifier itself leaves inside a bundle. A signature covers what the
#: builder shipped, so neither the record it signs nor the scanner's own verdict may
#: move the hash — and an artifact that ships either of them is refused at install.
_SIGNED_OUTSIDE = frozenset({SIG_FILENAME, VERIFY_FILENAME})


def _stray_signature_records(plugin_dir: Path) -> list[Path]:
    """Signature records below the plugin root.

    `dir_sha256` excludes the signature file NAME at any depth (so signing does
    not change the hash it signs). The same exclusion makes a second record
    hidden in a subdirectory invisible to the signature — content there is not
    covered by any key. Such a package is refused rather than trusted."""
    root = Path(plugin_dir)
    stray: list[Path] = []
    for name in (SIG_FILENAME, VERIFY_FILENAME):
        stray.extend(p for p in sorted(root.rglob(name)) if p.parent != root)
    return sorted(stray)


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

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRST_PARTY_PEM_PATH = REPO_ROOT / "plugins" / "first-party.pub.pem"


def key_fingerprint(public_pem: bytes) -> str:
    """SHA-256 of the DER subject public key, so the same key prints the same value
    under any PEM encoding. Empty for bytes that are not a public key."""
    try:
        der = serialization.load_pem_public_key(public_pem).public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    except Exception:  # noqa: BLE001 — an unparseable key has no identity, never a wrong one
        return ""
    return hashlib.sha256(der).hexdigest()


@dataclass(frozen=True)
class TrustedKey:
    """One key the verifier may use, the class it was installed as, and where it came
    from. `origin` is printed by the install verb, so it names a folder the reader
    owns (`config:trusted-keys/<file>`) or a file of this checkout (`checkout:<path>`)
    — an absolute path would be somebody else's machine on every run."""

    pem: bytes
    trust_class: str
    origin: str

    @property
    def fingerprint(self) -> str:
        return key_fingerprint(self.pem)


def load_trusted_key_records(extra_dir: Path | None = None) -> list[TrustedKey]:
    """Every key the verifier may use, each with its class and origin.

    Three sources and no fourth: a key of this checkout, a key the user placed in the
    `trusted-keys` folder of the config dir, and the test seam. A marketplace index, a
    listing entry or a fetched bundle adds none of them, which is the only reason a
    first-party signature says anything about who published the bytes.
    """
    if TRUSTED_KEYS_LOADER is not None:
        seam: list[TrustedKey] = []
        for item in TRUSTED_KEYS_LOADER():
            pem, key_class = item if isinstance(item, tuple) else (item, USER)
            seam.append(
                TrustedKey(pem=pem, trust_class=str(key_class), origin="loader")
            )
        return seam
    keys: list[TrustedKey] = []
    if FIRST_PARTY_PEM_PATH.is_file():
        keys.append(
            TrustedKey(
                pem=FIRST_PARTY_PEM_PATH.read_bytes(),
                trust_class=FIRST_PARTY,
                origin=f"checkout:{FIRST_PARTY_PEM_PATH.relative_to(REPO_ROOT).as_posix()}",
            )
        )
    base = Path(extra_dir) if extra_dir is not None else config_root() / "trusted-keys"
    if base.is_dir():
        for pem_file in sorted(base.glob("*.pub.pem")):
            keys.append(
                TrustedKey(
                    pem=pem_file.read_bytes(),
                    trust_class=USER,
                    origin=f"config:trusted-keys/{pem_file.name}",
                )
            )
    return keys


def load_trusted_keys_with_class(extra_dir: Path | None = None) -> list[tuple[bytes, str]]:
    """Trusted keys with the class they were installed as; the class is not a label
    a signature can choose."""
    return [(key.pem, key.trust_class) for key in load_trusted_key_records(extra_dir)]


def trusted_pems_for_class(trust_class: str | None) -> list[bytes]:
    """Keys of one class. A named class with no keys returns none: never all keys."""
    if trust_class is None:
        return load_trusted_public_keys()
    return [pem for pem, cls in load_trusted_keys_with_class() if cls == trust_class]


def _key_set(
    trusted_public_pems: list[bytes] | None, trust_class: str | None
) -> list[TrustedKey]:
    """The keys one verification may try.

    A named class narrows to keys installed as that class, and a class with no keys
    narrows to nothing: an `official` artifact is never satisfied by a key the user
    happened to install. A caller that passes PEMs and no class is answerable to those
    PEMs alone — this function never falls back to the keyring on its own."""
    if trust_class is not None:
        return [key for key in load_trusted_key_records() if key.trust_class == trust_class]
    if trusted_public_pems is None:
        return []
    return [
        TrustedKey(pem=pem, trust_class="caller", origin="caller-supplied")
        for pem in trusted_public_pems
    ]


def _verify_against_keys(
    plugin_dir: Path,
    record: dict[str, Any],
    keys: list[TrustedKey],
    *,
    trust_class: str | None,
    require_dir_name: bool,
) -> tuple[bool, str]:
    """One record against one key set.

    The order of checks is the contract: identity and drift are answered before any
    cryptographic attempt, so a bundle whose manifest disagrees with the record is
    refused without the verifier ever trusting the record's own hash."""
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
        return (
            False,
            f"stray {SIG_FILENAME} below the plugin root is not covered by the hash: {stray[0]}",
        )
    if record.get("name") != manifest["name"] or record.get("version") != manifest["version"]:
        return False, "identity mismatch"
    if record.get("alg") != SIG_ALG:
        return False, "unsupported algorithm"
    current = dir_sha256(plugin_dir, exclude_names=_SIGNED_OUTSIDE)
    if record.get("sha256") != current:
        return (
            False,
            f"drift: directory changed after signing (recorded {str(record.get('sha256'))[:12]}…, now {current[:12]}…)",
        )
    if not keys:
        if trust_class is not None:
            return False, f"no_trusted_key for class {trust_class}"
        return False, "no_trusted_key"
    payload = {k: record[k] for k in ("alg", "kid", "name", "version", "sha256") if k in record}
    for key in keys:
        if verify(payload, str(record["signature"]), key.pem):
            return True, ""
    return False, "signature not from a trusted key"


def _accepted_key(
    record: dict[str, Any],
    keys: list[TrustedKey],
    *,
    trust_class: str | None,
) -> dict[str, str] | None:
    """Which key answered, once the verdict is yes.

    Asked after the fact and separately, so the verdict stays the single authority:
    a caller that replaces `verify_plugin_dir` still decides the outcome, and this
    only names the key. No key matching a verdict of yes means the answer came from
    somewhere else, and the record says so by being absent."""
    payload = {k: record[k] for k in ("alg", "kid", "name", "version", "sha256") if k in record}
    for key in keys:
        if verify(payload, str(record["signature"]), key.pem):
            return {
                "alg": str(record.get("alg") or SIG_ALG),
                "kid": str(record.get("kid") or ""),
                "sha256": str(record.get("sha256") or ""),
                "trust_class": str(trust_class or key.trust_class),
                "key_fingerprint": key.fingerprint,
                "key_origin": key.origin,
            }
    return None


def verify_plugin_dir_with_key(
    plugin_dir: Path,
    record: dict[str, Any],
    trusted_public_pems: list[bytes] | None = None,
    *,
    trust_class: str | None = None,
    require_dir_name: bool = True,
) -> tuple[bool, str, dict[str, str] | None]:
    """`verify_plugin_dir`, plus which key accepted.

    The install verb prints that record: a verdict a reader cannot attribute to a key
    is the ceremony the plan's pre-mortem names. The dictionary carries the signed
    `kid` beside the fingerprint of the key that answered, because a `kid` is what the
    signer called itself and only the fingerprint is ours."""
    ok, reason = verify_plugin_dir(
        plugin_dir,
        record,
        trusted_public_pems,
        trust_class=trust_class,
        require_dir_name=require_dir_name,
    )
    if not ok:
        return False, reason, None
    return True, "", _accepted_key(record, _key_set(trusted_public_pems, trust_class), trust_class=trust_class)


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
    return _verify_against_keys(
        plugin_dir,
        record,
        _key_set(trusted_public_pems, trust_class),
        trust_class=trust_class,
        require_dir_name=require_dir_name,
    )


def verify_detached_artifact(
    payload: bytes,
    record: dict[str, Any],
    trusted_public_pems: list[bytes] | None = None,
    *,
    trust_class: str | None = FIRST_PARTY,
) -> tuple[bool, str, dict[str, str] | None]:
    """Verify a record that stands beside an artifact file against its bytes.

    A source folder whose index carries no signature can still say who built an
    artifact, but only through a key the source does not hold: the record is read from
    beside the file and must verify against the checkout's or the user's keys, with
    the digest recomputed from the bytes being installed. The signed fields are the
    algorithm, the signer's own name and that digest — a record inside the archive
    would be the artifact signing itself."""
    if not isinstance(record, dict) or not record.get("signature"):
        return False, "no signature record", None
    if record.get("alg") != SIG_ALG:
        return False, "unsupported algorithm", None
    digest = hashlib.sha256(payload).hexdigest()
    if record.get("sha256") != digest:
        return (
            False,
            "drift: artifact bytes changed after signing "
            f"(recorded {str(record.get('sha256'))[:12]}…, now {digest[:12]}…)",
            None,
        )
    keys = _key_set(trusted_public_pems, trust_class)
    if not keys:
        if trust_class is not None:
            return False, f"no_trusted_key for class {trust_class}", None
        return False, "no_trusted_key", None
    signed = {k: record[k] for k in ("alg", "kid", "sha256") if k in record}
    for key in keys:
        if verify(signed, str(record["signature"]), key.pem):
            return (
                True,
                "",
                {
                    "alg": str(record.get("alg") or SIG_ALG),
                    "kid": str(record.get("kid") or ""),
                    "sha256": digest,
                    "trust_class": str(trust_class or key.trust_class),
                    "key_fingerprint": key.fingerprint,
                    "key_origin": key.origin,
                },
            )
    return False, "signature not from a trusted key", None


def load_trusted_public_keys(extra_dir: Path | None = None) -> list[bytes]:
    """Trusted public PEMs: the seam (if set), the repo first-party key (if
    present) and `~/.ephe/trusted-keys/*.pub.pem` (scanned by DEFAULT)."""
    return [key.pem for key in load_trusted_key_records(extra_dir)]


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
    from core import path_guard
    from core.plugin_manifest import BUILTIN_PLUGINS_ROOT, SIG_FILENAME
    from core.plugin_store import PLUGIN_NAME_RE

    for base in (config_root() / "plugins", BUILTIN_PLUGINS_ROOT):
        directory = path_guard.child(base, plugin_id, pattern=PLUGIN_NAME_RE)
        if directory is None:
            continue
        candidate = directory / SIG_FILENAME
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
