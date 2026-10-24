"""The one path into a loadable plugin directory.

Download, hash, safe extraction, manifest validation, listing identity and
signature verification all happen under staging. Only a candidate that passed
every check replaces the installed directory, and the installed version is
kept as a one-slot backup for rollback.
"""
from __future__ import annotations

import json
import re
import shutil
import zipfile
from collections.abc import Callable
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any

from core import plugin_manifest, plugin_versions
from core.guarded_fetch import GuardedFetchError, fetch_https
from core.plugin_admin import (
    _audit_install,
    _installed_version,
    _register_installed,
    _version_key,
)
from core.plugin_listing import load_marketplace
from core.plugin_store import config_root, sha256_hex


def _default_fetcher(url: str) -> bytes:
    return fetch_https(
        url,
        max_bytes=MAX_ARCHIVE_BYTES,
        timeout=30,
        accept="application/zip, application/octet-stream",
    )


MAX_ARCHIVE_MEMBERS = 2000
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_RATIO = 100
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

def _safe_extract(payload: bytes, dest: Path) -> str | None:
    """Zip extraction with a zip-slip guard. Returns an error string or None.

    The guard compares resolved paths for real (`is_relative_to`). A string
    prefix test is not a containment test: with dest `…/.staging-x/payload` a
    member `../payload-shadow/f` resolves to `…/.staging-x/payload-shadow/f`,
    which starts with the destination's name and passed the old check. What
    actually kept the bytes inside the destination was `extractall`'s own name
    sanitization — the guard's promise is a separate claim, and it held only
    by accident."""
    try:
        zf = zipfile.ZipFile(BytesIO(payload))
    except zipfile.BadZipFile:
        return "not a zip archive"
    infos = zf.infolist()
    if len(infos) > MAX_ARCHIVE_MEMBERS:
        return (
            "unsafe_archive: members "
            f"{len(infos)} exceed {MAX_ARCHIVE_MEMBERS}"
        )
    total_bytes = sum(info.file_size for info in infos)
    if total_bytes > MAX_ARCHIVE_BYTES:
        return (
            "unsafe_archive: uncompressed bytes "
            f"{total_bytes} exceed {MAX_ARCHIVE_BYTES}"
        )
    compressed_bytes = sum(info.compress_size for info in infos)
    if compressed_bytes and total_bytes / compressed_bytes > MAX_ARCHIVE_RATIO:
        return (
            "unsafe_archive: compression ratio "
            f"{total_bytes / compressed_bytes:.0f} exceeds {MAX_ARCHIVE_RATIO}"
        )
    dest_resolved = dest.resolve()
    for info in infos:
        mode = (info.external_attr >> 16) & 0o170000
        if mode and mode not in (0o100000, 0o040000):
            return "unsafe_archive: non-regular member"
        member = info.filename
        parts = PurePosixPath(member).parts
        # `my-tool/..` resolves to the destination itself, so containment alone
        # accepts it; the extractor then writes over a directory and raises. A
        # member that climbs is refused before anything is written.
        if not parts or ".." in parts or PurePosixPath(member).is_absolute():
            return "unsafe_archive: path traversal member"
        target = (dest / member).resolve()
        if not target.is_relative_to(dest_resolved) or target == dest_resolved:
            return "unsafe_archive: path traversal member"
        if member.endswith("/"):
            continue
    try:
        zf.extractall(dest)
    except (OSError, zipfile.BadZipFile) as exc:
        return f"unsafe_archive: extractor refused the archive ({type(exc).__name__})"
    return None


def _install_from_marketplace(
    name: str,
    *,
    marketplace: dict[str, Any] | None = None,
    fetcher: Callable[[str], bytes] | None = None,
    root: Path | None = None,
    trusted_public_keys: list[bytes] | None = None,
    allow_local_trust: bool = False,
    inspect: Callable[[Path, dict[str, Any]], str | None] | None = None,
) -> dict[str, Any]:
    """Install one marketplace plugin, verifying everything in staging.

    The plugins root only receives a directory that has passed hash, manifest,
    listing-identity and trust checks. Official, verified and community entries
    require a valid signature regardless of the enable-time drift setting; a
    local unsigned artifact needs `allow_local_trust`, lands disabled and
    carries the local-trust warning.
    """
    if not _SLUG_RE.fullmatch(str(name)):
        return {
            "status": "invalid_name",
            "name": str(name),
            "error": "plugin name must be a lowercase slug",
        }
    listing = marketplace if marketplace is not None else load_marketplace()
    entry = None
    for e in listing.get("plugins", []):
        if str(e.get("name")) == name:
            entry = e
            break
    if entry is None:
        return {
            "status": "unknown_plugin",
            "name": name,
            "error": "not in marketplace listing",
        }

    trust = str(entry.get("trust") or "local").strip().lower()
    if trust not in {"official", "verified", "community", "local", "blocked"}:
        return {
            "status": "invalid_trust",
            "name": name,
            "trust": trust,
            "error": "unknown trust class",
        }
    if trust == "blocked":
        return {
            "status": "blocked_source",
            "name": name,
            "trust": trust,
            "error": "the source is blocked",
        }
    signature = entry.get("signature")
    signed = isinstance(signature, dict)
    if not signed and trust in {"official", "verified", "community"}:
        return {
            "status": "signature_required",
            "name": name,
            "trust": trust,
            "error": "the trust class requires a verified artifact signature",
        }
    if not signed and trust == "local" and not allow_local_trust:
        return {
            "status": "local_trust_required",
            "name": name,
            "trust": trust,
            "error": "a local unsigned artifact needs explicit trust",
        }

    url = str(entry.get("url") or "")
    if not url:
        return {
            "status": "no_url",
            "name": name,
            "error": "marketplace entry carries no artifact url",
        }

    fetch = fetcher if fetcher is not None else _default_fetcher
    try:
        payload = fetch(url)
    except GuardedFetchError as exc:
        return {"status": "fetch_failed", "name": name, "code": exc.code}
    except Exception:  # noqa: BLE001 — honest status, never a crash
        return {"status": "fetch_failed", "name": name, "error": "fetch_failed"}

    expected = str(entry.get("sha256") or "")
    if not expected or sha256_hex(payload) != expected:
        return {
            "status": "hash_mismatch",
            "name": name,
            "error": "artifact hash does not match the marketplace entry",
        }

    plugins_root = (
        Path(root)
        if root is not None
        else config_root() / plugin_manifest.PLUGINS_DIRNAME
    )
    staging = plugin_versions.plugin_dir(plugins_root, name, prefix=".staging-")
    payload_dir = staging / "payload"
    err = _safe_extract(payload, payload_dir)
    if err:
        shutil.rmtree(staging, ignore_errors=True)
        return {"status": "unsafe_archive", "name": name, "error": err}

    # The artifact must unpack to a directory named after the plugin. Either the
    # zip carries that top-level dir, or its manifest sits at the archive root —
    # in which case the payload is gathered into a directory of that name,
    # because the manifest validator requires name == directory name and
    # `.staging-<name>` is not a valid plugin slug.
    candidate = plugin_versions.plugin_dir(payload_dir, name)
    if not (candidate / plugin_manifest.MANIFEST_FILENAME).is_file():
        if (payload_dir / plugin_manifest.MANIFEST_FILENAME).is_file():
            candidate.mkdir(parents=True, exist_ok=True)
            for stray in sorted(payload_dir.iterdir()):
                if stray != candidate:
                    shutil.move(str(stray), str(candidate / stray.name))
        else:
            shutil.rmtree(staging, ignore_errors=True)
            return {
                "status": "quarantined",
                "name": name,
                "error": f"archive does not contain {name}/{plugin_manifest.MANIFEST_FILENAME}",
            }

    manifest, merr = plugin_manifest.load_manifest(candidate)
    if merr or manifest is None:
        shutil.rmtree(staging, ignore_errors=True)
        return {"status": "quarantined", "name": name, "error": merr}

    # Identity has three witnesses — the listing, the manifest, the signature —
    # and the listing is the one the user read before pressing install. An
    # artifact that carries another version than the entry promised is refused,
    # even when a trusted key signed it: the signature binds name+version, not
    # the entry the operator listed.
    declared = str(entry.get("version") or "")
    delivered = str(manifest.get("version", ""))
    if declared and declared != delivered:
        shutil.rmtree(staging, ignore_errors=True)
        return {
            "status": "identity_mismatch",
            "name": name,
            "error": f"listing offers {declared}, the artifact carries {delivered}",
        }

    if inspect is not None:
        refusal = inspect(candidate, manifest)
        if refusal:
            shutil.rmtree(staging, ignore_errors=True)
            return {
                "status": "refused",
                "name": name,
                "error": str(refusal)[:300],
            }

    # E4b: the signature is verified against the STAGED content, before anything
    # is moved to a loadable path. Fail-closed → the staging directory goes away
    # and the installed plugin (if any) is left untouched.
    if isinstance(signature, dict):
        from core import plugin_signing

        explicit = trusted_public_keys is not None
        pems = (
            trusted_public_keys
            if explicit
            else plugin_signing.load_trusted_public_keys()
        )
        verify_class = None if explicit else (
            plugin_signing.FIRST_PARTY
            if trust in {"official", "verified"}
            else plugin_signing.USER
        )
        ok, reason = plugin_signing.verify_plugin_dir(
            candidate,
            signature,
            pems,
            trust_class=verify_class,
        )
        if not ok:
            shutil.rmtree(staging, ignore_errors=True)
            return {
                "status": "quarantined",
                "name": name,
                "error": f"signature_invalid: {reason}",
            }
        # Persist the verified record inside the dir for enable-time drift checks.
        (candidate / plugin_manifest.SIG_FILENAME).write_text(
            json.dumps(signature, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    from core import plugin_signing

    final = plugin_versions.plugin_dir(plugins_root, name)
    installed = _installed_version(final)
    if not installed:
        # A damaged installed manifest must not erase the floor; the last
        # verified pin still names the version that was installed.
        pin = plugin_signing.load_pin(name)
        installed = str(pin.get("version") or "") if pin else ""
    if installed and _version_key(str(manifest.get("version", ""))) < _version_key(installed):
        # T-03: the signature says who built the artifact, not that it is the
        # newest one. An old signed artifact served by a listing, or signed by a
        # key that was trusted once, must not replace a newer install.
        shutil.rmtree(staging, ignore_errors=True)
        return {
            "status": "downgrade_refused",
            "name": name,
            "error": (
                f"installed {installed}, refused to replace it with "
                f"{manifest.get('version')}"
            ),
        }
    backup = plugin_versions.backup_current(final) if final.exists() else None
    if final.exists():
        shutil.rmtree(staging, ignore_errors=True)
        return {
            "status": "commit_failed",
            "name": name,
            "error": "the installed directory could not be moved aside",
        }
    try:
        candidate.rename(final)
    except OSError as exc:
        plugin_versions.restore_backup(backup, final)
        shutil.rmtree(staging, ignore_errors=True)
        return {
            "status": "commit_failed",
            "name": name,
            "error": f"the new version could not be committed: {exc}",
        }
    try:
        if isinstance(signature, dict):
            plugin_signing.record_pin(name, signature, trust_class=verify_class)
        else:
            # A deliberate unsigned local install is not a lost record; it is a
            # new identity and must not inherit the previous signature's pin.
            plugin_signing.clear_pin(name)
    except OSError:
        shutil.rmtree(final, ignore_errors=True)
        plugin_versions.restore_backup(backup, final)
        shutil.rmtree(staging, ignore_errors=True)
        return {
            "status": "pin_failed",
            "name": name,
            "error": "pin_failed",
        }
    plugin_versions.commit_backup(final)
    shutil.rmtree(staging, ignore_errors=True)

    _register_installed(name)
    result = {
        "status": "extracted",
        "name": name,
        "version": delivered,
        "trust": trust,
    }
    if trust == "local" and not signed:
        result["warning"] = "local_trust"
    return result


def install_from_marketplace(
    name: str,
    *,
    marketplace: dict[str, Any] | None = None,
    fetcher: Callable[[str], bytes] | None = None,
    root: Path | None = None,
    trusted_public_keys: list[bytes] | None = None,
    allow_local_trust: bool = False,
    inspect: Callable[[Path, dict[str, Any]], str | None] | None = None,
) -> dict[str, Any]:
    """Install and record every outcome in the audit log.

    A replacement of the same version with different bytes was invisible
    before: the switch state did not change, so no lifecycle row existed. The
    install row carries the artifact identity and the result.
    """
    try:
        result = _install_from_marketplace(
            name,
            marketplace=marketplace,
            fetcher=fetcher,
            root=root,
            trusted_public_keys=trusted_public_keys,
            allow_local_trust=allow_local_trust,
            inspect=inspect,
        )
    except Exception as exc:
        _audit_install(name, {"status": "raised", "error": type(exc).__name__}, marketplace)
        raise
    _audit_install(name, result, marketplace)
    return result


