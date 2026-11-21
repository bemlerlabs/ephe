/**
 * #88 — reading the verdict a browser step leaves in its own result.
 *
 * The payload below is copied from a live run of `browser_go` against a real page on
 * 2026-11-05, so the field names here are the ones `core/browser.py` writes. The parse is
 * the surface's only chance to tell `observed` apart from `unproven`, and a parser that
 * guessed would turn a step nobody confirmed into a green line on a run screen.
 */
import { describe, it, expect } from 'vitest'
import { evidenceFacts, parseStepEvidence, signed } from './browserStepEvidence'

/** Measured, not invented: the first line `browser_go` answered with on a real navigation. */
const LIVE =
  'STEP_EVIDENCE:{"step":"browser_go","verdict":"observed","url":"https://example.com/",' +
  '"title":"Example Domain","delta":{"nodes":19,"text_len":991,"scroll_y":0,"checked":0,' +
  '"url_changed":1,"title_changed":1}}\nThis domain is for use in illustrative examples.'

describe('the STEP_EVIDENCE line a browser step carries', () => {
  it('reads the verdict and the numbers the page moved by', () => {
    const evidence = parseStepEvidence(LIVE)
    expect(evidence?.verdict).toBe('observed')
    expect(evidence?.step).toBe('browser_go')
    expect(evidence?.deltas).toEqual({ elements: 19, characters: 991, scrolled: 0, checked: 0 })
    expect(evidence?.changed).toEqual({ address: true, title: true, focus: false })
    expect(evidence?.moved).toBe(true)
  })

  it('leaves a count that did not move out of what it states', () => {
    const facts = evidenceFacts(parseStepEvidence(LIVE)!)
    expect(facts.map((fact) => fact.kind)).toEqual(['elements', 'characters', 'address', 'title'])
    expect(facts.find((fact) => fact.kind === 'elements')?.value).toBe(19)
  })

  /** The line arrives after the tool's own prose as often as before it. */
  it('finds the line wherever the result puts it', () => {
    const wrapped = `Click executed, then:\n${LIVE}`
    expect(parseStepEvidence(wrapped)?.verdict).toBe('observed')
  })

  it('keeps a step that proved nothing unproven, with nothing to show', () => {
    const line =
      'STEP_EVIDENCE:{"step":"browser_click","verdict":"unproven","url":"","title":"",' +
      '"delta":{},"reason":"nothing observable changed"}'
    const evidence = parseStepEvidence(line)
    expect(evidence?.verdict).toBe('unproven')
    expect(evidence?.moved).toBe(false)
    expect(evidenceFacts(evidence!)).toEqual([])
  })

  it('carries a loss with its sign', () => {
    const line =
      'STEP_EVIDENCE:{"step":"browser_scroll","verdict":"observed","delta":{"nodes":-5,' +
      '"text_len":0,"scroll_y":900,"checked":0}}'
    const evidence = parseStepEvidence(line)
    expect(evidence?.deltas.elements).toBe(-5)
    expect(evidenceFacts(evidence!)).toContainEqual({ kind: 'scrolled', value: 900 })
    expect(signed(-5)).toBe('-5')
    expect(signed(900)).toBe('+900')
  })

  it('says nothing when it read nothing', () => {
    expect(parseStepEvidence(null)).toBeNull()
    expect(parseStepEvidence('The page looks fine.')).toBeNull()
    expect(parseStepEvidence('STEP_EVIDENCE:not json at all')).toBeNull()
    expect(parseStepEvidence('STEP_EVIDENCE:{"verdict":"maybe","delta":{}}')).toBeNull()
    expect(parseStepEvidence('STEP_EVIDENCE:{"delta":{"nodes":"many"}}')).toBeNull()
  })

  /** A number the backend wrote as a string is still the number it measured. */
  it('reads a count written as text without inventing one', () => {
    const line = 'STEP_EVIDENCE:{"verdict":"observed","delta":{"nodes":"12","text_len":null}}'
    const evidence = parseStepEvidence(line)
    expect(evidence?.deltas.elements).toBe(12)
    expect(evidence?.deltas.characters).toBe(0)
  })
})
