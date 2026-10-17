/**
 * Ephe — PWA chat UX plan, task B1: ThinkingBlock
 *
 * GIVEN  ThinkingBlock with props { thinking: ThinkingPhase | null }
 * WHEN   the thinking phase is null / running / finished
 * THEN   null / live „Denkt nach…" (aria-busy) / collapsible „Gedacht für Ns" // language-gate: ignore — both are the German locale labels the product renders (locales/de.json)
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

  it('rendert null wenn thinking null ist', () => {
    const { container } = render(<ThinkingBlock thinking={null} />)
    expect(container.firstChild).toBeNull()
  })

  it('zeigt live-Label „Thinking…" mit aria-busy während Thinking läuft', () => {
    render(<ThinkingBlock thinking={{ start: Date.now(), end: null }} />)
    expect(screen.getByText('Thinking…')).toBeInTheDocument()
    expect(document.querySelector('[aria-busy="true"]')).not.toBeNull()
  })

  it('zeigt „Thought for 4s" wenn Thinking 4s dauerte (kollabiert)', () => {
    const now = Date.now()
    render(<ThinkingBlock thinking={{ start: now - 4000, end: now }} />)
    const label = screen.getByText('Thought for 4s')
    expect(label).toBeInTheDocument()
    const btn = label.closest('button') as HTMLButtonElement
    expect(btn.getAttribute('aria-expanded')).toBe('false')
  })

  it('zeigt „Thought briefly" bei < 1s Thinking', () => {
    const now = Date.now()
    render(<ThinkingBlock thinking={{ start: now - 200, end: now }} />)
    expect(screen.getByText('Thought briefly')).toBeInTheDocument()
  })

  it('expandiert per Klick (aria-expanded true)', () => {
    const now = Date.now()
    render(<ThinkingBlock thinking={{ start: now - 4000, end: now }} />)
    const btn = screen.getByRole('button', { name: /thought for 4s/i })
    expect(btn.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(btn)
    expect(btn.getAttribute('aria-expanded')).toBe('true')
  })

  it('streamt Reasoning-Text LIVE während thinking.end null ist (KI-Client-Parität)', () => {
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

  it('zeigt Reasoning-Text bei Expanded (collapsed: nur Label + Zeit)', () => {
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
