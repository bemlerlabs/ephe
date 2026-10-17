/**
 * F3: the five tool chips keep their words at phone width.
 *
 * The row used to render the label `hidden md:inline`, so below 768 px a reader
 * got five glyphs with a caret and nothing else — the words lived in `title`,
 * which never renders on a touch screen. Measured 2026-10-10 at 390x844: 0 of 5
 * labels shown, 22 px chips. The chip now stacks the word under the glyph instead
 * of dropping it: 5 of 5 shown, 30-47 px chips, the group still at 0 px overflow
 * and the row still 44 px tall (`f3-after-5173-toolbar-390.png`).
 *
 * What this file can and cannot hold. jsdom applies no media queries, so no test
 * here proves the 390 px layout — that is the Playwright measurement above. The
 * two rules it does hold are the ones a later edit can break silently: the label
 * node must exist for every chip, and it must not be hidden below md again.
 */
import { describe, it, expect, afterEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { render, screen, cleanup } from '@testing-library/react'
import ToolbarRow from './ToolbarRow'

const SOURCE = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'ToolbarRow.tsx'), 'utf8')

const TOOLS = ['files', 'preview', 'terminal', 'git']

afterEach(cleanup)

describe('toolbar chips at phone width', () => {
  it('carries a label node for every tool', () => {
    render(<ToolbarRow />)
    for (const tab of TOOLS) {
      const chip = screen.getByTestId(`toolbar-${tab}`)
      const span = chip.querySelector('span')
      expect(span, `toolbar-${tab} lost its label node`).toBeTruthy()
      expect((span?.textContent || '').trim().length).toBeGreaterThan(0)
    }
  })

  it('does not hide the label below md', () => {
    const line = SOURCE.split('\n').find((l) => l.includes('max-lg:text-ui-2xs'))
    expect(line, 'the stacked label lost its mobile type step').toBeTruthy()
    expect(line).not.toMatch(/\bhidden\b/)
    expect(SOURCE).toMatch(/max-lg:flex-col/)
  })
})
