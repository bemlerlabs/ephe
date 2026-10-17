/**
 * W10 group 8, reopened by W13 — the toolbar row: the 24 px floor at both widths
 * and one glyph size inside the row.
 *
 * GIVEN the toolbar row rendered
 * WHEN a chip, a chip caret and the palette chip are inspected
 * THEN each carries the floor as an unconditional class, and the caret is a
 *      14 px icon node like every other glyph in the row.
 *
 * The floor entered this row width-guarded: the caret carried
 * `max-lg:min-w-6 max-lg:min-h-6` and the chips only a `py-1`, so the phone paid
 * the floor and the desktop client kept the violation. Measured in the live client
 * at 1440 px (2026-10-13): carets 8.8 x 21 px, chips 23 px, palette chip
 * 69.4 x 18 px, and a 10 px text caret beside the row's 14 px icons
 * (ephe-notes/parity/team-d-ui-deltas.md, items 1 and 9). A width-guarded floor is
 * the defect, not the repair — the tokens below are unconditional, and the caret
 * still measures 24 x 24 at 390 px, the value it already had before this change.
 *
 * jsdom applies no media queries, so this file holds the class contract; the px
 * above are the live measurement (e2e/walkthrough/persona-07-handy.spec.ts at
 * 390 x 844, plus the 1440 px pass in the W13 report).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts && 'minutes' in opts ? `${key}:${opts.minutes}` : key,
  }),
}))

import ToolbarRow from './ToolbarRow'

const TOOL_TABS = ['files', 'preview', 'terminal', 'git']

/** The class tokens of an element — Tailwind reads them one by one. */
function tokensOf(el: Element): string[] {
  return el.className.split(/\s+/)
}

/**
 * A viewport at `lg` and above, where the desktop client runs (1440 px). jsdom
 * ignores the query, so the width guard a class carries is the only visible
 * difference between the two cases.
 */
function stubDesktopViewport(): void {
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: query.includes('min-width: 1024px'),
    media: query,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }))
}

describe('ToolbarRow carets (W10 g8)', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ available: false }),
      })),
    )
    localStorage.clear()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('the chip keeps its 44 px phone height', () => {
    render(<ToolbarRow />)
    for (const tab of TOOL_TABS) {
      expect(screen.getByTestId(`toolbar-${tab}`).className).toContain('max-lg:min-h-11')
    }
  })
})

describe('ToolbarRow at desktop width (W13)', () => {
  beforeEach(() => {
    stubDesktopViewport()
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({
        ok: true,
        json: async () => ({ available: false }),
      })),
    )
    localStorage.clear()
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('every chip carries the floor with no width guard', () => {
    render(<ToolbarRow />)
    for (const tab of TOOL_TABS) {
      const tokens = tokensOf(screen.getByTestId(`toolbar-${tab}`))
      expect(tokens, `${tab} chip height at desktop`).toContain('min-h-6')
    }
  })

  it('every caret carries 24 x 24 as an unconditional class', () => {
    render(<ToolbarRow />)
    for (const tab of TOOL_TABS) {
      const tokens = tokensOf(screen.getByTestId(`toolbar-${tab}-menu`))
      expect(tokens, `${tab} caret width at desktop`).toContain('min-w-6')
      expect(tokens, `${tab} caret height at desktop`).toContain('min-h-6')
    }
  })

  it('the palette chip carries the floor and stays desktop-only', () => {
    render(<ToolbarRow />)
    const tokens = tokensOf(screen.getByTestId('toolbar-palette'))
    expect(tokens).toContain('min-h-6')
    expect(tokens).toContain('hidden')
    expect(tokens).toContain('md:inline-flex')
  })

  it('the row draws one glyph size: a 14 px caret icon beside 14 px chip icons', () => {
    render(<ToolbarRow />)
    for (const tab of TOOL_TABS) {
      const caret = screen.getByTestId(`toolbar-${tab}-menu`).querySelector('svg')
      expect(caret, `${tab} caret is a text glyph, not an icon`).toBeTruthy()
      expect(caret!.getAttribute('class')).toContain('h-3.5 w-3.5')
      const chipIcon = screen.getByTestId(`toolbar-${tab}`).querySelector('svg')
      expect(chipIcon!.getAttribute('class')).toContain('h-3.5 w-3.5')
    }
  })
})
