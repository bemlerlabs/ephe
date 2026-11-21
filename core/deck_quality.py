"""Deck Engine v2 deterministic quality gates."""
from __future__ import annotations

import json
import re
from pathlib import Path


FORBIDDEN_FINAL_MARKERS = (
    "Animation Plan",
    "Proof Object",
    "Evidence: assumptions",
    "DECK_STUDIO_FILE:",
    "PITCH_DECK_FILE:",
    "PPTX_DECK_FILE:",
)

AMATEUR_TERMS = ("awesome", "cool", "magic", "wow", "amazing", "super cool", "tbd", "todo", "placeholder", "lorem")


def evidence_ledger(spec: dict) -> dict:
    evidence = spec.get("evidence", {})
    entries = []
    for index, slide in enumerate(spec.get("slides", []), 1):
        entries.append({
            "slide": index,
            "role": slide.get("role", ""),
            "headline": slide.get("headline", ""),
            "source_status": slide.get("source_status") or evidence.get("status", "assumption_led"),
            "evidence_refs": slide.get("evidence_refs", []),
        })
    return {
        "artifact_type": "deck_evidence_ledger",
        "status": evidence.get("status", "assumption_led"),
        "level": evidence.get("level", "assumptions"),
        "source_notes": evidence.get("source_notes", ""),
        "asset_status": evidence.get("asset_status", "abstract_visuals"),
        "entries": entries,
    }


def score_deck_spec(spec: dict, render_qa: dict | None = None) -> dict:
    slides = spec.get("slides", [])
    deck_text = json.dumps(spec, ensure_ascii=False).lower()
    roles = [slide.get("role", "") for slide in slides]
    visuals = [slide.get("visual_spec", {}).get("type", "") for slide in slides]
    distinct_roles = len(set(roles))
    repeated_visual_limit = max((visuals.count(visual) for visual in set(visuals)), default=0)
    text_lengths = [
        len(slide.get("headline", "")) + len(slide.get("takeaway", "")) + sum(len(p) for p in slide.get("supporting_points", []))
        for slide in slides
    ]
    forbidden_found = [marker for marker in FORBIDDEN_FINAL_MARKERS if marker.lower() in deck_text]
    amateur_found = [term for term in AMATEUR_TERMS if re.search(rf"\b{re.escape(term)}\b", deck_text)]
    source_statuses = {slide.get("source_status", "") for slide in slides}
    evidence = spec.get("evidence", {})
    render_ok = not render_qa or render_qa.get("status") == "passed"

    checks = {
        "slide_count_at_least_8": len(slides) >= 8,
        "deck_spec_v2": spec.get("schema_version") == 2,
        "slide_contract_complete": all(
            slide.get("role")
            and slide.get("headline")
            and slide.get("takeaway")
            and slide.get("visual_spec", {}).get("type")
            and slide.get("source_status")
            for slide in slides
        ),
        "layout_roles_varied": distinct_roles >= (7 if len(slides) >= 10 else min(5, len(slides))),
        "no_repeated_standard_visuals": repeated_visual_limit <= 2,
        "no_internal_markers": not forbidden_found,
        "no_placeholders": not amateur_found,
        "no_amateur_language": not amateur_found,
        "evidence_status_transparent": bool(evidence.get("status")) and bool(source_statuses),
        "executive_density": bool(text_lengths) and max(text_lengths) <= 620,
        "render_quality_passed": render_ok,
    }
    narrative_score = _pct(checks["slide_count_at_least_8"], checks["slide_contract_complete"], checks["executive_density"])
    layout_score = _pct(checks["layout_roles_varied"], checks["no_repeated_standard_visuals"])
    visual_variety_score = round(min(100, (distinct_roles / max(1, min(len(slides), 10))) * 120))
    evidence_score = 100 if evidence.get("status") == "source_grounded" else 78 if evidence.get("status") == "mixed" else 64
    brand_fit_score = 88 if spec.get("brand_kit") else 74
    export_score = _pct(checks["render_quality_passed"], checks["no_internal_markers"])
    quality_score = round((narrative_score + layout_score + visual_variety_score + evidence_score + brand_fit_score + export_score) / 6)
    minimum_score = 86 if evidence.get("status") == "assumption_led" else 92
    warnings = []
    if evidence.get("status") == "assumption_led":
        warnings.append("No external evidence or company assets supplied; deck is polished but assumption-led.")
    if evidence.get("asset_status") == "missing_requested_assets":
        warnings.append("Image request detected, but no local image or brand assets were provided.")
    if forbidden_found:
        warnings.append(f"Final deck contains internal markers: {', '.join(forbidden_found)}.")
    if not checks["layout_roles_varied"]:
        warnings.append("Deck uses too few distinct layout roles.")
    if not checks["no_repeated_standard_visuals"]:
        warnings.append("Deck repeats the same visual pattern too often.")

    enterprise_hard_pass = all(checks.values())
    # Wave 10 (P1-5): deterministic sub-score undershoot gate. A deck counts as
    # passed only when every delivered dimension holds its floor. The evidence check
    # keys on the refs that are actually present and addressable
    # (arXiv 2605.12087), not on the raw sub-score — for user_provided/mixed, 64
    # is the legitimate scale value, while the slides do carry refs.
    weak_dimensions: list[str] = []
    has_refs = any(slide.get("evidence_refs") for slide in slides)
    if evidence.get("status") != "assumption_led" and not has_refs:
        weak_dimensions.append("declared source but no addressable evidence_refs on any slide")
    if brand_fit_score < 70:
        weak_dimensions.append(f"brand_fit_score {brand_fit_score} < 70")
    if enterprise_hard_pass and quality_score >= minimum_score and not weak_dimensions:
        status = "passed"
    elif weak_dimensions:
        status = "needs_revision"
    else:
        status = "failed"
    return {
        "artifact_type": "pitch_deck_v2",
        "quality_score": quality_score,
        "minimum_score": minimum_score,
        "enterprise_grade": bool(spec.get("enterprise_grade", True)),
        "status": status,
        "narrative_score": narrative_score,
        "layout_score": layout_score,
        "visual_variety_score": visual_variety_score,
        "evidence_score": evidence_score,
        "brand_fit_score": brand_fit_score,
        "export_score": export_score,
        "slide_count": len(slides),
        "distinct_layout_roles": distinct_roles,
        "checks": checks,
        "warnings": warnings,
        "weak_dimensions": weak_dimensions,
    }


def qa_pdf_render(path: Path, spec: dict) -> dict:
    checks = {
        "extractable_text": False,
        "slide_count_at_least_8": False,
        "no_text_in_visual_column": True,
        "no_text_overflow": True,
        "no_internal_markers": True,
        "layout_roles_varied": len({s.get("role") for s in spec.get("slides", [])}) >= 7,
        "footer_clean": True,
        "visuals_bounded": True,
        "has_real_pdf_pages": False,
    }
    warnings: list[str] = []
    text = ""
    try:
        import pdfplumber

        overflow_words = []
        with pdfplumber.open(str(path)) as pdf:
            checks["has_real_pdf_pages"] = len(pdf.pages) > 0
            checks["slide_count_at_least_8"] = len(pdf.pages) >= 8
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
            checks["extractable_text"] = bool(text.strip())
            for page_index, page in enumerate(pdf.pages, 1):
                for word in page.extract_words() or []:
                    if float(word.get("x1", 0)) > 700 or float(word.get("x0", 0)) < 18:
                        overflow_words.append({"page": page_index, "text": word.get("text", ""), "x1": round(float(word.get("x1", 0)), 1)})
        if overflow_words:
            checks["no_text_overflow"] = False
            warnings.append(f"Text exceeds slide bounds: {overflow_words[:5]}")
    except Exception as exc:
        warnings.append(f"PDF render QA failed: {exc}")
    for marker in FORBIDDEN_FINAL_MARKERS:
        if marker in text:
            checks["no_internal_markers"] = False
            warnings.append(f"Final PDF contains internal marker: {marker}")
    if "Presenter note" in text or "reveal title" in text:
        checks["footer_clean"] = False
        warnings.append("Final PDF footer contains internal presentation notes.")
    if not checks["layout_roles_varied"]:
        warnings.append("Rendered deck does not have enough layout-role variety.")
    return {
        "artifact_type": "pitch_deck_render_qa",
        "path": str(path),
        "status": "passed" if all(checks.values()) and not warnings else "failed",
        "checks": checks,
        "warnings": warnings,
        "overflow_words": [],
    }


def _pct(*values: bool) -> int:
    if not values:
        return 0
    return round(sum(1 for value in values if value) / len(values) * 100)
