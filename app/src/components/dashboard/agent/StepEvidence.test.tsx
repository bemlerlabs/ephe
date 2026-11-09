/**
 * #88 — the verdict shows beside the page it describes.
 *
 * The parse is tested where it lives; this proves the row a reader sees: one verdict word,
 * one chip per fact the page moved by, and nothing at all when the step carried no evidence
 * line. The copy is read from `locales/en.json` while the test runs, so a chip with no key
 * behind it fails here rather than shipping a bare `chat.stepElements`.
 */
import { describe, it, expect, vi } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { render, screen } from '@testing-library/react'
import { StepEvidence } from './StepEvidence'

/** app/src, found from the run's cwd (vitest runs at the app or the repo root). */
function findSrc(): string {
  for (const base of [process.cwd(), resolve(process.cwd(), 'app')]) {
    const candidate = resolve(base, 'src')
    if (existsSync(resolve(candidate, 'locales/en.json'))) return candidate
  }
  throw new Error(`app/src not found below ${process.cwd()}`)
}
const CHAT = JSON.parse(readFileSync(resolve(findSrc(), 'locales/en.json'), 'utf8')).chat as Record<
  string,
  string
>

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const leaf = key.split('.')[1] ?? ''
      const template = CHAT[leaf] ?? String(options?.defaultValue ?? key)
      return template.replace(/\{\{(\w+)\}\}/g, (_match: string, name: string) =>
        String(options?.[name] ?? ''),
      )
    },
  }),
}))

/** The live `browser_go` line, measured on 2026-11-05. */
const LIVE =
  'STEP_EVIDENCE:{"step":"browser_go","verdict":"observed","url":"https://example.com/",' +
  '"title":"Example Domain","delta":{"nodes":19,"text_len":991,"scroll_y":0,"checked":0,' +
  '"url_changed":1,"title_changed":1}}\nThis domain is for use in illustrative examples.'

const UNPROVEN =
  'STEP_EVIDENCE:{"step":"browser_click","verdict":"unproven","url":"","title":"",' +
  '"delta":{},"reason":"nothing observable changed"}'

describe('the browser step states what the page answered', () => {
  it('names the verdict and every fact that moved', () => {
    render(<StepEvidence result={LIVE} />)
    const row = screen.getByTestId('step-evidence')
    expect(row.dataset.verdict).toBe('observed')
    expect(screen.getByTestId('step-evidence-verdict').textContent).toBe(CHAT['stepObserved'])
    expect(row.textContent).toContain('+19 elements')
    expect(row.textContent).toContain('+991 characters')
    expect(row.textContent).toContain('new address')
    expect(row.textContent).toContain('new title')
  })

  /** A count that did not move is not a fact, and a row of zeroes would be theatre. */
  it('keeps a count that stayed where it was out of the row', () => {
    render(<StepEvidence result={LIVE} />)
    expect(screen.queryByTestId('step-evidence-scrolled')).toBeNull()
    expect(screen.queryByTestId('step-evidence-checked')).toBeNull()
  })

  it('says unproven and states nothing else', () => {
    render(<StepEvidence result={UNPROVEN} />)
    expect(screen.getByTestId('step-evidence').dataset.verdict).toBe('unproven')
    // One element carries a data-testid below the row itself: the verdict. Anything else in
    // this row would be a number the page did not produce.
    expect(screen.queryAllByTestId(/^step-evidence-/)).toHaveLength(1)
    expect(screen.getByTestId('step-evidence').textContent).toBe(CHAT['stepUnproven'])
  })

  it('renders no row when the step carried no evidence line', () => {
    const { container } = render(<StepEvidence result="Click executed successfully." />)
    expect(container.textContent).toBe('')
    expect(screen.queryByTestId('step-evidence')).toBeNull()
  })

  it('renders no row when there is no result yet', () => {
    render(<StepEvidence result={null} />)
    expect(screen.queryByTestId('step-evidence')).toBeNull()
  })

  /** The audit's own sentence is English from the server; the row must not become its carrier. */
  it('leaves the backend reason out of the reader surface', () => {
    render(<StepEvidence result={UNPROVEN} />)
    expect(screen.getByTestId('step-evidence').textContent).not.toContain('nothing observable')
  })
})
