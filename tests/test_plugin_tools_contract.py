"""TCT-01..09 — `components.tools` as declared entries, and the name each one serves.

Two shapes are pinned here: what one `components.tools` entry has to look like before a
bundle is accepted, and what string the runtime serves it under. They are the same claim
read twice — the entry that passes validation is the entry the confined worker resolves
(#9), and the name the manifest derives is the name the gate (#11) reads off the scan — so
neither layer is left guessing what the other meant, and a bundle that validates is a
bundle that can mount.

The refusals are the contract: a field this contract does not carry, a suffix outside the
tool-name charset, an entry that leaves the plugin directory or names something other than
a Python file or carries no callable, a family the manifest did not ask for, a name
declared twice in one manifest, a derived name that collides with another plugin's, and a
version-2 manifest that still lists bare kernel tool names. web-research serves its
two names from the worker. The last test pins a clean scan and that those two names
left the kernel map.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import plugin_manifest, plugin_runtime
from core.plugin_manifest import MANIFEST_FILENAME, load_manifest
from core.plugin_registry import (
    CapabilityKind,
    PluginRegistry,
    RegistryError,
    load_tool_activations,
    scan_tool_activations,
)
from core.plugin_tools_contract import (
    MAX_SERVED_NAME_CHARS,
    descriptors_for,
    reserved_namespace,
    tool_claims,
)
from core.tools.dynamic_registry import (
    COLLISION_KERNEL,
    TRANSPORT_PLUGIN,
    default_registry,
    fingerprint_for,
    served_tool_name,
)


def _tool(**over) -> dict:
    """The smallest entry a version-2 manifest accepts."""
    tool = {
        "name": "tick",
        "entry": "handlers.py:run",
        "family": "read",
        "description": "Report how many seconds are left.",
    }
    tool.update(over)
    return tool


def _manifest(
    name: str,
    *,
    version: int = 2,
    tools: list = (),
    families: tuple[str, ...] = ("read",),
) -> dict:
    manifest = {
        "manifest_version": version,
        "name": name,
        "version": "1.0.0",
        "description": f"The {name} bundle.",
        "permissions": {"tool_families": list(families), "data_roots": []},
        "components": {"skills": [], "commands": [], "tools": list(tools)},
    }
    if version == 2:
        manifest["publisher"] = {"name": "Ephe"}
        manifest["license"] = "MIT"
    return manifest


def _write(root: Path, manifest: dict) -> Path:
    """The plugin directory, with the manifest and the files its entries point at."""
    plugin_dir = root / str(manifest["name"])
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / MANIFEST_FILENAME).write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    for tool in manifest.get("components", {}).get("tools", []) or []:
        if isinstance(tool, dict):
            _ship(plugin_dir, str(tool.get("entry") or ""))
    return plugin_dir


def _ship(plugin_dir: Path, entry: str) -> None:
    """Write the file one declared entry points at, when the entry stays inside."""
    path_part, sep, callable_name = entry.rpartition(":")
    if not sep or not path_part or not callable_name.isidentifier():
        return
    target = _inside(plugin_dir, path_part)
    if target is None:
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"def {callable_name}(arguments, state_dir):\n"
        "    return {'arguments': arguments}\n",
        encoding="utf-8",
    )


def _inside(plugin_dir: Path, relative: str) -> Path | None:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        return None
    return plugin_dir / candidate


def _lane(tmp_path: Path, monkeypatch) -> Path:
    """A plugins root and a config dir the runtime gate reads instead of the tree."""
    root = tmp_path / "plugins"
    root.mkdir(parents=True, exist_ok=True)
    (tmp_path / "cfg").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("EPHE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setattr(plugin_manifest, "PLUGINS_ROOT_OVERRIDE", root)
    plugin_runtime.invalidate_ownership_cache()
    return root


def _disable(config_dir: Path, plugin_id: str) -> None:
    from core.plugin_lifecycle import STATE_FILENAME, PluginLifecycle

    PluginLifecycle(
        config_dir / STATE_FILENAME, versions=plugin_runtime._installed_versions()
    ).set_enabled(plugin_id, False)


def _holds_a_callable(value) -> bool:
    if callable(value):
        return True
    if isinstance(value, dict):
        return any(_holds_a_callable(item) for item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_holds_a_callable(item) for item in value)
    return False


def test_a_version_1_manifest_still_declares_kernel_tool_names(tmp_path) -> None:
    _write(tmp_path, _manifest("legacy", version=1, tools=["read_file"]))
    manifest, error = load_manifest(tmp_path / "legacy")
    assert error is None and manifest is not None
    claims = tool_claims(manifest)
    assert [(claim.name, claim.contributed) for claim in claims] == [
        ("read_file", False)
    ]
    scanned = scan_tool_activations(tmp_path)
    assert scanned.owners == (("read_file", "legacy"),)
    assert scanned.conflicts == ()
    assert scanned.contributed == ()


def test_a_version_2_manifest_refuses_a_bare_kernel_tool_name(tmp_path) -> None:
    _write(tmp_path, _manifest("modern", tools=["read_file"]))
    manifest, error = load_manifest(tmp_path / "modern")
    assert manifest is None, "v2 declares an entry, not a name out of the kernel map"
    assert error is not None and "components.tools" in error


def test_a_version_1_manifest_refuses_an_entry_object(tmp_path) -> None:
    """The two shapes are a function of the version, so no bundle sits half in each."""
    _write(tmp_path, _manifest("legacy", version=1, tools=[_tool()]))
    manifest, error = load_manifest(tmp_path / "legacy")
    assert manifest is None
    assert error is not None and "components.tools" in error


@pytest.mark.parametrize(
    ("tool", "needle"),
    [
        ({**_tool(), "runtime": "python"}, "unknown field"),
        (_tool(name="Tick"), "tool name"),
        (_tool(name="1tick"), "tool name"),
        (_tool(name="tick-run"), "tool name"),
        (_tool(name=""), "tool name"),
        (_tool(entry="/tmp/handlers.py:run"), "relative"),
        (_tool(entry="../outside.py:run"), "outside the plugin directory"),
        (_tool(entry="handlers.js:run"), ".py"),
        (_tool(entry="handlers"), "callable"),
        (_tool(entry="handlers.py:"), "callable"),
        (_tool(entry="handlers.py:run(x)"), "callable"),
        (_tool(entry="my-tools/handlers.py:run"), "module path"),
        (_tool(family="teleport"), "family"),
        (_tool(description="   "), "description"),
        (_tool(parameters=[]), "parameters"),
    ],
)
def test_one_bad_entry_quarantines_the_whole_bundle(tmp_path, tool, needle) -> None:
    _write(tmp_path, _manifest("acme", tools=[tool]))
    manifest, error = load_manifest(tmp_path / "acme")
    assert manifest is None, "a declared tool is accepted whole or not at all"
    assert error is not None and needle in error, error


def test_one_manifest_cannot_declare_the_same_tool_twice(tmp_path) -> None:
    _write(
        tmp_path,
        _manifest("acme", tools=[_tool(), _tool(description="A second declaration.")]),
    )
    manifest, error = load_manifest(tmp_path / "acme")
    assert manifest is None
    assert error is not None and "duplicate" in error


def test_the_family_a_tool_declares_is_the_family_the_manifest_asks_for(tmp_path) -> None:
    """#11 refuses an undeclared family at the call; validation refuses the bundle.

    One rule answered where the fact is readable, so no plugin installs into a state in
    which every call it could make is refused.
    """
    _write(tmp_path, _manifest("acme", tools=[_tool(family="write")], families=["read"]))
    manifest, error = load_manifest(tmp_path / "acme")
    assert manifest is None
    assert error is not None and "permissions.tool_families" in error


def test_a_declared_name_past_the_ceiling_is_refused(tmp_path) -> None:
    """The ceiling is a property of the name the bundle wrote, not of a built string."""
    long_name = "t" * (MAX_SERVED_NAME_CHARS + 1)
    _write(tmp_path, _manifest("acme", tools=[_tool(name=long_name)]))
    manifest, error = load_manifest(tmp_path / "acme")
    assert manifest is None
    assert error is not None and str(MAX_SERVED_NAME_CHARS) in error


def test_the_served_name_is_the_name_the_manifest_declares() -> None:
    """#98: the package carries the namespace, the tool keeps the name the model knows.

    This is what turns the flagship migration from a rename into a swap. `web_search` is
    what prompts, tool cards and saved sessions already say, and a bundle that takes over
    that capability serves the same string from the other side of the boundary.
    """
    assert served_tool_name("web-research", "web_search") == "web_search"
    assert served_tool_name("timer-lite", "x") == "x"
    assert served_tool_name("timer", "lite_x") == "lite_x"
    # The pair the derived form used to collapse into one string are two names again.
    assert served_tool_name("timer-lite", "x") != served_tool_name("timer", "lite_x")


def test_two_plugins_declaring_one_name_are_contested_for_both(tmp_path, monkeypatch) -> None:
    """The guard the prefix was believed to be needed for, tested as the rule itself.

    Nothing about the name tells who owns it, so the scan reads the portfolio: two
    declarations of `tick` make the name contested, both plugins lose it, and the reason
    names both of them. A load raises rather than picking a winner.
    """
    root = _lane(tmp_path, monkeypatch)
    _write(root, _manifest("timer", tools=[_tool(name="tick")]))
    _write(root, _manifest("timer-lite", tools=[_tool(name="tick")]))

    scanned = scan_tool_activations(root)
    assert scanned.conflicts == ("tick",)
    reason = scanned.reason_for("tick")
    assert "'timer' declares 'tick'" in reason
    assert "'timer-lite' declares 'tick'" in reason
    assert plugin_runtime.is_tool_visible("tick") is False, "hidden from both"
    with pytest.raises(RegistryError) as err:
        load_tool_activations(root)
    assert err.value.code == "duplicate_tool_activation"
    assert "tick" in err.value.detail and "timer-lite" in err.value.detail


def test_a_lone_claimant_serves_the_name_it_declared(tmp_path, monkeypatch) -> None:
    root = _lane(tmp_path, monkeypatch)
    _write(root, _manifest("timer-lite", tools=[_tool(name="x")]))
    scanned = scan_tool_activations(root)
    assert scanned.conflicts == ()
    assert scanned.owners == (("x", "timer-lite"),)
    assert plugin_runtime.is_tool_visible("x") is True


def test_a_name_the_kernel_holds_is_refused_at_the_mount(tmp_path, monkeypatch) -> None:
    """The other half of the guarantee: a bundle cannot take a live kernel name.

    `delete_file` stays on the kernel map, so declaring it is refused with the
    reserved-namespace code. `read_file` left that map with the shell bundle.
    """
    from core.plugin_lifecycle_types import LifecycleError
    from core.plugin_mount_trust import refuse_contested_names

    assert reserved_namespace("web_search") == ""
    assert reserved_namespace("fetch_url") == ""
    assert reserved_namespace("read_file") == ""
    assert reserved_namespace("run_shell") == ""
    assert reserved_namespace("delete_file") == "reserved_kernel"
    batch = descriptors_for(_manifest("acme", tools=[_tool(name="delete_file")]))
    with pytest.raises(LifecycleError) as err:
        refuse_contested_names("acme", batch)
    assert "reserved_kernel" in str(err.value) or err.value.data is not None


def test_the_scan_owns_a_contributed_name_and_its_switch(tmp_path, monkeypatch) -> None:
    root = _lane(tmp_path, monkeypatch)
    _write(root, _manifest("acme", tools=[_tool()]))
    served = served_tool_name("acme", "tick")

    scanned = scan_tool_activations(root)
    assert scanned.owners == ((served, "acme"),)
    assert scanned.contributed == (served,)
    assert plugin_runtime.is_tool_visible(served) is True

    _disable(tmp_path / "cfg", "acme")
    gate = plugin_runtime.tool_gate(served)
    assert gate.visible is False and gate.plugin == "acme"


def test_a_valid_bundle_yields_descriptors_the_registry_can_mount(tmp_path) -> None:
    _write(
        tmp_path,
        _manifest(
            "acme",
            tools=[
                _tool(),
                _tool(name="tock", entry="tools/tock.py:run", family="network"),
            ],
            families=("read", "network"),
        ),
    )
    manifest, error = load_manifest(tmp_path / "acme")
    assert error is None and manifest is not None

    batch = descriptors_for(manifest)
    assert [descriptor.name for descriptor in batch] == ["tick", "tock"]
    assert [descriptor.entry for descriptor in batch] == ["handlers:run", "tools.tock:run"]
    assert [descriptor.tool_family for descriptor in batch] == ["read", "network"]
    for descriptor in batch:
        assert descriptor.transport == TRANSPORT_PLUGIN
        assert descriptor.plugin_id == "acme"
        assert descriptor.fingerprint == fingerprint_for(descriptor.schema)
        assert not _holds_a_callable(descriptor.__dict__), "ruling A1: no plugin callable"

    registry = default_registry()
    outcome = registry.replace_for_plugin("acme", batch)
    assert outcome.ok is True, outcome
    assert {"tick", "tock"} <= set(registry.names())
    assert registry.unregister_plugin("acme") == 2
    assert not {"tick", "tock"} & set(registry.names())


def test_the_declared_path_is_the_module_the_confined_worker_resolves(tmp_path) -> None:
    from core.sandbox.runner import resolve_entry_file

    plugin_dir = _write(
        tmp_path,
        _manifest("acme", tools=[_tool(name="tock", entry="tools/tock.py:run")]),
    )
    manifest, error = load_manifest(plugin_dir)
    assert error is None and manifest is not None

    descriptor = descriptors_for(manifest)[0]
    assert descriptor.entry == "tools.tock:run"
    target, resolution_error = resolve_entry_file(plugin_dir, descriptor.entry)
    assert resolution_error == ""
    assert target == (plugin_dir / "tools" / "tock.py").resolve()


def test_a_served_name_never_steps_into_the_kernel_or_mcp_namespace() -> None:
    """The reserved map is read from the live kernel, and `plugin_manager` is in it.

    The second line is the one that matters since #98: a plain declared name is not
    reserved merely because it is plain, so the guard refuses the collision and nothing
    else. `acme`'s `tick` is free; the kernel's `plugin_manager` is not.
    """
    assert reserved_namespace("plugin_manager") == COLLISION_KERNEL
    assert reserved_namespace(served_tool_name("acme", "tick")) == ""


def test_a_contributed_name_is_a_capability_of_its_own_plugin(tmp_path, monkeypatch) -> None:
    root = _lane(tmp_path, monkeypatch)
    _write(root, _manifest("acme", tools=[_tool()]))
    registry = PluginRegistry.load(root, ROOT / "skills")
    served = served_tool_name("acme", "tick")

    assert registry.owner_of(f"tool:{served}") == "acme"
    assert [row.name for row in registry.capabilities(CapabilityKind.PLUGIN_TOOL)] == [
        served
    ]
    assert registry.activation_owner(served) == "acme"


def test_a_declared_tool_is_granted_by_the_manifest_that_declares_it(tmp_path, monkeypatch) -> None:
    """The family gate now reads a declaration off the bundle that carries it.

    Before #13 a contributed name had no manifest behind it, so #11's gate could only
    withhold: it asked about the call and refused it in a read-only mode. A declared
    family is a fact the gate can read now, so both answers turn on.
    """
    from core.tools import dynamic_gate

    root = _lane(tmp_path, monkeypatch)
    _write(root, _manifest("acme", tools=[_tool()]))
    manifest, error = load_manifest(root / "acme")
    assert error is None and manifest is not None
    descriptor = descriptors_for(manifest)[0]
    assert default_registry().replace_for_plugin("acme", (descriptor,)).ok
    try:
        assert dynamic_gate.declares_family("acme", "read") is True
        assert dynamic_gate.permission_denial(descriptor.name, {}) is None
        assert dynamic_gate.runs_read_only(descriptor.name) is True
    finally:
        default_registry().unregister_plugin("acme")


def test_the_shipped_bundles_still_scan_clean() -> None:
    from core.tools.registry import TOOL_MAP, addressable_tool_names

    scanned = scan_tool_activations(ROOT / "plugins")
    assert scanned.conflicts == ()
    assert scanned.contributed == (
        "analyze_image", "analyze_project",
        "browser_click", "browser_evaluate", "browser_exec", "browser_go",
        "browser_press", "browser_screenshot", "browser_scroll", "browser_type",
        "build_document", "create_diagram", "create_docx", "create_pdf",
        "create_pitch_deck", "create_pptx_deck", "create_qrcode",
        "create_source_notebook", "create_svg", "create_xlsx", "edit_file",
        "edit_pptx_template", "export_source_brief",
        "extract_pdf_text", "fetch_url", "file_search", "format_code",
        "generate_chart", "generate_image", "inspect_pptx_template",
        "list_directory", "load_workspace",
        "memory", "qa_pptx_deck", "query_source_notebook",
        "read_file", "run_linter", "run_shell", "run_tests", "scaffold_project",
        "synthesize", "transcribe",
        "verify_artifact", "vision_click", "vision_type", "web_search",
        "write_file",
    )
    assert len(scanned.owners) == 47
    kernel = [name for name, _owner in scanned.owners if name not in scanned.contributed]
    assert all(name in TOOL_MAP for name in kernel)
    assert "web_search" not in TOOL_MAP and "fetch_url" not in TOOL_MAP
    assert "memory" not in TOOL_MAP
    assert "browser_go" not in TOOL_MAP and "browser_exec" not in TOOL_MAP
    assert "vision_click" not in TOOL_MAP and "vision_type" not in TOOL_MAP
    assert "analyze_image" not in TOOL_MAP
    assert "run_shell" not in TOOL_MAP and "read_file" not in TOOL_MAP
    assert "write_file" not in TOOL_MAP and "edit_file" not in TOOL_MAP
    assert "run_tests" not in TOOL_MAP and "format_code" not in TOOL_MAP
    assert "create_pdf" not in TOOL_MAP and "create_docx" not in TOOL_MAP
    assert "verify_artifact" not in TOOL_MAP and "extract_pdf_text" not in TOOL_MAP
    assert "create_xlsx" not in TOOL_MAP and "generate_chart" not in TOOL_MAP
    assert "create_pptx_deck" not in TOOL_MAP and "create_pitch_deck" not in TOOL_MAP
    assert "create_diagram" not in TOOL_MAP and "create_svg" not in TOOL_MAP
    assert "generate_image" not in TOOL_MAP
    assert "synthesize" not in TOOL_MAP and "transcribe" not in TOOL_MAP
    assert "qa_pptx_deck" not in TOOL_MAP and "edit_pptx_template" not in TOOL_MAP
    addressable = addressable_tool_names()
    assert {
        "web_search", "fetch_url", "memory", "browser_go", "browser_exec",
        "vision_click", "vision_type", "analyze_image", "read_file",
        "generate_image", "synthesize", "transcribe",
    } <= addressable
