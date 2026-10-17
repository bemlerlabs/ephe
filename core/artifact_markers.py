"""The artifact-marker table exists once, here.

Every tool in ``core/tools`` and the deck pipeline announces a produced file with a
``*_FILE:`` marker line. Three modules read that set and each used to keep its own
copy: the evidence gate in ``core/tools/registry.py`` stamps ``ARTIFACT_VERIFIED``,
``core/quality.py`` turns the markers into typed artifacts, and
``server/routes/chat.py`` registers the library row. Two copies fell behind, so a
produced file reached neither the library nor the evidence stamp. The set now lives
only here; the callers import it and filter it, never restate it.
``tests/test_artifact_marker_single_source.py`` fails the moment one grows a copy
again.

Row shape: ``(marker, kind, label, activity_word, with_name)``. ``kind`` is the
library kind the workbench stores; ``with_name`` appends the file name to the
activity-rail label. The marker strings sit in string literals on purpose — a label
reaches the UI, so localising it is a locale-file job, not a rename here.
"""
from __future__ import annotations

# Copied verbatim from the emitters (rg "'_FILE:'" across core/). The four trailing
# rows name markers no tool emits in this revision; they stay so a declared kind and
# a silent library cannot drift apart again.
ARTIFACT_MARKERS: tuple[tuple[str, str, str, str, bool], ...] = (
    ("CHART_FILE:", "chart", "📊 Chart created", "Chart", False),
    ("PDF_FILE:", "pdf", "📄 PDF", "PDF", True),
    ("SVG_FILE:", "svg", "🎨 SVG", "SVG", True),
    ("XLSX_FILE:", "xlsx", "📊 Excel", "Excel", True),
    ("DOCX_FILE:", "docx", "📝 Word", "Word", True),
    ("PNG_FILE:", "png", "🖼️ Bild", "Image", True),
    ("PITCH_DECK_FILE:", "deck", "📊 Deck", "Deck", True),
    ("PPTX_DECK_FILE:", "pptx", "📊 Folien", "Folien", True),
    ("SCREENSHOT_FILE:", "screenshot", "📷 Screenshot", "Screenshot", True),
    ("WRITE_FILE:", "file", "📝 File saved", "File", True),
    ("PREVIEW_FILE:", "html", "🎞️ Deck preview", "Preview", True),
    ("SCORECARD_FILE:", "scorecard", "🧮 Scorecard", "Scorecard", True),
    ("MANIFEST_FILE:", "manifest", "📋 Manifest", "Manifest", True),
    ("RENDER_QA_FILE:", "render_qa", "🔎 Render QA", "Render QA", True),
    ("VISUAL_QA_FILE:", "visual_qa", "👁️ Visual QA", "Visual QA", True),
    ("DECK_SPEC_FILE:", "deck_spec", "📐 Deck spec", "Deck spec", True),
    ("EVIDENCE_LEDGER_FILE:", "evidence_ledger", "📑 Evidence ledger", "Evidence ledger", True),
    ("QA_FILE:", "qa", "✅ Deck QA", "QA", True),
    ("PPTX_QA_FILE:", "pptx_qa", "✅ PPTX QA", "PPTX QA", True),
    ("CONTACT_SHEET_FILE:", "html", "🗂️ Contact sheet", "Contact sheet", True),
    ("PPTX_TEMPLATE_ANALYSIS_FILE:", "pptx_template_analysis", "🧩 Template analysis", "Template analysis", True),
    ("SOURCE_NOTEBOOK_FILE:", "source_notebook", "📓 Source notebook", "Source notebook", True),
    ("SOURCE_BRIEF_FILE:", "source_brief", "📄 Source brief", "Source brief", True),
    ("DECK_STUDIO_FILE:", "deck_studio", "🎛️ Deck Studio", "Deck Studio", True),
    ("DIAGRAM_FILE:", "diagram", "🧭 Diagram", "Diagram", True),
    ("VIDEO_FILE:", "video", "🎬 Video", "Video", True),
    ("SOURCES_FILE:", "sources", "🔖 Sources", "Sources", True),
)

#: The marker column, in table order — what the evidence gate scans for.
ARTIFACT_MARKER_PREFIXES: tuple[str, ...] = tuple(row[0] for row in ARTIFACT_MARKERS)

#: Marker by library kind. A kind repeats only where two markers share one ("html"
#: is preview and contact sheet), so a caller resolving a kind unique here — the
#: twelve ``core/quality.py`` validates — is exact.
MARKER_BY_KIND: dict[str, str] = {kind: marker for marker, kind, *_ in ARTIFACT_MARKERS}
