"""Ephe – Pitch deck / PPTX tools."""

from __future__ import annotations

import html
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path



from core.tools._deck_common import _deck_palette, _resolve_allowed_file, _split_lines, _xml_escape


def _inspect_pptx_template_file(path: str | Path) -> dict:
    src = _resolve_allowed_file(str(path), allow_artifacts=True)
    if src.suffix.lower() != ".pptx":
        raise ValueError("Template must be a .pptx file")
    with zipfile.ZipFile(src) as pptx:
        names = set(pptx.namelist())
        slide_names = sorted(name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
        text_runs = 0
        colors: dict[str, int] = {}
        samples: list[str] = []
        for slide_name in slide_names:
            xml = pptx.read(slide_name).decode("utf-8", errors="replace")
            text_runs += xml.count("<a:t>")
            for color in re.findall(r'<a:srgbClr val="([0-9A-Fa-f]{6})"', xml):
                colors[color.upper()] = colors.get(color.upper(), 0) + 1
            for text in re.findall(r"<a:t>(.*?)</a:t>", xml):
                clean = re.sub(r"\s+", " ", html.unescape(text)).strip()
                if clean and len(samples) < 12:
                    samples.append(clean[:120])
        presentation_xml = pptx.read("ppt/presentation.xml").decode("utf-8", errors="replace") if "ppt/presentation.xml" in names else ""
    ranked_colors = sorted(colors.items(), key=lambda item: item[1], reverse=True)
    return {
        "template_path": str(src),
        "slide_count": len(slide_names),
        "editable_text_runs": text_runs,
        "primary_color": ranked_colors[0][0] if ranked_colors else "",
        "secondary_color": ranked_colors[1][0] if len(ranked_colors) > 1 else "",
        "palette": [color for color, _ in ranked_colors[:8]],
        "wide_screen": "type=\"wide\"" in presentation_xml or "12192000" in presentation_xml,
        "sample_text": samples,
        "warnings": [] if slide_names else ["No slide XML files found."],
    }


def _emu(inches: float) -> int:
    return int(inches * 914400)


def _hex_from_pdf_rgb(rgb: str) -> str:
    parts = [float(part) for part in rgb.split()[:3]]
    return "".join(f"{max(0, min(255, round(part * 255))):02X}" for part in parts)


def _pptx_textbox(
    shape_id: int,
    name: str,
    text: str,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    font_size: int,
    color: str,
    bold: bool = False,
) -> str:
    bold_attr = ' b="1"' if bold else ""
    return f"""
<p:sp>
  <p:nvSpPr><p:cNvPr id="{shape_id}" name="{_xml_escape(name)}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm><a:off x="{_emu(x)}" y="{_emu(y)}"/><a:ext cx="{_emu(w)}" cy="{_emu(h)}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></p:spPr>
  <p:txBody><a:bodyPr wrap="square"/><a:lstStyle/><a:p><a:r><a:rPr lang="en-US" sz="{font_size * 100}"{bold_attr}><a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:latin typeface="Aptos"/></a:rPr><a:t>{_xml_escape(text)}</a:t></a:r><a:endParaRPr lang="en-US" sz="{font_size * 100}"/></a:p></p:txBody>
</p:sp>"""


def _pptx_rect(shape_id: int, name: str, x: float, y: float, w: float, h: float, fill: str, line: str | None = None) -> str:
    line_xml = f'<a:ln><a:solidFill><a:srgbClr val="{line}"/></a:solidFill></a:ln>' if line else '<a:ln><a:noFill/></a:ln>'
    return f"""
<p:sp>
  <p:nvSpPr><p:cNvPr id="{shape_id}" name="{_xml_escape(name)}"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr>
  <p:spPr><a:xfrm><a:off x="{_emu(x)}" y="{_emu(y)}"/><a:ext cx="{_emu(w)}" cy="{_emu(h)}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val="{fill}"/></a:solidFill>{line_xml}</p:spPr>
  <p:txBody><a:bodyPr/><a:lstStyle/><a:p/></p:txBody>
</p:sp>"""


def _pptx_slide_xml(
    index: int,
    total: int,
    slide: dict[str, str],
    *,
    deck_profile: str,
    design_theme: str,
    source_notes: str,
    evidence_level: str,
    brand_kit: dict[str, str] | None = None,
) -> str:
    palette = _deck_palette(design_theme)
    ink = _hex_from_pdf_rgb(palette["ink"])
    muted = _hex_from_pdf_rgb(palette["muted"])
    band = (brand_kit or {}).get("primary") or _hex_from_pdf_rgb(palette["band"])
    soft = _hex_from_pdf_rgb(palette["soft"])
    accent = (brand_kit or {}).get("secondary") or _hex_from_pdf_rgb(palette["accent"])
    brand_name = (brand_kit or {}).get("brand_name") or "Ephe"
    shapes = [
        _pptx_rect(2, "Background", 0, 0, 13.333, 7.5, _hex_from_pdf_rgb(palette["paper"])),
        _pptx_rect(3, "Top Bar", 0, 0, 13.333, 0.16, band),
        _pptx_rect(4, "Proof Panel", 7.75, 1.45, 4.25, 4.35, soft, "D6E3DC"),
        _pptx_textbox(5, "Slide Number", f"{index:02d} / {total:02d}", 0.7, 0.42, 1.2, 0.25, font_size=8, color=muted),
        _pptx_textbox(6, "Deck Profile", f"{brand_name} Deck - {deck_profile}", 9.55, 0.42, 2.9, 0.25, font_size=8, color=muted),
        _pptx_textbox(7, "Title", " ".join(_split_lines(slide["title"], max_chars=42, max_lines=2)), 0.7, 1.05, 6.5, 0.8, font_size=25, color=ink, bold=True),
        _pptx_textbox(8, "Claim", " ".join(_split_lines(slide["claim"], max_chars=72, max_lines=3)), 0.7, 2.05, 6.65, 0.85, font_size=15, color=band, bold=True),
        _pptx_textbox(9, "Body", " ".join(_split_lines(slide["body"], max_chars=86, max_lines=5)), 0.7, 3.0, 6.45, 1.0, font_size=11, color=muted),
        _pptx_textbox(10, "Proof Object", f"Proof Object: {slide.get('proof', 'Proof object')}", 8.12, 1.84, 3.45, 0.35, font_size=10, color=ink, bold=True),
        _pptx_textbox(11, "Evidence Level", f"Evidence: {evidence_level}", 8.12, 2.18, 3.3, 0.25, font_size=8, color=muted),
        _pptx_rect(12, "Visual Object A", 8.35, 2.85, 0.7, 0.7, band),
        _pptx_rect(13, "Visual Object B", 9.35, 3.45, 0.7, 0.7, accent),
        _pptx_rect(14, "Visual Object C", 10.35, 4.05, 0.7, 0.7, band),
        _pptx_textbox(15, "Animation Plan", f"Animation Plan: reveal title, then claim, then proof object ({slide['visual']}).", 0.7, 6.85, 8.1, 0.25, font_size=8, color=ink, bold=True),
    ]
    if source_notes and index == total:
        shapes.append(_pptx_textbox(16, "Source Notes", f"Source Notes: {source_notes}", 0.7, 5.82, 10.8, 0.45, font_size=8, color=muted))
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>
      <p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>
      {''.join(shapes)}
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>
</p:sld>"""


def _write_pitch_deck_pptx(
    path: Path,
    title: str,
    slides: list[dict[str, str]],
    *,
    deck_profile: str,
    design_theme: str,
    source_notes: str,
    evidence_level: str,
    brand_kit: dict[str, str] | None = None,
) -> None:
    slide_overrides = "\n".join(
        f'<Override PartName="/ppt/slides/slide{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/>'
        for i in range(1, len(slides) + 1)
    )
    slide_ids = "\n".join(
        f'<p:sldId id="{255 + i}" r:id="rId{i}"/>'
        for i in range(1, len(slides) + 1)
    )
    rels = "\n".join(
        f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" Target="slides/slide{i}.xml"/>'
        for i in range(1, len(slides) + 1)
    )
    content_types = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
  <Override PartName="/ppt/presentation.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"/>
  {slide_overrides}
</Types>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="ppt/presentation.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""
    presentation = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:sldIdLst>{slide_ids}</p:sldIdLst>
  <p:sldSz cx="12192000" cy="6858000" type="wide"/>
  <p:notesSz cx="6858000" cy="9144000"/>
</p:presentation>"""
    presentation_rels = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  {rels}
</Relationships>"""
    created = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    core_props = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{_xml_escape(title)}</dc:title>
  <dc:creator>Ephe</dc:creator>
  <cp:lastModifiedBy>Ephe</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>
</cp:coreProperties>"""
    app_props = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>Ephe</Application>
  <PresentationFormat>On-screen Show (16:9)</PresentationFormat>
  <Slides>{len(slides)}</Slides>
</Properties>"""

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as pptx:
        pptx.writestr("[Content_Types].xml", content_types)
        pptx.writestr("_rels/.rels", root_rels)
        pptx.writestr("docProps/core.xml", core_props)
        pptx.writestr("docProps/app.xml", app_props)
        pptx.writestr("ppt/presentation.xml", presentation)
        pptx.writestr("ppt/_rels/presentation.xml.rels", presentation_rels)
        for index, slide in enumerate(slides, 1):
            pptx.writestr(
                f"ppt/slides/slide{index}.xml",
                _pptx_slide_xml(
                    index,
                    len(slides),
                    slide,
                    deck_profile=deck_profile,
                    design_theme=design_theme,
                    source_notes=source_notes,
                    evidence_level=evidence_level,
                    brand_kit=brand_kit,
                ),
            )


def _qa_pptx_deck_file(path: Path) -> dict:
    warnings: list[str] = []
    slides: list[dict] = []
    try:
        with zipfile.ZipFile(path) as pptx:
            names = set(pptx.namelist())
            slide_names = sorted(name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
            if not slide_names:
                warnings.append("No slide XML files found.")
            for index, slide_name in enumerate(slide_names, 1):
                xml = pptx.read(slide_name).decode("utf-8", errors="replace")
                texts = [html.unescape(t).strip() for t in re.findall(r"<a:t>(.*?)</a:t>", xml)]
                texts = [text for text in texts if text]
                text_chars = sum(len(text) for text in texts)
                editable_runs = xml.count("<a:t>")
                proof_present = "Proof Object:" in xml
                if editable_runs < 4:
                    warnings.append(f"Slide {index} has low editable text density.")
                if text_chars > 900:
                    warnings.append(f"Slide {index} is text-heavy.")
                if not proof_present:
                    warnings.append(f"Slide {index} is missing a proof object.")
                slides.append({
                    "slide": index,
                    "editable_text_runs": editable_runs,
                    "text_chars": text_chars,
                    "proof_object": proof_present,
                    "preview_text": texts[:5],
                })
    except Exception as exc:
        warnings.append(f"PPTX QA failed: {exc}")
    return {
        "artifact_type": "pptx_visual_qa",
        "path": str(path),
        "slide_count": len(slides),
        "status": "passed" if not warnings else "warning",
        "slides": slides,
        "warnings": warnings,
        "contact_sheet": str(path.with_suffix(".contact-sheet.html")),
    }


def _render_pptx_contact_sheet(path: Path, qa: dict) -> str:
    cards = []
    for slide in qa.get("slides", []):
        text = " ".join(slide.get("preview_text", []))
        proof = "Proof OK" if slide.get("proof_object") else "Missing proof"
        cards.append(
            "<article>"
            f"<span>Slide {slide.get('slide')}</span>"
            f"<h2>{html.escape(text[:150] or 'No extractable text')}</h2>"
            f"<p>{html.escape(proof)} - {slide.get('editable_text_runs', 0)} editable text runs - {slide.get('text_chars', 0)} chars</p>"
            "</article>"
        )
    warnings = "".join(f"<li>{html.escape(str(warning))}</li>" for warning in qa.get("warnings", []))
    return f"""<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ephe PPTX Contact Sheet</title>
<style>
body{{margin:0;background:#f8faf9;color:#101820;font-family:Arial,sans-serif;padding:32px}}
header{{display:flex;justify-content:space-between;gap:24px;align-items:end;border-bottom:4px solid #101820;padding-bottom:18px;margin-bottom:24px}}
h1{{margin:0;font-size:30px}} small{{color:#53606f}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}}
article{{background:white;border:1px solid #d6e3dc;border-left:6px solid #16a34a;padding:16px;min-height:150px}}
span{{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:#53606f;font-weight:700}}
h2{{font-size:17px;line-height:1.25;margin:10px 0;color:#101820}}
p,li{{font-size:13px;color:#53606f;line-height:1.4}}
.warnings{{margin-top:26px;background:#fff7ed;border-left:6px solid #d97706;padding:14px 18px}}
</style>
<header><div><h1>PPTX Contact Sheet</h1><small>{html.escape(str(path))}</small></div><b>{html.escape(str(qa.get('status', 'unknown')))}</b></header>
<section class="grid">{''.join(cards)}</section>
<section class="warnings"><b>Warnings</b><ul>{warnings or '<li>None</li>'}</ul></section>
</html>"""
