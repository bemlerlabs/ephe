"""One marketplace index: schema, aliases and the catalog migration.

Three catalog files grew beside each other: the generated metadata manifest,
the store catalog with directory hashes, and the legacy install listing with
three empty artifacts. This module names the one document they migrate into,
`marketplace/index.json`, and the fields an entry has to carry before it may
appear there: publisher, licence, version, SHA-256, source and content.

The migration is deterministic and writes only when the bytes change. It reads
the three catalogs for what the built index cannot know (German descriptions,
icons, legacy names) and the built index for the artifact identity, because
that is the only one of the four documents whose hash names bytes a user can
download.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from core import marketplace_index

TARGET_ENTRIES = 25
DEFAULT_LICENSE = "BUSL-1.1"
PACK_LICENSE = "LicenseRef-Ephe"

CATALOG_FILES = (
    "ephe-marketplace.json",
    "plugin-catalog.json",
    "plugin-marketplace.json",
)

#: Legacy install names and the one entry that carries the same function now.
#: `plugin_store.LEGACY_SLUG_MAP` fans the old state out to every successor;
#: a catalog lookup needs exactly one answer.
ALIASES: dict[str, str] = {
    "web-search": "web-research",
    "coding-suite": "code-shell",
    "document-factory": "local-document-factory",
}

_REQUIRED_CHECKS = ("publisher", "license", "version", "sha256", "source", "content")


class CatalogError(ValueError):
    def __init__(self, code: str, path: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.path = path
        self.detail = detail


def _fail(code: str, path: str, detail: str = "") -> None:
    raise CatalogError(code, path, detail)


def _description_text(raw: Any) -> dict[str, str]:
    if isinstance(raw, str):
        return {"en": raw}
    if isinstance(raw, dict):
        return {str(key): str(value) for key, value in raw.items() if isinstance(value, str)}
    return {}


def license_for(plugin: dict[str, Any]) -> str:
    if plugin.get("kind") == "skill-pack":
        return PACK_LICENSE
    return DEFAULT_LICENSE if plugin.get("provenance") != "third-party" else "MIT"


def _verification(plugin: dict[str, Any]) -> dict[str, Any]:
    versions = plugin.get("versions") or []
    version = versions[0] if versions and isinstance(versions[0], dict) else {}
    source = version.get("source") if isinstance(version.get("source"), dict) else {}
    description = _description_text(plugin.get("description"))
    checks = {
        "publisher": bool(str((plugin.get("publisher") or {}).get("name") or "").strip()),
        "license": bool(plugin.get("license")),
        "version": bool(version.get("version")),
        "sha256": bool(source.get("sha256")),
        "source": bool(source.get("url")),
        "content": bool(str(description.get("en") or "").strip()),
    }
    signature = any(
        isinstance(item.get("source"), dict) and item["source"].get("signature")
        for item in versions
        if isinstance(item, dict)
    )
    publisher = "verified" if (plugin.get("publisher") or {}).get("verified") else "unverified"
    if publisher == "unverified" and plugin.get("provenance") == "third-party":
        publisher = "reviewed"
    return {
        "content": "verified" if all(checks.values()) else "incomplete",
        "publisher": publisher,
        "signature": "signed" if signature else "unsigned",
        "checks": checks,
    }


def decorate(index: dict[str, Any]) -> dict[str, Any]:
    """Add licence, aliases and the verification record to a built index.

    Deterministic: the same input yields the same fields, so the builder and
    the migration produce byte-identical documents.
    """
    out = copy.deepcopy(index)
    plugins = out.get("plugins")
    if not isinstance(plugins, list):
        return out
    names = {str(plugin.get("name")) for plugin in plugins if isinstance(plugin, dict)}
    for plugin in plugins:
        if not isinstance(plugin, dict):
            continue
        plugin.setdefault("license", license_for(plugin))
        plugin["verification"] = _verification(plugin)
    declared = out.get("aliases")
    if not isinstance(declared, dict):
        declared = {alias: canonical for alias, canonical in ALIASES.items() if canonical in names}
    out["aliases"] = dict(sorted(declared.items()))
    return out


def validate_catalog(raw: Any) -> dict[str, Any]:
    """Validate the one index, raising the first field that breaks the contract."""
    try:
        parsed = marketplace_index.validate_index(raw, source_kind="bundled")
    except marketplace_index.IndexError as exc:
        raise CatalogError(exc.code, exc.path, exc.detail) from exc
    for plugin in parsed["plugins"]:
        path = f"plugins.{plugin['name']}"
        if not plugin.get("license"):
            _fail("license", f"{path}.license", "a licence is required")
        verification = plugin.get("verification")
        if not isinstance(verification, dict):
            _fail("verification", f"{path}.verification", "a verification record is required")
        checks = verification.get("checks")
        if not isinstance(checks, dict):
            _fail("verification", f"{path}.verification.checks")
        missing = [name for name in _REQUIRED_CHECKS if checks.get(name) is not True]
        if missing:
            _fail("incomplete", path, ", ".join(missing))
        for version in plugin["versions"]:
            if not marketplace_index._HEX64.match(version["source"]["sha256"]):
                _fail("sha256", f"{path}.versions.{version['version']}.source.sha256")
    return parsed


def coverage(index: dict[str, Any], *, target: int = TARGET_ENTRIES) -> dict[str, Any]:
    verified = [
        plugin["name"]
        for plugin in index.get("plugins", [])
        if (plugin.get("verification") or {}).get("content") == "verified"
    ]
    return {
        "entries": len(index.get("plugins", [])),
        "verified": len(verified),
        "target": target,
        "gap": max(0, target - len(verified)),
        "verified_ids": verified,
    }


def artifact_checks(root: Path, index: dict[str, Any]) -> list[dict[str, str]]:
    """Compare every indexed ZIP digest with the bytes on disk."""
    findings: list[dict[str, str]] = []
    base = Path(root) / "marketplace"
    for plugin in index.get("plugins", []):
        version = plugin["versions"][0]
        target = base / version["source"]["url"]
        actual = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() else ""
        findings.append(
            {
                "name": plugin["name"],
                "version": version["version"],
                "status": "ok" if actual == version["source"]["sha256"] else "mismatch",
            }
        )
    return findings


def _catalog_entries(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]]]:
    """Every id the three catalogs name, kept with the catalog file that names it."""
    seen: dict[str, dict[str, Any]] = {}
    owners: dict[str, list[str]] = {}
    for filename in CATALOG_FILES:
        try:
            raw = json.loads((Path(root) / filename).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        items = raw.get("plugins") if isinstance(raw, dict) else None
        if items is None and isinstance(raw, dict):
            items = raw.get("public")
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict) or not item.get("name"):
                continue
            name = str(item["name"])
            owners.setdefault(name, []).append(filename)
            seen.setdefault(name, item)
    return seen, owners


def _pack_source(root: Path, name: str) -> dict[str, Any]:
    """What the pack's own directory can prove: upstream licence and German copy."""
    base = Path(root) / "marketplace" / "sources" / name
    found: dict[str, Any] = {}
    try:
        provenance = json.loads((base / "PROVENANCE.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        provenance = {}
    licence = provenance.get("license") if isinstance(provenance, dict) else None
    if isinstance(licence, dict) and licence.get("id"):
        found["license"] = str(licence["id"])
    try:
        manifest = json.loads((base / "ephe-plugin.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        manifest = {}
    i18n = _description_text(manifest.get("description_i18n")) if isinstance(manifest, dict) else {}
    if i18n:
        found["description_i18n"] = i18n
    return found


def _enrich(index: dict[str, Any], root: Path) -> dict[str, Any]:
    out = copy.deepcopy(index)
    metadata = _catalog_entries(root)[0]
    icon_dir = Path(root) / "marketplace" / "icons"
    for plugin in out.get("plugins", []):
        name = str(plugin.get("name"))
        meta = metadata.get(name) or {}
        own = _pack_source(root, name)
        description = _description_text(plugin.get("description"))
        catalog_i18n = _description_text(meta.get("description_i18n"))
        own_i18n = _description_text(own.get("description_i18n"))
        for lang, value in (*catalog_i18n.items(), *own_i18n.items()):
            if value and not description.get(lang):
                description[lang] = value
        if description:
            plugin["description"] = description
        if own.get("license"):
            plugin["license"] = str(own["license"])
        icon = plugin.get("icon")
        if not (isinstance(icon, dict) and icon.get("light")):
            candidate = icon_dir / f"{name}.svg"
            if candidate.is_file():
                plugin["icon"] = {
                    "light": f"icons/{name}.svg",
                    "dark": f"icons/{name}.svg",
                    "alt": str(plugin.get("displayName") or name),
                }
        if not plugin.get("license"):
            plugin["license"] = license_for(plugin)
    return out


def migrate(root: Path) -> dict[str, Any]:
    """Merge the three catalogs into `marketplace/index.json`; write on change."""
    root = Path(root)
    target = root / "marketplace" / "index.json"
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CatalogError("index_unreadable", "marketplace/index.json", str(exc)) from exc
    if not isinstance(raw, dict):
        raise CatalogError("index_unreadable", "marketplace/index.json", "object expected")

    merged = decorate(_enrich(raw, root))
    parsed = validate_catalog(merged)
    if "signature" in raw:
        parsed["signature"] = raw["signature"]
    body = json.dumps(parsed, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    changed = not target.is_file() or target.read_text(encoding="utf-8") != body
    if changed:
        tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        tmp.write_text(body, encoding="utf-8")
        os.replace(tmp, target)

    _, owners = _catalog_entries(root)
    duplicates = [
        {"id": name, "catalogs": files}
        for name, files in sorted(owners.items())
        if len(files) > 1
    ]
    summary = coverage(parsed)
    return {
        **summary,
        "changed": changed,
        "duplicates": duplicates,
        "aliases": parsed.get("aliases", {}),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Migrate the marketplace catalogs into one index")
    parser.add_argument("--root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--check", action="store_true", help="report drift, write nothing")
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.check:
        target = root / "marketplace" / "index.json"
        before = target.read_text(encoding="utf-8")
        summary = migrate(root)
        after = target.read_text(encoding="utf-8")
        if summary["changed"]:
            target.write_text(before, encoding="utf-8")
            print("marketplace index is stale; run core.marketplace_catalog without --check")
            return 1
        print(
            f"marketplace index is fresh: {summary['verified']} verified entries, "
            f"gap {summary['gap']} to {summary['target']}"
        )
        return 0
    summary = migrate(root)
    print(
        f"marketplace index: {summary['verified']} verified entries, "
        f"gap {summary['gap']} to {summary['target']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
