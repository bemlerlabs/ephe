import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'

vi.mock('@/lib/paperRustle', () => ({ paperRustle: vi.fn() }))

import { PaperMoth } from './PaperMoth'
import { PaperMothGlyph } from './PaperMothGlyph'

describe('PaperMothGlyph', () => {
  it('draws the figure as geometry, not as a shrunken photo', () => {
    render(<PaperMothGlyph />)
    const svg = screen.getByTestId('paper-moth-glyph')
    expect(svg.tagName.toLowerCase()).toBe('svg')
    expect(svg.querySelectorAll('polygon').length).toBe(6)
    expect(svg.querySelectorAll('path').length).toBe(1)
    expect(svg.querySelectorAll('.moth-knot').length).toBe(2)
  })

  it('stays out of the accessibility tree — the product name stands beside it', () => {
    render(<PaperMothGlyph />)
    expect(screen.getByTestId('paper-moth-glyph').getAttribute('aria-hidden')).toBe('true')
  })
})

describe('PaperMoth', () => {
  afterEach(() => {
    vi.useRealTimers()
    window.localStorage.clear()
  })

  it('carries its state on the stage, which is what the sheet animates', () => {
    const { rerender } = render(<PaperMoth state="working" />)
    const moth = screen.getByTestId('paper-moth')
    expect(moth.getAttribute('data-state')).toBe('working')
    rerender(<PaperMoth state="waiting" />)
    expect(screen.getByTestId('paper-moth').getAttribute('data-state')).toBe('waiting')
    expect(screen.getByTestId('paper-moth').querySelectorAll('.knot').length).toBe(2)
  })

  it('unfolds once per install, after the film has been seen', () => {
    vi.useFakeTimers()
    window.localStorage.setItem('ephe.intro.seen.v1', '1')
    const first = render(<PaperMoth unfold />)
    expect(screen.getByTestId('paper-moth').getAttribute('data-unfold')).toBe('true')
    act(() => {
      vi.advanceTimersByTime(1900)
    })
    expect(screen.getByTestId('paper-moth').getAttribute('data-unfold')).toBeNull()
    first.unmount()

    render(<PaperMoth unfold />)
    expect(screen.getByTestId('paper-moth').getAttribute('data-unfold')).toBeNull()
  })

  it('leaves the very first start to the film', () => {
    render(<PaperMoth unfold />)
    expect(screen.getByTestId('paper-moth').getAttribute('data-unfold')).toBeNull()
  })
})
