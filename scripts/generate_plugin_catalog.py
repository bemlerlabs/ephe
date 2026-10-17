"""◑ Ephe — plugin catalog regenerator (Extensions v2, E1).
scripts/generate_plugin_catalog.py

Reads every plugins/<slug>/ephe-plugin.json and writes plugin-catalog.json
(repo root) in the store schema: {version, public: [...], personal: []} with
name/description/version/tags/enabled/sha256/manifest. sha256 = dir_sha256
of the plugin dir (identical to the E3 computation; the drift-gate basis).

Tags are carried over from the existing catalog (mapped by slug) so that
curatorial tags survive renames. Run:
    .venv/bin/python scripts/generate_plugin_catalog.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # core.* is not importable when run by path


from core.plugin_manifest import dir_sha256, load_manifest
from core.plugin_store import catalog_path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / "plugins"


def build_catalog() -> tuple[dict[str, object], list[str]]:
    old_path = catalog_path()
    old_tags: dict[str, list[str]] = {}
    if old_path.is_file():
        try:
            old = json.loads(old_path.read_text(encoding="utf-8"))
            for seg in ("public", "personal"):
                for e in old.get(seg, []):
                    if isinstance(e, dict) and e.get("name"):
                        old_tags[str(e["name"])] = [
                            str(t) for t in e.get("tags", []) if isinstance(t, str)
                        ]
        except (OSError, ValueError):
            pass

    skips: list[str] = []
    public: list[dict[str, object]] = []
    for plugin_dir in sorted(p for p in PLUGINS.iterdir() if p.is_dir()):
        manifest, err = load_manifest(plugin_dir)
        if manifest is None:
            skips.append(f"{plugin_dir.name}: {err}")
            continue
        slug = str(manifest["name"])
        public.append(
            {
                "name": slug,
                "description": str(manifest["description"]),
                "tags": old_tags.get(slug, []),
                "enabled": True,
                "sha256": dir_sha256(plugin_dir),
                "url": "",
                "manifest": True,
                "version": str(manifest["version"]),
                "origin": str(manifest.get("origin", "first-party")),
            }
        )

    return {"version": 1, "public": public, "personal": []}, skips


def public_entries(catalog: dict[str, object]) -> list[dict[str, object]]:
    """The catalog's `public` list, narrowed from what json hands back as `object`."""
    raw = catalog.get("public")
    if not isinstance(raw, list):
        return []
    return [entry for entry in raw if isinstance(entry, dict)]


def check_only(expected: dict[str, object], skips: list[str]) -> int:
    """Compare the catalog the plugins imply against the one that is committed.

    `--check` exists because a freshness job must not write: on this shared worktree a regenerator that
    always writes has already been observed producing a byte-identical file (measured 2026-10-11, so the
    committed catalog is current) and a diff line it cannot explain.
    """
    path = catalog_path()
    for line in skips:
        print(f"plugin-catalog: SKIP {line}")
    if not path.is_file():
        print("plugin-catalog: no committed plugin-catalog.json to compare against")
        return 1
    committed = path.read_text(encoding="utf-8")
    rendered = json.dumps(expected, ensure_ascii=False, indent=2) + "\n"
    if committed == rendered:
        print(f"plugin-catalog: fresh -- {len(public_entries(expected))} plugins, "
              f"{len(skips)} skipped")
        return 0
    old = json.loads(committed)
    old_entries, new_entries = public_entries(old), public_entries(expected)
    names = {str(entry.get("name")) for entry in old_entries}
    now = {str(entry.get("name")) for entry in new_entries}
    for name in sorted(names - now):
        print(f"plugin-catalog: FAIL {name} is in the committed catalog and not on disk")
    for name in sorted(now - names):
        print(f"plugin-catalog: FAIL {name} is on disk and missing from the committed catalog")
    by_name = {str(entry.get("name")): entry for entry in old_entries}
    for entry in new_entries:
        previous = by_name.get(str(entry.get("name")))
        if previous and previous.get("sha256") != entry["sha256"]:
            print(f"plugin-catalog: FAIL {entry['name']}: sha256 "
                  f"{str(previous['sha256'])[:12]}... != {str(entry['sha256'])[:12]}...")
        elif previous and previous.get("version") != entry["version"]:
            print(f"plugin-catalog: FAIL {entry['name']}: version "
                  f"{previous['version']} != {entry['version']}")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1].strip())
    parser.add_argument("--check", action="store_true", help="compare against the committed catalog, write nothing")
    args = parser.parse_args(argv)

    if not PLUGINS.is_dir():
        print(f"plugin-catalog: no {PLUGINS} directory to read")
        return 1
    expected, skips = build_catalog()
    if args.check:
        return check_only(expected, skips)

    catalog_path().write_text(
        json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"plugin-catalog.json written: {len(public_entries(expected))} plugins")
    return 0


if __name__ == "__main__":
    sys.exit(main())
