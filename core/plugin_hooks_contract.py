"""Ephe — `components.hooks`: the observers a bundle runs around a turn.

core/plugin_hooks_contract.py

A version 2 bundle may name at most one hook for the start of a turn and one for its end.
It says so once, in the manifest, and the kernel decides every consequence: the event
vocabulary, the payload, the ordering, the confinement, the timeout and the silence.
Nothing here imports plugin code, and nothing here runs at turn time — the claim is data
the dispatcher reads, and `core/plugin_turn_hooks.py` is the one place a process is
started from it.

Both payloads are fixed by the kernel and metadata-only, by construction. The start
payload carries the turn id and the moment the turn began; the end payload carries the
loop's stop reason, the names of the tools the turn called and the turn's duration. No
answer text, no history, no tool arguments, and nothing of the workspace or context
report. `docs/CONTEXT_CONTRACT.md` makes that resolver the one channel that decides what
the model sees; a hook is not a second one, and a manifest field asking for the answer is
refused here rather than silently ignored.

Why version 2 only. A live hook is the same class of bundle code as a contributed tool
entry, and version 2 is where identity and licence are already mandatory
(`core/plugin_manifest_contract.py`). A version 1 manifest that carries the section is
quarantined, exactly like a version 1 `capabilities` object.

Fail-closed rules, in one list: `components.hooks` in a version 1 manifest, a `hooks`
value that is not an object, an event outside `HOOK_EVENTS`, an event body that is not an
object, an unknown field, a missing or malformed `entry` (the same lexical and containment
rule a tool entry obeys, through `_entry_field_error`), a `timeout_seconds` that is a
bool, not a whole number, or outside `MIN_HOOK_TIMEOUT_SECONDS` .. `MAX_HOOK_TIMEOUT_SECONDS`,
and more hooks than `MAX_HOOKS_PER_BUNDLE`. Each of them quarantines the whole bundle.

At most two hooks per bundle, one per event, and the two events are a turn's start and its
end. `pre_tool`, `post_tool`, a mutating or vetoing hook, an answer-bearing payload and a
network transport are later cuts, each with its own approval and audit design; the event
tuple is where one gets added, and a name a manifest guesses is refused.

Everything a hook writes stays inside its confined run and its own state root: the bundle
directory and its declared `permissions.data_roots` are the only reads, and the reply is
discarded. The network is denied at the OS boundary for every worker (`core/sandbox/
supervisor.py`), and no bridge dispatch is passed, so a hook that asks for the launcher's
third parameter fails its own run instead of reaching a product handle.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

__all__ = [
    "HOOK_EVENTS",
    "HOOK_FIELDS",
    "MAX_HOOKS_PER_BUNDLE",
    "MAX_HOOK_TIMEOUT_SECONDS",
    "MIN_HOOK_TIMEOUT_SECONDS",
    "TurnHook",
    "hook_claims",
    "hook_facts",
    "scan_turn_hooks",
    "validate_hooks",
]

#: The events a hook may listen for, in the order a turn reaches them. A later event is
#: a row in this tuple plus its dispatch site in the kernel, never a name a manifest
#: invents.
HOOK_EVENTS: tuple[str, ...] = ("turn_start", "turn_end")
#: The fields one event body carries. The payload is not a field: it is the kernel's.
HOOK_FIELDS: frozenset[str] = frozenset({"entry", "timeout_seconds"})
#: One hook per event, so the vocabulary bounds a bundle at two runs per turn. The cap is
#: checked on its own so a grown vocabulary cannot quietly grant a third spawn per turn.
MAX_HOOKS_PER_BUNDLE = 2
#: The window a run must fit in. The lower bound keeps a hook from being a pause, the
#: upper bound keeps a per-turn spawn from outliving the turn's own user.
MIN_HOOK_TIMEOUT_SECONDS = 1
MAX_HOOK_TIMEOUT_SECONDS = 3


@dataclass(frozen=True)
class TurnHook:
    """One declared turn hook, normalized the way the dispatcher reads it.

    ``plugin_id`` owns the declaration and is what the lifecycle gate asks about.
    ``plugin_dir`` is the folder the claim was scanned from; it is empty for a claim read
    from a manifest alone, and the dispatcher refuses a run it cannot place.
    """

    plugin_id: str
    event: str
    entry: str
    timeout_seconds: int
    plugin_dir: str = ""


def _timeout_error(label: str, timeout: Any) -> str | None:
    """The declared bound, read against the kernel's window; a bool is not a number."""
    if isinstance(timeout, bool) or not isinstance(timeout, int):
        return f"{label}: a whole number of seconds expected"
    if not MIN_HOOK_TIMEOUT_SECONDS <= timeout <= MAX_HOOK_TIMEOUT_SECONDS:
        return (
            f"{label}: {timeout} is outside "
            f"{MIN_HOOK_TIMEOUT_SECONDS}..{MAX_HOOK_TIMEOUT_SECONDS} seconds"
        )
    return None


def _event_error(label: str, body: Any, plugin_dir: Path) -> str | None:
    from core.plugin_tools_contract import _entry_field_error

    if not isinstance(body, dict):
        return f"{label}: object expected"
    unknown_fields = sorted(set(body) - HOOK_FIELDS)
    if unknown_fields:
        return (
            f"{label}: unknown field(s): {', '.join(unknown_fields)} — a hook receives "
            "the kernel's metadata payload and cannot declare another field"
        )
    entry_error = _entry_field_error(label, body.get("entry"), plugin_dir)
    if entry_error:
        return entry_error
    return _timeout_error(f"{label}.timeout_seconds", body.get("timeout_seconds"))


def validate_hooks(manifest: Any, plugin_dir: Path) -> str | None:
    """The `components.hooks` contract; called once from the manifest contract."""
    if not isinstance(manifest, dict):
        return None
    components = manifest.get("components")
    if not isinstance(components, dict) or "hooks" not in components:
        return None
    if manifest.get("manifest_version") != 2:
        return "components.hooks: manifest_version 2 required"
    hooks = components.get("hooks")
    if not isinstance(hooks, dict):
        return "components.hooks: object expected"
    unknown_events = sorted(set(hooks) - set(HOOK_EVENTS))
    if unknown_events:
        return (
            "components.hooks: unknown event(s): "
            f"{', '.join(unknown_events)} (known events are "
            f"{', '.join(HOOK_EVENTS)})"
        )
    if len(hooks) > MAX_HOOKS_PER_BUNDLE:
        return (
            f"components.hooks: at most {MAX_HOOKS_PER_BUNDLE} hooks per bundle, one per "
            f"event; {len(hooks)} declared"
        )
    for event in HOOK_EVENTS:
        if event not in hooks:
            continue
        error = _event_error(f"components.hooks.{event}", hooks[event], plugin_dir)
        if error:
            return error
    return None


def hook_claims(manifest: Any) -> tuple[TurnHook, ...]:
    """Every turn hook one valid manifest declares, in event order.

    A malformed declaration yields no claim rather than a wrong one: the manifest that
    carries it was quarantined by `validate_hooks` before anything read this. The shape
    is checked again because this reader also sees manifests that no loader validated
    (the store's best-effort annotations).
    """
    if not isinstance(manifest, dict) or manifest.get("manifest_version") != 2:
        return ()
    components = manifest.get("components")
    if not isinstance(components, dict):
        return ()
    hooks = components.get("hooks")
    if not isinstance(hooks, dict):
        return ()
    claims: list[TurnHook] = []
    for event in HOOK_EVENTS:
        body = hooks.get(event)
        if not isinstance(body, dict):
            continue
        entry = body.get("entry")
        timeout = body.get("timeout_seconds")
        if not isinstance(entry, str) or not entry.strip():
            continue
        if _timeout_error("timeout", timeout) is not None:
            continue
        claims.append(
            TurnHook(
                plugin_id=str(manifest.get("name") or ""),
                event=event,
                entry=entry.strip(),
                timeout_seconds=int(timeout),
            )
        )
    return tuple(claims)


def hook_facts(manifest: Any) -> list[dict[str, Any]]:
    """The declaration as a surface reads it: the event and its bound, nothing else.

    One producer for the store row and the view annotation, so the two surfaces cannot
    state different facts about the same manifest.
    """
    return [
        {"event": claim.event, "timeout_seconds": claim.timeout_seconds}
        for claim in hook_claims(manifest)
    ]


def scan_turn_hooks(entries: Iterable[dict[str, Any]]) -> tuple[TurnHook, ...]:
    """Claims from one manifest scan (`core.plugin_manifest.scan_plugins`).

    Takes the entries rather than scanning them, so this module stays below the loader
    it is called from and a caller owns the root it reads. A bundle's claim carries the
    folder it was scanned from, so the dispatcher spawns from the directory the scan read
    instead of walking the portfolio a second time per turn.
    """
    hooks: list[TurnHook] = []
    for entry in entries:
        manifest = entry.get("manifest")
        if entry.get("error") or not manifest:
            continue
        directory = str(entry.get("dir") or "")
        for claim in hook_claims(manifest):
            hooks.append(replace(claim, plugin_dir=directory))
    order = {event: index for index, event in enumerate(HOOK_EVENTS)}
    return tuple(
        sorted(
            hooks,
            key=lambda hook: (
                hook.plugin_id,
                order.get(hook.event, len(HOOK_EVENTS)),
            ),
        )
    )
