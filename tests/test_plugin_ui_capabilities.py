"""permissions.ui — what a plugin's webview surface may reach, and who says so.

The vocabulary is a contract for Wave 1: a floating countdown widget with
notifications and a dock badge has to be declarable in tier 1, carrying the
manifest and nothing else. Every name is checked at manifest time, so an
undeclared surface gets no capability and a name nobody defined quarantines the
plugin.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.plugin_manifest import KNOWN_TOOL_FAMILIES, MANIFEST_FILENAME, load_manifest
from core.plugin_ui_capabilities import (
    DEFAULT_UI_HEIGHT,
    DEFAULT_UI_WIDTH,
    ENFORCED_CAPABILITIES,
    GRANT_REQUIRED_CAPABILITIES,
    MAX_UI_DIMENSION,
    MAX_UI_TITLE_CHARS,
    REQUIRED_UI_FIELDS,
    UI_CAPABILITIES,
    UI_CAPABILITY_ENFORCEMENT,
    UI_TYPES,
    ui_descriptor,
    unenforced_ui_capabilities,
    validate_ui,
)

ENTRY_DOCUMENT = "<!doctype html><title>Countdown</title>"


def _surface(**over: object) -> dict:
    """The smallest surface the walking skeleton needs: one widget, two badges."""
    surface = {
        "type": "floating-window",
        "entry": "ui/index.html",
        "title": "Countdown",
        "capabilities": ["notifications", "dock-badge"],
    }
    surface.update(over)
    return surface


def _manifest(surface: object, *, manifest_version: int = 1) -> dict:
    manifest = {
        "manifest_version": manifest_version,
        "name": "acme-countdown",
        "version": "1.0.0",
        "description": "A countdown that survives a restart",
        "permissions": {"tool_families": [], "data_roots": []},
        "components": {"skills": [], "commands": [], "ui": surface},
    }
    if manifest_version == 2:
        manifest.update({"publisher": "Acme", "license": "MIT"})
    return manifest


def _dir(tmp_path: Path, entry: str = "ui/index.html") -> Path:
    """A plugin directory holding one entry document at `entry`."""
    if not entry.startswith("/") and ".." not in Path(entry).parts:
        document = tmp_path / entry
        document.parent.mkdir(parents=True, exist_ok=True)
        document.write_text(ENTRY_DOCUMENT, encoding="utf-8")
    return tmp_path


def _write_plugin(root: Path, manifest: dict) -> Path:
    plugin = root / str(manifest["name"])
    plugin.mkdir(parents=True, exist_ok=True)
    (plugin / "ui/index.html").parent.mkdir(parents=True, exist_ok=True)
    (plugin / "ui/index.html").write_text(ENTRY_DOCUMENT, encoding="utf-8")
    (plugin / MANIFEST_FILENAME).write_text(json.dumps(manifest), encoding="utf-8")
    return plugin


# The vocabulary: which names a manifest may use at all.


def test_the_vocabulary_is_pinned() -> None:
    assert UI_CAPABILITIES == frozenset(
        {
            "webgl",
            "wasm",
            "workers",
            "audio-out",
            "audio-in",
            "camera",
            "clipboard-read",
            "clipboard-write",
            "notifications",
            "fullscreen",
            "keyboard-capture",
            "file-save",
            "drag-drop",
            "dock-badge",
            "global-shortcut",
            "network",
        }
    ), "a vocabulary change is a contract change: Wave 1 reads these names"


def test_the_ui_axis_holds_no_file_or_process_family() -> None:
    # `network` is the one name on both axes; the eight file/process families stay
    # in permissions.tool_families, or two permission systems answer one question.
    assert UI_CAPABILITIES & KNOWN_TOOL_FAMILIES == {"network"}


def test_the_three_surface_types_are_named() -> None:
    assert UI_TYPES == frozenset({"floating-window", "dock-panel", "canvas-overlay"})
    assert REQUIRED_UI_FIELDS == ("type", "entry", "title")


def test_the_size_and_title_numbers_are_stated() -> None:
    assert (MAX_UI_DIMENSION, DEFAULT_UI_WIDTH, DEFAULT_UI_HEIGHT) == (4096, 480, 320)
    assert MAX_UI_TITLE_CHARS == 80


def test_every_capability_carries_a_layer_a_kind_and_a_grant_rule() -> None:
    assert set(UI_CAPABILITY_ENFORCEMENT) == set(UI_CAPABILITIES)
    for name, record in UI_CAPABILITY_ENFORCEMENT.items():
        assert record.layer.strip(), f"{name}: an empty enforcement layer is an empty promise"
        assert record.audit_kind == f"ui.{name}"
        assert type(record.enforced) is bool and type(record.grant) is bool


def test_the_enforcement_ratchet_is_empty_until_a_surface_can_be_confined() -> None:
    # A name may move to `enforced` only in the commit carrying that layer's own test.
    assert ENFORCED_CAPABILITIES == frozenset()
    assert set(unenforced_ui_capabilities()) == set(UI_CAPABILITIES)
    assert ENFORCED_CAPABILITIES <= UI_CAPABILITIES


def test_an_enforced_name_carries_a_witness_that_exists_on_disk() -> None:
    # The ratchet pairs every confinement claim with a witness: `observed_by` is the
    # repo-relative path of the test file watching that layer. An enforced name with
    # no witness, or with a witness that was never written, fails here — the honest
    # empty set above only pins today.
    for name, record in UI_CAPABILITY_ENFORCEMENT.items():
        if record.observed_by is not None:
            assert (ROOT / record.observed_by).is_file(), (
                f"{name}: observed_by names {record.observed_by!r}, a missing witness file"
            )
        if record.enforced:
            assert record.observed_by, (
                f"{name}: advertised as confined with no observing test to back it"
            )


def test_the_grant_list_holds_what_reaches_beyond_the_surface() -> None:
    assert GRANT_REQUIRED_CAPABILITIES <= UI_CAPABILITIES
    assert {"camera", "audio-in", "clipboard-read", "keyboard-capture", "global-shortcut"} \
        <= GRANT_REQUIRED_CAPABILITIES
    # Tier 1 has to cover the walking skeleton, so the widget's two names stay
    # declarable at install time.
    assert not {"notifications", "dock-badge"} & GRANT_REQUIRED_CAPABILITIES


# Default-deny: what the validator refuses before a surface is ever built.


def test_unknown_ui_capability_is_refused(tmp_path) -> None:
    surface = _surface(capabilities=["camera", "sudo"])
    err = validate_ui(_manifest(surface), _dir(tmp_path, surface["entry"]))
    assert err and "sudo" in err, "declared-but-unknown capabilities never run"


def test_an_undeclared_surface_gets_nothing(tmp_path) -> None:
    surface = _surface()
    del surface["capabilities"]
    manifest = _manifest(surface)
    assert validate_ui(manifest, _dir(tmp_path, surface["entry"])) is None
    assert ui_descriptor(manifest)["capabilities"] == []


@pytest.mark.parametrize("capability", ["notifications", "network"])
def test_a_capability_list_holds_names_only(tmp_path, capability) -> None:
    for value in (capability, [42]):
        surface = _surface(capabilities=value)
        err = validate_ui(_manifest(surface), _dir(tmp_path, surface["entry"]))
        assert err and "capabilities" in err


def test_a_capability_named_twice_is_two_declarations(tmp_path) -> None:
    surface = _surface(capabilities=["webgl", "webgl"])
    err = validate_ui(_manifest(surface), _dir(tmp_path, surface["entry"]))
    assert err and "duplicate" in err


def test_the_surface_is_one_descriptor(tmp_path) -> None:
    surface = [_surface(), _surface(type="dock-panel")]
    err = validate_ui(_manifest(surface), _dir(tmp_path))
    assert err and "object expected" in err


def test_the_capabilities_are_declared_on_the_descriptor(tmp_path) -> None:
    manifest = _manifest(_surface())
    manifest["permissions"]["ui"] = ["camera"]
    err = validate_ui(manifest, _dir(tmp_path))
    assert err and "permissions.ui" in err, "a key nothing reads would read as a grant"


# The entry point: one document, inside the plugin directory, shipped.


def test_entry_must_stay_inside_the_plugin_dir(tmp_path) -> None:
    surface = _surface(entry="../escape/index.html")
    err = validate_ui(_manifest(surface), _dir(tmp_path, "ui/index.html"))
    assert err and "entry" in err


def test_entry_must_not_be_absolute(tmp_path) -> None:
    surface = _surface(entry="/tmp/index.html")
    err = validate_ui(_manifest(surface), _dir(tmp_path))
    assert err and "entry" in err


def test_the_declared_entry_has_to_ship(tmp_path) -> None:
    surface = _surface(entry="ui/missing.html")
    err = validate_ui(_manifest(surface), _dir(tmp_path))
    assert err and "ui/missing.html" in err


def test_the_entry_is_an_html_document(tmp_path) -> None:
    surface = _surface(entry="ui/worker.js")
    err = validate_ui(_manifest(surface), _dir(tmp_path, "ui/worker.js"))
    assert err and ".html" in err


@pytest.mark.parametrize("field", REQUIRED_UI_FIELDS)
def test_the_required_fields_are_required(tmp_path, field) -> None:
    surface = _surface()
    surface.pop(field)
    err = validate_ui(_manifest(surface), _dir(tmp_path))
    assert err and field in err


@pytest.mark.parametrize("kind", ["dock_badge", "browser-tab", ""])
def test_the_type_is_one_of_three_names(tmp_path, kind) -> None:
    surface = _surface(type=kind)
    err = validate_ui(_manifest(surface), _dir(tmp_path, surface["entry"]))
    assert err and "type" in err


@pytest.mark.parametrize("title", ["", "   ", "x" * (MAX_UI_TITLE_CHARS + 1)])
def test_the_title_is_a_bounded_label(tmp_path, title) -> None:
    surface = _surface(title=title)
    err = validate_ui(_manifest(surface), _dir(tmp_path, surface["entry"]))
    assert err and "title" in err


def test_an_unknown_descriptor_field_is_refused(tmp_path) -> None:
    surface = _surface(role="widget")
    err = validate_ui(_manifest(surface), _dir(tmp_path, surface["entry"]))
    assert err and "role" in err


# Size and flags: the numbers and booleans a window builder reads.


@pytest.mark.parametrize(
    "size",
    [
        {"width": 0, "height": 320},
        {"width": -4, "height": 320},
        {"width": True, "height": 320},
        {"width": "480", "height": 320},
        {"width": 480.5, "height": 320},
        {"width": MAX_UI_DIMENSION + 1, "height": 320},
        {"width": 480, "height": MAX_UI_DIMENSION + 1},
        {"width": 480},
        {"height": 320},
        {"width": 480, "height": 320, "depth": 10},
    ],
)
def test_both_edges_are_positive_integers_under_the_cap(tmp_path, size) -> None:
    surface = _surface(default_size=size)
    err = validate_ui(_manifest(surface), _dir(tmp_path, surface["entry"]))
    assert err and "default_size" in err


def test_a_stated_size_is_kept(tmp_path) -> None:
    surface = _surface(default_size={"width": 640, "height": 480})
    manifest = _manifest(surface)
    assert validate_ui(manifest, _dir(tmp_path, surface["entry"])) is None
    described = ui_descriptor(manifest)
    assert (described["width"], described["height"]) == (640, 480)


@pytest.mark.parametrize("flag", ["transparent", "always_on_top"])
@pytest.mark.parametrize("value", ["yes", 1, 0, None])
def test_the_window_flags_are_booleans(tmp_path, flag, value) -> None:
    surface = _surface(**{flag: value})
    err = validate_ui(_manifest(surface), _dir(tmp_path, surface["entry"]))
    assert err and flag in err


def test_the_window_flags_are_accepted_as_booleans(tmp_path) -> None:
    surface = _surface(transparent=True, always_on_top=False)
    err = validate_ui(_manifest(surface), _dir(tmp_path, surface["entry"]))
    assert err is None


# The normalized view Wave 1 reads: `ui_descriptor`.


def test_a_countdown_widget_round_trips(tmp_path) -> None:
    surface = _surface(
        default_size={"width": 360, "height": 200},
        transparent=True,
        always_on_top=True,
        capabilities=["notifications", "dock-badge", "fullscreen"],
    )
    manifest = _manifest(surface)
    assert validate_ui(manifest, _dir(tmp_path, surface["entry"])) is None
    assert ui_descriptor(manifest) == {
        "plugin": "acme-countdown",
        "type": "floating-window",
        "entry": "ui/index.html",
        "title": "Countdown",
        "width": 360,
        "height": 200,
        "transparent": True,
        "always_on_top": True,
        "capabilities": ["dock-badge", "fullscreen", "notifications"],
        "grants": [],
    }, "the widget is tier 1: a manifest and no code permission"


def test_an_entry_is_normalized_to_one_relative_path(tmp_path) -> None:
    surface = _surface(entry="./ui/index.html")
    manifest = _manifest(surface)
    assert validate_ui(manifest, _dir(tmp_path)) is None
    assert ui_descriptor(manifest)["entry"] == "ui/index.html"


def test_defaults_fill_what_the_manifest_leaves_open(tmp_path) -> None:
    surface = _surface()
    del surface["capabilities"]
    described = ui_descriptor(_manifest(surface))
    assert (described["width"], described["height"]) == (DEFAULT_UI_WIDTH, DEFAULT_UI_HEIGHT)
    assert described["transparent"] is False and described["always_on_top"] is False


def test_a_manifest_without_a_surface_describes_nothing(tmp_path) -> None:
    manifest = _manifest(None)
    manifest["components"].pop("ui")
    assert validate_ui(manifest, tmp_path) is None
    assert ui_descriptor(manifest) == {}


def test_the_grant_list_is_derived_from_the_declaration(tmp_path) -> None:
    surface = _surface(capabilities=["camera", "notifications", "global-shortcut"])
    described = ui_descriptor(_manifest(surface))
    assert described["grants"] == ["camera", "global-shortcut"]


# The manifest gate: `load_manifest` is where these errors quarantine.


@pytest.mark.parametrize("manifest_version", [1, 2])
def test_the_surface_is_validated_in_both_manifest_versions(tmp_path, manifest_version) -> None:
    surface = _surface(capabilities=["notifications"])
    manifest = _manifest(surface, manifest_version=manifest_version)
    plugin = _write_plugin(tmp_path / f"v{manifest_version}", manifest)
    loaded, error = load_manifest(plugin)
    assert error is None and loaded is not None


def test_a_bad_surface_quarantines_the_plugin(tmp_path) -> None:
    manifest = _manifest(_surface(capabilities=["notifications", "sudo"]))
    loaded, error = load_manifest(_write_plugin(tmp_path, manifest))
    assert loaded is None
    assert error and "sudo" in error
