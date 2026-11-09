"""The records a hot mount keeps: the pin, its diff, the activation, the unmount ledger.

#15 moves three artifacts at once, and this file holds the shape of each one so the
transition in `core/plugin_lifecycle_mount.py` reads as a sequence of decisions rather
than as file formats:

- **the pin** — one record per contributed tool, written into the plugin's lockfile
  entry: the descriptor's fingerprint (sha256 over the canonical schema bytes), the
  description those bytes carried, and a digest of the parameter object. The two extra
  fields exist so a refusal can say *which* half of the contract moved. A fingerprint
  alone says "something changed"; a reader deciding whether to accept a rug pull needs
  "the sentence changed, the arguments did not", and the tool-poisoning attack is exactly
  the case where only the sentence moves.
- **the diff** — `diff_against_pins` compares a batch against the records on disk and
  says, per served name, whether it was `added`, `removed`, or changed in
  `description`, `parameters`, or (the residue no field explains) its `fingerprint`.
  Comparing a bundle against *nothing* is not a diff: a first mount has no records and
  the transition reports that instead of showing an empty alarm.
- **the activation record** — one entry per mounted bundle inside the lifecycle state
  document (`mounts`), carrying the version mounted, the served names and the
  fingerprint each was accepted at. It is not a switch: an entry in the `plugins`
  section without a committed value reads as a plugin switched off, so the mount's
  record lives beside the switches, in a section of its own.
- **the unmount ledger** — the names a removal took away, in this process only. It
  exists so a call that arrives for a just-unmounted name is answered with a coded
  refusal instead of the unknown-tool line: the model was offered that name last turn,
  and "never heard of it" is the wrong sentence to say to it.

Nothing here imports a plugin or resolves an entry — the records are text and hashes.

Ephe – Bad Liebenzell, Schwarzwald
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.plugin_lifecycle_types import TRUST_SIGNED

#: The lifecycle state document's section with one record per mounted bundle.
MOUNTS_FIELD = "mounts"

#: The field of that record holding the hash of the bytes the bundle was accepted with.
ARTIFACT_FIELD = "artifact"


#: How many unmounted names the ledger remembers. It answers one question — "was this
#: name served here a moment ago?" — and an unbounded ledger would be a slow leak in a
#: server that mounts and unmounts all day.
_LEDGER_LIMIT = 128

_LEDGER: "OrderedDict[str, str]" = OrderedDict()
_LEDGER_LOCK = threading.Lock()


@dataclass(frozen=True)
class ToolDiff:
    """One contributed tool whose contract is not the one the lockfile pins."""

    name: str
    old_fingerprint: str
    new_fingerprint: str
    changed: tuple[str, ...]
    old_description: str
    new_description: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "old_fingerprint": self.old_fingerprint,
            "new_fingerprint": self.new_fingerprint,
            "changed": list(self.changed),
            "old_description": self.old_description,
            "new_description": self.new_description,
        }

    def summary(self) -> str:
        """The audit's one-token form: which name, which field."""
        return f"{self.name}:{'|'.join(self.changed)}"


@dataclass(frozen=True)
class MountResult:
    """What one mount or unmount did: the names it left live, and the diff it showed."""

    plugin_id: str
    version: str = ""
    names: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    changed: tuple[ToolDiff, ...] = ()
    first_mount: bool = False
    artifact: str = ""
    trust: str = ""
    artifact_changed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "plugin": self.plugin_id,
            "version": self.version,
            "names": list(self.names),
            "removed": list(self.removed),
            "first_mount": self.first_mount,
            "artifact": self.artifact,
            "trust": self.trust,
            "artifact_changed": self.artifact_changed,
            "diff": [item.as_dict() for item in self.changed],
        }


def record_unmounted(plugin_id: str, names) -> None:
    """Remember the names one unmount took away, so a late call gets a reason."""
    with _LEDGER_LOCK:
        for name in names:
            _LEDGER[str(name)] = str(plugin_id)
            _LEDGER.move_to_end(str(name))
        while len(_LEDGER) > _LEDGER_LIMIT:
            _LEDGER.popitem(last=False)


def unmounted_owner(name: str) -> str:
    """The plugin a served name belonged to when it was unmounted, or "" for never."""
    with _LEDGER_LOCK:
        return str(_LEDGER.get(str(name), ""))


def _function_body(schema: dict) -> dict:
    body = schema.get("function")
    return body if isinstance(body, dict) else dict(schema)


def _parameters_digest(parameters: Any) -> str:
    """sha256 over the canonical parameter object, so a schema edit is nameable."""
    from core.tools.dynamic_registry import canonical_schema_bytes

    try:
        return hashlib.sha256(
            canonical_schema_bytes(parameters if isinstance(parameters, dict) else {})
        ).hexdigest()
    except (TypeError, ValueError):
        return ""


def pin_records(descriptors) -> tuple[dict[str, Any], ...]:
    """The lockfile records of one mounted batch: the pin plus what a diff compares."""
    return tuple(
        {
            "name": descriptor.name,
            "fingerprint": descriptor.fingerprint,
            "description": str(_function_body(descriptor.schema).get("description", "")),
            "parameters_sha256": _parameters_digest(
                _function_body(descriptor.schema).get("parameters")
            ),
        }
        for descriptor in sorted(descriptors, key=lambda item: item.name)
    )


def activation_record(
    plugin: str, version: str, descriptors, *, artifact: str = "", trust: str = ""
) -> dict[str, Any]:
    """The state document's record of what this bundle is serving right now.

    `artifact` is the hash of the directory the mount read, and `trust` the class it
    published under — both belong to the *record* rather than to the lockfile entry,
    because a lock rebuild recomputes the entry from the disk. The value that survives a
    rebuild is the one that was accepted, and that is the difference between a visible
    change and an invisible one.
    """
    return {
        "version": str(version),
        ARTIFACT_FIELD: str(artifact),
        "trust": str(trust),
        "signed": trust == TRUST_SIGNED,
        "names": sorted(item.name for item in descriptors),
        "fingerprints": {item.name: item.fingerprint for item in descriptors},
    }


def load_mounts(raw: dict[str, Any], data: dict[str, Any]) -> bool:
    """Reads the `mounts` section of a state file into `data`; False when malformed.

    A malformed section marks the whole state unproven — the same rule every other
    section follows, because a record this side of the machine cannot be trusted in
    parts.
    """
    mounts = raw.get(MOUNTS_FIELD)
    if mounts is None:
        return True
    if not isinstance(mounts, dict) or not all(
        isinstance(plugin_id, str) and isinstance(record, dict)
        for plugin_id, record in mounts.items()
    ):
        return False
    data[MOUNTS_FIELD] = {
        str(plugin_id): dict(record) for plugin_id, record in mounts.items()
    }
    return True


def merge_mounts(
    merged: dict[str, Any], local: dict[str, Any], loaded: dict[str, Any]
) -> dict[str, Any]:
    """Applies this instance's mount records onto the file another writer left.

    A mount writes one bundle's record and an unmount deletes one, so the merge moves
    exactly the records that changed here — including the ones that disappeared — and
    leaves a neighbour's mount alone.
    """
    records = merged.setdefault(MOUNTS_FIELD, {})
    if not isinstance(records, dict):
        records = {}
        merged[MOUNTS_FIELD] = records
    for plugin_id, record in (local or {}).items():
        if (loaded or {}).get(plugin_id) != record:
            records[str(plugin_id)] = record
    for plugin_id in list(records):
        if plugin_id not in (local or {}):
            records.pop(plugin_id, None)
    return merged


def diff_against_pins(descriptors, pinned) -> tuple[ToolDiff, ...]:
    """Every contract a batch offers that is not the one already accepted."""
    by_name = {str(record.get("name")): record for record in pinned}
    offered = {descriptor.name: descriptor for descriptor in descriptors}
    out: list[ToolDiff] = []
    for name in sorted(set(by_name) | set(offered)):
        descriptor = offered.get(name)
        record = by_name.get(name)
        if descriptor is not None and record is None:
            out.append(
                ToolDiff(
                    name=name,
                    old_fingerprint="",
                    new_fingerprint=descriptor.fingerprint,
                    changed=("added",),
                    old_description="",
                    new_description=str(
                        _function_body(descriptor.schema).get("description", "")
                    ),
                )
            )
            continue
        if descriptor is None or record is None:
            out.append(
                ToolDiff(
                    name=name,
                    old_fingerprint=str((record or {}).get("fingerprint", "")),
                    new_fingerprint="",
                    changed=("removed",),
                    old_description=str((record or {}).get("description", "")),
                    new_description="",
                )
            )
            continue
        old_fingerprint = str(record.get("fingerprint", ""))
        if old_fingerprint == descriptor.fingerprint:
            continue
        body = _function_body(descriptor.schema)
        old_description = str(record.get("description", ""))
        new_description = str(body.get("description", ""))
        changed: list[str] = []
        if old_description != new_description:
            changed.append("description")
        if str(record.get("parameters_sha256", "")) != _parameters_digest(
            body.get("parameters")
        ):
            changed.append("parameters")
        out.append(
            ToolDiff(
                name=name,
                old_fingerprint=old_fingerprint,
                new_fingerprint=descriptor.fingerprint,
                changed=tuple(changed or ("fingerprint",)),
                old_description=old_description,
                new_description=new_description,
            )
        )
    return tuple(out)


def plugin_directory(plugin: str) -> Path | None:
    """The directory a plugin id names, in the user root or the built-in one.

    Read from the roots rather than through `scan_plugins`, because the scan drops a
    bundle whose manifest does not validate: a mount asked for such a bundle has to say
    the manifest is broken, not pretend the plugin was never installed.

    `plugin` is the id in `POST /api/plugins/{id}/hot-mount`, so the join is done by
    `path_guard.child`: the slug pattern refuses `..`, a separator and an empty name,
    and `confine` proves the joined path against the root it was joined to
    (`core/path_guard.py:142`). Without that, `Path(base) / plugin` with `plugin = ".."`
    answers the *parent* of the plugins root — a directory that holds a manifest and was
    never installed — and the mount would publish tools from it. A valid slug is
    unchanged, and the returned path is the resolved directory the caller already used.
    """
    from core import path_guard, plugin_manifest
    from core.plugin_manifest import MANIFEST_FILENAME
    from core.plugin_store import PLUGIN_NAME_RE

    for base in (
        plugin_manifest.plugins_root(),
        plugin_manifest.BUILTIN_PLUGINS_ROOT,
    ):
        candidate = path_guard.child(base, plugin, pattern=PLUGIN_NAME_RE)
        if candidate is not None and candidate.is_dir() and (
            candidate / MANIFEST_FILENAME
        ).is_file():
            return candidate
    return None


def descriptor_registry():
    from core.tools.dynamic_registry import default_registry

    return default_registry()


def lockfile_path() -> Path:
    from core.plugin_lockfile import LOCK_FILENAME
    from core.plugin_store import config_root

    return config_root() / LOCK_FILENAME


def read_lock_bytes() -> bytes | None:
    try:
        return lockfile_path().read_bytes()
    except OSError:
        return None


def read_lock():
    from core.plugin_lockfile import read_lockfile

    path = lockfile_path()
    return read_lockfile(path) if path.exists() else None


def pinned_records(plugin: str) -> tuple[dict[str, Any], ...]:
    """The accepted contracts this bundle was mounted against, if any."""
    from core.plugin_lockfile import pinned_tools

    lock = read_lock()
    return pinned_tools(lock, plugin) if lock is not None else ()


def write_pins(plugin: str, records) -> None:
    """Pin one bundle's accepted contracts into its lockfile entry.

    The read and the write are one step: two mounts that each rebuilt from a lock read
    before the other wrote would leave one bundle's pins behind.
    """
    from core.plugin_lockfile import (
        LOCK_WRITE,
        build_lockfile,
        with_tool_pins,
        write_lockfile,
    )

    with LOCK_WRITE:
        lock = read_lock()
        body = with_tool_pins(
            lock if lock is not None else build_lockfile(None), plugin, records
        )
        write_lockfile(lockfile_path(), body)


def restore_lock(previous: bytes | None) -> None:
    """Put the lockfile back the way it was, or remove it when it did not exist."""
    from core.plugin_lockfile import LOCK_WRITE, write_lockfile

    path = lockfile_path()
    if previous is None:
        with LOCK_WRITE:
            path.unlink(missing_ok=True)
        return
    try:
        restored = json.loads(previous.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return
    if isinstance(restored, dict):
        with LOCK_WRITE:
            write_lockfile(path, restored)
