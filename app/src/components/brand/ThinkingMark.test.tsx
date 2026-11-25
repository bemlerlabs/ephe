/**
 * The thinking sign: the letter that turns into the moth while the engine reasons.
 *
 * Three claims, in the house's two registers — the figure in the DOM, the motion in
 * the sheet. A CSS animation cannot be watched in jsdom, so the motion is read off
 * `ThinkingMark.css` the way `styles/globals.runState.test.ts` reads the run layer:
 * only the compositor moves, the clock is the scene's, and both switches land the
 * sign on the standing letter. The third block is the one the owner asked for by
 * name: the sign marks thinking and nothing else.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import AgenticBar from '../shell/AgenticBar'
import ThinkingBlock from '../dashboard/ThinkingBlock'
import { PaperLetterGlyph, PaperMothGlyph } from './PaperMothGlyph'
import { ThinkingMark } from './ThinkingMark'

// Key-name form on purpose: the bundles are being edited elsewhere, so this file
// pins which key the surface asks for, never what it currently says.
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => `[[${key}]]`, i18n: { language: 'en' } }),
}))

afterEach(cleanup)

const css = readFileSync('src/components/brand/ThinkingMark.css', 'utf8').replace(
  /\/\*[\s\S]*?\*\//g,
  '',
)

/** The body of the first block whose selector matches `re`, brace-balanced. */
function block(re: RegExp): string {
  const m = re.exec(css)
  if (!m) return ''
  const open = css.indexOf('{', m.index)
  let depth = 0
  for (let i = open; i < css.length; i++) {
    if (css[i] === '{') depth++
    else if (css[i] === '}' && --depth === 0) return css.slice(open + 1, i)
  }
  return css.slice(open + 1)
}

describe('the sign — one figure, two faces, no word', () => {
  it('carries the letter and the moth in one square', () => {
    const { container } = render(<ThinkingMark />)
    const faces = Array.from(container.querySelectorAll('.ephe-think-frame')).map((face) =>
      face.getAttribute('data-face'),
    )
    expect(faces).toEqual(['letter', 'moth'])
    expect(container.querySelectorAll('.ephe-think-stage')).toHaveLength(1)
  })

  it('says nothing itself — the word beside it belongs to the locale bundles', () => {
    const { container } = render(<ThinkingMark />)
    expect(container.textContent).toBe('')
  })

  it('stays out of the accessible name', () => {
    render(<ThinkingMark />)
    const mark = screen.getByTestId('thinking-mark')
    expect(mark.getAttribute('aria-hidden')).toBe('true')
    expect(mark.getAttribute('role')).toBeNull()
  })

  it('carries no accent of its own — only the figure tones', () => {
    // The sign must survive all four accents and the one that drops the brand red, so
    // it asks for nothing but the paper tones and the figure's own firefly.
    const sources = [
      css,
      readFileSync('src/components/brand/PaperMothGlyph.tsx', 'utf8'),
      readFileSync('src/components/brand/ThinkingMark.tsx', 'utf8'),
    ].join('\n')
    expect(sources).toContain('--color-figure-paper')
    expect(sources).toContain('--color-firefly')
    expect(sources).not.toMatch(/--color-brand|--color-accent/)
  })

  it('reuses the bar’s moth rather than drawing a second one', () => {
    const { container } = render(<ThinkingMark />)
    const other = render(
      <>
        <PaperMothGlyph testId="bar-moth" />
        <PaperLetterGlyph testId="bar-letter" />
      </>,
    )
    for (const face of ['moth', 'letter'] as const) {
      const inSign = container.querySelector(`[data-testid="thinking-mark-${face}"]`)?.innerHTML
      const inBar = other.container.querySelector(`[data-testid="bar-${face}"]`)?.innerHTML
      expect(inSign, face).toBeTruthy()
      expect(inSign, face).toBe(inBar)
    }
  })
})

describe('the turn', () => {
  it('moves only the compositor', () => {
    const keyframes = block(/@keyframes\s+ephe-think-turn\s*\{/)
    expect(keyframes.length).toBeGreaterThan(0)
    for (const prop of keyframes.matchAll(/([\w-]+)\s*:/g)) {
      expect(['transform', 'opacity', 'animation-timing-function'], prop[1]).toContain(prop[1])
    }
    const stage = block(/\.ephe-think-stage\s*\{/)
    expect(stage).not.toMatch(/\b(left|top|width|height|margin|padding|font-size)\s*:/)
  })

  it('takes its clock from the scene and turns evenly', () => {
    expect(css).toContain('--ephe-think-cycle: calc(var(--ephe-scene-beat) * 6)')
    // An even rotation: linear over the cycle, the curve only inside the two turns.
    expect(css).toContain('animation: ephe-think-turn var(--ephe-think-cycle) linear infinite')
    expect(block(/@keyframes\s+ephe-think-turn\s*\{/)).toMatch(
      /animation-timing-function:\s*var\(--ease-organic\)/,
    )
  })

  it('lands on the standing letter under both switches', () => {
    for (const selector of [
      '@media (prefers-reduced-motion: reduce)',
      'html.no-motion .ephe-think-stage',
    ]) {
      expect(css).toContain(selector)
    }
    const still = block(/@media\s+\(prefers-reduced-motion:\s*reduce\)\s*\{/)
    expect(still).toContain('animation: none !important')
    expect(still).toContain('transform: none !important')
    expect(still).toContain(".ephe-think-frame[data-face='moth']")
    expect(block(/html\.no-motion \.ephe-think-frame\[data-face='moth'\]\s*\{/)).toContain(
      'opacity: 0 !important',
    )
  })
})

describe('the state it stands for', () => {
  it('marks the open thinking phase, word from the bundle key', () => {
    render(<ThinkingBlock thinking={{ start: Date.now(), end: null }} />)
    const status = screen.getByTestId('thinking-status')
    expect(status.textContent).toBe('[[chat.thinkingNow]]')
    expect(status.querySelector('[data-testid="thinking-mark"]')).not.toBeNull()
  })

  // Migrated from dashboard/a11y.surfaces.ws3.test.tsx, where these three facts were
  // pinned on a second, unrendered thinking surface: a status role, the word inside
  // it, and the figure kept out of what a reader says.
  it('announces the thinking state through a status role', () => {
    render(<ThinkingBlock thinking={{ start: Date.now(), end: null }} />)
    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('[[chat.thinkingNow]]')
    expect(status.getAttribute('aria-live')).toBe('polite')
    // Nothing but the word is read: the square carries no text and every shape it
    // draws is hidden, so the figure cannot add a word of its own to the announcement.
    const mark = status.querySelector('[data-testid="thinking-mark"]') as Element
    expect(mark.textContent).toBe('')
    const shapes = mark.querySelectorAll('svg')
    expect(shapes.length).toBeGreaterThan(0)
    for (const shape of shapes) expect(shape.getAttribute('aria-hidden')).toBe('true')
  })

  it('is not there once the thought has ended', () => {
    const now = Date.now()
    render(<ThinkingBlock thinking={{ start: now - 4000, end: now }} />)
    expect(screen.queryByTestId('thinking-mark')).toBeNull()
    expect(screen.queryByTestId('thinking-status')).toBeNull()
  })

  it('is not the mark of a working run — the bar keeps its own', () => {
    render(<AgenticBar state="working" onOpenPalette={() => {}} />)
    expect(screen.queryByTestId('thinking-mark')).toBeNull()
    expect(screen.getByTestId('agentic-moth')).toBeInTheDocument()
  })
})
