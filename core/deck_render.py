"""Deck Engine v2 renderers for PDF, PPTX, preview, and Studio artifacts."""
from __future__ import annotations

import html
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from core.deck_design import ROLE_LABELS, theme_palette
from core.deck_quality import evidence_ledger, qa_pdf_render, score_deck_spec


def deck_bundle_dir(main_path: Path) -> Path:
    """Canonical home of the diagnostic sidecars: ``<out>/artifacts/<stem>/``.

    The deliverable artifacts (pdf/pptx/preview/contact-sheet/studio) stay in the out
    folder; only the internal QA-/score/manifest JSONs move into the bundle. Keeps the
    Downloads folder at 1-2 visible files per deck (parity harness, wave 8).
    """
    return main_path.parent / "artifacts" / main_path.stem


def _write_json(path: Path, payload: dict) -> Path:
    # Wave 12 (L2): every bundle JSON becomes a first-class, versioned
    # work product (arXiv 2605.12087: typed, addressable, versioned, dependency-aware).
    # artifact_id = <name>@<iso-ts>; supersedes points at the artifact_id of the
    # previous version, if the file already existed (lineage chain).
    path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    supersedes: str | None = None
    if path.exists():
        try:
            prev = json.loads(path.read_text(encoding="utf-8"))
            supersedes = prev.get("artifact_id")
        except Exception:
            supersedes = None
    stamped = {
        "artifact_id": f"{path.name}@{generated_at}",
        "generated_at": generated_at,
        "supersedes": supersedes,
    }
    stamped.update(payload)
    path.write_text(json.dumps(stamped, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_deck_artifacts(
    *,
    spec: dict,
    pdf_path: Path,
    pptx_path: Path | None = None,
    include_preview: bool = True,
) -> dict[str, Path]:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    write_pdf(pdf_path, spec)
    render_qa = qa_pdf_render(pdf_path, spec)
    score = score_deck_spec(spec, render_qa=render_qa)
    ledger = evidence_ledger(spec)
    bundle = deck_bundle_dir(pdf_path)
    paths: dict[str, Path] = {"pdf": pdf_path}
    # Shared diagnostic sidecars: written ONCE. the pdf and pptx branches share
    # the same stem -> the same bundle file; no double write (wave 8, L6).
    paths["scorecard"] = _write_json(bundle / "scorecard.json", score)
    paths["manifest"] = _write_json(bundle / "manifest.json", _manifest(spec))
    paths["deck_spec"] = _write_json(bundle / "deck-spec.json", spec)
    # Wave 11 (L3): one canonical QA report per format. The visual checks are
    # a section in the primary QA report, not a second file with a contradictory
    # artifact_type (arXiv 2605.12087: one authoritative record).
    render_qa["visual"] = _visual_qa(spec, score)
    paths["render_qa"] = _write_json(bundle / "render-qa.json", render_qa)
    paths["visual_qa"] = paths["render_qa"]
    paths["evidence_ledger"] = _write_json(bundle / "evidence-ledger.json", ledger)
    if include_preview:
        preview_path = pdf_path.with_suffix(".preview.html")
        preview_path.write_text(render_preview(spec, score), encoding="utf-8")
        paths["preview"] = preview_path
    if pptx_path:
        write_pptx(pptx_path, spec)
        paths["pptx"] = pptx_path
        qa = qa_pptx_file(pptx_path)
        qa["visual"] = _visual_qa(spec, score)
        paths["pptx_qa"] = _write_json(bundle / "qa.json", qa)
        contact_path = pptx_path.with_suffix(".contact-sheet.html")
        contact_path.write_text(render_contact_sheet(spec, qa, score), encoding="utf-8")
        paths["contact_sheet"] = contact_path
    return paths


def _manifest(spec: dict) -> dict:
    return {
        "artifact_type": "pitch_deck",
        "schema_version": 2,
        "title": spec.get("title"),
        "enterprise_grade": spec.get("enterprise_grade", True),
        "theme": spec.get("theme", {}),
        "claim_spine": [slide.get("takeaway", "") for slide in spec.get("slides", [])],
        "slides": spec.get("slides", []),
        "evidence": spec.get("evidence", {}),
    }


def _visual_qa(spec: dict, score: dict) -> dict:
    roles = [slide.get("role", "") for slide in spec.get("slides", [])]
    visuals = [slide.get("visual_spec", {}).get("type", "") for slide in spec.get("slides", [])]
    return {
        "artifact_type": "deck_visual_qa",
        "status": "passed" if score.get("checks", {}).get("layout_roles_varied") and score.get("checks", {}).get("no_repeated_standard_visuals") else "failed",
        "distinct_layout_roles": len(set(roles)),
        "distinct_visuals": len(set(visuals)),
        "roles": roles,
        "warnings": score.get("warnings", []),
    }


def write_pdf(path: Path, spec: dict) -> None:
    width, height = 720, 405
    palette = theme_palette(spec.get("theme", {}).get("design_theme", "executive"))
    streams = []
    slides = spec.get("slides", [])
    for index, slide in enumerate(slides, 1):
        role = slide.get("role", "executive_summary")
        stream = [
            f"{palette['paper']} rg 0 0 {width} {height} re f\n",
            f"{palette['band']} rg 0 0 {width} 10 re f\n",
            _text(f"{index:02d} / {len(slides):02d}", 46, 370, 8, "F1", palette["muted"]),
            _text(_footer_label(spec), 520, 370, 8, "F1", palette["muted"]),
            _text(ROLE_LABELS.get(role, role.replace("_", " ").title()), 48, 350, 8, "F2", palette["accent"]),
        ]
        _draw_layout(stream, slide, role, palette)
        source_label = _source_label(slide)
        stream.append(_text(f"{source_label} | Local artifact generated by Ephe", 48, 28, 7, "F1", palette["muted"]))
        streams.append("".join(stream))
    _write_pdf_package(path, streams, width, height, spec.get("title", "Ephe Deck"))


def _draw_layout(stream: list[str], slide: dict, role: str, palette: dict[str, str]) -> None:
    if role == "cover":
        _headline_block(stream, slide, 48, 300, 31, 20, palette, title_chars=26, takeaway_chars=48, takeaway_lines=4, points_offset=180)
        stream.append(f"{palette['soft']} rg 540 82 90 90 re f {palette['accent']} RG 2 w 556 98 58 58 re S\n")
        stream.append(f"{palette['band']} rg 648 82 34 90 re f\n")
        return
    if role == "executive_summary":
        _headline_block(stream, slide, 48, 318, 28, 22, palette, points=False)
        for i, point in enumerate((slide.get("supporting_points") or [])[:3]):
            x = 64 + i * 205
            stream.append(f"1 1 1 rg {x} 86 168 112 re f {palette['line']} RG {x} 86 168 112 re S\n")
            stream.append(_text(str(i + 1).zfill(2), x + 16, 166, 18, "F2", palette["accent"]))
            _wrap_text(stream, point, x + 16, 142, 10, 20, palette["ink"], max_chars=24, max_lines=4)
        return
    if role in {"problem", "risk_controls"}:
        _headline_block(stream, slide, 48, 318, 28, 17, palette, takeaway_chars=34, points=False)
        labels = (slide.get("supporting_points") or [])[:4]
        for i, point in enumerate(labels):
            y = 218 - i * 50
            stream.append(f"{palette['warn']} RG 1.4 w 452 {y} 188 36 re S\n")
            _wrap_text(stream, point, 464, y + 22, 8, 11, palette["ink"], max_chars=28, max_lines=2)
        return
    if role == "market_map":
        _headline_block(stream, slide, 48, 318, 28, 22, palette, points=False)
        for i, point in enumerate((slide.get("supporting_points") or [])[:3]):
            x = 386 + (i % 2) * 118
            y = 182 - (i // 2) * 70
            stream.append(f"{palette['soft']} rg {x} {y} 104 52 re f {palette['line']} RG {x} {y} 104 52 re S\n")
            _wrap_text(stream, point, x + 10, y + 33, 8, 12, palette["ink"], max_chars=18, max_lines=2)
        return
    if role == "architecture":
        _headline_block(stream, slide, 48, 318, 28, 17, palette, takeaway_chars=36, takeaway_lines=4)
        xs = [370, 470, 570]
        for i, label in enumerate(("Model", "Tools", "QA")):
            stream.append(f"{palette['soft']} rg {xs[i]} 116 76 62 re f {palette['band']} RG 1.6 w {xs[i]} 116 76 62 re S\n")
            stream.append(_text(label, xs[i] + 18, 143, 10, "F2", palette["ink"]))
            if i < 2:
                stream.append(f"{palette['accent']} RG 1.4 w {xs[i]+76} 147 m {xs[i+1]} 147 l S\n")
        return
    if role == "workflow":
        _headline_block(stream, slide, 48, 318, 28, 17, palette, takeaway_chars=36, takeaway_lines=4)
        for i, label in enumerate(("Plan", "Execute", "Validate", "Deliver")):
            x = 342 + i * 78
            stream.append(f"{palette['accent']} rg {x} 116 46 46 re f\n")
            stream.append(_text(label, x - 2, 96, 8, "F2", palette["ink"]))
            if i < 3:
                stream.append(f"{palette['band']} RG 1.2 w {x+46} 139 m {x+74} 139 l S\n")
        return
    if role == "comparison_matrix":
        _headline_block(stream, slide, 48, 318, 28, 22, palette)
        stream.append(f"{palette['line']} RG 1 w 350 110 280 150 re S\n")
        for i, label in enumerate(("Control", "Quality", "Runtime")):
            y = 230 - i * 44
            stream.append(_text(label, 368, y, 9, "F2", palette["ink"]))
            stream.append(f"{palette['accent']} rg 510 {y-4} 72 14 re f\n")
        return
    if role == "roadmap":
        _headline_block(stream, slide, 48, 318, 28, 22, palette, points=False)
        stream.append(f"{palette['band']} RG 1.8 w 350 178 m 632 178 l S\n")
        for i, point in enumerate((slide.get("supporting_points") or [])[:4]):
            x = 354 + i * 72
            stream.append(f"{palette['accent']} rg {x} 170 16 16 re f\n")
            _wrap_text(stream, point, x - 8, 150, 7, 10, palette["ink"], max_chars=14, max_lines=3)
        return
    if role == "ask":
        _headline_block(stream, slide, 48, 318, 28, 22, palette)
        stream.append(f"{palette['band']} rg 386 126 218 118 re f\n")
        stream.append(_text("Approve", 422, 188, 30, "F2", "1 1 1"))
        return
    if role == "appendix_sources":
        _headline_block(stream, slide, 48, 318, 26, 20, palette)
        _wrap_text(stream, spec_source_text(slide), 356, 220, 9, 15, palette["muted"], max_chars=48, max_lines=8)
        return
    _headline_block(stream, slide, 48, 318, 28, 22, palette)
    stream.append(f"{palette['soft']} rg 386 118 226 134 re f {palette['line']} RG 386 118 226 134 re S\n")


def _headline_block(stream: list[str], slide: dict, x: int, y: int, title_size: int, takeaway_size: int, palette: dict[str, str], *, title_chars: int = 34, takeaway_chars: int = 52, takeaway_lines: int = 3, points_offset: int = 165, points: bool = True) -> None:
    _wrap_text(stream, slide.get("headline", ""), x, y, title_size, title_size + 4, palette["ink"], "F2", title_chars, 2)
    _wrap_text(stream, slide.get("takeaway", ""), x, y - 74, takeaway_size, takeaway_size + 8, palette["band"], "F2", takeaway_chars, takeaway_lines)
    # Wave 13: points=False when the role branch draws the supporting_points
    # itself as boxes — otherwise they duplicate (bullets + boxes) in the same stream.
    if not points:
        return
    y2 = y - points_offset
    for point in (slide.get("supporting_points") or [])[:4]:
        stream.append(f"{palette['accent']} rg {x} {y2+3} 5 5 re f\n")
        _wrap_text(stream, point, x + 16, y2, 10, 15, palette["muted"], "F1", 62, 2)
        y2 -= 36


def _source_label(slide: dict) -> str:
    return {
        "source_grounded": "Source-grounded",
        "user_provided": "User-provided",
        "mixed": "Mixed evidence",
    }.get(slide.get("source_status"), "Assumption-led")


def spec_source_text(slide: dict) -> str:
    return " ".join(slide.get("supporting_points") or []) or slide.get("takeaway", "")


def _footer_label(spec: dict) -> str:
    brand = (spec.get("brand_kit") or {}).get("brand_name") or "Ephe"
    return f"{brand} local deck"


def _wrap_text(stream: list[str], text: str, x: float, y: float, size: int, line_height: int, color: str, font: str = "F1", max_chars: int = 64, max_lines: int = 4) -> None:
    for i, line in enumerate(_split_lines(text, max_chars, max_lines)):
        stream.append(_text(line, x, y - i * line_height, size, font, color))


def _split_lines(text: str, max_chars: int, max_lines: int) -> list[str]:
    words = str(text or "").split()
    lines, current = [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines[:max_lines] or [""]


def _text(text: str, x: float, y: float, size: int, font: str, color: str) -> str:
    return f"BT {color} rg /{font} {size} Tf {x:.1f} {y:.1f} Td ({_pdf_escape(text)}) Tj ET\n"


def _pdf_escape(text: str) -> str:
    return str(text or "").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace("\n", " ")


def _write_pdf_package(path: Path, streams: list[str], width: int, height: int, title: str) -> None:
    objects, kids = [], []
    page_obj_start = 4
    for i, stream in enumerate(streams):
        page_obj = page_obj_start + i * 2
        content_obj = page_obj + 1
        kids.append(f"{page_obj} 0 R")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            f"/Resources << /Font << /F1 3 0 R /F2 {3 + len(streams) * 2 + 1} 0 R >> >> /Contents {content_obj} 0 R >>".encode("latin-1", "replace")
        )
        b = stream.encode("latin-1", "replace")
        objects.append(f"<< /Length {len(b)} >>\nstream\n".encode("latin-1") + b + b"endstream")
    bold_obj = 3 + len(streams) * 2 + 1
    all_objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(streams)} >>".encode("latin-1"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ] + objects + [b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"]
    if len(all_objects) != bold_obj:
        raise ValueError("PDF object numbering mismatch")
    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(all_objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("latin-1"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(all_objects)+1}\n0000000000 65535 f \n".encode("latin-1"))
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    output.extend(f"trailer << /Size {len(all_objects)+1} /Root 1 0 R /Info << /Title ({_pdf_escape(title)}) /Author (Ephe) >> >>\nstartxref\n{xref}\n%%EOF\n".encode("latin-1", "replace"))
    path.write_bytes(output)


def write_pptx(path: Path, spec: dict) -> None:
    slides = spec.get("slides", [])
    slide_overrides = "\n".join(f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>' for i in range(1, len(slides)+1))
    slide_ids = "\n".join(f'<p:sldId id="{255+i}" r:id="rId{i}"/>' for i in range(1, len(slides)+1))
    rels = "\n".join(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>' for i in range(1, len(slides)+1))
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as pptx:
        pptx.writestr("[Content_Types].xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/><Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/><Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>{slide_overrides}</Types>''')
        pptx.writestr("_rels/.rels", '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>''')
        pptx.writestr("ppt/presentation.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldIdLst>{slide_ids}</p:sldIdLst><p:sldSz cx="12192000" cy="6858000" type="wide"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>''')
        pptx.writestr("ppt/_rels/presentation.xml.rels", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>''')
        pptx.writestr("docProps/core.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><dc:title>{_xml(spec.get("title"))}</dc:title><dc:creator>Ephe</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created><dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified></cp:coreProperties>''')
        pptx.writestr("docProps/app.xml", f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>Ephe</Application><Slides>{len(slides)}</Slides></Properties>''')
        for index, slide in enumerate(slides, 1):
            pptx.writestr(f"ppt/slides/slide{index}.xml", _pptx_slide_xml(index, len(slides), slide, spec))


def _pptx_slide_xml(index: int, total: int, slide: dict, spec: dict) -> str:
    role = slide.get("role", "slide")
    title = slide.get("headline", "")
    takeaway = slide.get("takeaway", "")
    points = slide.get("supporting_points", [])[:4]
    shapes = [
        _pptx_rect(2, 0, 0, 13.333, 7.5, "FBFCFB"),
        _pptx_rect(3, 0, 7.34, 13.333, 0.16, "101820"),
        _pptx_text(4, ROLE_LABELS.get(role, role), 0.7, 0.45, 2.4, 0.25, 8, "16A34A", True),
        _pptx_text(5, f"{index:02d} / {total:02d}", 11.2, 0.45, 1.0, 0.25, 8, "56616B", False),
        _pptx_text(6, title, 0.7, 1.05, 5.8, 0.85, 25, "101820", True),
        _pptx_text(7, takeaway, 0.7, 2.15, 6.5, 1.0, 15, "0F5132", True),
    ]
    for i, point in enumerate(points):
        shapes.append(_pptx_text(8 + i, f"- {point}", 0.9, 3.35 + i * 0.43, 6.4, 0.32, 10, "56616B", False))
    shapes.extend(_pptx_visual_shapes(30, role))
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>{''.join(shapes)}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'''


def _pptx_visual_shapes(start_id: int, role: str) -> list[str]:
    if role in {"architecture", "workflow"}:
        return [_pptx_rect(start_id + i, 7.6 + i * 1.05, 2.55, 0.78, 0.62, "EEF7F1", "16A34A") for i in range(4)]
    if role in {"problem", "risk_controls"}:
        return [_pptx_rect(start_id + i, 7.7, 2.1 + i * 0.82, 3.7, 0.45, "FFFFFF", "C45613") for i in range(4)]
    if role == "roadmap":
        return [_pptx_rect(start_id + i, 7.3 + i * 0.95, 3.25, 0.35, 0.35, "16A34A") for i in range(4)]
    if role == "ask":
        return [_pptx_rect(start_id, 7.5, 2.2, 3.2, 1.4, "101820"), _pptx_text(start_id + 1, "Approve", 8.1, 2.72, 2.2, 0.48, 26, "FFFFFF", True)]
    return [_pptx_rect(start_id, 7.4, 1.85, 3.9, 3.1, "EEF7F1", "D6E3DC"), _pptx_rect(start_id + 1, 8.0, 2.55, 1.1, 1.1, "16A34A")]


def _pptx_text(shape_id: int, text: str, x: float, y: float, w: float, h: float, font_size: int, color: str, bold: bool) -> str:
    b = ' b="1"' if bold else ""
    return f'''<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="Text {shape_id}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="{_emu(x)}" y="{_emu(y)}"/><a:ext cx="{_emu(w)}" cy="{_emu(h)}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></p:spPr><p:txBody><a:bodyPr wrap="square"/><a:lstStyle/><a:p><a:r><a:rPr lang="en-US" sz="{font_size*100}"{b}><a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:latin typeface="Aptos"/></a:rPr><a:t>{_xml(text)}</a:t></a:r></a:p></p:txBody></p:sp>'''


def _pptx_rect(shape_id: int, x: float, y: float, w: float, h: float, fill: str, line: str | None = None) -> str:
    line_xml = f'<a:ln><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln>' if line else '<a:ln><a:noFill/></a:ln>'
    return f'''<p:sp><p:nvSpPr><p:cNvPr id="{shape_id}" name="Visual {shape_id}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="{_emu(x)}" y="{_emu(y)}"/><a:ext cx="{_emu(w)}" cy="{_emu(h)}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>{line_xml}</p:spPr><p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody></p:sp>'''


def _emu(inches: float) -> int:
    return int(inches * 914400)


def _xml(text: object) -> str:
    return html.escape(str(text or ""), quote=True)


def qa_pptx_file(path: Path) -> dict:
    warnings, slides = [], []
    try:
        with zipfile.ZipFile(path) as pptx:
            slide_names = sorted(name for name in pptx.namelist() if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
            for index, slide_name in enumerate(slide_names, 1):
                xml = pptx.read(slide_name).decode("utf-8", errors="replace")
                texts = [html.unescape(t).strip() for t in __import__("re").findall(r"<a:t>(.*?)</a:t>", xml) if t.strip()]
                if "Proof Object:" in xml or "Animation Plan" in xml:
                    warnings.append(f"Slide {index} contains internal marker text.")
                slides.append({"slide": index, "editable_text_runs": xml.count("<a:t>"), "text_chars": sum(len(t) for t in texts), "preview_text": texts[:5]})
            if len(slide_names) < 8:
                warnings.append("PPTX deck has fewer than 8 slides.")
    except Exception as exc:
        warnings.append(f"PPTX QA failed: {exc}")
    return {"artifact_type": "pptx_visual_qa", "path": str(path), "slide_count": len(slides), "status": "passed" if not warnings else "warning", "slides": slides, "warnings": warnings, "contact_sheet": str(path.with_suffix(".contact-sheet.html"))}


def render_contact_sheet(spec: dict, qa: dict, score: dict) -> str:
    cards = "".join(f"<article><span>{i:02d} · {html.escape(s.get('role',''))}</span><h2>{html.escape(s.get('headline',''))}</h2><p>{html.escape(s.get('takeaway',''))}</p><b>{html.escape(s.get('source_status',''))}</b></article>" for i, s in enumerate(spec.get("slides", []), 1))
    warnings = "".join(f"<li>{html.escape(str(w))}</li>" for w in score.get("warnings", [])) or "<li>No blocking warnings.</li>"
    return f"<!doctype html><meta charset='utf-8'><title>Deck Contact Sheet</title><style>body{{font-family:Inter,Arial,sans-serif;background:#f8faf9;color:#101820;padding:28px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px}}article{{background:white;border:1px solid #d9e2dc;border-left:5px solid #16a34a;padding:16px;min-height:180px}}span{{font-size:11px;color:#0f5132;font-weight:800;text-transform:uppercase}}h2{{font-size:19px}}p,li,b{{color:#56616b;font-size:13px;line-height:1.45}}</style><h1>{html.escape(spec.get('title','Deck'))}</h1><p>Quality {score.get('quality_score')}/100 · {score.get('status')}</p><section class='grid'>{cards}</section><h2>Warnings</h2><ul>{warnings}</ul>"


def render_preview(spec: dict, score: dict) -> str:
    # Wave 9 (L5): WYSIWYG — the preview mirrors the PDF layout 1:1. The same
    # theme palette, the same elements per slide (index line, role label,
    # headline, takeaway, supporting points, source footer line) as in write_pdf.
    palette = theme_palette(spec.get("theme", {}).get("design_theme", "executive"))
    footer = _footer_label(spec)
    slides = spec.get("slides", [])
    total = len(slides)
    sections = []
    for index, slide in enumerate(slides, 1):
        role = slide.get("role", "")
        role_label = ROLE_LABELS.get(role, role.replace("_", " ").title())
        points = "".join(
            f"<li>{html.escape(p)}</li>" for p in (slide.get("supporting_points") or [])[:4]
        )
        sections.append(
            "<section>"
            f"<div class='idx'><span>{index:02d} / {total:02d}</span><span>{html.escape(footer)}</span></div>"
            f"<small>{html.escape(role_label)}</small>"
            f"<h1>{html.escape(slide.get('headline',''))}</h1>"
            f"<p>{html.escape(slide.get('takeaway',''))}</p>"
            f"<ul>{points}</ul>"
            f"<footer>{html.escape(_source_label(slide))} | Local artifact generated by Ephe</footer>"
            "</section>"
        )
    body = "".join(sections)
    return (
        "<!doctype html><meta charset='utf-8'>"
        f"<title>{html.escape(spec.get('title','Deck'))}</title>"
        "<style>"
        "@keyframes enter{from{opacity:0;transform:translateY(18px)}to{opacity:1;transform:none}}"
        f"body{{margin:0;background:{palette.get('paper','#fbfcfb')};color:{palette.get('ink','#101820')};font-family:Inter,Arial,sans-serif}}"
        "section{min-height:100vh;display:grid;align-content:center;padding:8vw;animation:enter .5s ease both;"
        f"border-bottom:1px solid {palette.get('line','#d9e2dc')};position:relative}}"
        f".idx{{display:flex;justify-content:space-between;font-size:11px;color:{palette.get('muted','#56616b')};letter-spacing:.08em}}"
        f"small{{color:{palette.get('accent','#16a34a')};text-transform:uppercase;font-weight:800;letter-spacing:.16em;margin-top:10px}}"
        "h1{font-size:clamp(40px,7vw,96px);line-height:.94;max-width:1000px;margin:.3em 0}"
        "p{font-size:clamp(18px,2.2vw,30px);line-height:1.3;max-width:900px;color:"
        f"{palette.get('ink','#101820')}}}"
        f"ul{{max-width:900px;padding-left:1.2em;color:{palette.get('muted','#56616b')};line-height:1.5}}"
        "li{margin:.25em 0}"
        f"footer{{position:absolute;left:8vw;bottom:4vw;font-size:11px;color:{palette.get('muted','#56616b')}}}"
        f"</style>{body}"
    )


def render_studio(spec: dict, paths: dict[str, Path], wants_images: bool) -> str:
    score = json.loads(paths["scorecard"].read_text(encoding="utf-8"))
    cards = [
        ("Download PDF", paths.get("pdf"), "Share-ready PDF"),
        ("Download PPTX", paths.get("pptx"), "Editable PowerPoint"),
        ("Open Preview", paths.get("preview"), "Animated HTML preview"),
        ("Open Contact Sheet", paths.get("contact_sheet"), "Slide-by-slide QA"),
        ("Open QA Report", paths.get("pptx_qa") or paths.get("render_qa"), "Deterministic export checks"),
        ("Open Claim Manifest", paths.get("manifest"), "Storyline, claims, and export metadata"),
        ("Open DeckSpec", paths.get("deck_spec"), "Structured v2 deck model"),
        ("Open Visual QA", paths.get("visual_qa"), "Layout and visual checks"),
        ("Open Evidence Ledger", paths.get("evidence_ledger"), "Claim-to-evidence status"),
        ("Open Scorecard", paths.get("scorecard"), "Quality score breakdown"),
    ]
    download_html = "".join(f"<a class='download' data-qa='deck-studio-download' href='file://{html.escape(str(path))}'><b>{html.escape(label)}</b><span>{html.escape(desc)}</span><small>{html.escape(path.name)}</small></a>" for label, path, desc in cards if path)
    slide_html = "".join(f"<article><span>{i:02d} · {html.escape(slide.get('role',''))}</span><h3>{html.escape(slide.get('headline',''))}</h3><p>{html.escape(slide.get('takeaway',''))}</p><b>{html.escape(slide.get('source_status',''))}</b></article>" for i, slide in enumerate(spec.get("slides", []), 1))
    warnings = list(score.get("warnings", []))
    if wants_images and spec.get("evidence", {}).get("asset_status") == "missing_requested_assets":
        warnings.append("Image request detected, but no local image or brand assets were provided.")
    warning_html = "".join(f"<li>{html.escape(str(w))}</li>" for w in warnings) or "<li>No blocking warnings.</li>"
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(spec.get('title','Deck'))} - Ephe Slide Studio</title><style>
body{{margin:0;background:#fbfcfb;color:#101820;font-family:Inter,Aptos,Arial,sans-serif}}header{{min-height:64vh;display:grid;align-content:end;padding:7vw 8vw 5vw;background:linear-gradient(135deg,#f8faf7,#eef7f1)}}.eyebrow{{font-size:12px;letter-spacing:.18em;text-transform:uppercase;color:#0f5132;font-weight:900}}h1{{font-size:clamp(44px,7vw,94px);line-height:.92;max-width:980px}}.lead{{font-size:22px;color:#56616b;max-width:820px}}main{{padding:34px 8vw 70px}}.score{{display:inline-flex;gap:12px;background:white;border:1px solid #d9e2dc;padding:12px 16px}}.score b{{font-size:30px;color:#0f5132}}.downloads,.grid,.scores{{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px}}.download,article,.scorecard{{background:white;border:1px solid #d9e2dc;border-left:5px solid #16a34a;padding:18px;text-decoration:none;color:#101820}}.download span,.download small,p,li{{color:#56616b;line-height:1.42}}article span{{font-size:11px;color:#0f5132;text-transform:uppercase;font-weight:900}}.warnings{{margin-top:28px;background:#fffaf0;border-left:5px solid #b7791f;padding:18px}}</style><header><div class="eyebrow">Ephe Slide Studio · Deck Engine v2</div><h1>{html.escape(spec.get('title','Deck'))}</h1><p class="lead">Choose the output, inspect evidence coverage, and review visual QA before sharing.</p><div class="score"><b>{score.get('quality_score')}/100</b><span>{html.escape(score.get('status','unknown'))} · evidence {html.escape(spec.get('evidence',{}).get('status',''))}</span></div></header><main><h2>Choose Output</h2><section class="downloads">{download_html}</section><h2>Score Breakdown</h2><section class="scores">{_score_cards(score)}</section><h2>Slide Contact Sheet</h2><section class="grid">{slide_html}</section><section class="warnings"><b>Quality Notes</b><ul>{warning_html}</ul></section></main></html>"""


def _score_cards(score: dict) -> str:
    keys = ("narrative_score", "layout_score", "visual_variety_score", "evidence_score", "brand_fit_score", "export_score")
    return "".join(f"<div class='scorecard'><b>{key.replace('_',' ').title()}</b><p>{score.get(key, 0)}/100</p></div>" for key in keys)
