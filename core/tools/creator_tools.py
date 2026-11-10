"""Ephe — Creator Mode's bundle authoring tools (Creator wave 0).
core/tools/creator_tools.py

Each call answers against a contract the platform already owns:

- `create_plugin_scaffold` composes a declarative Manifest v2 bundle in a temporary
  directory and keeps it only when `core.plugin_manifest.load_manifest` reads it without
  an error, so staging cannot accumulate a folder the scanner would quarantine.
- `read_plugin_source` hands back one file of one staged bundle. The staged folder lives
  under the device root, which `core/path_guard.py` denies to the general file tools, so
  this is the only way the author can see what it is about to replace.
- `write_plugin_source` puts one file inside one staged bundle. The path is checked
  against the bundle's real path before a byte is written.
- `verify_plugin_bundle` carries the loader's own error, the confined worker's answer
  about each declared entry (`core.sandbox.runner.resolve_entry_file`), and the two name
  guards the mount applies (`default_reserved_names`, the activation scan).
- `install_plugin_bundle` packs the staged bytes as a `local` artifact and hands them to
  `core.plugin_install.install_from_marketplace` — the one path a directory takes to
  becoming loadable — so hash, extraction, validation, rollback and the audit row stay in
  that function. The bundle lands unsigned and is trusted by the person who wrote it.

A scaffolded bundle declares no tool: `components.tools` is the code escalation the two-
tier contract puts behind an explicit approval, so the first bundle is a surface.
"""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from core import plugin_manifest
from core.engine_config import config_root
from core.plugin_install import install_from_marketplace
from core.plugin_store import sha256_hex
from core.plugin_tools_contract import reserved_namespace, tool_claims
from core.tools.base import MAX_FILE_CHARS

STAGING_DIRNAME = "creator"
DEFAULT_PUBLISHER = "Independent"
DEFAULT_LICENSE = "LicenseRef-proprietary"
_DEFAULT_VERSION = "0.1.0"


#: The staging folder a creator authors in: `<device>/creator/plugins/<bundle>`. The
#: `plugins` segment is what the definition-of-done layout expects, so a staged tree can
#: be read by the same code that reads an installed one.
def bundles_root(config: Path | str | None = None) -> Path:
    root = Path(config) if config is not None else config_root()
    staging = root / STAGING_DIRNAME / plugin_manifest.PLUGINS_DIRNAME
    staging.mkdir(parents=True, exist_ok=True)
    return staging


def bundle_dir(name: str, config: Path | str | None = None) -> Path:
    return bundles_root(config) / str(name)


def _answer(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _refusal(code: str, detail: str, **extra: Any) -> str:
    return _answer({"error": code, "detail": detail, **extra})


def _name_reason(name: str) -> str:
    """Why this string cannot be a bundle directory, or "" when it can be one."""
    text = str(name or "")
    if not text or text in {".", ".."} or Path(text).is_absolute():
        return "a bundle name is one folder name"
    if Path(text).name != text or "/" in text or "\\" in text:
        return "a bundle name is one folder name, with no path in it"
    return ""


def _error_code(error: str) -> str:
    """The loader's own first word decides which refusal the author is told about."""
    if error.startswith("name:"):
        return "invalid_bundle_name"
    if error.startswith("description:"):
        return "invalid_description"
    return "invalid_manifest"


def _scaffold_manifest(
    name: str, description: str, publisher: str, license_id: str, title: str
) -> dict:
    return {
        "manifest_version": plugin_manifest.MANIFEST_VERSION_V2,
        "name": name,
        "version": _DEFAULT_VERSION,
        "description": description,
        "publisher": {"name": publisher or DEFAULT_PUBLISHER},
        "license": license_id or DEFAULT_LICENSE,
        "permissions": {"tool_families": [], "data_roots": []},
        "components": {
            "ui": {
                "type": "floating-window",
                "entry": "ui/index.html",
                "title": title or name,
                "default_size": {"width": 320, "height": 200},
            },
            "tools": [],
        },
        "changelog": f"{_DEFAULT_VERSION} - the first draft, scaffolded in Ephe.",
    }


_UI_FILES = {
    "ui/index.html": (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n<meta name="viewport" content="width=device-width">\n'
        '<link rel="stylesheet" href="app.css">\n<title>Bundle</title>\n</head>\n'
        '<body>\n<main id="app"><p data-role="line">Ready.</p></main>\n'
        '<script type="module" src="app.js"></script>\n</body>\n</html>\n'
    ),
    "ui/app.css": (
        ":root { color-scheme: light dark; font: 14px/1.4 system-ui; }\n"
        "#app { display: grid; gap: 8px; padding: 12px; }\n"
    ),
    "ui/app.js": "export const role = 'line';\n",
}


def create_plugin_scaffold(
    name: str,
    description: str = "",
    publisher: str = "",
    license: str = "",
    title: str = "",
) -> str:
    """Draft one declarative v2 bundle in staging, kept only when the loader accepts it.

    The `license` parameter carries the manifest's own field name.
    """
    blocked = _name_reason(name)
    if blocked:
        return _refusal("invalid_bundle_name", blocked, name=str(name))
    manifest = _scaffold_manifest(name, description, publisher, license, title)
    with tempfile.TemporaryDirectory(prefix=".ephe-scaffold-") as draft_root:
        draft = Path(draft_root) / str(name)
        draft.mkdir(parents=True)
        (draft / plugin_manifest.MANIFEST_FILENAME).write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        for relative, text in _UI_FILES.items():
            target = draft / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        _, error = plugin_manifest.load_manifest(draft)
        if error:
            return _refusal(_error_code(error), error, name=str(name))
        destination = bundle_dir(name)
        if destination.exists():
            return _refusal(
                "bundle_exists", "a staged bundle already carries that name", name=name
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(draft), str(destination))
    files = sorted(
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file()
    )
    return _answer(
        {
            "bundle": str(destination),
            "name": name,
            "version": manifest["version"],
            "license": manifest["license"],
            "publisher": manifest["publisher"]["name"],
            "files": files,
            "next": "write_plugin_source(bundle, path, content), then verify_plugin_bundle(bundle)",
        }
    )


def write_plugin_source(bundle: str, path: str, content: str) -> str:
    """Write one file inside one staged bundle, or say which rule the path broke."""
    directory = bundle_dir(bundle)
    if not directory.is_dir():
        return _refusal(
            "bundle_missing", "no staged bundle carries that name", bundle=str(bundle)
        )
    relative = str(path or "")
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        return _refusal(
            "path_outside_bundle",
            "the path has to name one file inside the bundle",
            bundle=str(bundle),
            path=relative,
        )
    root = directory.resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        return _refusal(
            "path_outside_bundle",
            "the path leaves the bundle once links are followed",
            bundle=str(bundle),
            path=relative,
        )
    if target.is_dir():
        return _refusal(
            "path_is_a_directory",
            "a file was expected",
            bundle=str(bundle),
            path=relative,
        )
    if not isinstance(content, str):
        return _refusal(
            "content_not_text",
            "the content has to be text",
            bundle=str(bundle),
            path=relative,
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.is_file()
    data = content.encode("utf-8")
    target.write_bytes(data)
    return _answer(
        {
            "bundle": str(directory),
            "path": relative,
            "bytes": len(data),
            "created": not existed,
            "next": "verify_plugin_bundle(bundle)",
        }
    )


def read_plugin_source(bundle: str, path: str) -> str:
    """Read one file inside one staged bundle, or say which rule the path broke.

    The author needs this to close its loop. Without it the only way to see a staged
    bundle is `read_file`, and `read_file` refuses it twice over: the staging folder
    sits under the device root, which `core/path_guard.py` denies to every agent tool
    with no approval able to open it, and the file tools of a mounted bundle are
    confined to the workspace. Live evidence 2026-11-09, run5: the turn scaffolded,
    reached for `read_file` to learn the manifest contract it was about to edit, was
    refused, and spent the rest of its 16-round budget on `file_search`,
    `list_directory` and `plugin_manager` without ever calling `write_plugin_source`.
    """
    directory = bundle_dir(bundle)
    if not directory.is_dir():
        return _refusal(
            "bundle_missing", "no staged bundle carries that name", bundle=str(bundle)
        )
    relative = str(path or "")
    if not relative or Path(relative).is_absolute() or ".." in Path(relative).parts:
        return _refusal(
            "path_outside_bundle",
            "the path has to name one file inside the bundle",
            bundle=str(bundle),
            path=relative,
        )
    root = directory.resolve()
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        return _refusal(
            "path_outside_bundle",
            "the path leaves the bundle once links are followed",
            bundle=str(bundle),
            path=relative,
        )
    if target.is_dir():
        return _refusal(
            "path_is_a_directory", "a file was expected", bundle=str(bundle), path=relative
        )
    if not target.is_file():
        return _refusal(
            "source_missing",
            "no file of that name is in the bundle",
            bundle=str(bundle),
            path=relative,
        )
    data = target.read_bytes()
    text = data.decode("utf-8", errors="replace")
    truncated = len(text) > MAX_FILE_CHARS
    return _answer(
        {
            "bundle": str(bundle),
            "path": relative,
            "bytes": len(data),
            "truncated": truncated,
            "content": text[:MAX_FILE_CHARS],
        }
    )


def _entry_problems(directory: Path, manifest: dict) -> list[str]:
    """Each declared tool entry as the confined worker will resolve it."""
    from core.sandbox.runner import resolve_entry_file

    problems: list[str] = []
    for claim in tool_claims(manifest):
        if not claim.contributed or claim.transport != "plugin":
            continue
        _, reason = resolve_entry_file(directory, claim.entry)
        if reason:
            problems.append(f"tool {claim.suffix!r}: {reason}")
    return problems


def _name_problems(manifest: dict) -> list[str]:
    """The two guards the mount applies, read before any byte lands in the plugins root."""
    from core.plugin_registry import scan_tool_activations

    conflicts = scan_tool_activations(None).conflicts
    problems: list[str] = []
    for claim in tool_claims(manifest):
        if not claim.contributed:
            continue
        collision = reserved_namespace(claim.name)
        if collision:
            problems.append(
                f"{claim.name!r} is held by the {collision} name space; "
                f"'{manifest.get('name')}' cannot serve it"
            )
        elif claim.name in conflicts:
            problems.append(f"{claim.name!r} is contested by another bundle")
    return problems


def _inspect_staged(candidate: Path, manifest: dict) -> str | None:
    """The refusal the install path asks for, in the same words verify uses."""
    problems = _entry_problems(candidate, manifest) + _name_problems(manifest)
    return "; ".join(problems)[:300] or None


def verify_plugin_bundle(bundle: str) -> str:
    """Say what the staged bytes really are: the loader's answer, the names, the digest."""
    directory = bundle_dir(bundle)
    if not directory.is_dir():
        return _refusal(
            "bundle_missing", "no staged bundle carries that name", bundle=str(bundle)
        )
    digest = plugin_manifest.dir_sha256(directory)
    manifest, error = plugin_manifest.load_manifest(directory)
    if error or not isinstance(manifest, dict):
        return _answer(
            {
                "ok": False,
                "error": "manifest_invalid",
                "bundle": str(directory),
                "sha256": digest,
                "problems": [error or "manifest unreadable"],
                "next": "write_plugin_source(bundle, 'ephe-plugin.json', ...)",
            }
        )
    entry_problems = _entry_problems(directory, manifest)
    if entry_problems:
        return _answer(
            {
                "ok": False,
                "error": "manifest_invalid",
                "bundle": str(directory),
                "sha256": digest,
                "problems": entry_problems,
                "next": "ship the file each entry names, inside the bundle",
            }
        )
    name_problems = _name_problems(manifest)
    if name_problems:
        return _answer(
            {
                "ok": False,
                "error": "name_reserved",
                "bundle": str(directory),
                "sha256": digest,
                "problems": name_problems,
                "next": "rename the tool in the manifest; a served name carries one declaration",
            }
        )
    return _answer(
        {
            "ok": True,
            "bundle": str(directory),
            "sha256": digest,
            "name": str(manifest.get("name")),
            "version": str(manifest.get("version")),
            "tools": [
                claim.name for claim in tool_claims(manifest) if claim.contributed
            ],
            "next": "install_plugin_bundle(bundle)",
        }
    )


def _artifact_bytes(directory: Path, name: str) -> bytes:
    """The zip the one install path unpacks: every file, under a directory of that name."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in directory.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(
                f"{name}/{path.relative_to(directory).as_posix()}",
                date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.external_attr = 0o100644 << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    return buffer.getvalue()


def install_plugin_bundle(bundle: str) -> str:
    """Hand the staged bytes to the install path, after verifying them in place."""
    directory = bundle_dir(bundle)
    if not directory.is_dir():
        return _refusal(
            "bundle_missing", "no staged bundle carries that name", bundle=str(bundle)
        )
    manifest, error = plugin_manifest.load_manifest(directory)
    if error or not isinstance(manifest, dict):
        return _answer(
            {
                "error": "not_verified",
                "bundle": str(directory),
                "problems": [error or "manifest unreadable"],
                "next": "verify_plugin_bundle(bundle) reads the same contract before install",
            }
        )
    payload = _artifact_bytes(directory, str(manifest.get("name")))
    entry = {
        "name": str(manifest.get("name")),
        "version": str(manifest.get("version")),
        "url": f"creator://{manifest.get('name')}.zip",
        "sha256": sha256_hex(payload),
        "trust": "local",
    }
    result = install_from_marketplace(
        str(manifest.get("name")),
        marketplace={"plugins": [entry]},
        fetcher=lambda _url: payload,
        allow_local_trust=True,
        root=plugin_manifest.plugins_root(),
        inspect=_inspect_staged,
    )
    if str(result.get("status")) != "extracted":
        return _answer(
            {
                "error": "install_refused",
                "bundle": str(directory),
                "detail": result,
                "next": "the installed bundle is unchanged; fix the staged bytes and verify again",
            }
        )
    from core import plugin_runtime

    plugin_runtime.invalidate_ownership_cache()
    installed = plugin_manifest.plugins_root() / str(manifest.get("name"))
    answer = {
        "status": "installed",
        "name": entry["name"],
        "version": entry["version"],
        "trust": str(result.get("trust") or ""),
        "sha256": plugin_manifest.dir_sha256(installed),
        "bundle": str(installed),
        "enabled": bool(plugin_runtime.is_plugin_active(entry["name"])),
        "next": "the Extensions surface holds the switch and the mount for this bundle",
    }
    if result.get("warning"):
        answer["warning"] = str(result["warning"])
    return _answer(answer)


CREATOR_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "create_plugin_scaffold",
            "description": (
                "Drafts a declarative Ephe plugin bundle in the creator's staging folder: a "
                "Manifest v2 descriptor, an html surface and its two asset files. The draft "
                "is kept only when the plugin loader reads it without an error. Use this when "
                "the user asks to start a plugin or a small Ephe extension."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Bundle slug: lowercase a-z0-9-.",
                    },
                    "description": {
                        "type": "string",
                        "description": "What the bundle does, as the catalog shows it.",
                    },
                    "publisher": {
                        "type": "string",
                        "description": "The author a reader sees; 'Independent' when left out.",
                    },
                    "license": {
                        "type": "string",
                        "description": "SPDX identifier; defaults to a proprietary reference.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Window title for the declared surface.",
                    },
                },
                "required": ["name", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_plugin_source",
            "description": (
                "Reads one file inside one staged bundle and answers with its text, the byte "
                "count of the file and whether the text was cut at the context cap. The path "
                "stays inside that bundle. Use this before replacing a file, so the bytes you "
                "send over are the ones you meant to change, and after a write to see what the "
                "bundle really holds."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bundle": {
                        "type": "string",
                        "description": "The staged bundle's name.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Bundle-relative file, e.g. ephe-plugin.json.",
                    },
                },
                "required": ["bundle", "path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_plugin_source",
            "description": (
                "Writes one file inside one staged bundle, replacing it when it exists. The "
                "path stays inside that bundle. Use this for the surface, the assets and the "
                "manifest edits a creator makes between verifications."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bundle": {
                        "type": "string",
                        "description": "The staged bundle's name.",
                    },
                    "path": {
                        "type": "string",
                        "description": "Bundle-relative file, e.g. ui/app.js.",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full text of the file.",
                    },
                },
                "required": ["bundle", "path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_plugin_bundle",
            "description": (
                "Reads one staged bundle the way the platform will: the manifest contract, the "
                "entry file each declared tool names, the tool names the registry already "
                "holds, and the digest of the bytes. Returns the problems it found, in the "
                "words of the check that found them."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bundle": {
                        "type": "string",
                        "description": "The staged bundle's name.",
                    }
                },
                "required": ["bundle"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "install_plugin_bundle",
            "description": (
                "Installs one verified staged bundle through the same path a marketplace "
                "artifact takes, as an unsigned local artifact the person who wrote it "
                "vouches for. The answer carries the trust class, the digest of the bytes "
                "that landed and whether the bundle is active. Use this when the user asks "
                "to try the bundle they just wrote."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bundle": {
                        "type": "string",
                        "description": "The staged bundle's name.",
                    }
                },
                "required": ["bundle"],
            },
        },
    },
]
