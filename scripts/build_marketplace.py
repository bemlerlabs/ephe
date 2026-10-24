"""Build the canonical bundled marketplace index and its immutable artifacts.

Every first-party plugin is packaged into a deterministic ZIP. The same source
tree produces byte-identical archives on every run, so a hash in the index is a
stable claim. With a signing key, each plugin directory is signed before it is
zipped and the index itself is signed; without one, the index is a bundled,
explicitly unsigned local catalog.

Usage:
    python scripts/build_marketplace.py [--out marketplace] [--sign-key key.pem]
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import marketplace_index, plugin_manifest, plugin_signing
from core.plugin_store import sha256_hex

SKIP_NAMES = {"__pycache__", ".DS_Store", ".git"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


class BuildError(RuntimeError):
    pass


def _files(directory: Path) -> list[Path]:
    out: list[Path] = []
    for path in sorted(directory.rglob("*")):
        if path.name in SKIP_NAMES or path.suffix in SKIP_SUFFIXES:
            continue
        if path.is_symlink():
            raise BuildError(f"symlink in plugin tree: {path}")
        if path.is_file():
            out.append(path)
    return out


def zip_plugin(directory: Path, name: str, target: Path, *, include_signature: bool = False) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in _files(directory):
            if path.name == plugin_manifest.SIG_FILENAME and not include_signature:
                continue
            relative = PurePosixPath(path.relative_to(directory)).as_posix()
            info = zipfile.ZipInfo(f"{name}/{relative}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o100644 & 0xFFFF) << 16
            zf.writestr(info, path.read_bytes(), compresslevel=9)
    return sha256_hex(target.read_bytes())


def zip_skill_pack(pack: dict, skills_dir: Path, target: Path) -> str:
    """Package one curated skill pack without a second mapping table."""
    pack_id = str(pack.get("id") or "")
    if not pack_id or not pack.get("skills"):
        raise BuildError(f"bad skill pack: {pack_id or '?'}")
    manifest = {
        "id": pack_id,
        "title": str(pack.get("title") or pack_id),
        "description": str(pack.get("description") or ""),
        "skills": [str(skill) for skill in pack["skills"]],
        "license": "LicenseRef-Ephe",
        "attribution": "Ephe",
        "source": "skills/pack-index.json",
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        info = zipfile.ZipInfo(f"{pack_id}/pack.json", date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = (0o100644 & 0xFFFF) << 16
        zf.writestr(info, json.dumps(manifest, sort_keys=True, indent=2) + "\n", compresslevel=9)
        for skill in manifest["skills"]:
            directory = skills_dir / skill
            if not (directory / "SKILL.md").is_file():
                raise BuildError(f"{pack_id}: skill {skill!r} has no SKILL.md")
            for path in _files(directory):
                relative = PurePosixPath(path.relative_to(directory)).as_posix()
                info = zipfile.ZipInfo(
                    f"{pack_id}/skills/{skill}/{relative}", date_time=(1980, 1, 1, 0, 0, 0)
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = (0o100644 & 0xFFFF) << 16
                zf.writestr(info, path.read_bytes(), compresslevel=9)
    return sha256_hex(target.read_bytes())


def _signed_copy(directory: Path, name: str, private_pem: bytes, kid: str, temp_root: Path) -> tuple[Path, dict]:
    target = temp_root / name
    target.mkdir(parents=True, exist_ok=True)
    for path in _files(directory):
        if path.name == plugin_manifest.SIG_FILENAME:
            continue
        relative = path.relative_to(directory)
        (target / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target / relative)
    record = plugin_signing.sign_plugin_dir(target, private_pem, kid)
    return target, record


def _display_name(name: str, listing: dict) -> str:
    return str(listing.get("displayName") or name.replace("-", " ").title())


def build(
    *,
    plugins_dir: Path,
    metadata_path: Path,
    out_dir: Path,
    private_pem: bytes | None,
    kid: str,
    min_ephe: str,
    third_party_path: Path | None = None,
) -> dict:
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        metadata = {}
    listing = {
        str(entry.get("name")): entry
        for entry in metadata.get("plugins", [])
        if isinstance(entry, dict) and entry.get("name")
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    artifacts = out_dir / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    timestamp = int(os.environ.get("SOURCE_DATE_EPOCH", "0"))

    plugins: list[dict] = []
    for directory in sorted(path for path in plugins_dir.iterdir() if path.is_dir()):
        manifest, error = plugin_manifest.load_manifest(directory)
        if error or manifest is None:
            continue
        name = str(manifest["name"])
        version = str(manifest["version"])
        meta = listing.get(name, {})
        with tempfile.TemporaryDirectory(prefix="ephe-market-") as temp:
            if private_pem is not None:
                source, record = _signed_copy(
                    directory, name, private_pem, kid, Path(temp)
                )
            else:
                source, record = directory, None
            archive = artifacts / f"{name}-{version}.zip"
            digest = zip_plugin(
                source, name, archive, include_signature=record is not None
            )
        description = meta.get("description_i18n") or {}
        english = (
            description.get("en")
            if isinstance(description, dict)
            else str(description or "")
        ) or str(manifest.get("description") or "")
        description = {"en": english}
        categories = [str(meta.get("category"))] if meta.get("category") else []
        components = [
            key
            for key, value in (manifest.get("components") or {}).items()
            if value
        ]
        entry = {
            "name": name,
            "displayName": _display_name(name, meta),
            "description": description,
            "publisher": {"name": str(meta.get("author") or "Ephe"), "verified": True},
            "trust": "official" if record is not None else "bundled",
            "quality_label": str(meta.get("quality_label") or "plugin"),
            "provenance": str(manifest.get("origin") or "first-party"),
            "categories": categories,
            "versions": [
                {
                    "version": version,
                    "publishTimestamp": timestamp,
                    "source": {
                        "type": "zip",
                        "url": f"artifacts/{archive.name}",
                        "sha256": digest,
                        **({"signature": record} if record is not None else {}),
                    },
                    "engines": {"ephe": min_ephe},
                    "permissions": manifest.get("permissions") or {},
                    "components": components,
                }
            ],
        }
        if isinstance(meta.get("measurement"), dict):
            entry["measurement"] = meta["measurement"]
        icon = meta.get("icon")
        if isinstance(icon, str) and (ROOT / icon).is_file():
            icon_target = out_dir / "icons" / f"{name}{Path(icon).suffix}"
            icon_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / icon, icon_target)
            entry["icon"] = {
                "light": f"icons/{icon_target.name}",
                "dark": f"icons/{icon_target.name}",
                "alt": entry["displayName"],
            }
        plugins.append(entry)

    # Third-party packs live outside plugins/ (they are not part of the
    # first-party portfolio the registry and its gates count), but they are
    # listed and installable like every other marketplace entry.
    third_party = third_party_path or (ROOT / "marketplace" / "third-party.json")
    try:
        foreign_dirs = [
            ROOT / str(item["path"])
            for item in json.loads(third_party.read_text(encoding="utf-8")).get("plugins", [])
            if isinstance(item, dict) and item.get("path")
        ]
    except (OSError, ValueError):
        foreign_dirs = []
    for directory in foreign_dirs:
        manifest, error = plugin_manifest.load_manifest(directory)
        if error or manifest is None:
            continue
        name = str(manifest["name"])
        version = str(manifest["version"])
        meta = listing.get(name, {})
        archive = artifacts / f"{name}-{version}.zip"
        digest = zip_plugin(directory, name, archive, include_signature=False)
        description = meta.get("description_i18n") or {}
        english = (
            description.get("en") if isinstance(description, dict) else str(description or "")
        ) or str(manifest.get("description") or "")
        entry = {
            "name": name,
            "displayName": _display_name(name, meta),
            "description": {"en": english},
            "publisher": {"name": str(meta.get("author") or manifest.get("origin") or "third-party"), "verified": False},
            "trust": "bundled",
            "quality_label": str(meta.get("quality_label") or "plugin"),
            "provenance": str(manifest.get("origin") or "third-party"),
            "categories": [str(meta.get("category"))] if meta.get("category") else [],
            "versions": [{
                "version": version,
                "publishTimestamp": timestamp,
                "source": {"type": "zip", "url": f"artifacts/{archive.name}", "sha256": digest},
                "engines": {"ephe": min_ephe},
                "permissions": manifest.get("permissions") or {},
                "components": [key for key, value in (manifest.get("components") or {}).items() if value],
            }],
        }
        if meta.get("kind"):
            entry["kind"] = str(meta["kind"])
        plugins.append(entry)

    try:
        packs = json.loads((ROOT / "skills" / "pack-index.json").read_text(encoding="utf-8"))["packs"]
    except (OSError, ValueError, KeyError) as exc:
        raise BuildError(f"skills/pack-index.json is unreadable: {type(exc).__name__}") from exc
    plugin_names = {entry["name"] for entry in plugins}
    tiers_path = ROOT / "skills" / "tiers.json"
    tier_counts = {}
    if tiers_path.is_file():
        tier_data = json.loads(tiers_path.read_text(encoding="utf-8")).get("counts") or {}
        tier_counts = {key: int(value) for key, value in tier_data.items()}
    for pack in packs:
        pack_id = str(pack.get("id") or "")
        if not pack_id or pack_id in plugin_names:
            raise BuildError(f"skill pack id collides with a plugin: {pack_id!r}")
        archive = artifacts / f"{pack_id}-1.0.0.zip"
        digest = zip_skill_pack(pack, ROOT / "skills", archive)
        plugins.append({
            "name": pack_id,
            "displayName": str(pack.get("title") or pack_id),
            "description": {"en": str(pack.get("description") or pack.get("title") or pack_id)},
            "publisher": {"name": "Ephe", "verified": True},
            "trust": "bundled",
            "kind": "skill-pack",
            "quality_label": "bundled",
            "provenance": "first-party",
            "tiers": tier_counts,
            "categories": ["skills"],
            "versions": [{
                "version": "1.0.0",
                "publishTimestamp": timestamp,
                "source": {
                    "type": "zip",
                    "url": f"artifacts/{archive.name}",
                    "sha256": digest,
                },
                "engines": {"ephe": min_ephe},
                "permissions": {},
                "components": ["skills"],
            }],
        })

    skill_tiers = {}
    if tiers_path.is_file():
        tier_data = json.loads(tiers_path.read_text(encoding="utf-8")).get("skills") or {}
        skill_tiers = {name: entry.get("tier") for name, entry in tier_data.items()}
    index = {
        "format": 2,
        "name": "ephe-bundled",
        "owner": {"name": "Ephe"},
        "metadata": {
            "categories": {
                category: {"title": {"en": category.title()}}
                for category in sorted(
                    {category for entry in plugins for category in entry["categories"]}
                )
            },
            "skill_tiers": skill_tiers,
        },
        "plugins": sorted(plugins, key=lambda entry: entry["name"]),
    }
    marketplace_index.validate_index(
        index, source_kind="remote" if private_pem is not None else "bundled"
    )
    if private_pem is not None:
        signature = plugin_signing.sign(index, private_pem)
        index["signature"] = {"alg": plugin_signing.SIG_ALG, "kid": kid, "signature": signature}
    (out_dir / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    revocations = out_dir / "revocations.json"
    if not revocations.exists():
        revocations.write_text(
            json.dumps({"format": 1, "revoked": []}, indent=2) + "\n", encoding="utf-8"
        )
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the bundled marketplace index")
    parser.add_argument("--plugins", default=str(ROOT / "plugins"))
    parser.add_argument("--metadata", default=str(ROOT / "ephe-marketplace.json"))
    parser.add_argument("--out", default=str(ROOT / "marketplace"))
    parser.add_argument("--sign-key", default="")
    parser.add_argument("--kid", default="first-party")
    parser.add_argument("--min-ephe", default=">=0.1.3")
    parser.add_argument("--third-party", default="")
    args = parser.parse_args()
    try:
        private_pem = Path(args.sign_key).read_bytes() if args.sign_key else None
        index = build(
            plugins_dir=Path(args.plugins),
            metadata_path=Path(args.metadata),
            out_dir=Path(args.out),
            private_pem=private_pem,
            kid=args.kid,
            min_ephe=args.min_ephe,
            third_party_path=Path(args.third_party) if args.third_party else None,
        )
    except (BuildError, ValueError, OSError, marketplace_index.IndexError) as exc:
        print(f"build_marketplace: {exc}", file=sys.stderr)
        return 2
    print(f"build_marketplace: {len(index['plugins'])} plugins")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
