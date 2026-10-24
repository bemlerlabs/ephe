"""Plugin lockfile and dependency order (P1).

The lockfile is built from what is on disk: one deterministic entry per valid
manifest with version, source, content hash, signature hash, dependencies and
the effective scope. It is written atomically and compared against the disk, so
a release or a start can say which plugin drifted instead of discovering it at
load time.

Dependencies resolve dependencies-first; a missing dependency or a cycle fails
closed. The legacy ``plugins.json`` import lives here because it is the same
one-shot migration boundary; the lifecycle service applies the result.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core import plugin_manifest

SCHEMA_VERSION = 1
LOCK_FILENAME = "plugin-lock.json"
SCOPES = ("user", "workspace")


class LockfileError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source(plugin_dir: Path) -> str:
    try:
        Path(plugin_dir).resolve().relative_to(
            plugin_manifest.BUILTIN_PLUGINS_ROOT.resolve()
        )
        return "builtin"
    except ValueError:
        return "user"


def trust_class_for(
    name: str, plugin_dir: Path, listing: dict[str, Any] | None = None
) -> str:
    """The key class an installed artifact was verified under.

    A pin written since TS-09 carries the class. Entries from before that are
    migrated from their source: a bundled plugin only ships against the
    repository key, an installed one takes the class its listing entry declares,
    and an entry nobody can vouch for is a user artifact. The result is never
    empty — an unknown class would mean "try every key", which is what TS-09
    removed.
    """
    from core import plugin_signing

    pin = plugin_signing.load_pin(name) or {}
    known = str(pin.get("trust_class") or "")
    if known in (plugin_signing.FIRST_PARTY, plugin_signing.USER):
        return known
    if _source(Path(plugin_dir)) == "builtin":
        return plugin_signing.FIRST_PARTY
    try:
        if listing is None:
            from core.plugin_listing import load_marketplace

            listing = load_marketplace()
        for entry in (listing or {}).get("plugins", []):
            if str(entry.get("name")) != name:
                continue
            if str(entry.get("trust") or "").strip().lower() in {"official", "verified"}:
                return plugin_signing.FIRST_PARTY
            break
    except Exception:  # noqa: BLE001 — a listing outage must not invent a class
        pass
    return plugin_signing.USER


def build_lockfile(
    plugins_root: Path | None = None,
    *,
    scopes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    scopes = dict(scopes or {})
    entries: list[dict[str, Any]] = []
    quarantined: list[dict[str, str]] = []
    # One listing read for the whole lock, not one per plugin.
    try:
        from core.plugin_listing import load_marketplace

        listing: dict[str, Any] = load_marketplace()
    except Exception:  # noqa: BLE001 — the migration default does not need it
        listing = {}
    for entry in plugin_manifest.scan_plugins(
        None if plugins_root is None else Path(plugins_root)
    ):
        directory = Path(entry["dir"])
        manifest = entry["manifest"]
        name = str(manifest["name"]) if manifest else directory.name
        if entry["error"] or not manifest:
            quarantined.append(
                {"name": name, "error": str(entry["error"] or "manifest missing")}
            )
            continue
        scope = scopes.get(name, "user")
        if scope not in SCOPES:
            raise LockfileError("invalid_scope", f"{name}: {scope}")
        dependencies = manifest.get("dependencies", [])
        if not isinstance(dependencies, list):
            quarantined.append({"name": name, "error": "dependencies: list expected"})
            continue
        signature_file = directory / plugin_manifest.SIG_FILENAME
        entries.append(
            {
                "name": name,
                "version": str(manifest["version"]),
                "source": _source(directory),
                "path": directory.name,
                "sha256": plugin_manifest.dir_sha256(directory),
                "signature_sha256": _sha256_file(signature_file)
                if signature_file.is_file()
                else "",
                "dependencies": [str(dep) for dep in dependencies],
                "scope": scope,
                "trust_class": trust_class_for(name, directory, listing=listing),
            }
        )
    entries.sort(key=lambda item: item["name"])
    quarantined.sort(key=lambda item: item["name"])
    return {"schema": SCHEMA_VERSION, "plugins": entries, "quarantined": quarantined}


def read_lockfile(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema": SCHEMA_VERSION, "plugins": [], "quarantined": []}
    if not isinstance(raw, dict):
        return {"schema": SCHEMA_VERSION, "plugins": [], "quarantined": []}
    return raw


def write_lockfile(path: Path, lock: dict[str, Any]) -> None:
    target = Path(path)
    body = json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True)
    tmp = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        os.replace(tmp, target)
        os.chmod(target, 0o600)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise LockfileError("lockfile_write_failed", str(exc)) from exc


def diff_lockfile(
    lock: dict[str, Any], plugins_root: Path | None = None
) -> list[dict[str, Any]]:
    current = build_lockfile(plugins_root)
    recorded = {
        str(entry["name"]): entry
        for entry in lock.get("plugins", [])
        if isinstance(entry, dict)
    }
    present = {str(entry["name"]): entry for entry in current["plugins"]}
    drift: list[dict[str, Any]] = []
    for name in sorted(recorded):
        expected = recorded[name]
        actual = present.get(name)
        if actual is None:
            drift.append({"name": name, "kind": "missing"})
            continue
        if str(expected.get("version")) != str(actual["version"]):
            drift.append(
                {
                    "name": name,
                    "kind": "version",
                    "expected": str(expected.get("version")),
                    "actual": str(actual["version"]),
                }
            )
        if str(expected.get("sha256")) != str(actual["sha256"]):
            drift.append({"name": name, "kind": "sha256"})
        if str(expected.get("signature_sha256")) != str(actual["signature_sha256"]):
            drift.append({"name": name, "kind": "signature"})
    for name in sorted(set(present) - set(recorded)):
        drift.append(
            {"name": name, "kind": "extra", "version": present[name]["version"]}
        )
    return drift


def dependency_order(entries: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    names = [str(entry["name"]) for entry in entries]
    if len(names) != len(set(names)):
        raise LockfileError(
            "duplicate_plugin", "duplicate plugin names in the install set"
        )
    remaining: dict[str, set[str]] = {}
    for entry in entries:
        name = str(entry["name"])
        dependencies = {str(dep) for dep in entry.get("dependencies", [])}
        unknown = sorted(dependencies - set(names))
        if unknown:
            raise LockfileError("missing_dependency", f"{name}: {', '.join(unknown)}")
        remaining[name] = dependencies
    order: list[str] = []
    while remaining:
        ready = sorted(
            name for name, dependencies in remaining.items() if not dependencies
        )
        if not ready:
            raise LockfileError("dependency_cycle", ", ".join(sorted(remaining)))
        for name in ready:
            order.append(name)
            del remaining[name]
        for dependencies in remaining.values():
            dependencies.difference_update(ready)
    return tuple(order)
