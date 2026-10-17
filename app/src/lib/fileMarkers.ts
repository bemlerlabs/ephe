/**
 * Server-parity artifact markers (server/routes/chat.py `_FILE_RESULT_PREFIXES`).
 *
 * Message text can still contain raw marker lines (persisted history, model
 * path, API consumers). Rendering them would leak internal plumbing — the
 * artifact itself arrives as a `file_result` event with preview/download UI.
 *
 * This list MUST stay identical to the server table, marker for marker:
 * `tests/test_artifact_marker_tables.py` parses both sides and fails when one
 * drifts. A table that drifts silently is how the artifact-library gap appeared.
 */
const FILE_MARKERS = [
  'CHART_FILE:',
  'PDF_FILE:',
  'SVG_FILE:',
  'XLSX_FILE:',
  'DOCX_FILE:',
  'PNG_FILE:',
  'PITCH_DECK_FILE:',
  'PPTX_DECK_FILE:',
  'SCREENSHOT_FILE:',
  'WRITE_FILE:',
  // Deck pipeline sidecars (create_pitch_deck / create_pptx_deck).
  'PREVIEW_FILE:',
  'SCORECARD_FILE:',
  'MANIFEST_FILE:',
  'RENDER_QA_FILE:',
  'VISUAL_QA_FILE:',
  'DECK_SPEC_FILE:',
  'EVIDENCE_LEDGER_FILE:',
  'QA_FILE:',
  'PPTX_QA_FILE:',
  'CONTACT_SHEET_FILE:',
  'PPTX_TEMPLATE_ANALYSIS_FILE:',
  // Source tools (create_source_notebook / export_source_brief).
  'SOURCE_NOTEBOOK_FILE:',
  'SOURCE_BRIEF_FILE:',
  // Declared across registry/quality/UI, emitted by no tool in this revision.
  'DECK_STUDIO_FILE:',
  'DIAGRAM_FILE:',
  'VIDEO_FILE:',
  'SOURCES_FILE:',
] as const

const MARKER_LINE_START = new RegExp(`^\\s*(?:${FILE_MARKERS.join('|')})\\S*\\s*$`)

/** Removes whole lines that start with an artifact marker; keeps everything else. */
export function stripFileMarkers(text: string): string {
  if (!text || !text.includes('_FILE:')) return text
  const cleaned = text
    .split('\n')
    .filter((line) => !MARKER_LINE_START.test(line))
    .join('\n')
  return cleaned.replace(/\n{3,}/g, '\n\n')
}
