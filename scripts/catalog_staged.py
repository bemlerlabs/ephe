"""◑ Ephe — the catalog row a commit leaves behind, judged from the index.
scripts/catalog_staged.py

A bundle edit that does not carry its catalog row leaves the store naming bytes
the directory no longer holds. The full suite reads those rows; the commit hook
did not, so the drift survived six commits (measured on 0ef1c8e6, two rows).

This reads the INDEX, never the disk: on a shared tree the file on disk can carry
another strand's unfinished edit, and a refusal naming an unstaged byte would be
this hook's own version of that defect. The index is what both the bundle and the
catalog will say once the commit exists.

Scope is the paths the commit takes. A bundle path names its own slug. A catalog
path names the slugs whose row this commit changes against HEAD, so a catalog-only
commit is judged on its own rows and not on every bundle in the shared index.

Exit: 0 the rows match, 1 drift, 2 the inputs could not be read (no verdict).
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys

CATALOG = "plugin-catalog.json"
LOCK = "skills-lock.json"
SIG_FILENAME = "ephe-plugin.sig.json"
#: The pack subfolders the skills lock counts, beside SKILL.md at pack level.
_PACK_SUBDIRS = ("references/", "templates/", "scripts/", "assets/")


def _git(*args: str) -> bytes | None:
    out = subprocess.run(["git", *args], capture_output=True)
    if out.returncode != 0:
        return None
    return out.stdout


def _rows(blob: bytes | None) -> dict[str, str]:
    if blob is None:
        return {}
    try:
        doc = json.loads(blob.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    out: dict[str, str] = {}
    for segment in ("public", "personal"):
        for entry in doc.get(segment, []):
            if isinstance(entry, dict) and entry.get("name"):
                out[str(entry["name"])] = str(entry.get("sha256") or "")
    return out


def _index_hash(slug: str) -> str | None:
    listing = _git("ls-files", "-s", "-z", "--", f"plugins/{slug}")
    if listing is None:
        return None
    prefix = f"plugins/{slug}/"
    entries: list[tuple[str, str]] = []
    for record in listing.split(b"\x00"):
        if not record:
            continue
        meta, _, raw_path = record.partition(b"\t")
        parts = meta.split()
        if len(parts) != 3:
            return None
        path = raw_path.decode("utf-8")
        if not path.startswith(prefix):
            continue
        rel = path[len(prefix):]
        if rel.rsplit("/", 1)[-1] == SIG_FILENAME:
            continue
        entries.append((rel, parts[1].decode("ascii")))
    digest = hashlib.sha256()
    for rel, sha in sorted(entries):
        blob = _git("cat-file", "blob", sha)
        if blob is None:
            return None
        digest.update(rel.encode("utf-8") + b"\x00" + blob + b"\x00")
    return digest.hexdigest()


def _lock_rows(blob: bytes | None) -> dict[str, str]:
    if blob is None:
        return {}
    try:
        doc = json.loads(blob.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {}
    out: dict[str, str] = {}
    for entry in doc.get("skills", []):
        if isinstance(entry, dict) and entry.get("name"):
            out[str(entry["name"])] = str(entry.get("computedHash") or "")
    return out


def _index_pack_hash(pack: str) -> str | None:
    """The skills-lock hash of one pack, read from the index blobs.

    Same algorithm as scripts/generate_skills_lock.py: SHA256 over the sorted
    concatenation of 'relpath\\n<sha256(file)>\\n' for SKILL.md and the files under
    the four counted subfolders. A file at pack level outside those is not counted.
    """
    listing = _git("ls-files", "-s", "-z", "--", f"skills/{pack}")
    if listing is None:
        return None
    prefix = f"skills/{pack}/"
    entries: list[str] = []
    for record in listing.split(b"\x00"):
        if not record:
            continue
        meta, _, raw_path = record.partition(b"\t")
        parts = meta.split()
        if len(parts) != 3:
            return None
        path = raw_path.decode("utf-8")
        if not path.startswith(prefix):
            continue
        rel = path[len(prefix):]
        if rel != "SKILL.md" and not rel.startswith(_PACK_SUBDIRS):
            continue
        blob = _git("cat-file", "blob", parts[1].decode("ascii"))
        if blob is None:
            return None
        entries.append(f"{rel}\n{hashlib.sha256(blob).hexdigest()}\n")
    payload = "".join(sorted(entries)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _check_plugins(paths: list[str]) -> tuple[int, list[str]]:
    touched: set[str] = set()
    for path in paths:
        if path.startswith("plugins/"):
            parts = path.split("/")
            if len(parts) > 2 and parts[1]:
                touched.add(parts[1])

    staged_blob = _git("show", f":{CATALOG}")
    if staged_blob is None:
        return 2, [f"catalog: NO VERDICT {CATALOG} is not in the index, so no row could be read"]
    staged = _rows(staged_blob)
    if CATALOG in paths:
        head = _rows(_git("show", f"HEAD:{CATALOG}"))
        touched.update(name for name, sha in staged.items() if head.get(name) != sha)
    if not touched:
        return 0, []

    drift: list[str] = []
    for slug in sorted(touched):
        actual = _index_hash(slug)
        if actual is None:
            return 2, [f"catalog: NO VERDICT the index entries of plugins/{slug} could not be read"]
        if slug not in staged:
            drift.append(f"catalog: DRIFT {slug}: the catalog names no row for this bundle")
        elif staged[slug] != actual:
            drift.append(f"catalog: DRIFT {slug}: row {staged[slug][:12]}… != bundle {actual[:12]}…")
    if drift:
        drift.append("catalog: run scripts/generate_plugin_catalog.py and stage the row")
        return 1, drift
    return 0, [f"catalog: {len(touched)} bundle row(s) match the index"]


def _check_skills(paths: list[str]) -> tuple[int, list[str]]:
    touched: set[str] = set()
    for path in paths:
        if path.startswith("skills/"):
            parts = path.split("/")
            if len(parts) > 2 and parts[1]:
                touched.add(parts[1])

    staged_blob = _git("show", f":{LOCK}")
    if staged_blob is None:
        return 2, [f"skills: NO VERDICT {LOCK} is not in the index, so no row could be read"]
    staged = _lock_rows(staged_blob)
    if LOCK in paths:
        head = _lock_rows(_git("show", f"HEAD:{LOCK}"))
        touched.update(name for name, sha in staged.items() if head.get(name) != sha)
    if not touched:
        return 0, []

    drift: list[str] = []
    for pack in sorted(touched):
        actual = _index_pack_hash(pack)
        if actual is None:
            return 2, [f"skills: NO VERDICT the index entries of skills/{pack} could not be read"]
        if pack not in staged:
            drift.append(f"skills: DRIFT {pack}: the lock names no row for this pack")
        elif staged[pack] != actual:
            drift.append(f"skills: DRIFT {pack}: row {staged[pack][:12]}… != pack {actual[:12]}…")
    if drift:
        drift.append("skills: run scripts/generate_skills_lock.py and stage the row")
        return 1, drift
    return 0, [f"skills: {len(touched)} pack row(s) match the index"]


def main(paths: list[str]) -> int:
    plugin_scope = any(p.startswith("plugins/") or p == CATALOG for p in paths)
    skills_scope = any(p.startswith("skills/") or p == LOCK for p in paths)
    if not plugin_scope and not skills_scope:
        print("catalog: no bundle, pack or catalog path in scope")
        return 0

    status = 0
    for scope, check in ((plugin_scope, _check_plugins), (skills_scope, _check_skills)):
        if not scope:
            continue
        code, lines = check(paths)
        for line in lines:
            print(line)
        # A no-verdict (2) outranks a drift (1): an unreadable input has decided
        # nothing, and the hook refuses the commit either way.
        status = max(status, code)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))