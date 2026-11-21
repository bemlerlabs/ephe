import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LoadingRow } from '@/components/ui'

/** WD-32 — the shared loading row. The surfaces used to draw loading six ways
 *  (colourless 12px spinner, half-opacity brand ring, bare text line); these
 *  hold the one treatment the rest of the dashboard now imports. */
describe('LoadingRow — one loading treatment for the dashboard', () => {
  it('renders the label beside a decorative brand spinner', () => {
    const { container } = render(<LoadingRow label="Loading…" />)
    expect(screen.getByText('Loading…')).toBeTruthy()
    const icon = container.querySelector('svg')
    expect(icon?.getAttribute('aria-hidden')).toBe('true')
    const cls = icon?.getAttribute('class') ?? ''
    expect(cls).toContain('animate-spin')
    expect(cls).toContain('text-brand')
    expect(cls).toContain('h-4')
    expect(cls).toContain('w-4')
  })

  it('stops the spin for reduced motion (the Ephe norm, as in Skeleton)', () => {
    const { container } = render(<LoadingRow label="Loading…" />)
    expect(container.querySelector('svg')?.getAttribute('class')).toContain(
      'motion-reduce:animate-none',
    )
  })

  it('keeps the label on the one faint token, whatever the caller lays out', () => {
    const { container } = render(<LoadingRow label="Loading…" className="px-1 py-8" />)
    const row = container.firstElementChild as HTMLElement
    expect(row.className).toContain('flex items-center gap-2')
    expect(row.className).toContain('px-1')
    expect(row.className).toContain('py-8')
    // The token must survive `cn` (twMerge folds text-ui-xs into text-ink-faint):
    const label = screen.getByText('Loading…')
    expect(label.className).toContain('text-ui-xs')
    expect(label.className).toContain('text-ink-faint')
  })

  it('passes through the attributes the surfaces rely on (data-testid, style)', () => {
    render(<LoadingRow label="Reading…" data-testid="voice-loading" style={{ paddingLeft: 26 }} />)
    const row = screen.getByTestId('voice-loading')
    expect(row.textContent).toContain('Reading…')
    expect(row.getAttribute('style')).toContain('padding-left: 26px')
  })
})
