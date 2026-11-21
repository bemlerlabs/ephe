import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Num, Rule, SectionHead } from '@/components/ui'

/** WAVE-1 — the three reading primitives of the redesign direction: a rule
 *  instead of a card, and one treatment for a number. These hold the two
 *  decisions that a later refactor would otherwise undo silently: the number
 *  keeps its 11px step even when a colour rides along (tailwind-merge reads
 *  every custom text-* step as a colour), and no primitive carries a radius,
 *  a shadow, or a second accent. */
describe('Num — one column of numbers', () => {
  it('keeps its size step and its ink on the same element as the numerals', () => {
    const { container } = render(<Num>162 tok</Num>)
    const cell = container.firstElementChild as HTMLElement
    const ink = cell.firstElementChild as HTMLElement
    expect(ink.textContent).toBe('162 tok')
    expect(ink.className).toContain('text-scale-data')
    expect(ink.className).toContain('text-ink-faint')
    expect(ink.className).toContain('font-mono')
    expect(ink.className).toContain('tabular-nums')
  })

  it('survives a colour from the caller without losing the size step', () => {
    const { container } = render(<Num className="text-status-danger">4 messages</Num>)
    const cell = container.firstElementChild as HTMLElement
    expect(cell.className).toContain('text-status-danger')
    expect(cell.firstElementChild?.className).toContain('text-scale-data')
  })

  it('gives every number the one right edge, and the accent only to now', () => {
    const { container, rerender } = render(<Num col={2}>Steps 21/22</Num>)
    const cell = container.firstElementChild as HTMLElement
    expect(cell.className).toContain('text-right')
    expect(cell.className).toContain('w-[var(--num-col-2)]')
    expect(cell.firstElementChild?.className).toContain('text-ink-faint')
    rerender(
      <Num col={2} now>
        Steps 21/22
      </Num>,
    )
    expect(container.firstElementChild?.firstElementChild?.className).toContain('text-brand-deep')
  })
})

describe('Rule — structure is drawn by rules and indents', () => {
  it('draws the 1px hairline and stays out of the reading order', () => {
    const { container } = render(<Rule />)
    const rule = container.firstElementChild as HTMLElement
    expect(rule.className).toContain('h-px')
    expect(rule.className).toContain('bg-hairline')
    expect(rule.getAttribute('aria-hidden')).toBe('true')
  })

  it('knows the second weight and the one accent, and nothing else', () => {
    const { container } = render(<Rule orientation="vertical" tone="selected" />)
    const rule = container.firstElementChild as HTMLElement
    expect(rule.className).toContain('w-0.5')
    expect(rule.className).toContain('bg-hairline-strong')
    const { container: accent } = render(<Rule tone="now" />)
    expect((accent.firstElementChild as HTMLElement).className).toContain('bg-brand')
  })
})

describe('SectionHead — what a card used to be', () => {
  it('sets the title on the one title step, over a rule, with the UI step under it', () => {
    const { container } = render(<SectionHead title="Engine" hint="Always your choice." />)
    const head = container.querySelector('h2') as HTMLElement
    expect(head.textContent).toBe('Engine')
    expect(head.className).toContain('text-scale-title')
    expect(container.firstElementChild?.querySelector('.bg-hairline')).toBeTruthy()
    const hint = container.querySelector('p') as HTMLElement
    expect(hint.className).toContain('text-scale-ui')
  })

  it('carries no radius and no shadow, and marks a running section with the accent', () => {
    const { container } = render(<SectionHead title="Research" now />)
    const section = container.firstElementChild as HTMLElement
    const classes = [section, ...section.querySelectorAll('*')].map((el) => el.className).join(' ')
    expect(classes).not.toMatch(/rounded|shadow/)
    expect(classes).toContain('bg-brand')
  })
})
