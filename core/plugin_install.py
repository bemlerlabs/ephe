"""The one path into a loadable plugin directory.

Download, hash, safe extraction, manifest validation, listing identity and
signature verification all happen under staging. Only a candidate that passed
every check replaces the installed directory, and the installed version is
kept as a one-slot backup for rollback.
"""
from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import threading
import uuid
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
from core.plugin_lockfile import LOCK_FILENAME, rebuild_lockfile
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
_STAGING_PREFIX = ".staging-"

#: Sidecars this installer writes beside an artifact, outside the artifact's bytes.
#: A re-install of the same bytes is the same package even when an older install
#: wrote no `VERIFY.json` at all, so the comparison ignores both sidecars.
_SIDECAR_NAMES = frozenset({plugin_manifest.SIG_FILENAME, "VERIFY.json"})

_THREAD_LOCKS: dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


#: A bundle id never leaves this alphabet, so a lock file name built from it cannot
#: walk anywhere (CodeQL: py/path-injection, one of five in the 0.6.4 review).
_SAFE_LOCK_KEY_RE = __import__("re").compile(r"[^a-z0-9-]")


def _lock_key(name: str) -> str:
    """A filesystem-safe key for the per-name install lock."""
    return _SAFE_LOCK_KEY_RE.sub("-", str(name).lower())[:64] or "unnamed"


def _thread_lock(key: str) -> threading.Lock:
    with _THREAD_LOCKS_GUARD:
        lock = _THREAD_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _THREAD_LOCKS[key] = lock
        return lock


@contextlib.contextmanager
def _install_lock(root: Path, name: str):
    """Serialises every write to one plugin name, across threads and processes.

    Two installers of one name used to share the staging folder `.staging-<name>`
    and each other's commit window: one removed the other's payload and the loser
    raised `FileNotFoundError` out of the install. The lock is one file per name
    under `<config>/plugin-locks/`, outside the plugins root, so a removal still
    leaves that root with nothing but plugin directories in it.
    """
    key = f"{Path(root).resolve()}::{name}"
    with _thread_lock(key):
        lock_dir = Path(root).resolve().parent / "plugin-locks"
        handle = None
        try:
            lock_dir.mkdir(parents=True, exist_ok=True)
            handle = open(lock_dir / f"install-{_lock_key(name)}.lock", "a+", encoding="utf-8")
            try:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            except (ImportError, OSError):
                # No POSIX advisory lock on this host: the thread lock above is
                # what remains, and it still keeps this process's installers apart.
                pass
            yield
        finally:
            if handle is not None:
                try:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                except (ImportError, OSError):
                    pass
                handle.close()


def _new_staging(root: Path, name: str) -> Path:
    """A staging folder only this call can see.

    The name carries the pid and one random token so two processes that ignore the
    advisory lock still cannot extract into one another's payload.
    """
    token = f"{name}-{os.getpid()}-{uuid.uuid4().hex[:12]}"
    return plugin_versions.plugin_dir(root, token, prefix=_STAGING_PREFIX)


def _sweep_staging(root: Path, name: str) -> None:
    """Removes a staging folder a killed installer left behind for this name."""
    try:
        children = list(Path(root).iterdir())
    except OSError:
        return
    obsolete = {f"{_STAGING_PREFIX}{name}"}
    prefix = f"{_STAGING_PREFIX}{name}-"
    for child in children:
        if child.name in obsolete or child.name.startswith(prefix):
            shutil.rmtree(child, ignore_errors=True)


def _same_artifact(candidate: Path, installed: Path) -> bool:
    """Whether the staged bytes are the installed bytes, sidecars aside."""
    try:
        return plugin_manifest.dir_sha256(
            candidate, exclude_names=_SIDECAR_NAMES
        ) == plugin_manifest.dir_sha256(installed, exclude_names=_SIDECAR_NAMES)
    except OSError:
        return False


def _rebuild_lock(plugins_root: Path) -> str:
    """Writes the portfolio lock after a commit; "lockfile_update_failed" on refusal.

    The one install path every caller shares (`ephe plugin install`, the Creator
    tools, the marketplace service) has to leave the lock describing what is on
    disk. It used to be written by the service alone, so the CLI left the file
    missing and the next release compared against nothing.
    """
    from core import plugin_manifest as manifest_module

    try:
        default_root = manifest_module.plugins_root().resolve()
    except Exception:  # noqa: BLE001 — a scan root we cannot prove stays explicit
        default_root = None
    scan_root = (
        None if default_root is not None and Path(plugins_root).resolve() == default_root
        else Path(plugins_root)
    )
    try:
        rebuild_lockfile(config_root() / LOCK_FILENAME, scan_root)
        return ""
    except Exception:  # noqa: BLE001 — the package change already happened
        return "lockfile_update_failed"

#: The move each refusal leaves the author or the operator, keyed by the status this
#: module answers with. The status and its `error` say what happened; this says what to do
#: next, and every surface that prints one prints the other beside it. `extracted` is the
#: success status and is deliberately absent.
INSTALL_NEXT_STEPS: dict[str, str] = {
    "already_installed": (
        "Nothing to install: the same bundle is already here. Change the bytes to repair it, or "
        "remove it with `ephe plugin remove <name>` and install again."
    ),
    "invalid_name": (
        "Rename the bundle to a lowercase slug (a-z, 0-9, dashes), in the listing and in "
        "its folder."
    ),
    "unknown_plugin": (
        "Add the entry to plugin-marketplace.json, or check the id with `ephe plugin list`."
    ),
    "invalid_trust": (
        "Set trust to official, verified, community, local or blocked in the listing entry."
    ),
    "blocked_source": (
        "Remove the artifact from the listing, or point the entry at a source that is not "
        "blocked."
    ),
    "signature_required": "Sign the artifact, or list it under the local trust class.",
    "local_trust_required": (
        "Re-run with `--trust-local` after reading the bytes, or sign the artifact."
    ),
    "no_url": "Add the artifact url to the listing entry.",
    "fetch_failed": "Check the connection and the url, then install again.",
    "hash_mismatch": (
        "Recompute the sha256 of the artifact and put it in the listing entry."
    ),
    "unsafe_archive": (
        "Repack the artifact as a zip that stays inside one folder, then install again."
    ),
    "quarantined": "Read the error, fix the artifact or its manifest, then install again.",
    "identity_mismatch": (
        "Align the version in the listing entry with the manifest, then install again."
    ),
    "refused": (
        "Fix what the refusal names in the staged bundle, verify it again, then install "
        "again."
    ),
    "downgrade_refused": (
        "Install a newer artifact, or keep the version that is already installed."
    ),
    "commit_failed": "Check that the plugins folder is writable, then install again.",
    "pin_failed": "Check that the config folder is writable, then install again.",
}


def next_step_for(result: dict[str, Any]) -> str:
    """The move a refusal leaves, framed for whichever surface prints it."""
    status = str(result.get("status") or "")
    return INSTALL_NEXT_STEPS.get(
        status,
        "Read the status and the error, fix the artifact or the listing, then install "
        "again.",
    )

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
    with _install_lock(plugins_root, name):
        _sweep_staging(plugins_root, name)
        staging = _new_staging(plugins_root, name)
        try:
            return _commit_staged(
                name=name,
                entry=entry,
                payload=payload,
                signature=signature,
                trust=trust,
                inspect=inspect,
                staging=staging,
                plugins_root=plugins_root,
                trusted_public_keys=trusted_public_keys,
            )
        finally:
            shutil.rmtree(staging, ignore_errors=True)


def _commit_staged(
    *,
    name: str,
    entry: dict[str, Any],
    payload: bytes,
    signature: Any,
    trust: str,
    inspect: Callable[[Path, dict[str, Any]], str | None] | None,
    staging: Path,
    plugins_root: Path,
    trusted_public_keys: list[bytes] | None,
) -> dict[str, Any]:
    """Verify the staged bytes and move exactly that directory into place."""
    signed = isinstance(signature, dict)
    payload_dir = staging / "payload"
    err = _safe_extract(payload, payload_dir)
    if err:
        return {"status": "unsafe_archive", "name": name, "error": err}

    # The artifact must unpack to a directory named after the plugin. Either the
    # zip carries that top-level dir, or its manifest sits at the archive root —
    # in which case the payload is gathered into a directory of that name,
    # because the manifest validator requires name == directory name and
    # `.staging-<name>` is not a valid plugin slug.
    candidate = plugin_versions.plugin_dir(payload_dir, name)
    if not (candidate / plugin_manifest.MANIFEST_FILENAME).is_file():
        if (payload_dir / plugin_manifest.MANIFEST_FILENAME).is_file():
            try:
                candidate.mkdir(parents=True, exist_ok=True)
                for stray in sorted(payload_dir.iterdir()):
                    if stray != candidate:
                        shutil.move(str(stray), str(candidate / stray.name))
            except OSError as exc:
                # A member named like the gathered directory is a crafted archive,
                # not a reason to answer 500.
                return {
                    "status": "quarantined",
                    "code": "manifest_missing",
                    "name": name,
                    "error": f"the archive root could not be gathered ({type(exc).__name__})",
                }
        else:
            return {
                "status": "quarantined",
                "code": "manifest_missing",
                "name": name,
                "error": f"archive does not contain {name}/{plugin_manifest.MANIFEST_FILENAME}",
            }

    manifest, merr = plugin_manifest.load_manifest(candidate)
    if merr or manifest is None:
        return {
            "status": "quarantined",
            "code": "manifest_invalid",
            "name": name,
            "error": merr,
        }

    # Identity has three witnesses — the listing, the manifest, the signature —
    # and the listing is the one the user read before pressing install. An
    # artifact that carries another version than the entry promised is refused,
    # even when a trusted key signed it: the signature binds name+version, not
    # the entry the operator listed.
    declared = str(entry.get("version") or "")
    delivered = str(manifest.get("version", ""))
    if declared and declared != delivered:
        return {
            "status": "identity_mismatch",
            "name": name,
            "error": f"listing offers {declared}, the artifact carries {delivered}",
        }

    if inspect is not None:
        refusal = inspect(candidate, manifest)
        if refusal:
            return {
                "status": "refused",
                "name": name,
                "error": str(refusal)[:300],
            }

    # E4b: the signature is verified against the STAGED content, before anything
    # is moved to a loadable path. Fail-closed → the staging directory goes away
    # and the installed plugin (if any) is left untouched.
    verify_class = None
    if signed:
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
            # The verifier's reason is a closed vocabulary (drift, identity,
            # signature, no_trusted_key, stray record) plus two short hashes; the
            # surface names it instead of answering a bare "quarantined".
            return {
                "status": "quarantined",
                "code": "signature_invalid",
                "reason": reason[:240],
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
    delivered_version = str(manifest.get("version", ""))
    if installed and _version_key(delivered_version) < _version_key(installed):
        # T-03: the signature says who built the artifact, not that it is the
        # newest one. An old signed artifact served by a listing, or signed by a
        # key that was trusted once, must not replace a newer install.
        return {
            "status": "downgrade_refused",
            "name": name,
            "error": (
                f"installed {installed}, refused to replace it with "
                f"{manifest.get('version')}"
            ),
        }
    if (
        installed == delivered_version
        and final.is_dir()
        and _same_artifact(candidate, final)
    ):
        # A retry of the same artifact returns a code and writes nothing. The old
        # path moved the installed directory into the backup slot and back, which
        # is the window two concurrent installers raced for one backup name in.
        result: dict[str, Any] = {
            "status": "already_installed",
            "name": name,
            "version": delivered_version,
            "installed_version": installed,
            "trust": trust,
        }
        if trust == "local" and not signed:
            result["warning"] = "local_trust"
        return result

    try:
        backup = plugin_versions.backup_current(final) if final.exists() else None
    except OSError as exc:
        return {
            "status": "commit_failed",
            "name": name,
            "error": f"the installed directory could not be moved aside ({type(exc).__name__})",
        }
    if final.exists():
        return {
            "status": "commit_failed",
            "name": name,
            "error": "the installed directory could not be moved aside",
        }
    try:
        candidate.rename(final)
    except OSError as exc:
        plugin_versions.restore_backup(backup, final)
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
        return {
            "status": "pin_failed",
            "name": name,
            "error": "pin_failed",
        }
    plugin_versions.commit_backup(final)

    _register_installed(name)
    result = {
        "status": "extracted",
        "name": name,
        "version": delivered_version,
        "trust": trust,
    }
    if trust == "local" and not signed:
        result["warning"] = "local_trust"
    lock_error = _rebuild_lock(plugins_root)
    if lock_error:
        result["lockfile_error"] = lock_error
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


