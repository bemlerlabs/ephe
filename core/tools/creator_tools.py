"""Ephe — Creator Mode's bundle authoring tools (Creator wave 0).
core/tools/creator_tools.py

Each call answers against a contract the platform already owns:

- `create_plugin_scaffold` renders one template of `core.plugin_templates` — a manifest
  and every file it names — into a temporary directory, and keeps it only when
  `core.plugin_manifest.load_manifest` reads it without an error, so staging cannot
  accumulate a folder the scanner would quarantine. A template ships the whole bundle,
  so the shape of a plugin exists before a model writes a line; the model picks the
  template and fills in its fields.
- `read_plugin_source` hands back one file of one staged bundle. The staged folder lives
  under the device root, which `core/path_guard.py` denies to the general file tools, so
  this is the only way the author can see what it is about to replace.
- `write_plugin_source` puts one file inside one staged bundle. The path is checked
  against the bundle's real path before a byte is written.
- `verify_plugin_bundle` carries the loader's own error, the confined worker's answer
  about each declared entry (`core.sandbox.runner.resolve_entry_file`), the Python those
  entries name (parsed with `ast` before the worker imports it), and the one reservation
  map the mount applies (`core.plugin_tools_contract.reserved_tool_names`).
- `install_plugin_bundle` packs the staged bytes as a `local` artifact and hands them to
  `core.plugin_install.install_from_marketplace` — the one path a directory takes to
  becoming loadable — so hash, extraction, validation, rollback and the audit row stay in
  that function. The bundle lands unsigned and is trusted by the person who wrote it.

The template family is the only place a bundle's shape is written down. A template that
ships a tool declares the family that tool works in; no template asks for `shell`, `write`
or a data root, and only the `network-tool` template names the `network` family, which the
bridge checks at the call.

A scaffolded bundle declares no tool: `components.tools` is the code escalation the two-
tier contract puts behind an explicit approval, so the first bundle is a surface.

Every answer ends on a move. A success names the call that comes next, and a refusal names
the code, the reason and the step that leads out — `REFUSAL_NEXT` holds the creator calls'
own steps, and an install the install path refuses carries that path's step
(`core.plugin_install.INSTALL_NEXT_STEPS`). A refusal is never an exception: the author
reads it in the same envelope it reads every other answer in.
"""

from __future__ import annotations

import io
import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from core import plugin_manifest, plugin_templates
from core.engine_config import config_root
from core.plugin_install import install_from_marketplace, next_step_for
from core.plugin_store import sha256_hex
from core.plugin_tools_contract import reserved_tool_refusals, tool_claims
from core.tools.base import MAX_FILE_CHARS

STAGING_DIRNAME = "creator"
DEFAULT_PUBLISHER = plugin_templates.DEFAULT_PUBLISHER
DEFAULT_LICENSE = plugin_templates.DEFAULT_LICENSE

#: The next call a refusal leaves, keyed by the code the refusal answers with. One place
#: for the sentence, so a code cannot be added without one.
REFUSAL_NEXT: dict[str, str] = {
    "invalid_bundle_name": (
        "Pick a lowercase slug (a-z, 0-9, dashes) and call create_plugin_scaffold again."
    ),
    "invalid_description": (
        "Pass one non-empty sentence as description and call create_plugin_scaffold again."
    ),
    "invalid_manifest": (
        "Read the loader's error, correct the field it names, then verify_plugin_bundle "
        "again."
    ),
    "bundle_exists": "Read the staged bundle with read_plugin_source, or pick another name.",
    "bundle_missing": (
        "Call create_plugin_scaffold first, then retry with the name it answered."
    ),
    "path_outside_bundle": "Name one file inside the bundle, for example ui/app.js.",
    "path_is_a_directory": "Name a file inside the bundle, not a folder.",
    "content_not_text": "Send the file content as a string.",
    "source_missing": "Write the file first with write_plugin_source, then read it.",
    "not_verified": "Fix the problems verify_plugin_bundle reports, then install again.",
    "install_raised": (
        "Read the audit row this install wrote for the failing step, fix what it names, "
        "then install again."
    ),
}


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
    """A refusal in one shape: the code, the reason, the step that leads out, then facts."""
    payload: dict[str, Any] = {"error": code, "detail": detail, **extra}
    step = REFUSAL_NEXT.get(code, "")
    if step:
        payload["next"] = step
    return _answer(payload)


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
    if error.startswith("components.tools"):
        return "invalid_tool"
    return "invalid_manifest"


def create_plugin_scaffold(
    name: str,
    description: str = "",
    publisher: str = "",
    license: str = "",
    title: str = "",
    template: str = plugin_templates.DEFAULT_TEMPLATE,
    tool: str = "",
) -> str:
    """Draft one templated v2 bundle in staging, kept only when the loader accepts it.

    The `license` parameter carries the manifest's own field name. `template` picks the
    shape; `tool` names the tool for a template that ships one.
    """
    blocked = _name_reason(name)
    if blocked:
        return _refusal("invalid_bundle_name", blocked, name=str(name))
    try:
        files = plugin_templates.render(
            template,
            name=name,
            description=description,
            publisher=publisher,
            license=license,
            title=title,
            tool=tool,
        )
    except plugin_templates.UnknownTemplate as refused:
        return _refusal(
            "unknown_template",
            str(refused),
            name=str(name),
            templates=sorted(plugin_templates.TEMPLATES),
            next=(
                "call create_plugin_scaffold again with one of `templates`; an ask none "
                "of them covers is named as the missing shape, not invented"
            ),
        )
    with tempfile.TemporaryDirectory(prefix=".ephe-scaffold-") as draft_root:
        draft = Path(draft_root) / str(name)
        draft.mkdir(parents=True)
        for relative, text in files.items():
            target = draft / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text, encoding="utf-8")
        manifest, error = plugin_manifest.load_manifest(draft)
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
            "template": template,
            "files": files,
            "version": str(manifest.get("version")),
            "license": str(manifest.get("license")),
            "publisher": str((manifest.get("publisher") or {}).get("name")),
            "tools": [claim.name for claim in tool_claims(manifest) if claim.contributed],
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


def _declared_entries(manifest: dict) -> list[tuple[str, str]]:
    """(label, dotted module entry) for every file the manifest makes the worker resolve.

    A plugin tool names its own entry; an MCP tool rides the bundle's server, whose one
    entry lives under `components.mcp`. Both are files this bundle has to ship.
    """
    from core.plugin_tools_contract import module_entry

    components = manifest.get("components", {})
    mcp = components.get("mcp") if isinstance(components, dict) else None
    server = ""
    if isinstance(mcp, dict) and isinstance(mcp.get("entry"), str):
        server = module_entry(mcp["entry"])
    entries: list[tuple[str, str]] = []
    for claim in tool_claims(manifest):
        if not claim.contributed:
            continue
        if claim.transport == "mcp":
            if server:
                entries.append(("mcp server", server))
            continue
        entries.append((f"tool {claim.suffix!r}", claim.entry))
    return entries


def _entry_problems(directory: Path, manifest: dict) -> list[str]:
    """Each declared entry as the confined worker will resolve it."""
    from core.sandbox.runner import resolve_entry_file

    problems: list[str] = []
    for label, entry in _declared_entries(manifest):
        _, reason = resolve_entry_file(directory, entry)
        if reason:
            problems.append(f"{label}: {reason}")
    return problems


def _entry_path(directory: Path, entry: str) -> Path | None:
    from core.sandbox.runner import resolve_entry_file

    target, reason = resolve_entry_file(directory, entry)
    return None if reason else target


def _syntax_problems(directory: Path, manifest: dict) -> list[str]:
    """The Python each declared entry names, parsed now instead of at the first call.

    A bundle whose `handlers.py` does not compile is not a bundle the worker can run, and
    the author can still fix it. The refusal names the file and the line the parser
    stopped on, which is the difference between a preflight and an ImportError in a
    subprocess the author never sees.
    """
    import ast

    problems: list[str] = []
    seen: set[Path] = set()
    for _label, entry in _declared_entries(manifest):
        target = _entry_path(directory, entry)
        if target is None or target in seen:
            continue
        seen.add(target)
        try:
            relative = target.relative_to(Path(directory).resolve()).as_posix()
        except ValueError:
            relative = target.name
        try:
            source = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"{relative}: cannot be read as UTF-8 ({type(exc).__name__})")
            continue
        try:
            ast.parse(source, filename=str(target))
        except SyntaxError as exc:
            problems.append(f"{relative}:{exc.lineno or 0}: syntax error: {exc.msg}")
    return problems


def _name_refusals(
    directory: Path | None, manifest: dict
) -> tuple[list[str], list[dict]]:
    """Reserved and contested names, as sentences and as the actionable records."""
    from core.plugin_registry import scan_tool_activations

    refusals = list(reserved_tool_refusals(manifest, directory))
    problems = [
        f"{refusal['code']}: {refusal['name']!r} is held by the "
        f"{refusal['namespace']} name space (owner: {refusal['owner']}); "
        f"{refusal['action']}"
        for refusal in refusals
    ]
    reserved = {refusal["name"] for refusal in refusals}
    conflicts = scan_tool_activations(None).conflicts
    for claim in tool_claims(manifest):
        if not claim.contributed or claim.name in reserved:
            continue
        if claim.name in conflicts:
            problems.append(f"{claim.name!r} is contested by another bundle")
    return problems, refusals


def _inspect_staged(candidate: Path, manifest: dict) -> str | None:
    """The refusal the install path asks for, in the same words verify uses."""
    problems = _entry_problems(candidate, manifest) + _name_refusals(candidate, manifest)[0]
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
    syntax_problems = _syntax_problems(directory, manifest)
    if syntax_problems:
        return _answer(
            {
                "ok": False,
                "error": "source_invalid",
                "bundle": str(directory),
                "sha256": digest,
                "problems": syntax_problems,
                "next": "fix the reported file and verify_plugin_bundle again",
            }
        )
    name_problems, refusals = _name_refusals(directory, manifest)
    if name_problems:
        return _answer(
            {
                "ok": False,
                "error": "name_reserved",
                "bundle": str(directory),
                "sha256": digest,
                "problems": name_problems,
                "refusals": refusals,
                "next": "rename the tool in the manifest; each refusal names a free one",
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
        return _refusal(
            "not_verified",
            error or "manifest unreadable",
            bundle=str(directory),
            problems=[error or "manifest unreadable"],
        )
    payload = _artifact_bytes(directory, str(manifest.get("name")))
    entry = {
        "name": str(manifest.get("name")),
        "version": str(manifest.get("version")),
        "url": f"creator://{manifest.get('name')}.zip",
        "sha256": sha256_hex(payload),
        "trust": "local",
    }
    try:
        result = install_from_marketplace(
            str(manifest.get("name")),
            marketplace={"plugins": [entry]},
            fetcher=lambda _url: payload,
            allow_local_trust=True,
            root=plugin_manifest.plugins_root(),
            inspect=_inspect_staged,
        )
    except Exception as exc:  # noqa: BLE001 — an author reads a refusal, never a traceback
        # The one install path audits the exception before it re-raises; the author still
        # gets the envelope it reads every other answer in, with the row that tells more.
        return _refusal(
            "install_raised",
            f"the install path stopped with {type(exc).__name__}",
            bundle=str(directory),
            status="raised",
        )
    if str(result.get("status")) != "extracted":
        return _answer(
            {
                "error": "install_refused",
                "bundle": str(directory),
                "detail": result,
                "next": next_step_for(result),
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
    if result.get("status") == "already_installed":
        answer["unchanged"] = True
    if result.get("warning"):
        answer["warning"] = str(result["warning"])
    return _answer(answer)


CREATOR_TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "create_plugin_scaffold",
            "description": (
                "Drafts a whole declarative Ephe plugin bundle in the creator's staging "
                "folder from one template: the Manifest v2 descriptor, the html surface and "
                "its assets, an optional tool and a README. The draft is kept only when the "
                "plugin loader reads it without an error. Use it first when the user asks "
                "for a plugin or a small Ephe extension, and pick the template whose shape "
                "matches the ask: `surface` for a window without a tool, `surface-tool` for "
                "a window that also brings one, `tool` for a tool alone and `network-tool` "
                "for a tool that needs `bridge.fetch`. Not for a name that is already "
                "staged: that draft is refused, so read it with read_plugin_source or pick "
                "another name. Every refusal carries the code, the reason and the next "
                "step. "
                'Example: create_plugin_scaffold(name="countdown", description="Counts '
                'down to a set time.", template="surface-tool", tool="remaining")'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": (
                            "Bundle slug and folder name: lowercase letters, digits and "
                            "dashes."
                        ),
                    },
                    "description": {
                        "type": "string",
                        "description": "One non-empty sentence that the catalog shows.",
                    },
                    "template": {
                        "type": "string",
                        "enum": sorted(plugin_templates.TEMPLATES),
                        "description": (
                            "The shape to draft: "
                            + plugin_templates.template_choices()
                            + ". Defaults to surface."
                        ),
                    },
                    "publisher": {
                        "type": "string",
                        "description": (
                            "Name a reader sees as the author; 'Independent' when left out."
                        ),
                    },
                    "license": {
                        "type": "string",
                        "description": (
                            "SPDX identifier, for example 'MIT'; a proprietary reference "
                            "when left out."
                        ),
                    },
                    "title": {
                        "type": "string",
                        "description": (
                            "Window title of the declared surface; defaults to the bundle "
                            "name."
                        ),
                    },
                    "tool": {
                        "type": "string",
                        "description": (
                            "Tool name for a template that ships one (a-z0-9_); defaults "
                            "to the bundle name in that spelling."
                        ),
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
                "Reads one file of one staged bundle: the text, the byte count, and whether "
                "the text was cut at the context cap. The path stays inside that bundle. Use "
                "it before replacing a file with write_plugin_source, and after a write to "
                "see what the bundle really holds. Not for files outside the staged bundle; "
                "the workspace file tools read those. "
                'Example: read_plugin_source(bundle="countdown", path="ephe-plugin.json")'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bundle": {
                        "type": "string",
                        "description": (
                            "Name of a staged bundle, as create_plugin_scaffold answered it."
                        ),
                    },
                    "path": {
                        "type": "string",
                        "description": (
                            "Bundle-relative file path, for example 'ephe-plugin.json'; an "
                            "absolute path or '..' is refused."
                        ),
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
                "Writes or replaces one whole file inside one staged bundle. The path is "
                "bundle-relative and is refused when it leaves the bundle. Use it for the "
                "surface, its assets and manifest edits; read the file first, because a "
                "write replaces all of it and content you leave out is gone. Not for a "
                "partial edit or for a file in the workspace. "
                'Example: write_plugin_source(bundle="countdown", path="ui/app.js", '
                'content="export const left = 60;")'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bundle": {
                        "type": "string",
                        "description": (
                            "Name of a staged bundle, as create_plugin_scaffold answered it."
                        ),
                    },
                    "path": {
                        "type": "string",
                        "description": (
                            "Bundle-relative file path, for example 'ui/app.js'; an absolute "
                            "path or '..' is refused."
                        ),
                    },
                    "content": {
                        "type": "string",
                        "description": (
                            "Full text of the file; the write replaces the file, so this is "
                            "not a patch."
                        ),
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
                "Checks one staged bundle against the rules the mount applies later: the "
                "manifest contract, the file every declared tool entry names, the tool names "
                "the registry already serves, and the digest of the bytes. It changes "
                "nothing, so it is safe to repeat. Use it after every write and before "
                "install_plugin_bundle; ok is true only when install will pass too. Not for "
                "deciding whether a bundle is welcome: it reports the contract, not the "
                "trust. The answer carries ok, sha256, problems and the next call."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bundle": {
                        "type": "string",
                        "description": (
                            "Name of a staged bundle, as create_plugin_scaffold answered it."
                        ),
                    },
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
                "Installs one staged bundle through the path a marketplace artifact takes, "
                "as an unsigned local artifact the person who wrote it vouches for. It "
                "re-reads the manifest first and refuses what verify_plugin_bundle reports. "
                "Use it after verify_plugin_bundle returned ok, when the user asked to keep "
                "or try the bundle. Not for a plugin from a marketplace listing; install "
                "that with `ephe plugin install`. "
                'Example: install_plugin_bundle(bundle="countdown")'
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "bundle": {
                        "type": "string",
                        "description": (
                            "Name of a staged bundle, as create_plugin_scaffold answered it."
                        ),
                    },
                },
                "required": ["bundle"],
            },
        },
    },
]
