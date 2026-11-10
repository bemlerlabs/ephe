"""The template family a plugin is generated from, read as bytes rather than promises.

Every rule the module states is checked here on the rendered files: the manifest goes
through the loader the install path uses, a shipped path stays inside the bundle, a
Python entry imports nothing, and the `network` family appears in exactly the one
template that reaches the net. The tests call the renderer the Creator tool calls, so a
template that changed shape without this file changing would be a red run.
"""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath

import pytest

from core import plugin_manifest, plugin_templates
from core.plugin_tools_contract import declared_families, tool_claims

KEYS = sorted(plugin_templates.TEMPLATES)

#: A real ask, used for every render below so a failure names the template.
PARAMS = {
    "name": "weather-card",
    "description": "Shows the sky over one town.",
    "publisher": "Independent",
    "title": "Weather card",
}

_IMPORT_STATEMENT = re.compile(r"(?m)^\s*(?:import\s+[A-Za-z_]" r"|from\s+[A-Za-z_.]+\s+import\b)")


def _files(key: str, **overrides) -> dict[str, str]:
    return plugin_templates.render(key, **{**PARAMS, **overrides})


def _write(files: dict[str, str], bundle: Path) -> Path:
    for relative, text in files.items():
        target = bundle / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return bundle


def test_the_family_covers_the_shapes_a_bundle_can_take() -> None:
    """A window, a window with a tool, a tool alone, a tool that reads the web."""
    assert KEYS == ["network-tool", "surface", "surface-tool", "tool"]
    assert plugin_templates.DEFAULT_TEMPLATE == "surface"
    shapes = {
        key: (template.surface, template.tool_family)
        for key, template in plugin_templates.TEMPLATES.items()
    }
    assert shapes == {
        "surface": (True, ""),
        "surface-tool": (True, "read"),
        "tool": (False, "read"),
        "network-tool": (False, "network"),
    }


@pytest.mark.parametrize("key", KEYS)
def test_every_template_renders_a_manifest_the_loader_accepts(key: str, tmp_path: Path) -> None:
    bundle = _write(_files(key), tmp_path / PARAMS["name"])
    manifest, error = plugin_manifest.load_manifest(bundle)
    assert error is None, error
    assert manifest["manifest_version"] == plugin_manifest.MANIFEST_VERSION_V2


@pytest.mark.parametrize("key", KEYS)
def test_every_path_a_template_ships_stays_under_the_plugin_folder(key: str) -> None:
    for relative in _files(key):
        assert relative and "\\" not in relative, relative
        path = PurePosixPath(relative)
        assert not path.is_absolute(), relative
        assert ".." not in path.parts, relative


@pytest.mark.parametrize("key", KEYS)
def test_every_entry_the_manifest_declares_is_a_file_the_template_ships(key: str) -> None:
    files = _files(key)
    manifest = json.loads(files["ephe-plugin.json"])
    surface = manifest["components"].get("ui")
    if surface is not None:
        assert surface["entry"] in files, surface["entry"]
    for tool in manifest["components"].get("tools", []):
        assert tool["entry"].split(":")[0] in files, tool["entry"]


@pytest.mark.parametrize("key", KEYS)
def test_every_template_ships_a_readme_that_names_the_bundle(key: str) -> None:
    readme = _files(key)["README.md"]
    assert PARAMS["name"] in readme
    assert f"`{key}`" in readme
    assert PARAMS["description"] in readme


@pytest.mark.parametrize("key", KEYS)
def test_no_template_ships_a_python_file_that_imports(key: str) -> None:
    """Ruling A1: nothing in this process imports a plugin, and the entry reaches nothing.

    A scaffolded tool runs in the confined worker, which has no application module to
    import; a source that carries `import` would fail at the call rather than at the
    scaffold. The renderer is where that is cheap to refuse.
    """
    for relative, text in _files(key).items():
        if not relative.endswith(".py"):
            continue
        assert _IMPORT_STATEMENT.search(text) is None, f"{relative} imports a module"
        assert "__import__" not in text, relative
        assert "importlib" not in text, relative


@pytest.mark.parametrize("key", KEYS)
def test_no_template_asks_for_shell_write_or_a_data_root(key: str) -> None:
    families = set(plugin_templates.TEMPLATES[key].families)
    assert families <= {"read", "network"}, families
    manifest = json.loads(_files(key)["ephe-plugin.json"])
    assert manifest["permissions"]["data_roots"] == []
    assert manifest["permissions"]["tool_families"] == list(
        plugin_templates.TEMPLATES[key].families
    )


def test_only_the_network_template_asks_for_the_network_family() -> None:
    asking = {
        key
        for key, template in plugin_templates.TEMPLATES.items()
        if "network" in template.families
    }
    assert asking == {"network-tool"}


def test_the_network_template_reaches_the_host_through_the_bridge_alone() -> None:
    """The family is what the bridge asks at the call, so the body names no other way out."""
    files = _files("network-tool")
    source = next(text for relative, text in files.items() if relative.endswith(".py"))
    assert "bridge.fetch(" in source
    for primitive in ("socket.", "urllib.", "http.client", "requests."):
        assert primitive not in source, primitive
    for key in set(KEYS) - {"network-tool"}:
        for text in _files(key).values():
            assert "bridge.fetch(" not in text, key


@pytest.mark.parametrize("key", KEYS)
def test_every_family_a_tool_declares_is_one_the_bundle_asks_for(key: str) -> None:
    manifest = json.loads(_files(key, tool="sky_read")["ephe-plugin.json"])
    declared = declared_families(manifest)
    assert declared <= plugin_manifest.KNOWN_TOOL_FAMILIES
    claims = tool_claims(manifest)
    assert [claim.family for claim in claims if claim.contributed] == (
        [plugin_templates.TEMPLATES[key].tool_family]
        if plugin_templates.TEMPLATES[key].tool_family
        else []
    )
    for claim in claims:
        assert claim.family in declared


def test_the_same_parameters_render_the_same_bytes() -> None:
    assert _files("surface") == _files("surface")


def test_an_unknown_template_is_refused_with_the_ones_that_exist() -> None:
    with pytest.raises(plugin_templates.UnknownTemplate) as raised:
        plugin_templates.render("holo-deck", **PARAMS)
    message = str(raised.value)
    for key in KEYS:
        assert key in message, message


def test_a_title_reaches_the_page_as_text_and_not_as_markup() -> None:
    files = _files("surface", title="<script>alert(1)</script>")
    document = files["ui/index.html"]
    assert "<script>alert(1)</script>" not in document
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in document


def test_the_tool_name_follows_the_bundle_name_in_the_served_spelling() -> None:
    """`sky-report` cannot be a tool name, so the template spells the served one."""
    manifest = json.loads(_files("tool", name="sky-report")["ephe-plugin.json"])
    assert [claim.name for claim in tool_claims(manifest)] == ["sky_report"]
