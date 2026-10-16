"""Shared design tokens for document rendering.

Single source of truth for PDF document styles (``core/tools/pdf_tools.py``):
a modular type scale (1.25 ratio on a 10 pt body), an 8 pt spacing grid,
named color tokens (the Ephe palette), and role styles for every paragraph
role the renderer emits. Pure data module - no renderer imports - so the
deck/chart/diagram engines can adopt the same tokens later without pulling
in a PDF library.

Determinism contract: every value here is derived from the constants below
with stable rounding, so the token set (and everything rendered from it) is
reproducible across runs and platforms.
"""
from __future__ import annotations

import re

# Type scale: modular scale, ratio 1.25, derived from a 10 pt body step and
# snapped to 0.5 pt so renderers write stable values. Steps -2..+4 relative
# to the body step.

TYPE_SCALE_RATIO = 1.25
TYPE_SCALE_BODY_PT = 10.0
# Tolerance for scale-membership checks (renderer rounding / text extraction).
TYPE_SCALE_TOLERANCE_PT = 0.26

_SCALE_STEPS = (-2, -1, 0, 1, 2, 3, 4)


def _snap_half_pt(value: float) -> float:
    """Snap a point value to the nearest 0.5 pt (deterministic rounding)."""
    return round(value * 2.0) / 2.0


def type_scale_step(step: int) -> float:
    """Return the type-scale size in points for a step relative to the body."""
    return _snap_half_pt(TYPE_SCALE_BODY_PT * (TYPE_SCALE_RATIO**step))


TYPE_SCALE_PT: tuple[float, ...] = tuple(type_scale_step(step) for step in _SCALE_STEPS)

# Named sizes on the scale (index into TYPE_SCALE_PT).
SIZE_CAPTION_MARKER_PT = TYPE_SCALE_PT[0]  # 6.5 - superscript citation counter
SIZE_CAPTION_PT = TYPE_SCALE_PT[1]  # 8.0
SIZE_BODY_PT = TYPE_SCALE_PT[2]  # 10.0
SIZE_H3_PT = TYPE_SCALE_PT[3]  # 12.5
SIZE_H2_PT = TYPE_SCALE_PT[4]  # 15.5
SIZE_H1_PT = TYPE_SCALE_PT[5]  # 19.5
SIZE_DISPLAY_PT = TYPE_SCALE_PT[6]  # 24.5


def is_on_type_scale(size_pt: float, tolerance: float = TYPE_SCALE_TOLERANCE_PT) -> bool:
    """Return True when a font size belongs to the modular type scale."""
    return any(abs(float(size_pt) - token) <= tolerance for token in TYPE_SCALE_PT)


# Spacing system: 8 pt grid with 4 pt half-steps for all spacing and margins.
# Margins stay above the 18 mm print floor (18 mm = 51.02 pt, so the smallest
# grid-aligned value above the floor is 56 pt).

SPACING_UNIT_PT = 8.0
SPACING_HALF_UNIT_PT = 4.0

PT_PER_MM = 72.0 / 25.4
MARGIN_FLOOR_MM = 18.0

MARGIN_LEFT_PT = 7 * SPACING_UNIT_PT  # 56 pt = 19.76 mm
MARGIN_RIGHT_PT = 7 * SPACING_UNIT_PT  # 56 pt = 19.76 mm
MARGIN_TOP_PT = 9 * SPACING_UNIT_PT  # 72 pt = 25.4 mm
MARGIN_BOTTOM_PT = 9 * SPACING_UNIT_PT  # 72 pt = 25.4 mm

MARGINS_PT: dict[str, float] = {
    "left": MARGIN_LEFT_PT,
    "right": MARGIN_RIGHT_PT,
    "top": MARGIN_TOP_PT,
    "bottom": MARGIN_BOTTOM_PT,
}


def pt_to_mm(pt: float) -> float:
    """Convert points to millimeters (rounded to 0.01 mm)."""
    return round(pt / PT_PER_MM, 2)


MARGINS_MM: dict[str, float] = {key: pt_to_mm(value) for key, value in MARGINS_PT.items()}

# Import-time floor guard: the token set must never drift below the print
# floor (also re-asserted at build time in the renderer).
assert min(MARGINS_MM.values()) >= MARGIN_FLOOR_MM, "Document margins violate the print floor."

# Decorative footer zone (below the content area, inside the bottom margin).
FOOTER_BASELINE_PT = 4 * SPACING_UNIT_PT  # 32 pt from the page bottom
FOOTER_FONT_PT = SIZE_CAPTION_PT  # 8 pt, on the type scale

# Horizontal rule under the title block.
RULE_THICKNESS_PT = 0.5
RULE_SPACE_AFTER_PT = SPACING_UNIT_PT


# Color tokens: the existing Ephe document palette as named tokens.

COLOR_TOKENS: dict[str, str] = {
    "paper": "#ffffff",
    "ink": "#111827",
    "muted": "#6b7280",
    "accent": "#16a34a",
    "accent_soft": "#22c55e",
    "line": "#9ca3af",
    "warn": "#b45309",
}


# Role styles: every paragraph role the PDF renderer emits. Values reference
# only the tokens above (no ad-hoc numbers). Heading roles must never strand
# at a page end (keep_with_next); text roles get widow/orphan protection.

def _heading_leading(size_pt: float) -> float:
    return _snap_half_pt(size_pt * 1.2)


def _text_leading(size_pt: float) -> float:
    return _snap_half_pt(size_pt * 1.5)


ROLE_STYLES: dict[str, dict] = {
    "title": {
        "font_name": "Helvetica-Bold",
        "font_size_pt": SIZE_DISPLAY_PT,
        "leading_pt": _heading_leading(SIZE_DISPLAY_PT),
        "text_color": "accent",
        "alignment": "center",
        "space_before_pt": 0.0,
        "space_after_pt": 2 * SPACING_UNIT_PT,
        "keep_with_next": True,
    },
    # Cover variant of the display title (document=True): same display size,
    # but ink instead of accent so the cover carries enough dark text mass to
    # stay legible in print and pass the dark-pixel legibility check.
    "cover_title": {
        "font_name": "Helvetica-Bold",
        "font_size_pt": SIZE_DISPLAY_PT,
        "leading_pt": _heading_leading(SIZE_DISPLAY_PT),
        "text_color": "ink",
        "alignment": "center",
        "space_before_pt": 0.0,
        "space_after_pt": 2 * SPACING_UNIT_PT,
        "keep_with_next": True,
    },
    "h1": {
        "font_name": "Helvetica-Bold",
        "font_size_pt": SIZE_H1_PT,
        "leading_pt": _heading_leading(SIZE_H1_PT),
        "text_color": "accent_soft",
        "alignment": "left",
        "space_before_pt": 3 * SPACING_UNIT_PT,
        "space_after_pt": SPACING_UNIT_PT,
        "keep_with_next": True,
    },
    "h2": {
        "font_name": "Helvetica-Bold",
        "font_size_pt": SIZE_H2_PT,
        "leading_pt": _heading_leading(SIZE_H2_PT),
        "text_color": "accent_soft",
        "alignment": "left",
        "space_before_pt": 2 * SPACING_UNIT_PT,
        "space_after_pt": SPACING_UNIT_PT,
        "keep_with_next": True,
    },
    "h3": {
        "font_name": "Helvetica-Bold",
        "font_size_pt": SIZE_H3_PT,
        "leading_pt": _heading_leading(SIZE_H3_PT),
        "text_color": "accent_soft",
        "alignment": "left",
        "space_before_pt": 1.5 * SPACING_UNIT_PT,
        "space_after_pt": SPACING_HALF_UNIT_PT,
        "keep_with_next": True,
    },
    "body": {
        "font_name": "Helvetica",
        "font_size_pt": SIZE_BODY_PT,
        "leading_pt": _text_leading(SIZE_BODY_PT),
        "text_color": "ink",
        "alignment": "left",
        "space_before_pt": 0.0,
        "space_after_pt": SPACING_HALF_UNIT_PT,
        "no_widows": True,
        "no_orphans": True,
    },
    "bullet": {
        "font_name": "Helvetica",
        "font_size_pt": SIZE_BODY_PT,
        "leading_pt": _text_leading(SIZE_BODY_PT),
        "text_color": "ink",
        "alignment": "left",
        "space_before_pt": 0.0,
        "space_after_pt": SPACING_HALF_UNIT_PT,
        "left_indent_pt": 1.5 * SPACING_UNIT_PT,
        "bullet_indent_pt": SPACING_HALF_UNIT_PT,
        "bullet_text": "-",
        "no_widows": True,
        "no_orphans": True,
    },
    "numbered": {
        "font_name": "Helvetica",
        "font_size_pt": SIZE_BODY_PT,
        "leading_pt": _text_leading(SIZE_BODY_PT),
        "text_color": "ink",
        "alignment": "left",
        "space_before_pt": 0.0,
        "space_after_pt": SPACING_HALF_UNIT_PT,
        "left_indent_pt": 1.5 * SPACING_UNIT_PT,
        "no_widows": True,
        "no_orphans": True,
    },
    "caption": {
        "font_name": "Helvetica",
        "font_size_pt": SIZE_CAPTION_PT,
        "leading_pt": _text_leading(SIZE_CAPTION_PT),
        "text_color": "muted",
        "alignment": "left",
        "space_before_pt": 0.0,
        "space_after_pt": SPACING_HALF_UNIT_PT,
        "no_widows": True,
        "no_orphans": True,
    },
    "citation": {
        "font_name": "Helvetica",
        "font_size_pt": SIZE_CAPTION_PT,
        "leading_pt": _text_leading(SIZE_CAPTION_PT),
        "text_color": "ink",
        "alignment": "left",
        "space_before_pt": 0.0,
        "space_after_pt": SPACING_HALF_UNIT_PT,
        "no_widows": True,
        "no_orphans": True,
    },
    # Compat roles kept on the same tokens (meta/appendix derive from the
    # caption role, numbered from the bullet role) so legacy documents
    # rendered before the token module keep their look.
    "meta": {
        "font_name": "Helvetica",
        "font_size_pt": SIZE_CAPTION_PT,
        "leading_pt": _text_leading(SIZE_CAPTION_PT),
        "text_color": "muted",
        "alignment": "center",
        "space_before_pt": 0.0,
        "space_after_pt": 1.5 * SPACING_UNIT_PT,
        "no_widows": True,
        "no_orphans": True,
    },
    "appendix": {
        "font_name": "Helvetica",
        "font_size_pt": SIZE_CAPTION_PT,
        "leading_pt": _text_leading(SIZE_CAPTION_PT),
        "text_color": "ink",
        "alignment": "left",
        "space_before_pt": 0.0,
        "space_after_pt": SPACING_HALF_UNIT_PT,
        "no_widows": True,
        "no_orphans": True,
    },
}

ROLE_ORDER: tuple[str, ...] = (
    "title",
    "cover_title",
    "h1",
    "h2",
    "h3",
    "body",
    "bullet",
    "numbered",
    "caption",
    "citation",
    "meta",
    "appendix",
)

assert set(ROLE_ORDER) == set(ROLE_STYLES), "Role order and role styles must stay in sync."

HEADING_ROLES: tuple[str, ...] = ("h1", "h2", "h3")


# P2 callouts: GitHub-style marker blocks (``> [!NOTE]``, ``> [!TIP]``,
# ``> [!WARNING]``) rendered as tinted boxes with a left accent bar and no
# icon. The tinted surface is derived deterministically from the color
# tokens by blending the token color onto the paper token, so callout text
# stays legible (ink on a pale tint) while the bar carries the full-strength
# token color. Mapping: note/tip -> accent_soft surface + accent bar,
# warning -> warn surface + warn bar (warn is the accent of the warning kind;
# a green bar on an amber surface would read as a design bug).

CALLOUT_MARKER_RE = re.compile(r"^>\s*\[!(NOTE|TIP|WARNING)\]\s*$")

# Share of the token color kept in the surface; the rest blends to paper.
CALLOUT_SURFACE_KEEP_RATIO = 0.12
CALLOUT_BAR_THICKNESS_PT = 3.0


def blend_hex_toward_paper(hex_color: str, keep_ratio: float = CALLOUT_SURFACE_KEEP_RATIO) -> str:
    """Blend a hex token color onto the paper token (stable rounding)."""
    surface = (hex_color or "").lstrip("#")
    paper = COLOR_TOKENS["paper"].lstrip("#")
    if len(surface) != 6 or len(paper) != 6:
        raise ValueError(f"Expected 6-digit hex colors, got {hex_color!r}.")
    blended = [
        round(int(surface[index:index + 2], 16) * keep_ratio + int(paper[index:index + 2], 16) * (1.0 - keep_ratio))
        for index in (0, 2, 4)
    ]
    return "#{:02x}{:02x}{:02x}".format(*blended)


CALLOUT_KINDS: dict[str, dict] = {
    "note": {"label": "Note", "surface_token": "accent_soft", "bar_token": "accent"},
    "tip": {"label": "Tip", "surface_token": "accent_soft", "bar_token": "accent"},
    "warning": {"label": "Warning", "surface_token": "warn", "bar_token": "warn"},
}


# Citation pipeline: input markers [S###-C###] (S = source, C = chunk) are
# rendered as numbered inline superscript counters and resolved by an
# automatic references section at the end of the document.

CITATION_MARKER_RE = re.compile(r"\[(S\d{3})-C(\d{3})\]")
CITATION_ENTRY_RE = re.compile(r"\[\d+\] Source S\d{3} - Chunk C\d{3}")

CITATION_MARKER_SIZE_PT = SIZE_CAPTION_MARKER_PT  # superscript counter size
CITATION_MARKER_RISE_PT = SPACING_HALF_UNIT_PT  # superscript baseline rise


def chunk_id_from_match(match: "re.Match[str]") -> str:
    """Rebuild the chunk id (e.g. ``S001-C001``) from a marker regex match."""
    return f"{match.group(1)}-C{match.group(2)}"


def scan_citation_numbers(content: str) -> dict[str, int]:
    """Map each unique ``[S###-C###]`` chunk marker to its reference number.

    Numbers follow first appearance in the content; repeated markers for the
    same chunk share one number. Without markers the map is empty (and the
    renderer adds no references section - backcompat behavior).
    """
    numbers: dict[str, int] = {}
    for match in CITATION_MARKER_RE.finditer(content or ""):
        chunk_id = chunk_id_from_match(match)
        if chunk_id not in numbers:
            numbers[chunk_id] = len(numbers) + 1
    return numbers


def citation_reference_text(number: int, chunk_id: str) -> str:
    """Render the reference-list entry line for one numbered citation."""
    source_id, _, chunk_part = (chunk_id or "").partition("-")
    return f"[{number}] Source {source_id} - Chunk {chunk_part}"
