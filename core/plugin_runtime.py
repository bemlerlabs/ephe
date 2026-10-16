"""Ephe — Plugin runtime (Extensions wave E1)
core/plugin_runtime.py

THE single consumer of plugin state. The store UI writes plugins.json; this
module makes those toggles real: mapped tool families vanish from the
model-facing schema view and execution fails closed with an honest denial.

Honesty contracts (pinned in tests/test_r60_plugin_runtime.py):
- Only EXPLICIT registry entries (plugins.json, written by the store UI)
  gate behavior. Catalog defaults never hide tools silently — no behavior
  change until the user flips a switch (never break userspace).
- Master switch `master_enabled` (top-level in plugins.json, default true):
  off = stock Ephe, nothing gated.
- TOOL_MAP stays complete; gating applies to the schema view + execution.
- Unknown plugin ids and unknown tool names never crash.

Mapping (catalog plugin id → tool surface):
  web-search → web_search, fetch_url      memory → memory
  vision → analyze_image, vision_click, vision_type
  image-gen → generate_image              shell → run_shell
  mcp → every tool with the "mcp_" prefix
  tts / skills → no tool surface yet; wired with their routes/manifests
  (E2/E5). Unmapped tools are always visible.

Ephe – Bad Liebenzell, Schwarzwald
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from core.plugin_store import REGISTRY_FILENAME, config_root, migrate_registry_items

# ── Mapping: catalog plugin id → tool surface ───────────────────────────────

CATALOG_TOOL_FAMILIES: dict[str, dict[str, object]] = {
    # Extensions v2 (14 product plugins, docs/EXTENSIONS_V2_PLAN.md):
    "web-research": {"tools": {"web_search", "fetch_url"}},
    "memory": {"tools": {"memory"}},
    "vision": {"tools": {"analyze_image", "vision_click", "vision_type"}},
    "image-studio": {"tools": {"generate_image"}},
    "voice": {},  # Route gate: /api/audio/synthesize (E5), no tool surface
    "browser-use": {
        "tools": {
            "browser_go", "browser_screenshot", "browser_click", "browser_type",
            "browser_press", "browser_scroll", "browser_evaluate", "browser_exec",
        }
    },
    "code-shell": {
        "tools": {
            "run_shell",
            "read_file", "write_file", "edit_file", "delete_file", "run_tests",
            "run_linter", "format_code", "scaffold_project", "analyze_project",
            "file_search", "load_workspace", "list_directory",
        }
    },
    "mcp-connector": {"prefixes": ("mcp_",)},
    "documents": {
        "tools": {
            "create_pdf", "create_docx", "create_qrcode", "extract_pdf_text",
            "build_document", "export_source_brief", "create_source_notebook",
            "query_source_notebook", "verify_artifact",
        }
    },
    "spreadsheets": {"tools": {"create_xlsx", "generate_chart"}},
    "presentations": {
        "tools": {
            "create_pptx_deck", "create_pitch_deck", "edit_pptx_template",
            "inspect_pptx_template", "qa_pptx_deck", "create_diagram", "create_svg",
        }
    },
    # Commands-only plugins: no tool gate, instructions via SKILL/Commands.
    "plugin-creator": {},
    "skill-creator": {},
    "guide": {},
}

MCP_PREFIX = "mcp_"


@dataclass(frozen=True)
class Gate:
    visible: bool
    plugin: str = ""


# State loading (fail-soft, deterministic)

def _read_registry(path=None) -> dict:
    """Raw registry dict: {"plugins": [...], "master_enabled": bool}."""
    target = path if path is not None else config_root() / REGISTRY_FILENAME
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return raw if isinstance(raw, dict) else {}


def load_master_enabled(path=None) -> bool:
    """Master switch; missing/legacy file → True (plugins system on)."""
    raw = _read_registry(path)
    value = raw.get("master_enabled")
    return bool(value) if isinstance(value, bool) else True


def load_registry_map(path=None) -> dict[str, bool]:
    """Explicit plugin-id → enabled map from the registry (user toggles).

    Legacy slugs are mapped onto the v2 portfolio slugs by
    migrate_registry_items (E1) — old plugins.json files keep working.
    """
    raw = _read_registry(path)
    items = raw.get("plugins")
    if not isinstance(items, list):
        return {}
    migrated = migrate_registry_items(
        [p for p in items if isinstance(p, dict) and p.get("name")]
    )
    return {str(p["name"]): bool(p["enabled"]) for p in migrated}


def set_master_enabled(enabled: bool, path=None) -> bool:
    """Persist the master switch (best-effort, keeps the plugin entries)."""
    target = path if path is not None else config_root() / REGISTRY_FILENAME
    raw = _read_registry(target)
    items = raw.get("plugins") if isinstance(raw.get("plugins"), list) else []
    body = {"plugins": items, "master_enabled": bool(enabled)}
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
    except OSError:
        return False
    return True


# Gate decisions

def is_plugin_active(plugin_id: str, path=None) -> bool:
    """True when master is on AND the plugin is not explicitly disabled.

    Registry-silent plugins are active (catalog defaults never gate)."""
    if not load_master_enabled(path):
        return True  # master off = stock: plugin state ignored, tools visible
    enabled_map = load_registry_map(path)
    return enabled_map.get(plugin_id, True)


def tool_gate(tool_name: str, path=None) -> Gate:
    """Gate decision for one tool. First matching family wins; unmapped
    tools are always visible."""
    if not load_master_enabled(path):
        return Gate(visible=True)
    enabled_map = load_registry_map(path)
    disabled = {pid for pid, on in enabled_map.items() if not on}
    if not disabled:
        return Gate(visible=True)
    for plugin_id, family in CATALOG_TOOL_FAMILIES.items():
        if plugin_id not in disabled:
            continue
        tools = family.get("tools") or set()
        if tool_name in tools:
            return Gate(visible=False, plugin=plugin_id)
        prefixes = family.get("prefixes") or ()
        if any(tool_name.startswith(prefix) for prefix in prefixes):
            return Gate(visible=False, plugin=plugin_id)
    return Gate(visible=True)


def is_tool_visible(tool_name: str, path=None) -> bool:
    return tool_gate(tool_name, path).visible


def filter_schemas(schemas: list[dict], path=None) -> list[dict]:
    """Post-filter for get_tool_schemas(): drop disabled families.

    Applied OUTSIDE the schema cache so a registry flip acts on the next
    call without cache invalidation plumbing."""
    if not load_master_enabled(path):
        return schemas
    enabled_map = load_registry_map(path)
    disabled = {pid for pid, on in enabled_map.items() if not on}
    if not disabled:
        return schemas
    out: list[dict] = []
    for entry in schemas:
        name = entry.get("function", {}).get("name", "")
        gate = tool_gate(name, path)
        if gate.visible:
            out.append(entry)
    return out
