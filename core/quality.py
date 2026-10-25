"""Local quality gates for Ephe skills and artifacts."""
from __future__ import annotations

import html as html_lib
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from core.artifact_markers import MARKER_BY_KIND
from core.tool_markers import (
    CURRENT_REFUSAL_MARKERS,
    FETCH_FAILED_MARKER,
    LEGACY_REFUSAL_MARKERS,
)


@dataclass
class ToolResult:
    tool: str
    status: str
    summary: str
    evidence: list[str] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    raw: str = ""


@dataclass
class QualityReport:
    status: str
    needs_revision: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ArtifactValidationReport:
    artifact_type: str
    status: str
    path: str
    warnings: list[str] = field(default_factory=list)
    # P1 document-quality roadmap: additive per-check detail (margins, type
    # scale, heading policy, citations). Optional with a default, so existing
    # consumers of the dataclass are unaffected.
    checks: dict = field(default_factory=dict)


#: P0-2 (Deep-Audit 2026-09-13): explicit error prefixes instead of the fragile
#: `startswith("[") and "error" in raw` heuristic. The chat/registry layers
#: emit different prefixes; `ARTIFACT_FAILED:` and `[TOOL-DENIED]`
#: carry no "error" word and would have slipped through the old heuristic as success.
ERROR_RESULT_PREFIXES: tuple[str, ...] = (
    "[TOOL-ERROR]",
    "[TOOL-DENIED]",
    "[tool-error",
    "[MCP-tool-error",
    "ARTIFACT_FAILED:",
    FETCH_FAILED_MARKER,
)


def is_error_result(raw: str) -> bool:
    """Deterministic error detection over the known tool-error prefixes.

    The legacy fallback for bracketed lines carrying an error keyword stays.
    """
    text = str(raw or "")
    if text.startswith(ERROR_RESULT_PREFIXES):
        return True
    return text.startswith("[") and ("Fehler" in text or "Error" in text or "error" in text.lower())


#: I1-9: the second axis of the audit log. `status` says whether a call ran —
#: `decision` says whether it was ever allowed to. A blockade standing as
#: `status=ok, decision=""` in the line does not answer the question the log is
#: written for ("the cell dies, the protocol stays").
#: The refusal markers are the constants the tools format with (`core/tool_markers.py`),
#: so producer and matcher cannot drift apart again.
BLOCKED_RESULT_PREFIXES: tuple[str, ...] = (
    "⚠️ Security:",
    *CURRENT_REFUSAL_MARKERS,
    "[TOOL-DENIED]",
    # `LEGACY_REFUSAL_MARKERS` — the German wording these tools used before the
    # switch. Rows already on disk carry it and must still read as `blocked`, not
    # silently as an ordinary run, so holding both costs nothing here. Removing it
    # is a deliberate later step once no reachable row carries it any more — an
    # owner's decision, not an oversight, and not part of this change.
    *LEGACY_REFUSAL_MARKERS,
)
#: No prefix: the cell reports its own refusal as a status word in a line that
#: otherwise describes a successful run (`[execute_code] runtime=… status=…`).
BLOCKED_RESULT_TOKENS: tuple[str, ...] = ("status=GUEST_UNVERIFIED",)


def result_decision(raw: str) -> str:
    """`blocked` when the tool pronounces its own blockade — otherwise `''`."""
    text = str(raw or "")
    if text.startswith(BLOCKED_RESULT_PREFIXES):
        return "blocked"
    if any(token in text for token in BLOCKED_RESULT_TOKENS):
        return "blocked"
    return ""


def normalize_tool_result(tool: str, result: str) -> ToolResult:
    raw = str(result or "")
    if is_error_result(raw):
        return ToolResult(
            tool=tool,
            status="error",
            summary=raw.strip("[]"),
            warnings=[raw],
            raw=raw,
        )

    artifacts = _artifacts_from_raw(raw)
    if artifacts:
        artifact_type = artifacts[0]["type"].upper()
        summary = f"{len(artifacts)} artifacts created" if len(artifacts) > 1 else f"{artifact_type} artifact created"
        return ToolResult(
            tool=tool,
            status="success",
            summary=summary,
            evidence=[f"{tool} returned {raw}"],
            artifacts=artifacts,
            raw=raw,
        )

    summary = raw.strip().splitlines()[0][:160] if raw.strip() else "Tool returned empty output"
    warnings = ["Tool returned empty output"] if not raw.strip() else []
    return ToolResult(
        tool=tool,
        status="warning" if warnings else "success",
        summary=summary,
        evidence=[raw[:500]] if raw.strip() else [],
        warnings=warnings,
        raw=raw,
    )


def budget_note_is_unfinished(text: str) -> bool:
    """R37: cap-end detection — the budget note is by definition unfinished
    (the quality gate reports 'fail', no pseudo-complete)."""
    return "budget exhausted" in (text or "")


#: Tools whose output can ground arithmetic over file contents. `read_file`
#: counts because a quoted total may already sit in the data; the comparison
#: below then checks it against that real output instead of trusting the answer.
ARITHMETIC_EVIDENCE_TOOLS: frozenset[str] = frozenset({
    "run_shell",
    "execute_code",
    "run_tests",
    "read_file",
    "extract_pdf_text",
    "query_source_notebook",
    "analyze_project",
})

_NUMBER_TOKEN_RE = re.compile(
    r"(?<![A-Za-z\d])-?(?:\d{1,3}(?:[.,\s\u00a0]\d{3})+|\d+)(?:[.,]\d+)?(?![A-Za-z])"
)
_FINAL_ANSWER_RE = re.compile(r"(?:EPHE_FINAL_ANSWER|FINAL ANSWER)\s*:", re.IGNORECASE)
_RESULT_LINE_RE = re.compile(r"\b(?:total|sum|highest|gesamt|summe)\b", re.IGNORECASE)


def _canonical_number(token: str) -> str:
    """One canonical decimal form for 101, 101.0, 1,250.00 and 1.250,00."""
    text = token.replace("\u00a0", "").replace(" ", "").replace("'", "")
    sign = "-" if text.startswith("-") else ""
    text = text.lstrip("+-")
    if "," in text and "." in text:
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        text = text.replace(thousands, "").replace(decimal, ".")
    elif "," in text:
        head, _, tail = text.rpartition(",")
        text = head + tail if len(tail) == 3 and 0 < len(head) <= 3 else head + "." + tail
    elif "." in text:
        head, _, tail = text.rpartition(".")
        text = head + tail if len(tail) == 3 and 0 < len(head) <= 3 and head != "0" else head + "." + tail
    if text.startswith("0") and not text.startswith("0."):
        text = text.lstrip("0") or "0"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    if not text or text == "-":
        return "0"
    return ("-" + text) if sign and text != "0" else text


def _numbers_in_text(text: str) -> set[str]:
    return {_canonical_number(match.group(0)) for match in _NUMBER_TOKEN_RE.finditer(text or "")}


def _ordered_numbers(text: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for match in _NUMBER_TOKEN_RE.finditer(text or ""):
        number = _canonical_number(match.group(0))
        if number not in seen:
            seen.add(number)
            ordered.append(number)
    return ordered


def _claimed_result_segments(answer: str) -> list[list[str]]:
    """Number groups that present themselves as the computed result.

    After an explicit ``FINAL ANSWER:`` marker the whole tail counts; outside
    one, only lines that name a result (total/sum/highest/gesamt/summe). A
    group is compared as a whole, so an incidental number beside the result
    cannot make an invented result look grounded.
    """
    segments: list[list[str]] = []
    marker = None
    for marker in _FINAL_ANSWER_RE.finditer(answer or ""):
        pass
    if marker is not None:
        numbers = _ordered_numbers((answer or "")[marker.end():])
        if numbers:
            segments.append(numbers)
    for line in (answer or "").splitlines():
        if _RESULT_LINE_RE.search(line):
            numbers = _ordered_numbers(line)
            if numbers:
                segments.append(numbers)
    return segments


def _arithmetic_verdict(question: str | None, answer: str, tool_results: list[ToolResult]) -> str:
    """'' when the arithmetic is grounded, otherwise the hard issue text."""
    if not question:
        return ""
    from core.persona import needs_compute_guard

    if not needs_compute_guard(question):
        return ""
    evidence = [
        result
        for result in tool_results
        if result.status != "error" and result.tool in ARITHMETIC_EVIDENCE_TOOLS
    ]
    if not evidence:
        return "Numbers not derived from tool output: file arithmetic requires tool execution."
    available: set[str] = set()
    for result in evidence:
        available |= _numbers_in_text(result.raw)
    for segment in _claimed_result_segments(answer):
        if not set(segment) & available:
            return "Numbers not derived from tool output: claimed result does not match computed tool output."
    return ""


def evaluate_quality(*, answer: str, skill, tool_results: list[ToolResult], question: str | None = None) -> QualityReport:
    issues: list[str] = []
    warnings: list[str] = []
    answer_text = answer or ""
    successful_artifacts = [
        artifact
        for result in tool_results
        if result.status == "success"
        for artifact in result.artifacts
    ]

    for artifact_type in getattr(skill, "artifact_types", []) or []:
        if _answer_claims_artifact(answer_text, artifact_type) and not any(
            artifact.get("type") == artifact_type for artifact in successful_artifacts
        ):
            issues.append(f"Missing real {artifact_type} artifact evidence for final answer.")

    arithmetic_issue = _arithmetic_verdict(question, answer_text, tool_results)
    if arithmetic_issue:
        issues.append(arithmetic_issue)

    # R38: expectation-based gate — declared skill test expectations are hard,
    # deterministic checks (no LLM) — but only for their own input case
    # (1:1 test semantics): the TEST block of the skill carries a concrete
    # input; with a differing current question the expectations count as
    # advisory (warnings), not as an issue. Without a declared input the gate
    # applies directly (generic-case semantics).
    test = getattr(skill, "test", None)
    expect_contains = str(getattr(test, "expect_contains", "") or "")
    expect_tool = str(getattr(test, "expect_tool", "") or "")
    if expect_contains or expect_tool:
        test_input = " ".join(str(getattr(test, "input", "") or "").lower().split())
        q_norm = " ".join((question or "").lower().split())
        hard = (not test_input) or (test_input == q_norm)
        bucket = issues if hard else warnings
        if expect_contains and expect_contains.lower() not in answer_text.lower():
            bucket.append(f"Expected content missing: '{expect_contains}'.")
        if expect_tool and not any(
            result.tool == expect_tool and result.status != "error" for result in tool_results
        ):
            bucket.append(f"Expected tool not executed: '{expect_tool}'.")

    if getattr(skill, "tools", None) and not tool_results:
        warnings.append("Skill declared tools but no tool results were captured.")

    if "tbd" in answer_text.lower() or "todo" in answer_text.lower():
        warnings.append("Answer contains unfinished placeholder wording.")

    return QualityReport(
        status="failed" if issues else "passed",
        needs_revision=bool(issues),
        issues=issues,
        warnings=warnings,
    )


def validate_artifact(artifact: dict) -> ArtifactValidationReport:
    if artifact.get("type") == "pdf":
        return validate_pdf_artifact(str(artifact.get("path", "")))
    if artifact.get("type") == "deck":
        return validate_pitch_deck_artifact(str(artifact.get("path", "")))
    if artifact.get("type") == "pptx":
        return validate_pptx_deck_artifact(str(artifact.get("path", "")))
    if artifact.get("type") == "deck_studio":
        return validate_deck_studio_artifact(str(artifact.get("path", "")))
    if artifact.get("type") == "notebook":
        return validate_source_notebook_artifact(str(artifact.get("path", "")))
    if artifact.get("type") == "source_brief":
        return validate_source_brief_artifact(str(artifact.get("path", "")))
    path = str(artifact.get("path", ""))
    warnings = []
    if not path or not Path(path).exists():
        warnings.append("Artifact file does not exist.")
    return ArtifactValidationReport(
        artifact_type=str(artifact.get("type", "artifact")),
        status="failed" if warnings else "passed",
        path=path,
        warnings=warnings,
    )


def validate_deck_studio_artifact(path: str) -> ArtifactValidationReport:
    warnings: list[str] = []
    studio_path = Path(path)
    if not studio_path.exists():
        return ArtifactValidationReport("deck_studio", "failed", path, ["Deck Studio file does not exist."])
    text = studio_path.read_text(encoding="utf-8", errors="replace")
    for marker in ("Ephe Slide Studio", "Choose Output", "Slide Contact Sheet"):
        if marker not in text:
            warnings.append(f"Deck Studio is missing required marker: {marker}.")
    has_pptx_download = "Download PPTX" in text or "Download editable PPTX" in text
    has_pdf_download = "Download PDF" in text or "Open PDF slides" in text
    if not has_pptx_download or not has_pdf_download:
        warnings.append("Deck Studio does not expose selectable PDF/PPTX downloads.")
    if "Open QA Report" not in text:
        warnings.append("Deck Studio does not expose the deterministic QA report.")
    if "Open Claim Manifest" not in text:
        warnings.append("Deck Studio does not expose the claim manifest.")
    linked_paths = _extract_existing_file_links(text)
    linked_suffixes = {path.suffix.lower() for path in linked_paths}
    linked_names = {path.name.lower() for path in linked_paths}
    if len(linked_paths) < 4:
        warnings.append("Deck Studio is missing real local download links.")
    if ".pdf" not in linked_suffixes:
        warnings.append("Deck Studio does not link to a real local PDF export.")
    if ".pptx" not in linked_suffixes:
        warnings.append("Deck Studio does not link to a real local PPTX export.")
    if not any(name.endswith(".qa.json") for name in linked_names):
        warnings.append("Deck Studio does not link to a real local QA report.")
    if not any(name.endswith(".manifest.json") for name in linked_names):
        warnings.append("Deck Studio does not link to a real local claim manifest.")
    return ArtifactValidationReport("deck_studio", "failed" if warnings else "passed", str(studio_path), warnings)


def _extract_existing_file_links(text: str) -> list[Path]:
    paths: list[Path] = []
    for raw_href in re.findall(r'href=["\']file://([^"\']+)["\']', text or ""):
        candidate = Path(html_lib.unescape(raw_href)).expanduser()
        if candidate.exists():
            paths.append(candidate)
    return paths


def validate_source_notebook_artifact(path: str) -> ArtifactValidationReport:
    warnings: list[str] = []
    notebook_path = Path(path)
    if not notebook_path.exists():
        return ArtifactValidationReport("notebook", "failed", path, ["Source notebook file does not exist."])
    try:
        import json

        payload = json.loads(notebook_path.read_text(encoding="utf-8"))
        if int(payload.get("schema_version", 0)) < 1:
            warnings.append("Source notebook schema version is missing.")
        if int(payload.get("source_count", 0)) < 1:
            warnings.append("Source notebook has no indexed sources.")
        if int(payload.get("chunk_count", 0)) < 1:
            warnings.append("Source notebook has no evidence chunks.")
        chunks = payload.get("chunks", [])
        if chunks and not all(chunk.get("chunk_id") and chunk.get("text") for chunk in chunks[:10]):
            warnings.append("Source notebook chunks are missing IDs or text.")
    except Exception as exc:
        warnings.append(f"Source notebook validation failed: {exc}")
    return ArtifactValidationReport("notebook", "failed" if warnings else "passed", str(notebook_path), warnings)


def validate_source_brief_artifact(path: str) -> ArtifactValidationReport:
    warnings: list[str] = []
    brief_path = Path(path)
    if not brief_path.exists():
        return ArtifactValidationReport("source_brief", "failed", path, ["Source brief file does not exist."])
    text = brief_path.read_text(encoding="utf-8", errors="replace")
    for marker in ("Executive Summary", "Evidence Register", "Source Manifest"):
        if marker not in text:
            warnings.append(f"Source brief is missing required section: {marker}.")
    if not re_search_citation(text):
        warnings.append("Source brief does not contain source chunk citations.")
    return ArtifactValidationReport("source_brief", "failed" if warnings else "passed", str(brief_path), warnings)


def validate_pptx_deck_artifact(path: str) -> ArtifactValidationReport:
    warnings: list[str] = []
    pptx_path = Path(path)
    if not pptx_path.exists():
        return ArtifactValidationReport("pptx", "failed", path, ["PPTX deck file does not exist."])
    if pptx_path.suffix.lower() != ".pptx":
        warnings.append("Deck export is not a .pptx file.")
    try:
        with zipfile.ZipFile(pptx_path) as pptx:
            names = set(pptx.namelist())
            required = {"[Content_Types].xml", "_rels/.rels", "ppt/presentation.xml", "ppt/_rels/presentation.xml.rels"}
            missing = sorted(required - names)
            if missing:
                warnings.append(f"PPTX package is missing required parts: {', '.join(missing)}.")
            slide_names = sorted(name for name in names if name.startswith("ppt/slides/slide") and name.endswith(".xml"))
            if len(slide_names) < 8:
                warnings.append("PPTX deck has fewer than 8 slides.")
            text_runs = 0
            for slide_name in slide_names:
                xml = pptx.read(slide_name).decode("utf-8", errors="replace")
                text_runs += xml.count("<a:t>")
                if "Proof Object:" in xml or "Animation Plan" in xml:
                    warnings.append("PPTX deck contains internal presentation markers.")
            if text_runs < max(12, len(slide_names) * 4):
                warnings.append("PPTX deck has too few editable text runs.")
    except Exception as exc:
        warnings.append(f"PPTX validation failed: {exc}")

    warnings.extend(_validate_deck_sidecars(pptx_path))
    from core.deck_render import deck_bundle_dir
    qa_path = deck_bundle_dir(pptx_path) / "qa.json"
    contact_path = pptx_path.with_suffix(".contact-sheet.html")
    if not qa_path.exists():
        warnings.append("PPTX visual QA report is missing.")
    if not contact_path.exists():
        warnings.append("PPTX contact sheet is missing.")
    return ArtifactValidationReport(
        artifact_type="pptx",
        status="failed" if warnings else "passed",
        path=str(pptx_path),
        warnings=warnings,
    )


def _validate_deck_sidecars(path: Path) -> list[str]:
    from core.deck_render import deck_bundle_dir
    bundle = deck_bundle_dir(path)
    warnings: list[str] = []
    score_path = bundle / "scorecard.json"
    if not score_path.exists():
        warnings.append("Deck scorecard is missing.")
    else:
        try:
            import json

            score = json.loads(score_path.read_text(encoding="utf-8"))
            minimum_score = int(score.get("minimum_score", 92 if score.get("enterprise_grade") else 85))
            if int(score.get("quality_score", 0)) < minimum_score:
                warnings.append("Deck scorecard is below the acceptance threshold.")
            if score.get("status") != "passed":
                warnings.append("Deck scorecard status is not acceptable.")
            if score.get("enterprise_grade") and not score.get("checks", {}).get("no_amateur_language"):
                warnings.append("Deck contains amateur language according to scorecard.")
        except Exception as exc:
            warnings.append(f"Deck scorecard validation failed: {exc}")

    manifest_path = bundle / "manifest.json"
    if not manifest_path.exists():
        warnings.append("Deck claim-spine manifest is missing.")
    render_qa_path = bundle / "render-qa.json"
    if path.suffix.lower() == ".pdf":
        if not render_qa_path.exists():
            warnings.append("Deck render QA report is missing.")
        else:
            try:
                import json

                render_qa = json.loads(render_qa_path.read_text(encoding="utf-8"))
                if render_qa.get("status") != "passed":
                    warnings.append("Deck render QA status is not acceptable.")
                checks = render_qa.get("checks", {})
                if checks.get("no_text_in_visual_column") is False:
                    warnings.append("Deck render QA detected text entering the visual column.")
                if not checks.get("visuals_bounded"):
                    warnings.append("Deck render QA detected out-of-bounds visual elements.")
            except Exception as exc:
                warnings.append(f"Deck render QA validation failed: {exc}")
    return warnings


def validate_pitch_deck_artifact(path: str) -> ArtifactValidationReport:
    warnings: list[str] = []
    pdf_path = Path(path)
    if not pdf_path.exists():
        return ArtifactValidationReport("deck", "failed", path, ["Pitch deck PDF file does not exist."])
    if pdf_path.suffix.lower() != ".pdf":
        warnings.append("Pitch deck export is not a PDF file.")

    try:
        import pdfplumber

        with pdfplumber.open(str(pdf_path)) as pdf:
            page_count = len(pdf.pages)
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        if page_count < 8:
            warnings.append("Pitch deck has fewer than 8 slides.")
        for marker in ("Animation Plan", "Proof Object:", "Evidence: assumptions", MARKER_BY_KIND["deck_studio"]):
            if marker in text:
                warnings.append(f"Pitch deck contains internal marker: {marker}.")
        if not text.strip():
            warnings.append("Pitch deck has no extractable text.")
        if "(cid:" in text:
            warnings.append("Pitch deck text extraction contains broken glyph markers.")
    except Exception as exc:
        warnings.append(f"Pitch deck validation failed: {exc}")

    try:
        import json as _json

        from core.deck_quality import qa_pdf_render
        from core.deck_render import deck_bundle_dir
        bundle = deck_bundle_dir(pdf_path)
        spec_path = bundle / "deck-spec.json"
        spec = _json.loads(spec_path.read_text(encoding="utf-8")) if spec_path.exists() else {"slides": []}
        render_qa = qa_pdf_render(pdf_path, spec)
        bundle.mkdir(parents=True, exist_ok=True)
        (bundle / "render-qa.json").write_text(
            json.dumps(render_qa, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        warnings.append(f"Pitch deck render QA failed: {exc}")

    warnings.extend(_validate_deck_sidecars(pdf_path))

    render_warning = _pdf_render_contrast_warning(pdf_path)
    if render_warning and "No such file or directory" not in render_warning:
        warnings.append(render_warning)

    return ArtifactValidationReport(
        artifact_type="deck",
        status="failed" if warnings else "passed",
        path=str(pdf_path),
        warnings=warnings,
    )


def validate_pdf_artifact(path: str) -> ArtifactValidationReport:
    warnings: list[str] = []
    pdf_path = Path(path)
    if not pdf_path.exists():
        return ArtifactValidationReport("pdf", "failed", path, ["PDF file does not exist."])
    if pdf_path.suffix.lower() != ".pdf":
        warnings.append("File extension is not .pdf.")

    text = ""
    try:
        import pdfplumber

        with pdfplumber.open(str(pdf_path)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        if not text.strip():
            warnings.append("PDF has no extractable text.")
        if "(cid:" in text:
            warnings.append("PDF text extraction contains broken glyph markers.")
    except Exception as exc:
        warnings.append(f"PDF text validation failed: {exc}")

    render_warning = _pdf_render_contrast_warning(pdf_path)
    if render_warning:
        warnings.append(render_warning)

    # P1 document-quality roadmap: additive, manifest-driven criteria
    # (margins, type scale, heading policy, citation integrity). Warning
    # level; PDFs without a render manifest are not flagged (backcompat).
    extended_warnings, checks = _extended_pdf_doc_checks(pdf_path, text)
    warnings.extend(extended_warnings)

    return ArtifactValidationReport(
        artifact_type="pdf",
        status="failed" if warnings else "passed",
        path=str(pdf_path),
        warnings=warnings,
        checks=checks,
    )


def _extended_pdf_doc_checks(pdf_path: Path, extracted_text: str) -> tuple[list[str], dict]:
    """P1 document-quality checks based on the build-time render manifest.

    All extended criteria are driven by the sidecar manifest that create_pdf
    writes next to the PDF (``<stem>.doc-manifest.json``):

    - margins >= 18 mm: build-time token values. reportlab stores no margin
      metadata inside the PDF itself, so measurable margin validation is
      manifest-based and the renderer asserts the floor at build time
      (documented in ``core/tools/pdf_tools.py``).
    - font sizes within the modular type scale of ``core/doc_design.py``.
    - no heading rendered in the bottom 10% of a page (pdfplumber geometry).
    - citation integrity: every numbered reference entry is rendered, and no
      reference entries exist without inline citation markers.
    - P2 (additive, warning-level): rendered tables keep a consistent column
      count; documents built with ``document=True`` carry their cover markers
      on page 1; declared TOC entries are present in the rendered text.

    Documents without a render manifest (foreign or legacy artifacts) are not
    flagged at all: the checks return no warnings and an empty checks dict,
    so old documents validate exactly as before.
    """
    warnings: list[str] = []
    checks: dict = {}
    manifest_path = pdf_path.with_suffix(".doc-manifest.json")
    if not manifest_path.exists():
        return warnings, checks
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"PDF render manifest is unreadable: {exc}"], {"manifest_ok": False}

    from core.doc_design import (
        CITATION_ENTRY_RE,
        MARGIN_FLOOR_MM,
        citation_reference_text,
        is_on_type_scale,
    )

    checks["manifest_ok"] = True

    # Margins (build-time token values recorded in the manifest).
    margins_mm = {str(k): float(v) for k, v in (manifest.get("margins_mm") or {}).items()}
    checks["margins_mm"] = margins_mm
    margins_ok = bool(margins_mm) and all(value >= MARGIN_FLOOR_MM for value in margins_mm.values())
    checks["margins_ok"] = margins_ok
    if not margins_ok:
        warnings.append(f"PDF margins below the {MARGIN_FLOOR_MM:g} mm floor: {margins_mm}.")

    # Type-scale conformance of the rendered font sizes.
    sizes = [float(size) for size in (manifest.get("font_sizes_pt") or [])]
    off_scale = [size for size in sizes if not is_on_type_scale(size)]
    checks["off_scale_sizes_pt"] = off_scale
    checks["type_scale_ok"] = not off_scale
    if off_scale:
        warnings.append(f"PDF font sizes off the document type scale: {off_scale}.")

    # Heading page-break policy: no heading in the bottom 10% of any page.
    checks["heading_bottom_pages"] = []
    role_sizes = manifest.get("roles") or {}
    heading_sizes = [float(role_sizes[role]) for role in (manifest.get("heading_roles") or []) if role in role_sizes]
    if heading_sizes:
        try:
            import pdfplumber

            threshold = min(heading_sizes)
            bottom_pages: list[int] = []
            with pdfplumber.open(str(pdf_path)) as pdf:
                for page_index, page in enumerate(pdf.pages, 1):
                    limit = page.height * 0.9
                    for char in page.chars:
                        if (
                            float(char.get("size", 0)) >= threshold
                            and str(char.get("fontname", "")).endswith("Bold")
                            and float(char.get("top", 0)) > limit
                        ):
                            bottom_pages.append(page_index)
                            break
            checks["heading_bottom_pages"] = sorted(set(bottom_pages))
            if checks["heading_bottom_pages"]:
                warnings.append(
                    f"Heading rendered in the bottom 10% of page(s): {checks['heading_bottom_pages']}."
                )
        except Exception:
            checks["heading_geometry_checked"] = False

    # Citation integrity between inline markers and the references section.
    citations = manifest.get("citations") or {}
    references = citations.get("references") or []
    integrity_ok = True
    body_text = extracted_text or ""
    if references:
        for entry in references:
            expected = citation_reference_text(int(entry.get("number", 0)), str(entry.get("chunk_id", "")))
            if expected not in body_text:
                integrity_ok = False
                warnings.append(f"PDF reference entry missing in rendered document: {expected}.")
    else:
        orphan_entries = CITATION_ENTRY_RE.findall(body_text)
        if orphan_entries:
            integrity_ok = False
            warnings.append("PDF document contains reference entries without inline citation markers.")
    checks["citations"] = {
        "inline_count": int(citations.get("inline_count") or 0),
        "reference_count": len(references),
        "integrity_ok": integrity_ok,
    }

    # P2 document-quality checks: tables, cover, TOC. All additive and gated
    # on manifest keys that P1-era manifests do not carry, so legacy
    # documents without those fields stay warning-free.
    tables_info = manifest.get("tables") if isinstance(manifest.get("tables"), dict) else {}
    declared_tables = int(tables_info.get("count") or 0)
    has_cover = bool(manifest.get("has_cover"))
    toc_entries = manifest.get("toc_entries") if isinstance(manifest.get("toc_entries"), list) else []

    checks["tables"] = {"declared": declared_tables, "extracted": 0, "columns_consistent": True}
    checks["cover"] = {"declared": has_cover, "present": True}
    checks["toc"] = {"declared": len(toc_entries), "missing": []}

    if declared_tables or has_cover or toc_entries:
        try:
            page_count = 0
            page1_text = ""
            extracted_tables: list = []
            import pdfplumber

            with pdfplumber.open(str(pdf_path)) as pdf:
                page_count = len(pdf.pages)
                if page_count:
                    page1_text = pdf.pages[0].extract_text() or ""
                if declared_tables:
                    for page in pdf.pages:
                        extracted_tables.extend(page.extract_tables() or [])
        except Exception:
            checks["geometry_checked"] = False
        else:
            consistency_warnings = _table_column_consistency_warnings(extracted_tables)
            warnings.extend(consistency_warnings)
            checks["tables"] = {
                "declared": declared_tables,
                "extracted": len(extracted_tables),
                "columns_consistent": not consistency_warnings,
            }
            if declared_tables and not extracted_tables:
                warnings.append("PDF manifest declares tables but none were extractable from the rendered document.")
            if has_cover:
                # Extraction wraps long cover titles across lines; compare on
                # whitespace-normalized text so the marker check stays honest.
                title_text = " ".join(str(manifest.get("title") or "").split())
                normalized_page1 = " ".join(page1_text.split())
                cover_present = page_count >= 2 and bool(title_text) and title_text in normalized_page1
                checks["cover"]["present"] = cover_present
                if not cover_present:
                    warnings.append("PDF document=True cover markers missing on page 1.")
            missing_toc = []
            for entry in toc_entries:
                entry_text = " ".join(str(entry.get("text") or "").split()) if isinstance(entry, dict) else ""
                if entry_text and entry_text not in " ".join((extracted_text or "").split()):
                    missing_toc.append(entry_text)
            checks["toc"] = {"declared": len(toc_entries), "missing": missing_toc}
            if missing_toc:
                warnings.append(f"PDF TOC entries missing in rendered document: {missing_toc}.")
    return warnings, checks


def _table_column_consistency_warnings(tables: list) -> list[str]:
    """P2: within each rendered table, every row must carry the same number
    of columns (pdfplumber extraction geometry)."""
    warnings: list[str] = []
    for index, table in enumerate(tables or [], 1):
        widths = sorted({len(row or []) for row in (table or [])})
        if len(widths) > 1:
            warnings.append(f"PDF table {index} has inconsistent column counts across rows: {widths}.")
    return warnings


def _artifact_from_raw(raw: str) -> dict | None:
    artifacts = _artifacts_from_raw(raw)
    return artifacts[0] if artifacts else None


# Artifact kinds this module validates, in the order its callers expect. The markers
# themselves come from core/artifact_markers; only the kinds are chosen here, and
# "notebook" is this module's own name for the source-notebook kind.
_VALIDATED_KINDS: tuple[str, ...] = (
    "deck", "pptx", "deck_studio", "render_qa", "deck_spec", "visual_qa",
    "evidence_ledger", "source_notebook", "source_brief", "pdf", "svg", "chart",
)
_QUALITY_TYPE = {"source_notebook": "notebook"}


def _artifacts_from_raw(raw: str) -> list[dict]:
    lines = str(raw or "").splitlines()
    artifacts: list[dict] = []
    for kind in _VALIDATED_KINDS:
        marker = MARKER_BY_KIND[kind]
        for line in lines:
            if line.startswith(marker):
                path = line[len(marker):].strip()
                if path:
                    artifact = {"type": _QUALITY_TYPE.get(kind, kind), "path": path}
                    if artifact not in artifacts:
                        artifacts.append(artifact)
    return artifacts


def re_search_citation(text: str) -> bool:
    import re

    return bool(re.search(r"\[S\d{3}-C\d{3}\]", text or ""))


def _answer_claims_artifact(answer: str, artifact_type: str) -> bool:
    lowered = answer.lower()
    if artifact_type == "pdf":
        return "pdf" in lowered or ".pdf" in lowered
    return artifact_type in lowered


def _pdf_render_contrast_warning(path: Path) -> str | None:
    if not shutil.which("pdftoppm"):
        return None
    try:
        from PIL import Image
    except Exception:
        return None

    with tempfile.TemporaryDirectory() as tmp:
        prefix = Path(tmp) / "page"
        try:
            subprocess.run(
                ["pdftoppm", "-png", "-f", "1", "-l", "1", str(path), str(prefix)],
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            image = Image.open(Path(tmp) / "page-1.png").convert("RGB")
        except Exception as exc:
            return f"PDF render validation failed: {exc}"

        width, height = image.size
        crop = image.crop((int(width * 0.08), int(height * 0.14), int(width * 0.92), int(height * 0.55)))
        pixels = crop.tobytes()
        dark_pixels = sum(
            1
            for index in range(0, len(pixels), 3)
            if pixels[index] < 100 and pixels[index + 1] < 100 and pixels[index + 2] < 100
        )
        if dark_pixels < 400:
            return "PDF render has too few dark text pixels for reliable legibility."
    return None
