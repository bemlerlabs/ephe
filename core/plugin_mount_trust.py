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
    "bundle_trust",
    "content_digest",
    "moved_content",
    "manifest_of",
    "refuse_contested_names",
]


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


def refuse_contested_names(plugin: str, descriptors) -> None:
    """Refuse a name the portfolio contests, or one a live name space already holds."""
    from core import plugin_tools_contract
    from core.plugin_lifecycle_types import LifecycleError
    from core.plugin_registry import scan_tool_activations

    scanned = scan_tool_activations(None)
    for descriptor in descriptors:
        collision = plugin_tools_contract.reserved_namespace(descriptor.name)
        if collision:
            raise LifecycleError(
                collision,
                409,
                f"{descriptor.name!r} is held by the {collision} name space; "
                f"plugin '{plugin}' cannot serve it",
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
