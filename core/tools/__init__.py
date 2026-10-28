"""Ephe – Tool Engine (package).

All public symbols are re-exported from submodules for backward compatibility.
Usage: from core.tools import web_search, execute_tool, get_tool_schemas
"""

from core.tools.base import (
    WebSearchError,
    FileNotAllowedError,
    DirectoryNotFoundError,
    ShellConfirmationRequired,
    SandboxConfirmationRequired,
    ShellTimeoutError,
    ALLOWED_COMMANDS,
    BLOCKED_PATTERNS,
    ALLOWED_ROOTS,
    SHELL_TIMEOUT_SECONDS,
    MAX_FILE_CHARS,
    MAX_WORKSPACE_CHARS,
    MAX_WORKSPACE_DEPTH,
    SUPPORTED_IMAGE_EXTENSIONS,
    ENTERPRISE_DECK_PROFILES,
    ENTERPRISE_DESIGN_THEMES,
    AMATEUR_DECK_TERMS,
    _shared_client,
    TOOL_SCHEMA_CACHE_TTL_SECONDS,
    _TOOL_SCHEMA_CACHE,
    _get_shared_client,
    _get_allowed_roots,
    _is_path_allowed,
)

from core.tools.web_search import (
    web_search,
    OFFICIAL_SOURCE_DOMAINS,
)

from core.tools.fetch_tools import fetch_url

from core.tools.file_ops import (
    file_search,
    read_file,
    edit_file,
    write_file,
    delete_file,
    _extract_pdf_text,
    list_directory,
)

from core.tools.test_tools import run_tests

from core.tools.video_tools import create_video

from core.tools.source_tools import (
    create_source_notebook,
    query_source_notebook,
    export_source_brief,
)

from core.tools.shell_tools import (
    run_shell,
    execute_confirmed_shell,
    task_output,
    task_stop,
)

from core.tools.sandbox_tools import (
    run_sandboxed_code,
)

from core.tools.system_tools import (
    get_datetime,
    discover_projects,
    analyze_project,
    load_workspace,
    analyze_image,
    take_screenshot,
    create_svg,
    EN_WEEKDAYS,
    EN_MONTHS,
)

from core.tools.browser_tools import (
    browser_go,
    browser_screenshot,
    browser_click,
    browser_type,
    browser_press,
    browser_scroll,
    browser_evaluate,
    clipboard_read,
    clipboard_write,
    get_display_info,
    browser_exec,
    _get_vision_click,
    _get_vision_type,
    _vision_click_wrapper,
    _vision_type_wrapper,
    _get_browser_manager,
    vision_click,
    vision_type,
)

from core.tools.chart_tools import (
    generate_chart,
    _generate_svg_chart,
)

from core.tools.codebase_tools import query_codebase

from core.tools.pdf_tools import (
    create_pdf,
    _apply_pdf_template,
)

from core.tools.office_tools import (
    create_xlsx,
    create_docx,
    create_qrcode,
)

from core.tools.image_tools import (
    generate_image,
)

from core.tools.diagram_tools import (
    create_diagram,
)

from core.tools.verify_tools import (
    verify_artifact,
)

from core.tools.factory_tools import (
    scaffold_project,
    build_document,
)

from core.tools.deck_tools import (
    create_pitch_deck,
    create_pptx_deck,
    inspect_pptx_template,
    edit_pptx_template,
    qa_pptx_deck,
    _safe_download_filename,
    _split_lines,
    _enterprise_clean_text,
    _normalize_enterprise_slides,
    _default_deck_slides,
    _parse_deck_slides,
    _pdf_escape,
    _pdf_text,
    _xml_escape,
    _resolve_allowed_file,
    _normalize_hex_color,
    _normalize_brand_kit,
    _deck_v2_brand_kit,
    _normalize_deck_asset_paths,
    _inspect_pptx_template_file,
    _emu,
    _hex_from_pdf_rgb,
    _pptx_textbox,
    _pptx_rect,
    _pptx_slide_xml,
    _write_pitch_deck_pptx,
    _qa_pptx_deck_file,
    _render_pptx_contact_sheet,
    _deck_palette,
    _visual_commands,
    _write_pitch_deck_pdf,
    _qa_pitch_deck_render_file,
    _deck_text,
    _score_pitch_deck,
    _build_pitch_deck_manifest,
    _render_pitch_deck_preview,
)

from core.tools.task_tools import manage_tasks
from core.tools.code_kernel import execute_code
from core.tools.todo_tools import todo_list
from core.tools.process_tools import process_manage
from core.tools.discovery import tool_search, tool_describe, tool_call
from core.tools.state_tools import memory, skill_manage
from core.tools.workbench_tools import read_cell_journal, read_transcript
from core.tools.utility_tools import (
    extract_pdf_text,
    format_code,
    run_linter,
    validate_json,
)

from core.tools.ask_gate import (
    ask_user,
)

from core.tools.registry import (
    TOOL_MAP,
    execute_tool,
    get_tool_schemas,
    get_filtered_tool_schemas,
    invalidate_tool_schema_cache,
    register_tool_hook,
    clear_tool_hooks,
    _agent_message_impl as agent_message,
    get_assertions,
    reset_assertion_ledger,
)
from core.tools.subagent_tool import spawn_agent, SPAWN_AGENT_SCHEMA
from core.tools.mcp_client import (
    MCPClient,
    MCPServerSpec,
    parse_server_spec,
    set_mcp_servers,
    sync_mcp_tools,
    register_mcp_tool,
    unregister_mcp_tools,
    get_mcp_tools,
    call_registered_mcp_tool,
    mcp_tool_names,
)

__all__ = [
    "web_search", "file_search", "read_file", "edit_file", "list_directory",
    "fetch_url",
    "get_datetime", "discover_projects", "analyze_project",
    "create_source_notebook", "query_source_notebook", "export_source_brief",
    "run_shell", "execute_confirmed_shell",
    "task_output", "task_stop", "agent_message",
    "run_sandboxed_code",
    "load_workspace", "analyze_image", "take_screenshot", "create_svg",
    "browser_go", "browser_screenshot", "browser_click", "browser_type", "browser_press",
    "browser_scroll", "browser_evaluate", "clipboard_read", "clipboard_write", "get_display_info",
    "browser_exec",
    "vision_click", "vision_type",
    "generate_chart", "create_pdf",
    "create_xlsx", "create_docx", "create_qrcode", "create_diagram",
    "generate_image",
    "create_video",
    "verify_artifact", "scaffold_project", "build_document",
    "create_pitch_deck", "create_pptx_deck",
    "inspect_pptx_template", "edit_pptx_template", "qa_pptx_deck",
    "manage_tasks",
    "execute_code", "todo_list", "process_manage",
    "read_transcript", "read_cell_journal",
    "tool_search", "tool_describe", "tool_call",
    "memory", "skill_manage",
    "spawn_agent", "SPAWN_AGENT_SCHEMA",
    "TOOL_MAP", "execute_tool", "get_tool_schemas", "get_filtered_tool_schemas", "invalidate_tool_schema_cache",
    "query_codebase",
    "register_tool_hook", "clear_tool_hooks", "get_assertions", "reset_assertion_ledger",
    "MCPClient", "MCPServerSpec", "parse_server_spec", "set_mcp_servers",
    "sync_mcp_tools", "register_mcp_tool", "unregister_mcp_tools",
    "get_mcp_tools", "call_registered_mcp_tool", "mcp_tool_names",
    "WebSearchError", "FileNotAllowedError", "DirectoryNotFoundError",
    "ShellConfirmationRequired", "SandboxConfirmationRequired", "ShellTimeoutError",
    "ALLOWED_COMMANDS", "BLOCKED_PATTERNS", "ALLOWED_ROOTS",
    "SHELL_TIMEOUT_SECONDS", "MAX_FILE_CHARS", "MAX_WORKSPACE_CHARS",
    "MAX_WORKSPACE_DEPTH", "SUPPORTED_IMAGE_EXTENSIONS",
    "ENTERPRISE_DECK_PROFILES", "ENTERPRISE_DESIGN_THEMES", "AMATEUR_DECK_TERMS",
    "extract_pdf_text",
    "format_code",
    "run_linter",
    "validate_json",
]
