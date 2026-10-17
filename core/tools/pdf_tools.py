"""Ephe - create_pdf tool (reportlab, token-driven via core.doc_design)."""

from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path

from core.doc_design import (
    CALLOUT_BAR_THICKNESS_PT,
    CALLOUT_KINDS,
    CALLOUT_MARKER_RE,
    CITATION_MARKER_RE,
    CITATION_MARKER_RISE_PT,
    CITATION_MARKER_SIZE_PT,
    COLOR_TOKENS,
    FOOTER_BASELINE_PT,
    FOOTER_FONT_PT,
    HEADING_ROLES,
    MARGIN_FLOOR_MM,
    MARGINS_MM,
    MARGINS_PT,
    ROLE_ORDER,
    ROLE_STYLES,
    RULE_SPACE_AFTER_PT,
    RULE_THICKNESS_PT,
    SIZE_BODY_PT,
    SIZE_H3_PT,
    SPACING_HALF_UNIT_PT,
    SPACING_UNIT_PT,
    TYPE_SCALE_PT,
    TYPE_SCALE_RATIO,
    blend_hex_toward_paper,
    chunk_id_from_match,
    citation_reference_text,
    scan_citation_numbers,
)

# P2 font strategy, evaluated honestly: reportlab's base-14 Helvetica is
# WinAnsi-encoded and already covers the umlaut/typography range our
# documents need (pinned by the clean-glyph checks in the test suite).
# reportlab bundles Bitstream Vera TTFs (Vera.ttf/VeraBd.ttf, license file
# included), so embedding would be possible without any download - but Vera
# adds no measurable glyph coverage or legibility gain over WinAnsi Helvetica
# for our Latin-1 documents while inflating file size and adding a second
# font family. Decision: Helvetica stays the document font; an embedded
# serif/sans display pair remains a P3 roadmap topic. No font download, no
# external font files in the repo.
FONT_STRATEGY = "base14-helvetica-winansi"

# P2 cover/TOC labels (document=True). German labels match the product
# voice ("Seite", filename defaults).
COVER_BRAND_LABEL = "Ephe"
TOC_HEADING_TEXT = "Inhaltsverzeichnis"

# P2 chart embedding: a WHOLE-LINE ``![alt](/absolute/path.png)`` marker
# embeds an existing local PNG (any alt text is accepted, only the path is
# significant). Image syntax inline in a sentence or with a relative path is
# not the convention and keeps rendering as plain text.
IMAGE_MARKER_RE = re.compile(r"^!\[[^\]]*\]\(([^)]+)\)$")


def _apply_pdf_template(content: str, template: str) -> str:
    text = (content or "").strip()
    lowered = text.lower()
    template = (template or "report").lower()
    sections: dict[str, list[str]] = {
        "report": ["# Executive Summary", "## Findings", "## Next Steps", "### Source Notes"],
        "brief": ["# Executive Summary", "## Key Points", "### Source Notes"],
        "analysis": ["# Executive Summary", "## Evidence", "## Risks", "## Recommendations", "### Appendix"],
        "checklist": ["# Executive Summary", "## Checklist", "## Acceptance Criteria", "### Source Notes"],
    }
    required = sections.get(template, sections["report"])
    missing = [section for section in required if section.lstrip("# ").lower() not in lowered]
    if not missing:
        return text
    inserted = [missing[0], text]
    for section in missing[1:]:
        inserted.extend(["", section, "- Not specified in the source input."])
    return "\n".join(inserted).strip()


def _san(text: str) -> str:
    text = text.replace("■", "-").replace("\u25aa", "-").replace("¶", "")
    return re.sub(r" {2,}", " ", text)


def _render_citation_markers(escaped_text: str, citation_numbers: dict[str, int]) -> str:
    """Replace [S###-C###] chunk markers with numbered superscript counters."""
    if not citation_numbers:
        return escaped_text

    def _replace(match):
        number = citation_numbers.get(chunk_id_from_match(match))
        if number is None:
            return match.group(0)
        size = f"{CITATION_MARKER_SIZE_PT:g}"
        rise = f"{CITATION_MARKER_RISE_PT:g}"
        return f'<super size="{size}" rise="{rise}">{number}</super>'

    return CITATION_MARKER_RE.sub(_replace, escaped_text)


# P2 markdown extensions: pipe tables, callout blocks, image markers.
# All parsers are conservative: content without the documented markers keeps
# rendering exactly as before (plain paragraphs), so legacy documents are
# unaffected.


def _split_table_row(line: str) -> list[str]:
    """Split one markdown pipe-table row into stripped cell texts.

    ``\\|`` escapes stay literal pipes; leading/trailing pipes are optional.
    """
    text = (line or "").strip().replace("\\|", "\x00")
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.replace("\x00", "|").strip() for cell in text.split("|")]


def _is_table_separator(line: str) -> bool:
    """True for a pipe-table separator row (``| --- | :---: |`` style).

    Lenient on dash count (one or more) and on leading/trailing pipes, but
    every cell must be a dash (optionally with alignment colons).
    """
    if "|" not in (line or "") or "-" not in line:
        return False
    cells = _split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-+:?", cell) for cell in cells)


def _pad_table_row(cells: list[str], column_count: int) -> list[str]:
    """Normalize a row to the header width (pad short, truncate long rows)."""
    return cells[:column_count] + [""] * (column_count - len(cells))


def _column_alignments(separator_cells: list[str]) -> list[str]:
    """P2 remainder: alignment from the colons of the separator row
    (``:---`` left, ``:---:`` center, ``---:`` right, ``---`` left default)."""
    out = []
    for cell in separator_cells:
        left = cell.startswith(":")
        right = cell.endswith(":")
        if left and right:
            out.append("CENTER")
        elif right:
            out.append("RIGHT")
        else:
            out.append("LEFT")
    return out or ["LEFT"]


def _build_image_flowables(
    path_text: str,
    stats: dict,
    content_width: float,
    usable_height: float,
    body_style,
):
    """P2 chart embedding flowables for one ``![chart](path)`` marker line.

    An existing, readable local image is embedded scaled to the content
    width with the aspect ratio preserved - downscaled only (never upscaled,
    documented strategy) and capped to the usable page height. A missing or
    unreadable file renders an honest placeholder paragraph instead - the
    document build never crashes on a broken chart reference.
    """
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image, Paragraph

    path = Path(path_text.strip()).expanduser()
    try:
        if path.is_absolute() and path.is_file():
            image_width, image_height = ImageReader(str(path)).getSize()
            if image_width > 0 and image_height > 0:
                width = min(float(image_width), content_width)
                height = width * float(image_height) / float(image_width)
                if height > usable_height:
                    height = usable_height
                    width = height * float(image_width) / float(image_height)
                image = Image(str(path), width=width, height=height)
                image.spaceBefore = SPACING_UNIT_PT
                image.spaceAfter = SPACING_UNIT_PT
                stats["count"] += 1
                return [image]
    except Exception:
        pass
    stats["missing_count"] += 1
    placeholder = Paragraph(f"[chart missing: {path_text.strip()}]", body_style)
    placeholder.spaceBefore = SPACING_UNIT_PT
    placeholder.spaceAfter = SPACING_UNIT_PT
    return [placeholder]


def _build_render_manifest(
    citation_numbers: dict[str, int],
    inline_marker_count: int,
    *,
    title: str,
    callout_counts: dict[str, int],
    table_specs: list[dict],
    image_stats: dict,
    has_cover: bool,
    toc_entries: list[dict],
) -> dict:
    """Build-time render manifest: the measurable bridge between the
    token-driven build and ``validate_pdf_artifact`` (extended QA criteria).

    P2 additions are purely additive: callout/table/image counts, cover flag
    and TOC entries, plus the documented font strategy. ``schema_version``
    stays 1 - existing manifest consumers only read keys that never changed.
    """
    font_sizes = {spec["font_size_pt"] for spec in ROLE_STYLES.values()}
    font_sizes.add(FOOTER_FONT_PT)
    if citation_numbers:
        font_sizes.add(CITATION_MARKER_SIZE_PT)
    return {
        "generator": "ephe.create_pdf",
        "schema_version": 1,
        "title": title,
        "font_strategy": FONT_STRATEGY,
        "type_scale_ratio": TYPE_SCALE_RATIO,
        "type_scale_pt": list(TYPE_SCALE_PT),
        "font_sizes_pt": sorted(font_sizes),
        "roles": {role: ROLE_STYLES[role]["font_size_pt"] for role in ROLE_ORDER},
        "heading_roles": list(HEADING_ROLES),
        "margins_pt": dict(MARGINS_PT),
        "margins_mm": dict(MARGINS_MM),
        "citations": {
            "marker_format": "S###-C###",
            "inline_count": inline_marker_count,
            "references": [
                {"number": number, "chunk_id": chunk_id}
                for chunk_id, number in citation_numbers.items()
            ],
        },
        "callouts": {
            "count": sum(callout_counts.values()),
            "kinds": dict(callout_counts),
        },
        "tables": {
            "count": len(table_specs),
            "column_counts": [spec["columns"] for spec in table_specs],
        },
        "images": dict(image_stats),
        "has_cover": has_cover,
        "toc_entries": toc_entries,
    }


def _write_render_manifest(pdf_path: Path, manifest: dict) -> None:
    """Write the render manifest (QA sidecar) next to the PDF.

    The manifest carries the build-time style/margin values that
    ``validate_pdf_artifact`` measures. Persisting it must never fail the
    document itself - validation simply skips the extended checks when the
    sidecar is missing (foreign/legacy PDFs).
    """
    try:
        pdf_path.with_suffix(".doc-manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    except Exception:
        pass


def _normalize_pdf_filename(filename: str) -> str:
    safe_name = Path(filename).name
    safe_name = re.sub(r"\s+", "_", safe_name.strip())
    safe_name = re.sub(r"[^A-Za-z0-9._-]", "", safe_name)
    safe_name = re.sub(r"_+", "_", safe_name).strip("._-")
    if not safe_name:
        safe_name = "ephe_dokument.pdf"
    if not safe_name.lower().endswith(".pdf"):
        safe_name += ".pdf"
    return safe_name


def _build_pdf_styles(token_colors: dict):
    """Role styles + derived table/callout/TOC styles (token scale).

    Returns ``(styles, table_header_style, table_cell_style, callout_label_styles,
    toc_level_styles)`` — the same token scale as before the split, only outside
    the orchestration core.
    """
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_LEFT, TA_CENTER

    alignment_by_token = {"left": TA_LEFT, "center": TA_CENTER}
    styles: dict[str, ParagraphStyle] = {}
    for role in ROLE_ORDER:
        spec = ROLE_STYLES[role]
        styles[role] = ParagraphStyle(
            f"ephe-{role}",
            fontName=spec["font_name"],
            fontSize=spec["font_size_pt"],
            leading=spec["leading_pt"],
            textColor=token_colors[spec["text_color"]],
            alignment=alignment_by_token[spec["alignment"]],
            spaceBefore=spec["space_before_pt"],
            spaceAfter=spec["space_after_pt"],
            leftIndent=spec.get("left_indent_pt", 0),
            bulletIndent=spec.get("bullet_indent_pt", 0),
            bulletText=spec.get("bullet_text"),
            keepWithNext=spec.get("keep_with_next", False),
            allowWidows=0 if spec.get("no_widows") else 1,
            allowOrphans=0 if spec.get("no_orphans") else 0,
        )
    table_header_style = ParagraphStyle(
        "ephe-table-header", parent=styles["body"], fontName="Helvetica-Bold",
    )
    table_cell_style = styles["body"]
    callout_label_styles = {
        token_name: ParagraphStyle(
            f"ephe-callout-label-{token_name}",
            parent=styles["caption"],
            fontName="Helvetica-Bold",
            textColor=token_colors[token_name],
        )
        for token_name in {spec["bar_token"] for spec in CALLOUT_KINDS.values()}
    }
    toc_level_styles = [
        ParagraphStyle(
            "ephe-toc-level-1",
            fontName="Helvetica-Bold",
            fontSize=SIZE_H3_PT,
            leading=ROLE_STYLES["h3"]["leading_pt"],
            textColor=token_colors["ink"],
            spaceBefore=SPACING_HALF_UNIT_PT,
            spaceAfter=0,
        ),
        ParagraphStyle(
            "ephe-toc-level-2",
            fontName="Helvetica",
            fontSize=SIZE_BODY_PT,
            leading=ROLE_STYLES["body"]["leading_pt"],
            textColor=token_colors["ink"],
            leftIndent=1.5 * SPACING_UNIT_PT,
        ),
    ]
    return styles, table_header_style, table_cell_style, callout_label_styles, toc_level_styles


def _render_pdf_doc(story, out, document, title, toc, styles, token_colors, citation_numbers, inline_fn, footer_fn, a4):
    """Builds the reportlab document and renders it; returns ``(pages, toc_record)``.

    document=True → ``_TocDocTemplate`` (feeds marked H1/H2 into the TOC,
    ``multiBuild`` converges the page numbers); otherwise ``SimpleDocTemplate``.
    References section only when citation markers exist (unchanged).
    """
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    # W19 (E5): the real page count in the return — the agent/deliver text may
    # only claim "done" with a measured page count (no phantom document).
    if citation_numbers:
        story.append(Paragraph("References", styles["h1"]))
        for chunk_id, number in citation_numbers.items():
            story.append(Paragraph(inline_fn(citation_reference_text(number, chunk_id)), styles["citation"]))

    if document:
        class _TocDocTemplate(SimpleDocTemplate):
            """Feeds marked H1/H2 paragraphs into the TableOfContents.

            Headings travel inside KeepTogether groups, so afterFlowable
            introspects the container's content as well. document=False
            never uses this template and keeps the plain build path.
            """

            def afterFlowable(self, flowable):
                wrapped = getattr(flowable, "_content", None)
                for item in (wrapped if wrapped is not None else [flowable]):
                    entry = getattr(item, "_ephe_toc_entry", None)
                    if entry is not None:
                        self.notify("TOCEntry", (entry[0], entry[1], self.page))

        doc = _TocDocTemplate(
            str(out), pagesize=a4,
            rightMargin=MARGINS_PT["right"], leftMargin=MARGINS_PT["left"],
            topMargin=MARGINS_PT["top"], bottomMargin=MARGINS_PT["bottom"],
            title=title, author="Ephe", subject="Ephe report",
        )
    else:
        doc = SimpleDocTemplate(
            str(out), pagesize=a4,
            rightMargin=MARGINS_PT["right"], leftMargin=MARGINS_PT["left"],
            topMargin=MARGINS_PT["top"], bottomMargin=MARGINS_PT["bottom"],
            title=title, author="Ephe", subject="Ephe report",
        )

    if document:
        # multiBuild converges the TOC page numbers across passes.
        doc.multiBuild(story, onFirstPage=footer_fn, onLaterPages=footer_fn)
        toc_record = [
            {"level": int(level) + 1, "text": str(text), "page": int(page)}
            for level, text, page, _key in getattr(toc, "_entries", [])
        ]
    else:
        doc.build(story, onFirstPage=footer_fn, onLaterPages=footer_fn)
        toc_record = []
    pages = getattr(doc, "page", 0) or 1
    return pages, toc_record


async def create_pdf(
    title: str,
    content: str,
    filename: str = "ephe_dokument.pdf",
    template: str = "report",
    document: bool = False,
) -> str:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib import colors
        from reportlab.platypus import (
            HRFlowable,
            KeepTogether,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
        from reportlab.platypus.tableofcontents import TableOfContents
        from reportlab.lib.enums import TA_LEFT, TA_CENTER

        from core.engine_config import artifact_output_dir

        downloads = artifact_output_dir()
        out = downloads / _normalize_pdf_filename(filename)

        # P1 margin floor: margins come exclusively from doc_design tokens.
        # reportlab stores no margin metadata inside the PDF, so measurable
        # margin validation is manifest-based: the floor is asserted here at
        # build time and the token values are written to the render manifest.
        if min(MARGINS_MM.values()) < MARGIN_FLOOR_MM:
            raise ValueError("Document margins violate the 18 mm print floor.")

        content_width = A4[0] - MARGINS_PT["left"] - MARGINS_PT["right"]
        usable_height = A4[1] - MARGINS_PT["top"] - MARGINS_PT["bottom"]

        token_colors = {name: colors.HexColor(value) for name, value in COLOR_TOKENS.items()}

        (
            styles,
            table_header_style,
            table_cell_style,
            callout_label_styles,
            toc_level_styles,
        ) = _build_pdf_styles(token_colors)

        content = _apply_pdf_template(content, template)
        citation_numbers = scan_citation_numbers(content)
        inline_marker_count = len(CITATION_MARKER_RE.findall(content))
        title_norm = title.strip()

        # P2 render-manifest bookkeeping.
        callout_counts: dict[str, int] = {kind: 0 for kind in CALLOUT_KINDS}
        table_specs: list[dict] = []
        image_stats = {"count": 0, "missing_count": 0}
        toc_record: list[dict] = []

        def _inline(text: str) -> str:
            escaped = html.escape(text, quote=False)
            bolded = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", escaped)
            return _render_citation_markers(bolded, citation_numbers)

        story = []
        toc: TableOfContents | None = None
        if document:
            # P2 document mode: page 1 = cover (brand label, display title,
            # date), page 2 = TOC over the content H1/H2, then the content.
            # The in-flow title block is skipped - the cover carries it.
            toc = TableOfContents(levelStyles=toc_level_styles, dotsMinLevel=0)
            story.append(Spacer(1, 10 * SPACING_UNIT_PT))
            story.append(Paragraph(COVER_BRAND_LABEL, styles["meta"]))
            story.append(Spacer(1, 12 * SPACING_UNIT_PT))
            story.append(Paragraph(title, styles["cover_title"]))
            story.append(HRFlowable(
                width="30%",
                thickness=RULE_THICKNESS_PT,
                color=token_colors["accent"],
                spaceBefore=SPACING_UNIT_PT,
                spaceAfter=SPACING_UNIT_PT,
                hAlign="CENTER",
            ))
            story.append(Paragraph(datetime.now().strftime("%d.%m.%Y"), styles["meta"]))
            story.append(PageBreak())
            story.append(Paragraph(TOC_HEADING_TEXT, styles["h1"]))
            story.append(toc)
            story.append(PageBreak())
        else:
            story.append(Paragraph(title, styles["title"]))
            story.append(Paragraph(
                f"Created by Ephe - {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                styles["meta"],
            ))
            story.append(HRFlowable(
                width="100%",
                thickness=RULE_THICKNESS_PT,
                color=token_colors["accent"],
                spaceAfter=RULE_SPACE_AFTER_PT,
            ))

        def _heading(role: str, text: str) -> Paragraph:
            # TOC notification is attached only in document mode; the TOC
            # lists the content H1/H2 (generated sections like References
            # stay out - they carry no marker attribute).
            para = Paragraph(_inline(text), styles[role])
            if document and role in ("h1", "h2"):
                para._ephe_toc_entry = (0 if role == "h1" else 1, text)
            return para

        def _build_table(rows: list[str], alignments: list[str] | None = None) -> Table:
            """P2 markdown pipe table -> reportlab Table (full grid from the
            line token, accent_soft header row, 8 pt-grid cell padding,
            repeated header row). Width strategy: EQUAL column widths across
            the content width - deterministic and grid-friendly; long cell
            text wraps inside its column instead of resizing the table.
            P2-Restposten: column alignment from the separator colons and
            zebra striping on body rows (token blend, deterministic)."""
            from reportlab.lib.enums import TA_RIGHT
            from core.doc_design import blend_hex_toward_paper

            header = _split_table_row(rows[0])
            column_count = max(1, len(header))
            align_map = {"LEFT": TA_LEFT, "CENTER": TA_CENTER, "RIGHT": TA_RIGHT}
            column_alignments = (alignments or ["LEFT"] * column_count)[:column_count]
            while len(column_alignments) < column_count:
                column_alignments.append("LEFT")

            def _cell_style(base, alignment: str):
                return ParagraphStyle(
                    f"{base.name}-{alignment}",
                    parent=base,
                    alignment=align_map.get(alignment, TA_LEFT),
                )

            normalized = [header] + [_pad_table_row(_split_table_row(row), column_count) for row in rows[1:]]
            data = [
                [
                    Paragraph(
                        _inline(cell),
                        (
                            table_header_style
                            if row_index == 0
                            else _cell_style(table_cell_style, column_alignments[col_index])
                        ),
                    )
                    for col_index, cell in enumerate(table_row)
                ]
                for row_index, table_row in enumerate(normalized)
            ]
            grid = Table(
                data,
                colWidths=[content_width / column_count] * column_count,
                repeatRows=1,
                hAlign="LEFT",
            )
            zebra_tint = blend_hex_toward_paper(token_colors["accent_soft"].hexval().replace("0x", "#"), 0.10)
            grid.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), RULE_THICKNESS_PT, token_colors["line"]),
                ("BACKGROUND", (0, 0), (-1, 0), token_colors["accent_soft"]),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [token_colors["paper"], zebra_tint]),
                ("LEFTPADDING", (0, 0), (-1, -1), SPACING_UNIT_PT),
                ("RIGHTPADDING", (0, 0), (-1, -1), SPACING_UNIT_PT),
                ("TOPPADDING", (0, 0), (-1, -1), SPACING_HALF_UNIT_PT),
                ("BOTTOMPADDING", (0, 0), (-1, -1), SPACING_HALF_UNIT_PT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            grid.spaceBefore = SPACING_UNIT_PT
            grid.spaceAfter = SPACING_UNIT_PT
            table_specs.append({"columns": column_count})
            return grid

        def _build_callout(kind: str, paragraph_texts: list[str]) -> Table:
            """P2 callout box: tinted surface (token blend) + left accent bar,
            label in the caption role, body text in the body role."""
            spec = CALLOUT_KINDS[kind]
            flowables: list = [Paragraph(spec["label"], callout_label_styles[spec["bar_token"]])]
            flowables.extend(Paragraph(_inline(text), table_cell_style) for text in paragraph_texts)
            box = Table([[flowables]], colWidths=[content_width])
            box.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1),
                 colors.HexColor(blend_hex_toward_paper(COLOR_TOKENS[spec["surface_token"]]))),
                ("LINEBEFORE", (0, 0), (0, -1), CALLOUT_BAR_THICKNESS_PT, token_colors[spec["bar_token"]]),
                ("LEFTPADDING", (0, 0), (-1, -1), SPACING_UNIT_PT + CALLOUT_BAR_THICKNESS_PT),
                ("RIGHTPADDING", (0, 0), (-1, -1), SPACING_UNIT_PT),
                ("TOPPADDING", (0, 0), (-1, -1), SPACING_HALF_UNIT_PT),
                ("BOTTOMPADDING", (0, 0), (-1, -1), SPACING_HALF_UNIT_PT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ]))
            box.spaceBefore = SPACING_UNIT_PT
            box.spaceAfter = SPACING_UNIT_PT
            callout_counts[kind] = callout_counts.get(kind, 0) + 1
            return box

        def _flush(group: list):
            if not group:
                return
            story.append(KeepTogether(list(group)) if len(group) > 1 else group[0])

        group: list = []
        in_appendix = False
        raw_lines = [_san(line.strip()) for line in content.splitlines()]
        index = 0
        while index < len(raw_lines):
            line = raw_lines[index]
            if not line:
                index += 1
                continue

            # P2 chart embedding: whole-line ![chart](/absolute/path.png).
            image_match = IMAGE_MARKER_RE.match(line)
            if image_match:
                _flush(group)
                group = []
                story.extend(_build_image_flowables(
                    image_match.group(1), image_stats, content_width, usable_height, table_cell_style,
                ))
                index += 1
                continue

            # P2 tables: a pipe row followed by a separator row opens a block.
            if line.startswith("|") and index + 1 < len(raw_lines) and _is_table_separator(raw_lines[index + 1]):
                _flush(group)
                group = []
                block = [line]
                separator_cells = _split_table_row(raw_lines[index + 1])
                index += 2  # header + separator consumed
                while index < len(raw_lines) and raw_lines[index].startswith("|"):
                    block.append(raw_lines[index])
                    index += 1
                story.append(_build_table(block, _column_alignments(separator_cells)))
                continue

            # P2 callouts: GitHub-style "> [!NOTE]" marker + quoted body.
            callout_match = CALLOUT_MARKER_RE.match(line)
            if callout_match:
                _flush(group)
                group = []
                kind = callout_match.group(1).lower()
                index += 1
                paragraphs: list[list[str]] = [[]]
                while index < len(raw_lines) and raw_lines[index].startswith(">"):
                    if CALLOUT_MARKER_RE.match(raw_lines[index]):
                        break  # a new marker opens the next callout block
                    body_line = raw_lines[index][1:].strip()
                    if body_line:
                        paragraphs[-1].append(body_line)
                    elif paragraphs[-1]:
                        paragraphs.append([])
                    index += 1
                story.append(_build_callout(kind, [" ".join(part) for part in paragraphs if part]))
                continue

            if line.startswith("## Evidence Appendix"):
                _flush(group)
                group = [_heading("h2", line[3:])]
                in_appendix = True
                index += 1
                continue
            if line.startswith("### "):
                _flush(group)
                group = [_heading("h3", line[4:])]
                index += 1
                continue
            if line.startswith("## "):
                _flush(group)
                group = [_heading("h2", line[3:])]
                index += 1
                continue
            if line.startswith("# "):
                if line[2:].strip() == title_norm:
                    index += 1
                    continue
                _flush(group)
                group = [_heading("h1", line[2:])]
                index += 1
                continue
            if line.startswith(("- ", "* ")):
                para = Paragraph(_inline(line[2:]), styles["appendix"] if in_appendix else styles["bullet"])
            elif re.match(r"^\d+\.\s+", line):
                para = Paragraph(_inline(line), styles["appendix"] if in_appendix else styles["numbered"])
            else:
                para = Paragraph(_inline(line), styles["appendix"] if in_appendix else styles["body"])
            if len(group) >= 3:
                _flush(group)
                group = []
            group.append(para)
            index += 1
        _flush(group)

        def _footer(canvas, pdf_doc):
            canvas.saveState()
            canvas.setFont("Helvetica", FOOTER_FONT_PT)
            canvas.setFillColor(token_colors["muted"])
            canvas.drawString(MARGINS_PT["left"], FOOTER_BASELINE_PT, "Ephe")
            canvas.drawRightString(A4[0] - MARGINS_PT["right"], FOOTER_BASELINE_PT, f"Seite {pdf_doc.page}")
            canvas.restoreState()

        pages, toc_record = _render_pdf_doc(
            story, out, document, title, toc, styles, token_colors,
            citation_numbers, _inline, _footer, A4,
        )
        _write_render_manifest(out, _build_render_manifest(
            citation_numbers,
            inline_marker_count,
            title=title,
            callout_counts=callout_counts,
            table_specs=table_specs,
            image_stats=image_stats,
            has_cover=document,
            toc_entries=toc_record,
        ))
        return f"PDF_FILE:{out}\nPDF_PAGES:{pages}"

    except ImportError:
        return "[pdf: reportlab is not installed — 'pip install reportlab']"
    except Exception as e:
        return f"[pdf-Fehler: {e}]"
