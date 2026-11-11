"""What a mount refuses before it writes, and which trust it accepted while doing so.

`core/plugin_lifecycle_mount.py` is the transition; this file is the pair of questions it
asks first, so a bundle that fails either leaves nothing behind:

- **does this bundle's name space belong to anybody else?** Contested and reserved names
  are answered by the registry scan, never by a second implementation — `descriptors_for`
  builds a descriptor for a contested name happily, because validation reads one directory
  and cannot see its neighbours.
- **is this the same code the caller accepted?** The tool contract's pin (#15) says what
  the served schema looked like; it cannot see a change to the file the entry runs. The
  activation record therefore carries the digest of the bundle directory, and a mount that
  finds a different digest refuses until it is acknowledged. That is the local case of the
  rule the market install already follows with its artifact hash: a bundle the reader never
  agreed to does not start.

The trust word is the answer to a question the signature gate cannot ask. An unsigned
bundle in the user's own root passes that gate — there is no record to verify — so the
mount names the class it is publishing under: `signed` when a record came with the
directory, `local` when the author is the user. It is reported to the caller and written
into the state record, because a surface that offers "mount this" has to say which of the
two it is mounting.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from core.plugin_lifecycle_types import (
    REFUSE_CONFLICT,
    REFUSE_MANIFEST,
    TRUST_LOCAL,
    TRUST_SIGNED,
)
from core.plugin_manifest import SIG_FILENAME, dir_sha256
from core.plugin_mount_records import ARTIFACT_FIELD

__all__ = [
    "TRUST_LOCAL",
    "TRUST_SIGNED",
    "MountNamespace",
    "bundle_trust",
    "content_digest",
    "invalidate_mount_answers",
    "moved_content",
    "manifest_of",
    "refuse_contested_names",
]

#: Bumped by `invalidate_mount_answers`; a namespace holding an older number re-reads.
_ANSWERS_GENERATION = 0
_ANSWERS_LOCK = threading.Lock()


def invalidate_mount_answers() -> None:
    """Drop the portfolio answers a mount namespace may still hold.

    The ownership cache drops the manifest-derived views after an install, a remove or
    an edit; a namespace that spans such a write must not answer from what it read
    before it.
    """
    global _ANSWERS_GENERATION
    with _ANSWERS_LOCK:
        _ANSWERS_GENERATION += 1


def _answers_generation() -> int:
    with _ANSWERS_LOCK:
        return _ANSWERS_GENERATION


class MountNamespace:
    """The portfolio answers one replay pass asks for, read at most once.

    A replay re-mounts every recorded bundle, and each mount asks the same two
    questions: which names are reserved, and which names the scanned bundles claim.
    The folders cannot change inside one pass, so the pass reads both answers once and
    drops them with the pass; a namespace built for a single mount answers the same
    questions for that mount only. A write between the pass and an answer moves the
    generation, and the namespace re-reads instead of serving the pre-write portfolio.
    """

    __slots__ = ("_generation", "_reserved", "_entries", "_scanned")

    def __init__(self) -> None:
        self._generation = _answers_generation()
        self._reserved: dict[str, Any] | None = None
        self._entries: list[dict[str, Any]] | None = None
        self._scanned: Any | None = None

    def _refresh(self) -> None:
        generation = _answers_generation()
        if generation != self._generation:
            self._generation = generation
            self._reserved = None
            self._entries = None
            self._scanned = None

    @property
    def entries(self) -> list[dict[str, Any]]:
        self._refresh()
        if self._entries is None:
            from core import plugin_manifest

            self._entries = plugin_manifest.scan_plugins(None)
        return self._entries

    @property
    def reserved(self) -> dict[str, Any]:
        self._refresh()
        if self._reserved is None:
            from core import plugin_tools_contract

            self._reserved = plugin_tools_contract.reserved_tool_names()
        return self._reserved

    @property
    def scanned(self):
        self._refresh()
        if self._scanned is None:
            from core.plugin_registry import scan_tool_activations

            self._scanned = scan_tool_activations(
                None, entries=self.entries, reserved=self.reserved
            )
        return self._scanned

    def directory(self, plugin: str) -> Path | None:
        """The bundle directory the portfolio holds for one plugin id, if any."""
        for record in self.entries:
            manifest = record.get("manifest")
            if isinstance(manifest, dict) and str(manifest.get("name")) == plugin:
                return Path(record["dir"])
        return None


def content_digest(directory: Path) -> str:
    """The hash of the bytes a mount would run, manifest included."""
    return dir_sha256(Path(directory))


def bundle_trust(directory: Path) -> str:
    """Which class this bundle arrives under: a record vouches for it, or you do."""
    return TRUST_SIGNED if (Path(directory) / SIG_FILENAME).is_file() else TRUST_LOCAL


def manifest_of(plugin: str, directory: Path) -> dict[str, Any]:
    """The validated manifest of a located bundle, or the coded reason it cannot mount."""
    from core import plugin_manifest
    from core.plugin_lifecycle_types import LifecycleError

    manifest, error = plugin_manifest.load_manifest(directory)
    if error or not isinstance(manifest, dict):
        raise LifecycleError(
            REFUSE_MANIFEST, 422, f"plugin '{plugin}': {error or 'manifest missing'}"
        )
    return manifest


def refuse_contested_names(plugin: str, descriptors, *, namespace=None) -> None:
    """Refuse a name the portfolio contests, a reserved one, or one a live space holds.

    The reservation is asked once, owner-aware: the shipped bundle may re-serve its own
    name, every other bundle — including one staged in the user root — is refused with the
    namespace code, the held name and the free name it can choose instead. ``namespace``
    is the replay pass's shared answer set; without one this mount reads its own.
    """
    from core import plugin_tools_contract
    from core.plugin_lifecycle_types import LifecycleError

    answers = namespace if namespace is not None else MountNamespace()
    directory = answers.directory(plugin)
    reserved = answers.reserved
    scanned = answers.scanned
    for descriptor in descriptors:
        held = plugin_tools_contract.reserved_tool(
            descriptor.name,
            plugin_id=plugin,
            plugin_dir=directory,
            reserved=reserved,
        )
        if held is not None:
            raise LifecycleError(
                held.code,
                409,
                f"{descriptor.name!r} is held by the {held.code} name space "
                f"(owner: {held.owner}); plugin '{plugin}' cannot serve it; "
                f"{held.action(plugin)}",
                data={
                    "code": plugin_tools_contract.RESERVED_TOOL_CODE,
                    "name": held.name,
                    "namespace": held.code,
                    "owner": held.owner,
                    "action": held.action(plugin),
                },
            )
        if descriptor.name in scanned.conflicts:
            raise LifecycleError(
                REFUSE_CONFLICT, 409, scanned.reason_for(descriptor.name)
            )


def moved_content(record, current: str) -> dict[str, Any] | None:
    """The accepted-vs-installed hash pair, when the two disagree. None otherwise."""
    accepted = str((record or {}).get(ARTIFACT_FIELD) or "")
    if not accepted or not current or accepted == current:
        return None
    return {"accepted": accepted, "installed": current}


def content_guard(plugin, record, current, acknowledged):
    """The accepted-vs-installed pair, and when it is a refusal.

    A vouched artifact whose bytes moved is tampering: nothing mounts until the caller
    says otherwise. A `local` bundle's own author is the user, and the Creator loop edits
    those bytes on purpose, so the move is reported instead of blocked — the contract pin
    still guards the schema, and the audit says the files moved. Returning the pair is
    what lets both statements be true in one mount.
    """
    from core.plugin_lifecycle_types import LifecycleError, REFUSE_ARTIFACT

    moved = moved_content(record, current)
    if moved is None:
        return None
    if str((record or {}).get("trust") or "") == TRUST_SIGNED and not acknowledged:
        raise LifecycleError(
            REFUSE_ARTIFACT,
            409,
            f"plugin '{plugin}' changed its files since the accepted mount: "
            f"{moved['accepted'][:12]} -> {moved['installed'][:12]}",
            data={"artifact": moved},
        )
    return moved
