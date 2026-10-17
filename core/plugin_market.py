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
from core.plugin_store import REGISTRY_FILENAME, config_root, load_registry, sha256_hex, _write_registry

MARKETPLACE_FILENAME = "plugin-marketplace.json"
MARKETPLACE_VERSION = 1


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
    dest_resolved = dest.resolve()
    for member in zf.namelist():
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
) -> dict[str, Any]:
    """Install one marketplace plugin, verifying everything in staging.

    The plugins root only receives a directory that has passed hash, manifest,
    listing-identity and (when the entry carries one) signature checks.
    """
    listing = marketplace if marketplace is not None else load_marketplace()
    entry = None
    for e in listing.get("plugins", []):
        if str(e.get("name")) == name:
            entry = e
            break
    if entry is None:
        return {"status": "unknown_plugin", "name": name, "error": "not in marketplace listing"}
    url = str(entry.get("url") or "")
    if not url:
        return {"status": "no_url", "name": name, "error": "marketplace entry carries no artifact url"}

    fetch = fetcher if fetcher is not None else _default_fetcher
    try:
        payload = fetch(url)
    except Exception as exc:  # noqa: BLE001 — honest status, never a crash
        return {"status": "fetch_failed", "name": name, "error": str(exc)[:200]}

    expected = str(entry.get("sha256") or "")
    if not expected or sha256_hex(payload) != expected:
        return {"status": "hash_mismatch", "name": name, "error": "artifact hash does not match the marketplace entry"}

    plugins_root = Path(root) if root is not None else config_root() / plugin_manifest.PLUGINS_DIRNAME
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
            return {"status": "quarantined", "name": name, "error": f"archive does not contain {name}/{plugin_manifest.MANIFEST_FILENAME}"}

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
    signature = entry.get("signature")
    if isinstance(signature, dict):
        from core import plugin_signing

        pems = trusted_public_keys if trusted_public_keys is not None else plugin_signing.load_trusted_public_keys()
        ok, reason = plugin_signing.verify_plugin_dir(candidate, signature, pems)
        if not ok:
            shutil.rmtree(staging, ignore_errors=True)
            return {"status": "quarantined", "name": name, "error": f"signature_invalid: {reason}"}
        # Persist the verified record inside the dir for enable-time drift checks.
        (candidate / plugin_manifest.SIG_FILENAME).write_text(
            json.dumps(signature, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    final = plugins_root / name
    if final.exists():
        shutil.rmtree(final, ignore_errors=True)
    candidate.rename(final)
    shutil.rmtree(staging, ignore_errors=True)

    _register_installed(name)
    return {"status": "extracted", "name": name, "version": delivered}


def _register_installed(name: str) -> None:
    """Best-effort: make the installed plugin visible as an explicit registry
    entry. E5 wiring: the deep setting `plugins.plugin_autorun` (default
    OFF, conservative) decides whether a fresh install lands enabled."""
    from core.settings_schema import deep_bool

    enabled = deep_bool("plugins.plugin_autorun")
    items = load_registry()
    if any(str(p.get("name")) == name for p in items):
        return
    items.append({"name": name, "enabled": enabled})
    try:
        _write_registry(items, config_root() / REGISTRY_FILENAME)
    except OSError:
        pass
