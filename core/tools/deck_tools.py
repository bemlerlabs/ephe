"""Ephe – Pitch deck / PPTX tools (aggregator facade).

The implementation lives in the layers _deck_common/_deck_pptx/_deck_pdf/
_deck_public; this module only re-exports the public + internal API
so that all import paths (`from core.tools.deck_tools import ...`) stay stable.
"""

from __future__ import annotations

from core.tools._deck_common import (
    _safe_download_filename,
    _deck_slug,
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
    _deck_palette,
    _visual_commands,
)
from core.tools._deck_pptx import (
    _inspect_pptx_template_file,
    _emu,
    _hex_from_pdf_rgb,
    _pptx_textbox,
    _pptx_rect,
    _pptx_slide_xml,
    _write_pitch_deck_pptx,
    _qa_pptx_deck_file,
    _render_pptx_contact_sheet,
)
from core.tools._deck_pdf import (
    _write_pitch_deck_pdf,
    _qa_pitch_deck_render_file,
    _deck_text,
    _score_pitch_deck,
    _build_pitch_deck_manifest,
    _render_pitch_deck_preview,
)
from core.tools._deck_public import (
    create_pitch_deck,
    create_pptx_deck,
    inspect_pptx_template,
    edit_pptx_template,
    qa_pptx_deck,
)

__all__ = [
    "_safe_download_filename",
    "_deck_slug",
    "_split_lines",
    "_enterprise_clean_text",
    "_normalize_enterprise_slides",
    "_default_deck_slides",
    "_parse_deck_slides",
    "_pdf_escape",
    "_pdf_text",
    "_xml_escape",
    "_resolve_allowed_file",
    "_normalize_hex_color",
    "_normalize_brand_kit",
    "_deck_v2_brand_kit",
    "_normalize_deck_asset_paths",
    "_deck_palette",
    "_visual_commands",
    "_inspect_pptx_template_file",
    "_emu",
    "_hex_from_pdf_rgb",
    "_pptx_textbox",
    "_pptx_rect",
    "_pptx_slide_xml",
    "_write_pitch_deck_pptx",
    "_qa_pptx_deck_file",
    "_render_pptx_contact_sheet",
    "_write_pitch_deck_pdf",
    "_qa_pitch_deck_render_file",
    "_deck_text",
    "_score_pitch_deck",
    "_build_pitch_deck_manifest",
    "_render_pitch_deck_preview",
    "create_pitch_deck",
    "create_pptx_deck",
    "inspect_pptx_template",
    "edit_pptx_template",
    "qa_pptx_deck",
]
