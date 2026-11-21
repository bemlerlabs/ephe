"""Ephe – Pitch deck / PPTX tools."""

from __future__ import annotations

import html
import re
from pathlib import Path

from core.tools.base import (
    AMATEUR_DECK_TERMS,
    ENTERPRISE_DECK_PROFILES,
    ENTERPRISE_DESIGN_THEMES,
)


from core.tools._deck_common import _deck_palette, _pdf_escape, _pdf_text, _split_lines, _visual_commands


def _write_pitch_deck_pdf(
    path: Path,
    title: str,
    slides: list[dict[str, str]],
    *,
    deck_profile: str,
    design_theme: str,
    source_notes: str,
    evidence_level: str,
) -> None:
    width, height = 720, 405
    palette = _deck_palette(design_theme)
    page_streams: list[str] = []
    for index, slide in enumerate(slides, 1):
        visual_x, visual_y, visual_w, visual_h = 438, 78, 210, 235
        stream = [
            f"{palette['paper']} rg 0 0 720 405 re f\n",
            f"{palette['band']} rg 0 393 720 12 re f\n",
            f"{palette['soft']} rg {visual_x} {visual_y} {visual_w} {visual_h} re f\n",
            f"0.839 0.890 0.863 RG {visual_x} {visual_y} {visual_w} {visual_h} re S\n",
            _pdf_text(f"{index:02d} / {len(slides):02d}", 46, 370, 8, "F1", palette["muted"]),
            _pdf_text(f"Ephe Deck - {deck_profile}", 520, 370, 8, "F1", palette["muted"]),
            _pdf_text(f"Evidence: {evidence_level}", visual_x + 24, 268, 8, "F1", palette["muted"]),
        ]
        y = 326
        for line in _split_lines(slide["title"], max_chars=34, max_lines=2):
            stream.append(_pdf_text(line, 48, y, 25, "F2", palette["ink"]))
            y -= 29
        y -= 5
        for line in _split_lines(slide["claim"], max_chars=46, max_lines=4):
            stream.append(_pdf_text(line, 48, y, 15, "F2", palette["band"]))
            y -= 21
        y -= 8
        for line in _split_lines(slide["body"], max_chars=58, max_lines=5):
            stream.append(_pdf_text(line, 48, y, 11, "F1", palette["muted"]))
            y -= 17
        stream.append(_pdf_text(f"Proof Object: {slide.get('proof', 'Proof object')}", visual_x + 24, 286, 10, "F2", palette["ink"]))
        stream.extend(_visual_commands(slide.get("visual", "custom"), visual_x, visual_y, visual_w, visual_h, palette))
        stream.append(_pdf_text(f"Animation Plan: reveal title, then claim, then proof object ({slide['visual']}).", 48, 34, 8, "F2", palette["ink"]))
        if source_notes and index == len(slides):
            for note_index, line in enumerate(_split_lines(f"Source Notes: {source_notes}", max_chars=82, max_lines=3)):
                stream.append(_pdf_text(line, 48, 64 + note_index * 12, 8, "F1", palette["muted"]))
        page_streams.append("".join(stream))

    objects: list[bytes] = []
    kids = []
    page_obj_start = 4
    for i, stream in enumerate(page_streams):
        page_obj = page_obj_start + i * 2
        content_obj = page_obj + 1
        kids.append(f"{page_obj} 0 R")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            f"/Resources << /Font << /F1 3 0 R /F2 {3 + len(page_streams) * 2 + 1} 0 R >> >> "
            f"/Contents {content_obj} 0 R >>".encode("latin-1", "replace")
        )
        stream_bytes = stream.encode("latin-1", "replace")
        objects.append(f"<< /Length {len(stream_bytes)} >>\nstream\n".encode("latin-1") + stream_bytes + b"endstream")

    font_bold_obj = 3 + len(page_streams) * 2 + 1
    base_objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(page_streams)} >>".encode("latin-1"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    all_objects = base_objects + objects + [b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"]
    if len(all_objects) != font_bold_obj:
        raise ValueError("PDF object numbering mismatch")

    output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for number, obj in enumerate(all_objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode("latin-1"))
        output.extend(obj)
        output.extend(b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(all_objects) + 1}\n0000000000 65535 f \n".encode("latin-1"))
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode("latin-1"))
    output.extend(
        f"trailer << /Size {len(all_objects) + 1} /Root 1 0 R /Info << /Title ({_pdf_escape(title)}) /Author (Ephe) >> >>\n"
        f"startxref\n{xref}\n%%EOF\n".encode("latin-1", "replace")
    )
    path.write_bytes(output)


def _qa_pitch_deck_render_file(path: Path) -> dict:
    warnings: list[str] = []
    checks = {
        "extractable_text": False,
        "slide_count_at_least_8": False,
        "no_text_in_visual_column": True,
        "visuals_bounded": True,
        "has_real_pdf_pages": False,
    }
    overflow_words: list[dict[str, object]] = []
    allowed_visual_words = {
        "Proof", "Object:", "Evidence:", "assumptions", "user-provided", "sources", "mixed",
        "Input", "Tool", "Artifact", "Discover", "Build", "Validate", "Scale",
    }
    try:
        import pdfplumber

        with pdfplumber.open(str(path)) as pdf:
            checks["has_real_pdf_pages"] = len(pdf.pages) > 0
            checks["slide_count_at_least_8"] = len(pdf.pages) >= 8
            all_text = []
            for page_index, page in enumerate(pdf.pages, 1):
                text = page.extract_text() or ""
                all_text.append(text)
                words = page.extract_words() or []
                ignored_panel_tops = {
                    round(float(word.get("top", 0)), 1)
                    for word in words
                    if str(word.get("text", "")) in {"Proof", "Object:", "Evidence:"}
                }
                for word in words:
                    word_text = str(word.get("text", ""))
                    top = float(word.get("top", 0))
                    x0 = float(word.get("x0", 0))
                    if word_text in allowed_visual_words:
                        continue
                    if any(abs(top - ignored_top) <= 2.0 for ignored_top in ignored_panel_tops):
                        continue
                    if top < 86 or top > 330:
                        continue
                    if x0 >= 418:
                        overflow_words.append({
                            "page": page_index,
                            "text": word_text,
                            "x0": round(x0, 1),
                            "top": round(top, 1),
                        })
            checks["extractable_text"] = bool(" ".join(all_text).strip())
    except Exception as exc:
        warnings.append(f"Render text-position QA failed: {exc}")

    raw = path.read_text(encoding="latin-1", errors="replace") if path.exists() else ""
    rects = re.findall(r"([-0-9.]+)\s+([-0-9.]+)\s+([-0-9.]+)\s+([-0-9.]+)\s+re", raw)
    oversized_visual_rects = [
        (float(x), float(y), float(w), float(h))
        for x, y, w, h in rects
        if float(x) >= 400 and (float(w) > 240 or float(h) > 250)
    ]
    if overflow_words:
        checks["no_text_in_visual_column"] = False
        warnings.append(f"Main narrative text enters the visual column: {overflow_words[:6]}")
    if oversized_visual_rects:
        checks["visuals_bounded"] = False
        warnings.append(f"Visual commands exceed right-panel bounds: {oversized_visual_rects[:4]}")
    if not checks["extractable_text"]:
        warnings.append("Rendered deck has no extractable text.")
    if not checks["slide_count_at_least_8"]:
        warnings.append("Rendered deck has fewer than 8 slides.")
    if not checks["has_real_pdf_pages"]:
        warnings.append("Rendered deck has no readable PDF pages.")

    return {
        "artifact_type": "pitch_deck_render_qa",
        "path": str(path),
        "status": "passed" if all(checks.values()) and not warnings else "failed",
        "checks": checks,
        "warnings": warnings,
        "overflow_words": overflow_words[:20],
    }


def _deck_text(slides: list[dict[str, str]]) -> str:
    return " ".join(" ".join(str(value) for value in slide.values()) for slide in slides).lower()


def _score_pitch_deck(
    slides: list[dict[str, str]],
    *,
    deck_profile: str,
    design_theme: str,
    source_notes: str,
    evidence_level: str,
    enterprise_grade: bool,
    render_qa: dict | None = None,
) -> dict:
    deck_text = _deck_text(slides)
    amateur_terms_found = sorted(
        term
        for term in AMATEUR_DECK_TERMS
        if re.search(rf"\b{re.escape(term)}\b", deck_text)
    )
    executive_density_ok = all(
        len(slide.get("claim", "")) <= 180 and len(slide.get("body", "")) <= 360
        for slide in slides
    )
    checks = {
        "slide_count_at_least_8": len(slides) >= 8,
        "claim_on_every_slide": all(len(slide.get("claim", "").strip()) >= 14 for slide in slides),
        "proof_object_on_every_slide": all(len(slide.get("proof", "").strip()) >= 5 for slide in slides),
        "no_placeholders": not any(
            token in " ".join(str(value).lower() for value in slide.values())
            for slide in slides
            for token in ("tbd", "todo", "placeholder", "lorem")
        ),
        "visual_variety": len({slide.get("visual", "custom") for slide in slides}) >= min(5, len(slides)),
        "source_notes_or_assumptions_visible": bool(source_notes.strip()),
        "no_amateur_language": not amateur_terms_found,
        "enterprise_profile_valid": deck_profile in ENTERPRISE_DECK_PROFILES,
        "enterprise_theme_valid": design_theme in ENTERPRISE_DESIGN_THEMES,
        "executive_density": executive_density_ok,
        "evidence_level_declared": evidence_level in {"sources", "mixed", "assumptions", "user-provided"},
        "render_quality_passed": (render_qa or {}).get("status") == "passed",
    }
    passed = sum(1 for ok in checks.values() if ok)
    score = round((passed / len(checks)) * 100)
    warnings = []
    if not checks["visual_variety"]:
        warnings.append("Deck uses too few distinct visual proof objects.")
    if amateur_terms_found:
        warnings.append(f"Deck contains amateur wording: {', '.join(amateur_terms_found[:5])}.")
    if evidence_level == "assumptions":
        warnings.append("No external evidence supplied; deck is enterprise-formatted but assumption-led.")
    if render_qa and render_qa.get("status") != "passed":
        warnings.extend(str(warning) for warning in render_qa.get("warnings", [])[:4])
    minimum_score = 92 if enterprise_grade else 85
    status = "passed" if score >= minimum_score and not amateur_terms_found else "failed"
    return {
        "artifact_type": "pitch_deck",
        "quality_score": score,
        "minimum_score": minimum_score,
        "enterprise_grade": enterprise_grade,
        "status": status,
        "deck_profile": deck_profile,
        "design_theme": design_theme,
        "evidence_level": evidence_level,
        "slide_count": len(slides),
        "checks": checks,
        "warnings": warnings,
    }


def _build_pitch_deck_manifest(
    *,
    title: str,
    slides: list[dict[str, str]],
    deck_profile: str,
    design_theme: str,
    source_notes: str,
    evidence_level: str,
    enterprise_grade: bool,
    template_info: dict | None = None,
    brand_kit: dict | None = None,
) -> dict:
    return {
        "title": title,
        "artifact_type": "pitch_deck",
        "enterprise_grade": enterprise_grade,
        "deck_profile": deck_profile,
        "design_theme": design_theme,
        "evidence_level": evidence_level,
        "source_notes": source_notes,
        "template": template_info or {},
        "brand_kit": brand_kit or {},
        "claim_spine": [
            {
                "slide": index,
                "title": slide.get("title", ""),
                "claim": slide.get("claim", ""),
                "proof_object": slide.get("proof", ""),
                "visual": slide.get("visual", ""),
            }
            for index, slide in enumerate(slides, 1)
        ],
        "review_gates": [
            "one_claim_per_slide",
            "proof_object_per_slide",
            "source_notes_or_assumptions",
            "anti_amateur_language",
            "executive_density",
            "visual_variety",
            "extractable_pdf_text",
        ],
    }


def _render_pitch_deck_preview(topic: str, slides: list[dict[str, str]], score: dict | None = None) -> str:
    cards = []
    for index, slide in enumerate(slides, 1):
        cards.append(
            "<section class=\"slide\">"
            f"<span>{index:02d}</span>"
            f"<h1>{html.escape(slide['title'])}</h1>"
            f"<h2>{html.escape(slide['claim'])}</h2>"
            f"<p>{html.escape(slide['body'])}</p>"
            f"<strong>{html.escape(slide.get('proof', 'Proof object'))}</strong>"
            f"<small>Animation: title -> claim -> visual proof object</small>"
            "</section>"
        )
    score_html = ""
    if score:
        score_html = (
            "<aside class=\"score\">"
            f"<b>Quality score {score.get('quality_score', 0)}/100</b>"
            f"<span>{html.escape(score.get('deck_profile', 'deck'))} - {html.escape(score.get('design_theme', 'theme'))}</span>"
            "</aside>"
        )
    return """<!doctype html>
<html lang="en">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} - Ephe Deck Preview</title>
<style>
body{{margin:0;background:#101820;color:#101820;font-family:Inter,Arial,sans-serif;overflow-x:hidden}}
.slide{{min-height:100vh;display:grid;align-content:center;gap:18px;padding:8vw 12vw;background:#fbfcfb;border-bottom:10px solid #16a34a;animation:enter .72s ease both}}
.slide:nth-child(even){{background:#eef8f1}}
span{{color:#16a34a;font-weight:800;letter-spacing:.08em}}
h1{{font-size:clamp(38px,7vw,82px);line-height:.95;margin:0;max-width:980px}}
h2{{font-size:clamp(22px,3vw,38px);line-height:1.08;color:#16a34a;margin:0;max-width:920px}}
p{{font-size:clamp(17px,2vw,24px);line-height:1.35;color:#53606f;max-width:820px;margin:0}}
strong{{font-size:clamp(16px,2vw,22px);color:#101820}}
small{{font-size:14px;color:#53606f;text-transform:uppercase;letter-spacing:.08em}}
.score{{position:fixed;right:18px;top:18px;z-index:5;display:grid;gap:4px;background:#101820;color:white;padding:12px 14px;border-left:4px solid #16a34a;font-size:13px}}
.score span{{color:#b7c4bd;font-weight:600;letter-spacing:0}}
@keyframes enter{{from{{opacity:0;transform:translateY(28px) scale(.98)}}to{{opacity:1;transform:translateY(0) scale(1)}}}}
</style>
{score_html}
{cards}
</html>""".format(title=html.escape(topic or "Pitch Deck"), score_html=score_html, cards="\n".join(cards))
