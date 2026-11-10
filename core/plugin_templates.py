"""Ephe — the template family a plugin is generated from.

core/plugin_templates.py

A template is a whole bundle as data: the manifest plus every file the manifest names,
rendered from parameters. The Creator's scaffold used to hard-code one shape — a
floating window with two assets and no tool — so any other ask was written file by file
by the model, and the live runs spent their budget on a contract they could not see
(run5). Here the bundle exists before a model touches it.

Four rules, and none of them is a convention:

- Manifest v2, fail-closed. Every rendered manifest goes through
  `core.plugin_manifest.load_manifest` before a byte is staged, so the loader that would
  quarantine it is the one that answers.
- Paths stay under the plugin folder. `render` refuses a key that is absolute, carries a
  backslash or steps out with `..`, and the contract runs its own containment on each
  entry a manifest declares.
- No imports. A contributed tool is a callable the confined worker runs, and nothing in
  this process imports a plugin (ruling A1); the sources carry no `import`.
- The network only with the `network` family. One template declares it, and it reaches
  the net through the bridge, which asks the mount's families at the call
  (`core/sandbox/bridge_host.py`). Nothing here asks for `shell`, `write` or a data root.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from string import Template

from core import plugin_manifest
from core.plugin_tools_contract import MAX_SERVED_NAME_CHARS

__all__ = [
    "DEFAULT_LICENSE",
    "DEFAULT_PUBLISHER",
    "DEFAULT_TEMPLATE",
    "DEFAULT_VERSION",
    "MANIFEST_FILENAME",
    "TEMPLATES",
    "PluginTemplate",
    "UnknownTemplate",
    "render",
    "tool_name_for",
]

MANIFEST_FILENAME = plugin_manifest.MANIFEST_FILENAME
DEFAULT_VERSION = "0.1.0"
DEFAULT_PUBLISHER = "Independent"
DEFAULT_LICENSE = "LicenseRef-proprietary"

SURFACE_ENTRY = "ui/index.html"
SURFACE_DIR = "ui"
TOOL_DIR = "tools"
README_FILENAME = "README.md"
DEFAULT_TEMPLATE = "surface"

#: The tool name a bundle name spells in the tool namespace: `sky-report` cannot be a
#: tool name, and `sky_report` is the served spelling of the same bundle.
_TOOL_NAME_NOISE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class PluginTemplate:
    """One shape of bundle and the manifest fields it decides.

    `families` is the whole `permissions.tool_families` list and `tool_family` the one
    family the shipped tool works in; the contract needs the second in the first, so both
    are stated here rather than derived at render time.
    """

    key: str
    label: str
    summary: str
    surface: bool
    tool_family: str
    families: tuple[str, ...]

    @property
    def ships_tool(self) -> bool:
        return bool(self.tool_family)


TEMPLATES: dict[str, PluginTemplate] = {
    "surface": PluginTemplate(
        key="surface", label="A window",
        summary="one floating window and its page, no tool",
        surface=True, tool_family="", families=(),
    ),
    "surface-tool": PluginTemplate(
        key="surface-tool", label="A window with a tool",
        summary="the same window plus one tool the agent can call (read family)",
        surface=True, tool_family="read", families=("read",),
    ),
    "tool": PluginTemplate(
        key="tool", label="A tool",
        summary="one tool the agent can call, no window (read family)",
        surface=False, tool_family="read", families=("read",),
    ),
    "network-tool": PluginTemplate(
        key="network-tool", label="A web tool",
        summary="one tool that reads the web through the host's bridge (network family)",
        surface=False, tool_family="network", families=("network",),
    ),
}


class UnknownTemplate(ValueError):
    """A template key this build does not ship, with the ones it does in the message."""


def tool_name_for(name: str) -> str:
    """The tool name a bundle name implies, in the spelling the namespace accepts."""
    slug = _TOOL_NAME_NOISE.sub("_", str(name or "").strip().lower()).strip("_")
    if not slug:
        return "run"
    if not slug[0].isalpha():
        slug = f"run_{slug}"
    return slug[:MAX_SERVED_NAME_CHARS]


def _template(key: str) -> PluginTemplate:
    template = TEMPLATES.get(str(key or ""))
    if template is not None:
        return template
    raise UnknownTemplate(
        f"{key!r} is not a template this build ships; it has "
        + ", ".join(TEMPLATES)
        + " — pick the one whose shape matches the ask"
    )


def _relative_path_error(relative: str) -> str:
    """Why this key cannot be a file inside a bundle, or "" when it can be one."""
    text = str(relative or "")
    if not text or "\\" in text or ":" in text:
        return "a template names one relative posix path"
    path = PurePosixPath(text)
    if path.is_absolute() or ".." in path.parts:
        return "a template path stays inside the plugin folder"
    return ""


#: The manifest skeleton: only fields the contract's `KNOWN_MANIFEST_FIELDS` holds.
def _manifest(
    template: PluginTemplate,
    *,
    name: str,
    description: str,
    publisher: str,
    license_id: str,
    title: str,
    tool: str,
) -> dict:
    manifest: dict = {
        "manifest_version": plugin_manifest.MANIFEST_VERSION_V2,
        "name": name,
        "version": DEFAULT_VERSION,
        "description": description,
        "publisher": {"name": publisher or DEFAULT_PUBLISHER},
        "license": license_id or DEFAULT_LICENSE,
        "permissions": {"tool_families": list(template.families), "data_roots": []},
        "components": {"tools": []},
        "changelog": (
            f"{DEFAULT_VERSION} - the first draft, generated from the "
            f"{template.key} template."
        ),
    }
    if template.surface:
        manifest["components"]["ui"] = {
            "type": "floating-window",
            "entry": SURFACE_ENTRY,
            "title": title or name,
            "default_size": {"width": 320, "height": 200},
        }
    if template.ships_tool:
        manifest["components"]["tools"] = [_tool_entry(template, tool)]
    return manifest


def _tool_entry(template: PluginTemplate, tool: str) -> dict:
    """The one declared tool: what it answers to, the file that carries it, its family."""
    if template.tool_family == "network":
        description = "Reads one web address through the host's guarded reader."
        parameters = {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The address to read."}
            },
            "required": ["url"],
        }
    else:
        description = "Echoes the text it is given back to the caller."
        parameters = {
            "type": "object",
            "properties": {
                "input": {"type": "string", "description": "The text to echo."}
            },
        }
    return {
        "name": tool,
        "entry": f"{TOOL_DIR}/{tool}.py:run",
        "family": template.tool_family,
        "description": description,
        "parameters": parameters,
    }


_SURFACE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width">
<link rel="stylesheet" href="app.css">
<title>$title</title>
</head>
<body>
<main id="app"><p data-role="line">$bundle is ready.</p></main>
<script src="ephe.js"></script>
<script type="module" src="app.js"></script>
</body>
</html>
"""

_SURFACE_CSS = (
    ":root { color-scheme: light dark; font: 14px/1.4 system-ui; }"
    "\n#app { display: grid; gap: 8px; padding: 12px; }\n"
)

#: The page's own script. A comment that spelled the SDK call out would make an empty
#: scaffold pass the `state_bridge_used` check (the grader reads source text), so the
#: note points at the bridge without naming the call: a bundle has to make it.
_SURFACE_JS = (
    "// ephe.js is served by the mount; keep state on the storage bridge it exposes.\n"
    'export const role = "line";\n'
)

_READ_TOOL_PY = '''"""The one tool this bundle serves: `$tool`.

The worker calls this function with the call arguments and this bundle's own state
folder. Nothing is imported here: the worker has no application module, and the `read`
family in the manifest is what the host checks before it lets the call run.
"""


def run(arguments, state_dir):
    request = arguments or {}
    return {
        "tool": "$tool",
        "argument_keys": sorted(str(key) for key in request),
        "echo": str(request.get("input") or ""),
    }
'''

_NETWORK_TOOL_PY = '''"""The one tool this bundle serves: `$tool`.

The worker has no network of its own. The third argument is the host's bridge, and a
`fetch` on it is answered only because the manifest declares the `network` family and
this tool works in it; a bundle that asked for another family gets
`bridge_method_denied` instead.
"""


def run(arguments, state_dir, bridge):
    request = arguments or {}
    url = str(request.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "url is required"}
    page = bridge.fetch(url)
    body = str(page.get("text") or "")
    return {
        "ok": True,
        "url": url,
        "chars": len(body),
        "truncated": bool(page.get("truncated")),
    }
'''

_README = """# $bundle

$description

Generated by Ephe from the `$key` template — $summary.

Nothing here was written by hand: edit the files, then `verify_plugin_bundle` and
`install_plugin_bundle` in Creator mode.

## What ships

$files

## What it asks for

| | |
|---|---|
| `permissions.tool_families` | $families |
| `permissions.data_roots` | none |
| Components | $components |

A family is a request the host answers at the call: the `network` tool reaches the web
through the bridge handle only, and no template asks for `shell` or `write`.

## Changing it

- The surface is $entry, and every file it names stays inside this folder.
- The page SDK arrives as `ephe.js` from the mount; this folder never ships a copy.
  Keep state on `ephe.storage.get` / `ephe.storage.set`.
- A tool is one Python callable declared in `components.tools`, and it imports nothing.
"""


def _readme(
    template: PluginTemplate,
    files: dict[str, str],
    *,
    name: str,
    description: str,
    tool: str,
) -> str:
    listed = "\n".join(f"- `{relative}`" for relative in files)
    components = [template.label]
    if template.ships_tool:
        components.append(f"the tool `{tool}`")
    return Template(_README).substitute(
        bundle=name,
        description=description,
        key=template.key,
        summary=template.summary,
        files=listed,
        families=", ".join(f"`{family}`" for family in template.families) or "none",
        components=", ".join(components),
        entry=f"`{SURFACE_ENTRY}`" if template.surface else "none — this bundle ships no window",
    )


def render(
    key: str,
    *,
    name: str,
    description: str,
    publisher: str = "",
    license: str = "",
    title: str = "",
    tool: str = "",
) -> dict[str, str]:
    """Every file of one bundle, by relative path, from these parameters.

    The manifest is rendered last so it reads the same `title` and `tool` the files do;
    a name the loader would refuse is not this function's to judge, because the loader's
    own words are what the caller reports. `UnknownTemplate` is the one refusal here.
    """
    template = _template(key)
    tool_name = str(tool or tool_name_for(name))
    surface_title = html.escape(str(title or name), quote=False)
    files: dict[str, str] = {}
    if template.surface:
        files[f"{SURFACE_DIR}/index.html"] = Template(_SURFACE_HTML).substitute(
            title=surface_title, bundle=html.escape(str(name), quote=False)
        )
        files[f"{SURFACE_DIR}/app.css"] = _SURFACE_CSS
        files[f"{SURFACE_DIR}/app.js"] = _SURFACE_JS
    if template.ships_tool:
        source = _NETWORK_TOOL_PY if template.tool_family == "network" else _READ_TOOL_PY
        files[f"{TOOL_DIR}/{tool_name}.py"] = Template(source).substitute(tool=tool_name)
    for relative in files:
        error = _relative_path_error(relative)
        if error:
            raise ValueError(f"{relative!r}: {error}")
    files[README_FILENAME] = _readme(
        template,
        files,
        name=str(name),
        description=str(description),
        tool=tool_name,
    )
    manifest = _manifest(
        template,
        name=str(name),
        description=str(description),
        publisher=str(publisher),
        license_id=str(license),
        title=str(title),
        tool=tool_name,
    )
    rendered = {MANIFEST_FILENAME: json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"}
    rendered.update(files)
    return rendered


def template_choices() -> str:
    """One sentence naming every template, for a tool description that cannot drift."""
    return "; ".join(f"{template.key} = {template.summary}" for template in TEMPLATES.values())
