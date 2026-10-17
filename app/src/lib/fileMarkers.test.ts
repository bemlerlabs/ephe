import { describe, expect, it } from 'vitest'
import { stripFileMarkers } from './fileMarkers'

describe('stripFileMarkers', () => {
  it('removes a marker line and keeps the surrounding answer', () => {
    const input =
      '## QR code created\nContent: `https://example.com`\nPNG_FILE:/Users/me/Downloads/qr.png\n\nScannable PNG.'
    expect(stripFileMarkers(input)).toBe(
      '## QR code created\nContent: `https://example.com`\n\nScannable PNG.',
    )
  })

  it('removes multiple marker lines of different kinds', () => {
    const input = 'Intro\nXLSX_FILE:/tmp/budget.xlsx\nMiddle\nSVG_FILE:/tmp/map.svg\nOutro'
    const out = stripFileMarkers(input)
    expect(out).toBe('Intro\nMiddle\nOutro')
    expect(out).not.toContain('_FILE:')
  })

  it('returns text unchanged when no marker is present', () => {
    const input = '# Normal answer\n- no plumbing here\n- just content'
    expect(stripFileMarkers(input)).toBe(input)
  })

  it('ignores markers that appear mid-line (not at line start)', () => {
    const input = 'See the PDF_FILE: mention inside a sentence.'
    expect(stripFileMarkers(input)).toBe(input)
  })

  it('collapses blank gaps left behind by stripped lines', () => {
    const input = 'A\n\nPNG_FILE:/tmp/x.png\n\n\nB'
    expect(stripFileMarkers(input)).toBe('A\n\nB')
  })

  it('handles the full FILE_MARKER_MAP set', () => {
    const markers = [
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
      'SOURCE_NOTEBOOK_FILE:',
      'SOURCE_BRIEF_FILE:',
      'DECK_STUDIO_FILE:',
      'DIAGRAM_FILE:',
      'VIDEO_FILE:',
      'SOURCES_FILE:',
    ]
    for (const marker of markers) {
      expect(stripFileMarkers(`before\n${marker}/tmp/f\nafter`)).toBe('before\nafter')
    }
  })
})
