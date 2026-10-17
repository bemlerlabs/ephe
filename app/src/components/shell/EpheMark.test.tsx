// R2-0: the mark is a real node in the tree — otherwise its signature motion
// has nothing to animate.
import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { EpheMark } from './EpheMark'

const container = (host: HTMLElement) =>
  host.querySelector('[data-testid="ephe-mark"]') as HTMLElement

describe('EpheMark', () => {
  it('inline die SVG statt ein Bild — nur Kinder kann .ephe-mark kondensieren', () => {
    const { container: root } = render(<EpheMark state="condense" />)
    const mark = container(root)
    expect(mark.tagName).toBe('SPAN')
    expect(mark.getAttribute('data-state')).toBe('condense')
    expect(mark.querySelector('svg')).toBeTruthy()
    expect(mark.querySelector('img')).toBeNull()
    // The cascade addresses `svg > *`; without children the state would be decoration only.
    expect(mark.querySelectorAll('svg > *').length).toBeGreaterThan(1)
  })

  it('schreibt die Verlaufs-ids pro Instanz um, damit zwei Marken sich nicht löschen', () => {
    const { container: root } = render(
      <div>
        <EpheMark testId="a" />
        <EpheMark testId="b" />
      </div>,
    )
    const first = root.querySelector('[data-testid="a"]') as HTMLElement
    const second = root.querySelector('[data-testid="b"]') as HTMLElement
    const idsOf = (el: HTMLElement) => [...el.querySelectorAll('[id]')].map((n) => n.id)
    const a = idsOf(first)
    const b = idsOf(second)
    expect(a.length).toBeGreaterThan(0)
    expect(a.filter((id) => b.includes(id))).toEqual([])
    // Every reference has to resolve inside its own instance.
    for (const [el, ids] of [
      [first, a],
      [second, b],
    ] as const) {
      const refs = [...el.querySelectorAll('*')].flatMap((n) => {
        const attrs = n.attributes ?? []
        return [...attrs].flatMap((at) =>
          at.value.startsWith('url(#') ? [at.value.slice(5, -1)] : [],
        )
      })
      expect(refs.length).toBeGreaterThan(0)
      for (const ref of refs) expect(ids).toContain(ref)
    }
  })

  it('ist Zierde für Screenreader — der Produktname steht immer daneben', () => {
    const { container: root } = render(<EpheMark />)
    expect(container(root).getAttribute('aria-hidden')).toBe('true')
    expect(container(root).getAttribute('data-size')).toBeNull()
  })

  it('größen sich über das Token der Bibliothek, nicht über Klassen', () => {
    const { container: root } = render(<EpheMark size="4rem" compact />)
    const mark = container(root)
    expect(mark.style.getPropertyValue('--ephe-mark-size')).toBe('4rem')
    expect(mark.getAttribute('data-size')).toBe('compact')
  })
})
