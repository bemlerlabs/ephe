"""Hot mount: one atomic transition that puts a bundle's tools on the rail — or nothing.

The mount is a transition on the existing lifecycle machine (#15), not a parallel registry.
It reads the bundle, builds the descriptors #13 derives from its manifest, and hands them to
the registry in the one atomic swap `replace_for_plugin` gives. Nothing else may put a
descriptor into that registry: a tool that reached the rail by another route is a tool no
manifest declares, and the gate, the pin and the audit all read the manifest. The record
shapes it writes — the pin, the diff, the activation entry, the unmount ledger — live in
`core.plugin_mount_records`.

Three artifacts move, in this order: the lockfile entry, the activation record in the
lifecycle state file, the descriptor set in the registry. The last step drops the runtime's
cached view of the portfolio and publishes on the existing SSE stream. A failure anywhere
after the first write restores all three — the previous descriptor batch read back from the
registry's own snapshot, the previous activation record, the previous lockfile bytes — and
the audit row says which step broke. A half-applied mount would leave a plugin serving a
contract no record calls accepted, which is the corrupt state this file exists to prevent.

Refusals come before any write, each with its own code: an absent bundle (404, the word the
machine already speaks), an invalid manifest, a name two bundles contest
(`ToolActivations.reason_for` says which two, and the mount does not rebuild that answer), a
name the kernel map or the live MCP rail holds (the registry's own collision codes), and a
bundle whose contract moved since the last accepted mount. That last one is the alarm
Non-negotiable #4 asks for, the one that pins a contract instead of trusting it: until the
change is acknowledged by name the changed tool stays unoffered, because the registry keeps
holding the descriptor the last accepted mount installed and the bundle as it now sits on
disk mounts nothing.

A mount never turns a plugin on or off. A disabled plugin's mounted tool stays hidden by the
top gate and its call is refused there, under #11's contract.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from core.plugin_lifecycle_types import (
    MUTATING_STEPS,
    REFUSE_CHANGE,
    REFUSE_REGISTRY,
    REGISTRY_WRITTEN_STEPS,
    STEP_ACTIVATION,
    STEP_ARTIFACT,
    STEP_CLAIMS,
    STEP_DESCRIPTORS,
    STEP_LOCKFILE,
    STEP_MANIFEST,
    STEP_NOTIFY,
    STEP_PIN,
    STEP_REGISTRY,
)
from core.plugin_mount_records import (
    ARTIFACT_FIELD,
    MOUNTS_FIELD,
    MountResult,
    activation_record,
    descriptor_registry,
    diff_against_pins,
    pin_records,
    pinned_records,
    plugin_directory,
    read_lock_bytes,
    record_unmounted,
    restore_lock,
    write_pins,
)
from core.plugin_mount_trust import (
    bundle_trust,
    content_digest,
    manifest_of,
    content_guard,
    refuse_contested_names,
)

#: The step names, the mutating set and the mount's refusal codes live in
#: `core/plugin_mount_records.py`, beside the records they write.


class LifecycleMount:
    """`mount` and `unmount`, as transitions of the machine that owns plugin state.

    Mixed into `PluginLifecycle`; it reads that host's `_lock`, `_data`, `_versions`,
    `_persist`, `_publish` and `_audit_entry`, and adds no switch semantics of its own.
    """

    _lock: Any
    _data: dict[str, Any]
    _versions: dict[str, str]

    def mount(
        self,
        plugin_id: str,
        *,
        acknowledge=(),
        acknowledge_artifact: bool = False,
        expected_version: str | None = None,
        expected_etag: str | None = None,
        actor: str = "user",
        reason: str = "",
    ) -> MountResult:
        """Put one bundle's declared tools on the rail, or leave everything as it was."""
        with self._lock:
            return self._mount_locked(
                str(plugin_id),
                acknowledge=frozenset(str(name) for name in acknowledge),
                acknowledge_artifact=bool(acknowledge_artifact),
                expected_version=expected_version,
                expected_etag=expected_etag,
                actor=actor,
                reason=reason,
            )

    def mount_records(self) -> dict[str, dict]:
        """The `mounts` section, which outlives the descriptors it published.

        The read half of `core/plugin_mount_replay.py`: a new process starts with the
        intent recorded and none of its tools served.
        """
        with self._lock:
            return copy.deepcopy(self._data.get(MOUNTS_FIELD, {}))

    def unmount(
        self, plugin_id: str, *, actor: str = "user", reason: str = ""
    ) -> MountResult:
        """Take one plugin's tools off the rail; a second call removes nothing."""
        with self._lock:
            plugin = str(plugin_id)
            registry = descriptor_registry()
            owned = tuple(
                item
                for item in registry.descriptor_snapshot()
                if item.plugin_id == plugin
            )
            names = tuple(sorted(item.name for item in owned))
            if not names and plugin not in self._data.get(MOUNTS_FIELD, {}):
                return MountResult(plugin_id=plugin)
            before = copy.deepcopy(self._data.get(MOUNTS_FIELD, {}))
            if names:
                registry.unregister_plugin(plugin)
                record_unmounted(plugin, names)
            self._data.setdefault(MOUNTS_FIELD, {}).pop(plugin, None)
            try:
                self._persist()
            except BaseException as exc:
                registry.replace_for_plugin(plugin, owned)
                self._data[MOUNTS_FIELD] = before
                self._persist_or_log()
                self._audit_mount(
                    action="unmount", plugin=plugin, actor=actor, state="mounted",
                    status="rolled_back", code=STEP_ACTIVATION, reason=str(exc)[:240],
                )
                raise
            self._mount_notify(plugin, (), phase="unmounted")
            self._audit_mount(
                action="unmount", plugin=plugin, actor=actor, state="idle",
                status="committed", code="",
                reason=f"removed={len(names)}{' ' + reason if reason else ''}",
            )
            return MountResult(plugin_id=plugin, removed=names)

    # The transition, step by step

    def _mount_locked(
        self, plugin, *, acknowledge, acknowledge_artifact, expected_version,
        expected_etag, actor, reason
    ) -> MountResult:
        from core.plugin_lifecycle_types import LifecycleError

        # The bundle on disk is read before anything else, and the process-wide
        # installed-versions map is not consulted: it is a cache of a scan, and a mount
        # asked for a bundle the cache has not seen is the ordinary case after an install.
        manifest, directory = self._mount_read_manifest(plugin)
        installed = str(manifest.get("version") or "")
        artifact = content_digest(directory)
        trust = bundle_trust(directory)
        # `If-Match` on a mount is the bundle version the caller read, because that version
        # is the whole identity of what would be published: no state entry of this machine
        # is part of it, so the etag the switch routes compare cannot name this resource.
        for wanted in (expected_version, expected_etag):
            if wanted is not None and wanted != installed:
                raise LifecycleError(
                    "stale_state", 409, f"expected {wanted}, installed {installed}"
                )
        step = STEP_MANIFEST
        before_mounts = copy.deepcopy(self._data.get(MOUNTS_FIELD, {}))
        before_lock = read_lock_bytes()
        registry = descriptor_registry()
        before_descriptors = tuple(
            item for item in registry.descriptor_snapshot() if item.plugin_id == plugin
        )
        try:
            step = STEP_DESCRIPTORS
            descriptors = self._mount_descriptors(manifest)
            step = STEP_CLAIMS
            refuse_contested_names(plugin, descriptors)
            step = STEP_PIN
            records = pin_records(descriptors)
            first, diffs = self._mount_check_pins(plugin, descriptors, acknowledge)
            # The contract diff answers before the content digest: a rewritten description
            # moves both, and the field-level alarm is the one a reader can act on. The
            # digest is what catches the change the contract cannot see — an edited
            # `handlers.py` under an unchanged schema.
            step = STEP_ARTIFACT
            moved = content_guard(
                plugin, before_mounts.get(plugin), artifact, acknowledge_artifact
            )
            step = STEP_LOCKFILE
            self._mount_record_lockfile(plugin, records)
            step = STEP_ACTIVATION
            self._mount_record_activation(
                plugin, descriptors, installed, artifact=artifact, trust=trust
            )
            step = STEP_REGISTRY
            self._mount_publish_descriptors(plugin, descriptors)
            step = STEP_NOTIFY
            self._mount_notify(plugin, tuple(item.name for item in descriptors))
        except BaseException as exc:
            self._roll_back(
                plugin=plugin, actor=actor, step=step, exc=exc,
                before_mounts=before_mounts, before_lock=before_lock,
                before_descriptors=before_descriptors, registry=registry,
                version=installed,
            )
            raise
        if not descriptors:
            self._audit_mount(
                action="mount", plugin=plugin, actor=actor, state="idle",
                status="committed", code="", version=installed,
                reason="step=manifest no tool declared",
            )
            return MountResult(
                plugin_id=plugin, version=installed, artifact=artifact, trust=trust
            )
        self._audit_mount(
            action="mount", plugin=plugin, actor=actor, state="mounted",
            status="committed", code="", version=installed,
            reason=self._commit_summary(reason, records, diffs, first, trust, moved is not None),
        )
        return MountResult(
            plugin_id=plugin, version=installed, names=tuple(sorted(item.name for item in descriptors)),
            changed=diffs, first_mount=first, artifact=artifact, trust=trust,
            artifact_changed=moved is not None,
        )

    def _roll_back(
        self, *, plugin, actor, step, exc, before_mounts, before_lock,
        before_descriptors, registry, version
    ) -> None:
        """Undo what was written, then say in the audit which step broke.

        A refusal raised before the first mutation has nothing to undo and is recorded as
        one; that distinction belongs to a reader of the trail, so it is decided here
        rather than guessed downstream from a status word.
        """
        mutated = step in MUTATING_STEPS
        if mutated:
            if step in REGISTRY_WRITTEN_STEPS:
                registry.replace_for_plugin(plugin, before_descriptors)
            self._data[MOUNTS_FIELD] = before_mounts
            self._persist_or_log()
            restore_lock(before_lock)
        self._audit_mount(
            action="mount", plugin=plugin, actor=actor,
            state="mounted" if before_mounts.get(plugin) else "idle",
            status="rolled_back" if mutated else "refused",
            code=str(getattr(exc, "code", "") or "") or step,
            version=version,
            reason=f"step={step} {type(exc).__name__}: {str(exc)[:240]}",
        )

    # The steps, each one a seam a test can break at

    def _mount_read_manifest(self, plugin: str) -> tuple[dict, Path]:
        """The located bundle and its validated manifest; a bundle in neither root is 404.

        The manifest's own defect words live in `core/plugin_mount_trust.py`.
        """
        from core.plugin_lifecycle_types import LifecycleError

        directory = plugin_directory(plugin)
        if directory is None:
            raise LifecycleError(
                "unknown_plugin", 404, f"plugin '{plugin}' is not installed"
            )
        return manifest_of(plugin, directory), directory

    def _mount_descriptors(self, manifest: dict) -> tuple:
        from core import plugin_tools_contract

        return plugin_tools_contract.descriptors_for(manifest)

    def _mount_check_pins(self, plugin: str, descriptors, acknowledge):
        """(first_mount, diff): the alarm Non-negotiable #4 asks for, or silence."""
        from core.plugin_lifecycle_types import LifecycleError

        pinned = list(pinned_records(plugin))
        if not pinned:
            return True, ()
        diffs = diff_against_pins(descriptors, pinned)
        unacknowledged = [item for item in diffs if item.name not in acknowledge]
        if unacknowledged:
            raise LifecycleError(
                REFUSE_CHANGE,
                409,
                "the tool contract changed since the last accepted mount: "
                + ", ".join(item.summary() for item in unacknowledged),
                data={"diff": [item.as_dict() for item in unacknowledged]},
            )
        return False, diffs

    def _mount_record_lockfile(self, plugin: str, records) -> None:
        write_pins(plugin, records)

    def _mount_record_activation(
        self, plugin: str, descriptors, version: str, *, artifact: str, trust: str
    ) -> None:
        self._data.setdefault(MOUNTS_FIELD, {})[plugin] = activation_record(
            plugin, version, descriptors, artifact=artifact, trust=trust
        )
        self._persist()

    def _mount_publish_descriptors(self, plugin: str, descriptors) -> None:
        from core.plugin_lifecycle_types import LifecycleError

        outcome = descriptor_registry().replace_for_plugin(plugin, descriptors)
        if not outcome.ok:
            raise LifecycleError(
                REFUSE_REGISTRY, 409, f"{outcome.code}: {outcome.detail}"
            )

    def _mount_notify(self, plugin: str, names, *, phase: str = "mounted") -> None:
        """The one place the runtime learns that the served set moved.

        Dropping the ownership cache is what makes a mount take effect on the next read,
        and the event rides the existing SSE stream, so a surface watching a plugin sees its
        tools arrive without asking. One event per tool, so a subscriber can react to each
        registration individually — the batch event rides alongside for consumers that want
        the whole set in one frame.
        """
        from core import plugin_runtime

        plugin_runtime.invalidate_ownership_cache()
        for tool_name in names:
            self._publish(
                "plugin.tool_registered",
                {"plugin": plugin, "tool": tool_name, "phase": phase},
            )
        self._publish(
            "plugin.mount", {"name": plugin, "phase": phase, "tools": list(names)}
        )

    # Small reads, and the one audit shape

    def _persist_or_log(self) -> None:
        """A rollback write that fails must not hide the failure that caused it."""
        from core.plugin_lifecycle_types import LifecycleError

        try:
            self._persist()
        except LifecycleError as exc:
            from core.audit_log import audit_event

            audit_event(
                "plugin_lifecycle", tool="", decision="mount_restore", status="failed",
                detail=f"the state file did not take the rollback: {str(exc)[:200]}",
            )

    def _commit_summary(
        self, reason: str, records, diffs, first: bool, trust: str, moved: bool
    ) -> str:
        parts = [
            f"pinned={len(records)}", "first_mount" if first else "remount",
            f"trust={trust}",
        ]
        if moved:
            parts.append("artifact_moved")
        if diffs:
            parts.append("acknowledged=" + ",".join(item.summary() for item in diffs))
        if reason:
            parts.append(reason)
        return " ".join(parts)

    def _audit_mount(
        self, *, action, plugin, actor, state, status, code, reason, version=""
    ) -> None:
        """One row per outcome, in the shape every other transition writes.

        The host's own `_audit` is the audit sink, so this carries the mount word: a
        second spelling of the same row would be two shapes in one trail.
        """
        self._audit_entry(
            action=action,
            plugin=plugin,
            scope="mount",
            actor=actor,
            previous_state=state,
            requested_state="mounted" if action == "mount" else "idle",
            state=state,
            version=str(version or self._versions.get(plugin, "")),
            duration_ms=0,
            reason=f"{code} {reason}".strip(),
            status=status,
        )
