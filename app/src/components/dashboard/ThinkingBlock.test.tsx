/**
 * Ephe — PWA chat UX plan, task B1: ThinkingBlock
 *
 * GIVEN  ThinkingBlock with props { thinking: ThinkingPhase | null }
 * WHEN   the thinking phase is null / running / finished
 * THEN   null / the live thinking line (aria-busy) / a collapsed finished label
 *        (the words themselves belong to the locale bundles and are not quoted here)
 */
import { describe, it, expect, beforeAll, afterEach } from 'vitest'
import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import i18n from '@/i18n'
import ThinkingBlock from './ThinkingBlock'

afterEach(cleanup)

describe('ThinkingBlock', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('en')
  })

  it('renders null when thinking is null', () => {
    const { container } = render(<ThinkingBlock thinking={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('shows the live thinking line with aria-busy while thinking runs', () => {
    render(<ThinkingBlock thinking={{ start: Date.now(), end: null }} />)
    const status = screen.getByTestId('thinking-status')
    expect(status.getAttribute('role')).toBe('status')
    expect(status.getAttribute('aria-live')).toBe('polite')
    // The word comes from the bundle, so it is not quoted here — the line carries one.
    expect(status.textContent?.trim()).toBeTruthy()
    const mark = status.querySelector('[data-testid="thinking-mark"]') as Element
    expect(mark.getAttribute('aria-hidden')).toBe('true')
    // The per-second tick is deliberately outside the live region.
    expect(status.contains(screen.getByTestId('thinking-timer'))).toBe(false)
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull()
  })

  it('shows Thought for 4s when thinking took 4s (collapsed)', () => {
    const now = Date.now()
    render(<ThinkingBlock thinking={{ start: now - 4000, end: now }} />)
    const label = screen.getByText('Thought for 4s')
    expect(label).toBeInTheDocument()
    const btn = label.closest('button') as HTMLButtonElement
    expect(btn.getAttribute('aria-expanded')).toBe('false')
  })

  it('shows Thought briefly for thinking under a second', () => {
    const now = Date.now()
    render(<ThinkingBlock thinking={{ start: now - 200, end: now }} />)
    expect(screen.getByText('Thought briefly')).toBeInTheDocument()
  })

  it('expands on a click (aria-expanded true)', () => {
    const now = Date.now()
    render(<ThinkingBlock thinking={{ start: now - 4000, end: now }} />)
    const btn = screen.getByRole('button', { name: /thought for 4s/i })
    expect(btn.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(btn)
    expect(btn.getAttribute('aria-expanded')).toBe('true')
  })

  it('streams the reasoning text live while thinking.end is null (client parity)', () => {
    const { container } = render(
      <ThinkingBlock
        thinking={{ start: Date.now(), end: null, text: 'Ich analysiere die Aufgabe…' }}
      />,
    )
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull()
    // live text shown, no collapse-button UI
    expect(screen.getByText('Ich analysiere die Aufgabe…')).toBeInTheDocument()
    expect(container.querySelector('button')).toBeNull()
  })

  it('shows the reasoning text when expanded; collapsed keeps label plus time only', () => {
    const now = Date.now()
    const { container } = render(
      <ThinkingBlock
        thinking={{ start: now - 4000, end: now, text: 'Schritt 1: Analyse\nSchritt 2: Antwort' }}
      />,
    )
    // Collapsed: the reasoning text is not shown
    expect(container.textContent).not.toContain('Schritt 1: Analyse')
    fireEvent.click(screen.getByRole('button', { name: /thought for 4s/i }))
    // Expanded: text shown (whitespace-pre-wrap keeps \n → textContent check)
    expect(container.textContent).toContain('Schritt 1: Analyse\nSchritt 2: Antwort')
  })
})
