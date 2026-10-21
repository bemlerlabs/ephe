"""The kernel's permission mapping for plugin-declared tools (GAP-08).

A manifest may activate a kernel tool only when it also declares the family that
tool belongs to. The mapping is the single explicit table behind that check; an
unmapped tool name fails closed. Data roots are resolved into the plugin's file
scope, and a root that covers the home directory or a refused system folder is
rejected at validation.
"""
from __future__ import annotations

from pathlib import Path

_READ_TOOLS = (
    "read_file",
    "list_directory",
    "file_search",
    "load_workspace",
    "analyze_project",
)
_WRITE_TOOLS = (
    "write_file",
    "edit_file",
    "delete_file",
    "scaffold_project",
    "create_video",
)
_SHELL_TOOLS = ("run_shell", "run_tests", "run_linter", "format_code")
_BROWSER_TOOLS = (
    "browser_go",
    "browser_screenshot",
    "browser_click",
    "browser_type",
    "browser_press",
    "browser_scroll",
    "browser_evaluate",
    "browser_exec",
)
_VISION_TOOLS = ("analyze_image", "vision_click", "vision_type")
_NETWORK_TOOLS = ("web_search", "fetch_url", "generate_image")
_MEMORY_TOOLS = ("memory",)
_DOCS_TOOLS = (
    "create_pdf",
    "create_docx",
    "create_qrcode",
    "extract_pdf_text",
    "build_document",
    "export_source_brief",
    "create_source_notebook",
    "query_source_notebook",
    "verify_artifact",
    "create_xlsx",
    "generate_chart",
    "create_pptx_deck",
    "create_pitch_deck",
    "edit_pptx_template",
    "inspect_pptx_template",
    "qa_pptx_deck",
    "create_diagram",
    "create_svg",
)

TOOL_FAMILIES: dict[str, frozenset[str]] = {
    **{tool: frozenset({"read"}) for tool in _READ_TOOLS},
    **{tool: frozenset({"write"}) for tool in _WRITE_TOOLS},
    **{tool: frozenset({"shell"}) for tool in _SHELL_TOOLS},
    **{tool: frozenset({"browser"}) for tool in _BROWSER_TOOLS},
    **{tool: frozenset({"vision"}) for tool in _VISION_TOOLS},
    **{tool: frozenset({"network"}) for tool in _NETWORK_TOOLS},
    **{tool: frozenset({"memory"}) for tool in _MEMORY_TOOLS},
    **{tool: frozenset({"docs"}) for tool in _DOCS_TOOLS},
}


def validate_tool_permissions(manifest: dict) -> str | None:
    """Every declared tool needs a kernel family, and the manifest must hold it."""
    permissions = manifest.get("permissions", {})
    families = set(permissions.get("tool_families", []) or [])
    components = manifest.get("components", {})
    tools = components.get("tools", []) if isinstance(components, dict) else []
    for tool in tools:
        required = TOOL_FAMILIES.get(str(tool))
        if required is None:
            return (
                f"components.tools: unknown tool {tool!r} "
                "(no kernel permission mapping)"
            )
        missing = required - families
        if missing:
            return (
                f"components.tools: {tool!r} requires "
                f"{sorted(missing)} in permissions.tool_families"
            )
    return None


def validate_data_roots(roots: list) -> str | None:
    """Data roots are explicit, existing folders, never the home or a system root."""
    from core.engine_config import validate_workspace_dir

    home = Path.home().resolve()
    for root in roots:
        if not isinstance(root, str) or not root.strip():
            return "permissions.data_roots: non-empty path expected"
        path = Path(root).expanduser()
        if not path.is_absolute():
            if ".." in path.parts:
                return (
                    f"permissions.data_roots: {root!r} must not leave the workspace"
                )
            continue
        try:
            validated = validate_workspace_dir(str(path))
        except ValueError as exc:
            return f"permissions.data_roots: {root!r}: {exc}"
        if validated is None:
            return f"permissions.data_roots: {root!r} is not a directory"
        resolved = Path(validated)
        if resolved == home or home.is_relative_to(resolved):
            return (
                f"permissions.data_roots: {root!r} covers the home directory"
            )
    return None


def declared_data_roots(plugin: str) -> tuple[str, ...]:
    """The installed manifest's data roots for one plugin (first match wins)."""
    from core import plugin_manifest

    for entry in plugin_manifest.scan_plugins():
        manifest = entry["manifest"]
        if entry["error"] or not manifest:
            continue
        if str(manifest["name"]) != str(plugin):
            continue
        roots = manifest.get("permissions", {}).get("data_roots", [])
        return tuple(str(root) for root in roots) if isinstance(roots, list) else ()
    return ()
