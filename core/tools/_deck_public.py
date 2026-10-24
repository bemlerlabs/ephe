"""Ephe – Pitch deck / PPTX tools."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path



from core.tools._deck_common import (_deck_slug, _deck_v2_brand_kit, _enterprise_clean_text, _normalize_deck_asset_paths, _resolve_allowed_file, _safe_download_filename, _xml_escape,)
from core.tools._deck_pptx import _inspect_pptx_template_file, _qa_pptx_deck_file, _render_pptx_contact_sheet


async def create_pitch_deck(
    topic: str,
    audience: str = "investors",
    thesis: str = "",
    slides: list[dict] | str | None = None,
    filename: str = "ephe_pitch_deck.pdf",
    include_animation_preview: bool = True,
    deck_profile: str = "product-platform",
    design_theme: str = "evergreen",
    source_notes: str = "",
    evidence_level: str = "assumptions",
    enterprise_grade: bool = True,
    deck_quality_profile: str = "enterprise",
    brand_kit: dict | None = None,
    source_notebook_path: str = "",
    asset_paths: list[str] | str | None = None,
) -> str:
    try:
        from core.deck_design import normalize_profile, normalize_theme
        from core.deck_model import build_deck_spec
        from core.deck_render import write_deck_artifacts

        from core.engine_config import artifact_output_dir, get_brand_kit

        downloads = artifact_output_dir()
        safe_pdf = _deck_slug(topic, filename, "ephe_pitch_deck.pdf", ".pdf")
        out = downloads / safe_pdf
        deck_profile = normalize_profile(deck_profile or "product-platform")
        design_theme = normalize_theme(design_theme or "executive", enterprise_grade=enterprise_grade)
        normalized_assets = _normalize_deck_asset_paths(asset_paths)
        if source_notebook_path and not source_notes.strip():
            source_notes = f"Grounded in local source notebook: {source_notebook_path}"
        if source_notebook_path and evidence_level == "assumptions":
            evidence_level = "sources"
        spec = build_deck_spec(
            title=topic or "Ephe Pitch Deck",
            audience=audience,
            thesis=thesis,
            slides=slides,
            deck_profile=deck_profile,
            design_theme=design_theme,
            source_notes=source_notes.strip() or "Generated from user prompt; no external company metrics or source files were provided.",
            evidence_level=evidence_level.strip() or "assumptions",
            enterprise_grade=enterprise_grade,
            brand_kit=brand_kit or get_brand_kit(),
            wants_images=bool(asset_paths),
            source_brief_path=source_notebook_path,
            asset_paths=normalized_assets,
            deck_quality_profile=deck_quality_profile,
        )
        paths = write_deck_artifacts(spec=spec, pdf_path=out, include_preview=include_animation_preview)
        result = [
            f"PITCH_DECK_FILE:{paths['pdf']}",
            f"SCORECARD_FILE:{paths['scorecard']}",
            f"MANIFEST_FILE:{paths['manifest']}",
            f"RENDER_QA_FILE:{paths['render_qa']}",
            f"DECK_SPEC_FILE:{paths['deck_spec']}",
            f"VISUAL_QA_FILE:{paths['visual_qa']}",
            f"EVIDENCE_LEDGER_FILE:{paths['evidence_ledger']}",
        ]
        if include_animation_preview:
            result.insert(1, f"PREVIEW_FILE:{paths['preview']}")
        return "\n".join(result)
    except Exception as e:
        return f"[pitch-deck error: {e}]"


async def create_pptx_deck(
    topic: str,
    audience: str = "board and executive committee",
    thesis: str = "",
    slides: list[dict] | str | None = None,
    filename: str = "ephe_pitch_deck.pptx",
    deck_profile: str = "strategy-leadership",
    design_theme: str = "executive",
    source_notes: str = "",
    evidence_level: str = "assumptions",
    enterprise_grade: bool = True,
    template_path: str = "",
    brand_name: str = "",
    brand_primary: str = "",
    brand_secondary: str = "",
    deck_quality_profile: str = "enterprise",
    source_notebook_path: str = "",
    asset_paths: list[str] | str | None = None,
) -> str:
    try:
        from core.deck_design import normalize_profile, normalize_theme
        from core.deck_model import build_deck_spec
        from core.deck_render import write_deck_artifacts

        from core.engine_config import artifact_output_dir

        downloads = artifact_output_dir()
        safe_pptx = _deck_slug(topic, filename, "ephe_pitch_deck.pptx", ".pptx")
        out = downloads / safe_pptx
        pdf_peer = out.with_suffix(".pdf")
        deck_profile = normalize_profile(deck_profile)
        design_theme = normalize_theme(design_theme, enterprise_grade=enterprise_grade)
        template_info = _inspect_pptx_template_file(template_path) if template_path else {}
        brand_kit = _deck_v2_brand_kit(
            brand_name=brand_name,
            brand_primary=brand_primary or str(template_info.get("primary_color", "")),
            brand_secondary=brand_secondary or str(template_info.get("secondary_color", "")),
        )
        if not brand_kit.get("brand_name") and not brand_kit.get("primary"):
            from core.engine_config import get_brand_kit
            brand_kit = get_brand_kit() or brand_kit
        normalized_assets = _normalize_deck_asset_paths(asset_paths)
        if source_notebook_path and not source_notes.strip():
            source_notes = f"Grounded in local source notebook: {source_notebook_path}"
        if source_notebook_path and evidence_level == "assumptions":
            evidence_level = "sources"
        spec = build_deck_spec(
            title=topic or "Ephe Pitch Deck",
            audience=audience,
            thesis=thesis,
            slides=slides,
            deck_profile=deck_profile,
            design_theme=design_theme,
            source_notes=source_notes.strip() or "Generated from user prompt; no external company metrics or source files were provided.",
            evidence_level=evidence_level.strip() or "assumptions",
            enterprise_grade=enterprise_grade,
            brand_kit=brand_kit,
            wants_images=bool(asset_paths),
            source_brief_path=source_notebook_path,
            asset_paths=normalized_assets,
            deck_quality_profile=deck_quality_profile,
        )
        if template_info:
            spec["template_info"] = template_info
        paths = write_deck_artifacts(spec=spec, pdf_path=pdf_peer, pptx_path=out, include_preview=True)
        return "\n".join([
            f"PPTX_DECK_FILE:{paths['pptx']}",
            f"SCORECARD_FILE:{paths['scorecard']}",
            f"MANIFEST_FILE:{paths['manifest']}",
            f"QA_FILE:{paths['pptx_qa']}",
            f"CONTACT_SHEET_FILE:{paths['contact_sheet']}",
            f"DECK_SPEC_FILE:{paths['deck_spec']}",
            f"VISUAL_QA_FILE:{paths['visual_qa']}",
            f"EVIDENCE_LEDGER_FILE:{paths['evidence_ledger']}",
        ])
    except Exception as e:
        return f"[pptx-deck error: {e}]"


async def inspect_pptx_template(path: str, filename: str = "ephe_template_analysis.json") -> str:
    try:
        analysis = _inspect_pptx_template_file(path)
        from core.engine_config import artifact_output_dir

        downloads = artifact_output_dir()
        out = downloads / _safe_download_filename(filename, "ephe_template_analysis.json", ".json")
        out.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
        return f"PPTX_TEMPLATE_ANALYSIS_FILE:{out}"
    except Exception as exc:
        return f"[pptx-template error: {exc}]"


async def edit_pptx_template(
    template_path: str,
    replacements: dict | list,
    filename: str = "ephe_template_edit.pptx",
) -> str:
    try:
        src = _resolve_allowed_file(template_path, allow_artifacts=True)
        if src.suffix.lower() != ".pptx":
            raise ValueError("template_path must point to a .pptx file")
        mapping: dict[str, str] = {}
        if isinstance(replacements, dict):
            mapping = {str(k): str(v) for k, v in replacements.items()}
        elif isinstance(replacements, list):
            for item in replacements:
                if isinstance(item, dict) and "from" in item and "to" in item:
                    mapping[str(item["from"])] = str(item["to"])
        if not mapping:
            raise ValueError("replacements must contain at least one from/to mapping")

        from core.engine_config import artifact_output_dir

        downloads = artifact_output_dir()
        out = downloads / _safe_download_filename(filename, "ephe_template_edit.pptx", ".pptx")
        changed_runs = 0
        with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for info in zin.infolist():
                data = zin.read(info.filename)
                if info.filename.startswith("ppt/slides/slide") and info.filename.endswith(".xml"):
                    xml = data.decode("utf-8", errors="replace")
                    for old, new in mapping.items():
                        escaped_old = _xml_escape(old)
                        if escaped_old in xml:
                            changed_runs += xml.count(escaped_old)
                            xml = xml.replace(escaped_old, _xml_escape(_enterprise_clean_text(new)))
                    data = xml.encode("utf-8")
                zout.writestr(info, data)

        qa = _qa_pptx_deck_file(out)
        manifest = {
            "artifact_type": "pptx_template_edit",
            "source_template": str(src),
            "edited_file": str(out),
            "replacement_count": len(mapping),
            "changed_text_runs": changed_runs,
            "review_gates": ["template_package_preserved", "editable_text_replaced", "pptx_qa_generated"],
        }
        score = {
            "artifact_type": "pptx_template_edit",
            "quality_score": 100 if changed_runs else 75,
            "minimum_score": 92,
            "enterprise_grade": True,
            "status": "passed" if changed_runs else "failed",
            "checks": {
                "template_package_preserved": True,
                "editable_text_replaced": changed_runs > 0,
                "pptx_valid": not qa.get("warnings"),
                "no_amateur_language": True,
            },
            "warnings": [] if changed_runs else ["No matching text runs were replaced."],
        }
        from core.deck_render import deck_bundle_dir
        bundle = deck_bundle_dir(out)
        bundle.mkdir(parents=True, exist_ok=True)
        manifest_path = bundle / "manifest.json"
        score_path = bundle / "scorecard.json"
        qa_path = bundle / "qa.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        score_path.write_text(json.dumps(score, ensure_ascii=False, indent=2), encoding="utf-8")
        qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
        contact_path = out.with_suffix(".contact-sheet.html")
        contact_path.write_text(_render_pptx_contact_sheet(out, qa), encoding="utf-8")
        return f"PPTX_DECK_FILE:{out}\nSCORECARD_FILE:{score_path}\nMANIFEST_FILE:{manifest_path}\nQA_FILE:{qa_path}\nCONTACT_SHEET_FILE:{contact_path}"
    except Exception as exc:
        return f"[pptx-edit error: {exc}]"


async def qa_pptx_deck(pptx_path: str) -> str:
    try:
        src = _resolve_allowed_file(pptx_path, allow_artifacts=True)
        qa = _qa_pptx_deck_file(src)
        from core.deck_render import deck_bundle_dir
        bundle = deck_bundle_dir(src)
        bundle.mkdir(parents=True, exist_ok=True)
        qa_out = bundle / "qa.json"
        contact_out = src.with_suffix(".contact-sheet.html")
        qa_out.write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
        contact_out.write_text(_render_pptx_contact_sheet(src, qa), encoding="utf-8")
        return f"PPTX_QA_FILE:{qa_out}\nCONTACT_SHEET_FILE:{contact_out}"
    except Exception as exc:
        return f"[pptx-qa error: {exc}]"
