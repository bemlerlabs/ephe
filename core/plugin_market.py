"""Ephe — Plugin marketplace (Extensions wave E4a)
core/plugin_market.py

Resolution + installation of catalog plugins from a marketplace listing:
`plugin-marketplace.json` (repo root) maps plugin ids to versioned, hashed
artifacts (url). Install flow is strictly verify-before-write:

    resolve → fetch (injectable) → sha256 → SAFE unzip (staging only)
            → manifest validation → listing identity → SIGNATURE VERIFY
            → move into place

Nothing reaches a loadable path until every check above has passed: the bytes
stay under `.staging-<name>/` and a refused package leaves the previously
installed plugin exactly as it was.

- hash mismatch: REJECTED, nothing extracted.
- unsafe archive (path traversal / absolute members): REJECTED.
- invalid manifest: quarantined (the extracted directory is removed again).
- artifact version differs from the version the listing declares: REJECTED.
- signature invalid or missing on a signed entry: quarantined, before the move.
- unknown plugin id / missing url: honest status, never a crash.

The fetcher is injectable so tests (and offline users) never touch network.

Ephe – Bad Liebenzell, Schwarzwald
"""

from __future__ import annotations

import json
import shutil
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Any, Callable

from core import plugin_manifest
from core.plugin_store import (
    REGISTRY_FILENAME,
    config_root,
    load_registry,
    sha256_hex,
    _write_registry,
)

MARKETPLACE_FILENAME = "plugin-marketplace.json"
MARKETPLACE_VERSION = 1

#: Archive bounds checked before any member reaches the staging directory.
MAX_ARCHIVE_MEMBERS = 2000
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_RATIO = 100


def marketplace_path() -> Path:
    return Path(__file__).resolve().parent.parent / MARKETPLACE_FILENAME


def load_marketplace(path: Path | None = None) -> dict[str, Any]:
    """Fail-soft marketplace read: missing/broken → empty listing."""
    target = Path(path) if path is not None else marketplace_path()
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": MARKETPLACE_VERSION, "plugins": []}
    if not isinstance(raw, dict) or not isinstance(raw.get("plugins"), list):
        return {"version": MARKETPLACE_VERSION, "plugins": []}
    entries = [e for e in raw["plugins"] if isinstance(e, dict) and e.get("name")]
    return {"version": raw.get("version", MARKETPLACE_VERSION), "plugins": entries}


def resolve_entry(name: str, path: Path | None = None) -> dict[str, Any] | None:
    for entry in load_marketplace(path)["plugins"]:
        if str(entry.get("name")) == name:
            return entry
    return None


def _default_fetcher(url: str) -> bytes:
    import urllib.request

    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 (https pinned by operator config)
        return resp.read()


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
        target = (dest / member).resolve()
        if not target.is_relative_to(dest_resolved):
            return "unsafe_archive: path traversal member"
        if member.endswith("/"):
            continue
    zf.extractall(dest)
    return None


def install_from_marketplace(
    name: str,
    *,
    marketplace: dict[str, Any] | None = None,
    fetcher: Callable[[str], bytes] | None = None,
    root: Path | None = None,
    trusted_public_keys: list[bytes] | None = None,
    allow_local_trust: bool = False,
) -> dict[str, Any]:
    """Install one marketplace plugin, verifying everything in staging.

    The plugins root only receives a directory that has passed hash, manifest,
    listing-identity and trust checks. Official, verified and community entries
    require a valid signature regardless of the enable-time drift setting; a
    local unsigned artifact needs `allow_local_trust`, lands disabled and
    carries the local-trust warning.
    """
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
    except Exception as exc:  # noqa: BLE001 — honest status, never a crash
        return {"status": "fetch_failed", "name": name, "error": str(exc)[:200]}

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
    staging = plugins_root / f".staging-{name}"
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
    candidate = payload_dir / name
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

    # E4b: the signature is verified against the STAGED content, before anything
    # is moved to a loadable path. Fail-closed → the staging directory goes away
    # and the installed plugin (if any) is left untouched.
    if isinstance(signature, dict):
        from core import plugin_signing

        pems = (
            trusted_public_keys
            if trusted_public_keys is not None
            else plugin_signing.load_trusted_public_keys()
        )
        ok, reason = plugin_signing.verify_plugin_dir(candidate, signature, pems)
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

    final = plugins_root / name
    installed = _installed_version(final)
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
    if final.exists():
        shutil.rmtree(final, ignore_errors=True)
    candidate.rename(final)
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


def _version_key(version: str) -> tuple[int, ...]:
    """The numeric shape of an X.Y.Z manifest version, for the floor comparison."""
    try:
        return tuple(int(part) for part in str(version).split("."))
    except ValueError:
        return ()


def _installed_version(root: Path) -> str:
    """The version of the plugin already at `root`, or empty when none is there."""
    if not root.is_dir():
        return ""
    manifest, _error = plugin_manifest.load_manifest(root)
    return str(manifest.get("version", "")) if manifest else ""


def _register_installed(name: str) -> None:
    """Best-effort: make the installed plugin visible as an explicit registry
    entry. E5 wiring: the deep setting `plugins.plugin_autorun` (default
    OFF, conservative) decides whether a fresh install lands enabled."""
    from core import plugin_switch_policy
    from core.settings_schema import deep_bool

    enabled = deep_bool("plugins.plugin_autorun") and not plugin_switch_policy.read_only()
    items = load_registry()
    if any(str(p.get("name")) == name for p in items):
        return
    items.append({"name": name, "enabled": enabled})
    try:
        _write_registry(items, config_root() / REGISTRY_FILENAME)
    except OSError:
        pass
    from core import plugin_runtime
    from core.plugin_lifecycle import LifecycleError
    from core.skills import invalidate_skill_cache

    plugin_runtime.invalidate_ownership_cache()
    invalidate_skill_cache()
    try:
        plugin_runtime.lifecycle().set_enabled(
            name, enabled, reason="marketplace install"
        )
    except LifecycleError:
        pass
