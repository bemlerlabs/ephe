"""What a restart does with the bundles that were mounted.

The mount's intent lives in the state document (`mounts`), the tools it published live in
this process's descriptor registry. A new process therefore starts with the record of five
mounted bundles and none of their tools — and the Extensions surface, which reads the
record, keeps saying *mounted*. That is the shape this module exists to close: an instrument
asserting what it did not read.

It reuses the transition rather than inventing a second one. Each recorded bundle is
re-mounted through `PluginLifecycle.mount`, so the name scan, the contract pin, the atomic
descriptor swap, the rollback and the audit row are the same code a user-facing mount runs,
and nothing is acknowledged on the user's behalf: #17's content guard decides by class, so a
`local` bundle's edited bytes come back and a record accepted under a signature refuses —
and that refusal is the reported reason its tools are absent.

`ensure_published` runs once per process. Every surface reaches the tool set through
`core.tools.registry`, so the hook belongs on that read rather than on one startup path
that the CLI, the TUI and an imported server would each have to remember to call.
"""

from __future__ import annotations

from typing import Any

STATUS_PUBLISHED = "published"
STATUS_REFUSED = "refused"
STATUS_FAILED = "failed"

_ran = False
_last: dict[str, dict[str, Any]] = {}


def replay_of(plugin: str) -> dict[str, Any]:
    """What the last replay did with one bundle: `{"status": ..., "detail": ...}`."""
    return dict(_last.get(plugin) or {"status": "not-replayed", "detail": ""})


def reset() -> None:
    """Forget that a replay ran, so the next read of the tool set replays again."""
    global _ran
    _ran = False


def ensure_published() -> None:
    """Re-publish what the state document says is mounted, at most once per process."""
    global _ran
    if _ran:
        return
    _ran = True
    republish_all()


def publish_shipped_contributed() -> dict[str, dict[str, Any]]:
    """Publish first-party contributed tools through the mount, when their names are absent.

    A version 1 name lived in the kernel map and the switch only hid it. A version 2
    name exists after `lifecycle.mount` and nowhere else. The tool-set read is the
    one call the CLI, the TUI and the server share, so a shipped bundle is mounted
    here the first time its descriptors are missing. The switch stays the gate:
    the unfiltered schema list keeps the name, and a bundle that is off is dropped
    on the way out. That is what a cached offer list needs in order to show the
    name again on the next call after the switch flips.
    """
    from core import plugin_runtime
    from core.plugin_lifecycle_types import LifecycleError
    from core.plugin_manifest import BUILTIN_PLUGINS_ROOT, load_manifest
    from core.plugin_mount_records import descriptor_registry
    from core.plugin_tools_contract import tool_claims

    if not BUILTIN_PLUGINS_ROOT.is_dir():
        return {}
    registry = descriptor_registry()
    lifecycle = plugin_runtime.lifecycle()
    out: dict[str, dict[str, Any]] = {}
    for directory in sorted(path for path in BUILTIN_PLUGINS_ROOT.iterdir() if path.is_dir()):
        manifest, error = load_manifest(directory)
        if error or not isinstance(manifest, dict):
            continue
        if str(manifest.get("origin") or "") != "first-party":
            continue
        claims = tuple(claim for claim in tool_claims(manifest) if claim.contributed)
        if not claims:
            continue
        plugin = str(manifest.get("name") or directory.name)
        # A set already published for this plugin stays. Replacing it here would
        # drop a name this process registered beside the shipped ones. The first
        # read, with nothing published, is the mount.
        if any(item.plugin_id == plugin for item in registry.descriptor_snapshot()):
            continue
        try:
            result = lifecycle.mount(
                plugin, actor="startup", reason="shipped contributed tools"
            )
        except LifecycleError as exc:
            out[plugin] = {
                "status": STATUS_REFUSED,
                "detail": f"{exc.code}: {exc.detail}"[:400],
            }
            continue
        except Exception as exc:  # noqa: BLE001 — one bundle must not sink the offer list
            out[plugin] = {"status": STATUS_FAILED, "detail": type(exc).__name__[:200]}
            continue
        out[plugin] = {"status": STATUS_PUBLISHED, "detail": f"names={len(result.names)}"}
    return out


def republish_all() -> dict[str, dict[str, Any]]:
    """Re-mount every recorded bundle and return the per-bundle outcome."""
    from core import plugin_runtime

    lifecycle = plugin_runtime.lifecycle()
    records = lifecycle.mount_records()
    out: dict[str, dict[str, Any]] = {}
    for plugin in sorted(records):
        out[plugin] = republish_one(lifecycle, plugin, records.get(plugin) or {})
    global _last
    _last = out
    _audit_summary(out)
    return out


def republish_one(lifecycle, plugin: str, record: dict[str, Any]) -> dict[str, Any]:
    """One bundle's replay: the transition's own answer, or its own refusal.

    Nothing is acknowledged here. #17's content guard already decides by class — a `local`
    bundle's moved bytes mount and are re-recorded, a record accepted under a signature
    refuses — and passing an acknowledgment the replay does not have would be the machine
    agreeing on the user's behalf.
    """
    from core.plugin_lifecycle import LifecycleError

    try:
        result = lifecycle.mount(plugin, actor="startup", reason="restart replay")
    except LifecycleError as exc:
        return {"status": STATUS_REFUSED, "detail": f"{exc.code}: {exc.detail}"[:400]}
    except Exception as exc:  # noqa: BLE001 — a bundle that cannot be read is reported
        return {"status": STATUS_FAILED, "detail": f"{type(exc).__name__}"[:200]}
    return {"status": STATUS_PUBLISHED, "detail": f"names={len(result.names)}"}


def _audit_summary(out: dict[str, dict[str, Any]]) -> None:
    """One trail line for the replay, whenever it moved or withheld anything.

    A silent replay would leave the reader with a mounted label and no tool and no way to
    find out which of the two the machine believes. The per-bundle mount already writes its
    own row; this says the whole pass happened and how it went.
    """
    if not out:
        return
    from core.audit_log import audit_event

    published = sum(1 for row in out.values() if row["status"] == STATUS_PUBLISHED)
    withheld = [f"{name}:{row['status']}" for name, row in out.items()
                if row["status"] != STATUS_PUBLISHED]
    audit_event(
        "plugin_lifecycle",
        tool="",
        decision="mount_replay",
        status="done" if not withheld else "partial",
        detail=f"published={published} " + " ".join(withheld)[:360],
    )
