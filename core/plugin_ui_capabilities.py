"""Ephe — permissions.ui: what a plugin's webview surface may touch.

core/plugin_ui_capabilities.py

Two tiers decide what a manifest has to carry. Tier 1 is declarative: the plugin
bundles existing capabilities (skills, commands, MCP targets, one UI surface) and
ships no plugin code of its own. Tier 2 ships tool entry points, and that one
additionally needs an explicit escalation approval and a signature. Wave 1's
walking skeleton runs entirely on tier 1, so this contract has to be complete
enough for a floating countdown widget with notifications and a dock badge to say
everything it will do inside its manifest.

One surface per plugin in this version of the contract: `components.ui` is a
single descriptor object. Two surfaces need an `id` field and a dedup rule before a
list can be accepted, and a denial that cannot say which surface it refused is a
worse answer than one question per plugin.

Declared on the descriptor. The capabilities a surface may use are
`components.ui.capabilities`, one list beside the surface they govern. The axis is
called permissions.ui in the plan and the wave notes, and a manifest key of that
name is refused here: `permissions` holds what the kernel grants the plugin's code,
and a second place to declare the same list would give one question two answers.
The tier-2 half — tool entry points, their escalation approval, their signature —
is the next manifest task's work; this file owns the UI axis and reads nothing else.

Two axes, kept apart. `permissions.tool_families` (core/plugin_manifest.py
KNOWN_TOOL_FAMILIES) is what a plugin asks of the kernel's files and processes;
the set below is what one webview surface may reach. `network` is the single shared
name, and it asks the same question of two different actors: a kernel tool reaching
out, and a surface reaching out from its own origin. A file or process right (shell,
general filesystem access) stays in `tool_families`, because two permission systems
naming one grant is how a grant gets lost.

Default-deny. A surface that declares no capabilities gets none. One declared name
outside UI_CAPABILITIES is a manifest error and quarantines the whole plugin, the
same rule an unknown tool family already follows: a plugin that cannot say what it
will do gets nothing done.

report == enforced. Every name carries four things in
UI_CAPABILITY_ENFORCEMENT: the layer that confines it, whether that layer can
confine a plugin surface in this tree today (`enforced`), the audit kind it writes
through core/audit_log.py, and whether a user has to say yes to it beyond the
install declaration (`grant`). The honest reading today is that
ENFORCED_CAPABILITIES is empty: no plugin webview exists yet, so nothing here can
be confined per plugin. `tests/test_plugin_ui_capabilities.py` pins that emptiness,
and a name may move to enforced only in the commit carrying that layer's own
observing test: the record's `observed_by` names that file, and the ratchet refuses
an enforced name whose witness is missing from the table or from disk.

Where each name will be confined, group by group:

    webgl, wasm, audio-out, drag-drop — the webview feature policy of the surface
    builder (`app/src-tauri/src`, #43 native window, #44 overlay). A builder that
    never turns a feature on for a plugin's window label is the confinement.

    workers — the content security policy of the surface route (#42): `worker-src`
    sits on the app origin behind the per-document sandbox, and the layer is not
    per-plugin yet, so the name stays unenforced until a per-plugin origin exists.

    clipboard-read, clipboard-write, keyboard-capture, file-save, network — the
    plugin message bridge (#23) refuses a call the descriptor did not declare, and
    #42 gives the surface an origin of its own so the webview's clipboard, drag and
    connect policies have something to bind to. Anything leaving the process on the
    bridge's behalf also runs through core/network_guard.py.

    notifications, fullscreen, global-shortcut, dock-badge — the shell holds these
    already: notification, dialog and global-shortcut plugins are wired into the
    app, the dock badge is a native command in `app/src-tauri/src/desktop.rs`, and
    `app/src-tauri/capabilities/default.json` grants them to the `main` window
    label. A plugin surface needs its own capability entry per label (#43) before it
    can hold one; that per-plugin half is what is pending.

    audio-in, camera — the two this tree cannot honestly confine yet. A microphone
    request is covered by the bundle usage declaration in
    `app/src-tauri/Info.plist`; a camera request has no declaration there at all,
    and the comment above that file records what a page asking for an undeclared
    protected resource does to the host process. Both need the native shell to carry
    a per-surface permission first, and both are recorded grant-required.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from core.plugin_manifest import _under

#: The three surfaces a plugin may ask the shell to create.
UI_TYPES = frozenset({"floating-window", "dock-panel", "canvas-overlay"})

#: Fields a descriptor has to state; everything else has a default below.
REQUIRED_UI_FIELDS = ("type", "entry", "title")

#: Everything a descriptor may name. An unknown field is refused the way an
#: unknown manifest field is, so a typo cannot sit unread in a shipped plugin.
UI_FIELDS = frozenset(
    {
        "type",
        "entry",
        "title",
        "default_size",
        "transparent",
        "always_on_top",
        "capabilities",
    }
)

#: The two edges of `default_size`, and the ceiling a surface may ask for.
#: 4096 is what this contract fixes; #39 owns the measured number the shell will
#: honour on the machines Ephe actually runs on, and a surface asking past the
#: stated ceiling is a manifest error until that measurement says otherwise.
MAX_UI_DIMENSION = 4096
DEFAULT_UI_WIDTH = 480
DEFAULT_UI_HEIGHT = 320

#: A window title is laid out in a titlebar; 80 characters is the point past which
#: the shell has to truncate, and truncating a plugin's name is a support ticket.
MAX_UI_TITLE_CHARS = 80

#: The entry document a surface loads, by suffix. One HTML document per surface is
#: what the asset route (#42) can serve under one CSP.
UI_ENTRY_SUFFIX = ".html"


class CapabilityRecord(NamedTuple):
    """What one capability name commits the platform to.

    `layer` is where the refusal happens, `enforced` says whether that layer can
    refuse a plugin surface in this tree today, `audit_kind` is the label written to
    the audit log, and `grant` marks a name that reaches past the surface and so
    needs a user's yes beyond the install declaration. `observed_by` is the
    repo-relative path of the test file that can watch that confinement; an
    enforced name with no witness behind it stays None and stays unenforced."""

    layer: str
    enforced: bool
    audit_kind: str
    grant: bool
    observed_by: str | None = None


_BRIDGE = "plugin message bridge (#23)"
_SURFACE_BUILDER = "webview feature policy of the surface builder (app/src-tauri/src, #43/#44)"
_PLUGIN_ORIGIN = "per-document sandboxed CSP of the surface route (#42); the asset origin is still the app origin, no per-plugin origin exists yet"
_WINDOW_ACL = "per-window capability entry (app/src-tauri/capabilities, #43)"
_ORIGIN_AND_BRIDGE = _PLUGIN_ORIGIN + ", " + _BRIDGE
_ACL_AND_BRIDGE = _WINDOW_ACL + ", " + _BRIDGE
_NOTIFICATION_LAYER = _WINDOW_ACL + " over the notification plugin"
_FULLSCREEN_LAYER = _WINDOW_ACL + " (window allow-set-fullscreen)"
_SHORTCUT_LAYER = _WINDOW_ACL + " over the global-shortcut plugin"
_NETWORK_LAYER = _PLUGIN_ORIGIN + ", core/network_guard.py"
_AUDIO_IN_LAYER = (
    "microphone permission of the surface builder "
    "(app/src-tauri/Info.plist usage declaration), " + _BRIDGE
)
_CAMERA_LAYER = (
    "camera permission of the surface builder, which carries no camera usage "
    "declaration yet, " + _BRIDGE
)
_FILE_SAVE_LAYER = "native save dialog behind " + _BRIDGE + " (dialog is wired in the app)"
_DOCK_BADGE_LAYER = (
    "native dock command (app/src-tauri/src/desktop.rs) behind " + _BRIDGE
)

#: The vocabulary, and the record every name has to carry. Deriving
#: UI_CAPABILITIES from this table is what keeps a name from entering the
#: vocabulary without an answer to "who refuses it".
UI_CAPABILITY_ENFORCEMENT: dict[str, CapabilityRecord] = {
    "webgl": CapabilityRecord(_SURFACE_BUILDER, False, "ui.webgl", False),
    "wasm": CapabilityRecord(_SURFACE_BUILDER, False, "ui.wasm", False),
    "workers": CapabilityRecord(_PLUGIN_ORIGIN, False, "ui.workers", False),
    "audio-out": CapabilityRecord(_SURFACE_BUILDER, False, "ui.audio-out", False),
    "audio-in": CapabilityRecord(_AUDIO_IN_LAYER, False, "ui.audio-in", True),
    "camera": CapabilityRecord(_CAMERA_LAYER, False, "ui.camera", True),
    "clipboard-read": CapabilityRecord(_ORIGIN_AND_BRIDGE, False, "ui.clipboard-read", True),
    "clipboard-write": CapabilityRecord(_ORIGIN_AND_BRIDGE, False, "ui.clipboard-write", True),
    "notifications": CapabilityRecord(_NOTIFICATION_LAYER, False, "ui.notifications", False),
    "fullscreen": CapabilityRecord(_FULLSCREEN_LAYER, False, "ui.fullscreen", False),
    "keyboard-capture": CapabilityRecord(_ACL_AND_BRIDGE, False, "ui.keyboard-capture", True),
    "file-save": CapabilityRecord(_FILE_SAVE_LAYER, False, "ui.file-save", True),
    "drag-drop": CapabilityRecord(_SURFACE_BUILDER, False, "ui.drag-drop", False),
    "dock-badge": CapabilityRecord(_DOCK_BADGE_LAYER, False, "ui.dock-badge", False),
    "global-shortcut": CapabilityRecord(_SHORTCUT_LAYER, False, "ui.global-shortcut", True),
    "network": CapabilityRecord(_NETWORK_LAYER, False, "ui.network", True),
}

#: The names a manifest may declare, and nothing else.
UI_CAPABILITIES: frozenset[str] = frozenset(UI_CAPABILITY_ENFORCEMENT)

#: Names confined for a plugin surface in this tree today.
ENFORCED_CAPABILITIES: frozenset[str] = frozenset(
    name for name, record in UI_CAPABILITY_ENFORCEMENT.items() if record.enforced
)

#: Names that need an explicit user grant beyond the install declaration.
GRANT_REQUIRED_CAPABILITIES: frozenset[str] = frozenset(
    name for name, record in UI_CAPABILITY_ENFORCEMENT.items() if record.grant
)


def unenforced_ui_capabilities() -> tuple[str, ...]:
    """The vocabulary a permission notice has to say it cannot yet confine."""
    return tuple(
        sorted(
            name
            for name in UI_CAPABILITIES
            if name not in ENFORCED_CAPABILITIES
        )
    )


def _surface_of(manifest: object) -> object:
    """`components.ui` as the manifest holds it, or None when there is none."""
    if not isinstance(manifest, dict):
        return None
    components = manifest.get("components")
    if not isinstance(components, dict):
        return None
    return components.get("ui")


def _relative_entry(entry: str) -> str:
    """The declared path with its `./` noise taken out, one relative posix path."""
    parts = [part for part in entry.replace("\\", "/").split("/") if part not in ("", ".")]
    return "/".join(parts)


def _positive_dimension(value: object) -> int | None:
    """A stated edge as an integer inside the cap, or None when it is not one.

    `type(...) is int` because `True` is `1` and a boolean edge would otherwise read
    as a 1-pixel surface."""
    if type(value) is not int or value < 1 or value > MAX_UI_DIMENSION:
        return None
    return value


def _validate_size(surface: dict) -> str | None:
    size = surface["default_size"]
    if not isinstance(size, dict):
        return "components.ui.default_size: object with width and height expected"
    unknown = sorted(set(size) - {"width", "height"})
    if unknown:
        return f"components.ui.default_size: unknown field(s): {', '.join(unknown)}"
    for edge in ("width", "height"):
        if edge not in size:
            return f"components.ui.default_size: {edge} expected"
        if _positive_dimension(size[edge]) is None:
            return (
                f"components.ui.default_size.{edge}: positive integer up to "
                f"{MAX_UI_DIMENSION} expected"
            )
    return None


def _validate_capabilities(surface: dict) -> str | None:
    capabilities = surface["capabilities"]
    if not isinstance(capabilities, list):
        return "components.ui.capabilities: list of capability names expected"
    declared: set[str] = set()
    for name in capabilities:
        if not isinstance(name, str):
            return "components.ui.capabilities: list of capability names expected"
        if name not in UI_CAPABILITIES:
            return (
                f"components.ui.capabilities: unknown capability {name!r} "
                "(this vocabulary is closed; declared-but-unknown names never run, "
                "fail-closed quarantine)"
            )
        if name in declared:
            return f"components.ui.capabilities: duplicate capability {name!r}"
        declared.add(name)
    return None


def _validate_entry(surface: dict, plugin_dir: Path) -> str | None:
    entry = surface["entry"]
    path = Path(entry)
    if path.is_absolute():
        return f"components.ui.entry: {entry!r} must be a path inside the plugin directory"
    if ".." in path.parts:
        return f"components.ui.entry: {entry!r} must stay inside the plugin directory"
    if path.suffix.lower() != UI_ENTRY_SUFFIX:
        return f"components.ui.entry: {entry!r} must be an {UI_ENTRY_SUFFIX} document"
    ships = _under(plugin_dir, entry)
    if ships is None:
        return f"components.ui.entry: {entry!r} resolves outside the plugin directory"
    if not ships.is_file():
        return f"components.ui.entry: declared document {entry!r} does not ship"
    return None


def _misplaced_declaration(manifest: object) -> bool:
    """Whether the manifest tries to declare UI capabilities under `permissions`."""
    if not isinstance(manifest, dict):
        return False
    permissions = manifest.get("permissions")
    return isinstance(permissions, dict) and "ui" in permissions


def validate_ui(manifest: dict, plugin_dir: Path) -> str | None:
    """The contract check for `components.ui`: an error string, or None.

    Called from core/plugin_manifest._validate for every manifest, so a surface
    declared in the wrong place is refused too. Everything here answers one of
    three questions: is the field a field of this contract, does it hold a value of
    the right kind, and does the path it names stay inside the plugin directory.
    """
    if _misplaced_declaration(manifest):
        return (
            "permissions.ui: nothing reads this key; capabilities are declared on "
            "components.ui.capabilities, beside the surface they govern"
        )
    surface = _surface_of(manifest)
    if surface is None:
        return None
    if not isinstance(surface, dict):
        return "components.ui: descriptor object expected"

    for field in REQUIRED_UI_FIELDS:
        value = surface.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"components.ui.{field}: non-empty string expected"

    unknown = sorted(set(surface) - UI_FIELDS)
    if unknown:
        return f"components.ui: unknown field(s): {', '.join(unknown)}"

    if surface["type"] not in UI_TYPES:
        return (
            f"components.ui.type: {surface['type']!r} is not one of "
            f"{sorted(UI_TYPES)}"
        )
    title = surface["title"].strip()
    if len(title) > MAX_UI_TITLE_CHARS:
        return (
            f"components.ui.title: longer than {MAX_UI_TITLE_CHARS} characters"
        )
    entry_error = _validate_entry(surface, plugin_dir)
    if entry_error:
        return entry_error
    if "default_size" in surface:
        size_error = _validate_size(surface)
        if size_error:
            return size_error
    for flag in ("transparent", "always_on_top"):
        if flag in surface and type(surface[flag]) is not bool:
            return f"components.ui.{flag}: boolean expected"
    if "capabilities" in surface:
        capability_error = _validate_capabilities(surface)
        if capability_error:
            return capability_error
    return None


def ui_descriptor(manifest: dict) -> dict:
    """The normalized view of `components.ui` for the runtime side of Wave 1.

    Read it after `load_manifest` has returned the manifest, which is where the
    checks above already ran: this function fills defaults and sorts lists so a
    consumer never has to know which fields a plugin left out. A manifest with no
    surface describes nothing and returns an empty dict.
    """
    surface = _surface_of(manifest)
    if not isinstance(surface, dict):
        return {}
    size = surface.get("default_size")
    width = height = None
    if isinstance(size, dict):
        width = _positive_dimension(size.get("width"))
        height = _positive_dimension(size.get("height"))
    names = surface.get("capabilities", [])
    declared = (
        sorted({name for name in names if isinstance(name, str)})
        if isinstance(names, list)
        else []
    )
    return {
        "plugin": str(manifest.get("name", "")),
        "type": str(surface.get("type", "")),
        "entry": _relative_entry(str(surface.get("entry", ""))),
        "title": str(surface.get("title", "")).strip(),
        "width": width or DEFAULT_UI_WIDTH,
        "height": height or DEFAULT_UI_HEIGHT,
        "transparent": surface.get("transparent") is True,
        "always_on_top": surface.get("always_on_top") is True,
        "capabilities": declared,
        "grants": [name for name in declared if name in GRANT_REQUIRED_CAPABILITIES],
    }
