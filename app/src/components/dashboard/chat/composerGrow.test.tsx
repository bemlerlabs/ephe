/**
 * The composer growth budget (EPHE-UI-001, shrunk 2026-11-04).
 *
 * jsdom measures no layout, so the numbers held here are the ones the rule
 * applies to a real box: an empty composer is ONE line of the input ramp, a
 * six-line draft is fully visible, and nothing in between may turn the field
 * into a slab. `tests/playwright/*` measures the same in pixels.
 */
import { describe, it, expect, afterEach, vi } from 'vitest'
import { useRef } from 'react'
import { render, act, cleanup } from '@testing-library/react'
import {
  COMPOSER_EMPTY_PX,
  COMPOSER_LINE_PX,
  COMPOSER_MAX_LINES,
  COMPOSER_MAX_PX,
  COMPOSER_PADDING_PX,
  composerHeightPx,
  useComposerGrow,
} from './composerGrow'

describe('the composer growth budget', () => {
  it('starts an empty field at one line of the input ramp', () => {
    expect(COMPOSER_EMPTY_PX).toBe(COMPOSER_LINE_PX + COMPOSER_PADDING_PX)
    // The ceiling a future change may not cross without re-measuring the screen:
    // one line plus its padding. 48px was two and a half lines of nothing.
    expect(COMPOSER_EMPTY_PX).toBeLessThanOrEqual(28)
    expect(composerHeightPx(0)).toBe(COMPOSER_EMPTY_PX)
  })

  it('keeps a six-line draft fully readable and stops there', () => {
    expect(COMPOSER_MAX_LINES).toBe(6)
    // max-h-32 on the element is the same 128px from the CSS side.
    expect(COMPOSER_MAX_PX).toBe(128)
    expect(composerHeightPx(COMPOSER_LINE_PX * 6 + COMPOSER_PADDING_PX)).toBe(COMPOSER_MAX_PX)
    expect(composerHeightPx(4000)).toBe(COMPOSER_MAX_PX)
    expect(composerHeightPx(3 * COMPOSER_LINE_PX + COMPOSER_PADDING_PX)).toBe(68)
  })
})

function Host({ draft }: { draft: string }) {
  const ref = useRef<HTMLTextAreaElement>(null)
  useComposerGrow(ref, draft)
  return <textarea ref={ref} data-testid="grown" defaultValue={draft} />
}

const scrollPx = (el: HTMLTextAreaElement, px: number) =>
  Object.defineProperty(el, 'scrollHeight', { configurable: true, value: px })

describe('the rule applied to the field', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('writes the clamped height, and writes it again when the draft changes', () => {
    const { rerender } = render(<Host draft="" />)
    const el = document.querySelector('[data-testid="grown"]') as HTMLTextAreaElement
    scrollPx(el, 0)
    rerender(<Host draft="" />)
    expect(el.style.height).toBe(`${COMPOSER_EMPTY_PX}px`)

    scrollPx(el, COMPOSER_MAX_PX + 400)
    rerender(<Host draft={'1\n2\n3\n4\n5\n6\n7\n8\n9'} />)
    expect(el.style.height).toBe(`${COMPOSER_MAX_PX}px`)

    // The old box must not keep the height of the draft it no longer holds.
    scrollPx(el, COMPOSER_EMPTY_PX)
    rerender(<Host draft="" />)
    expect(el.style.height).toBe(`${COMPOSER_EMPTY_PX}px`)
  })

  it('re-measures when the field re-wraps at another width', () => {
    let fire: (() => void) | null = null
    class FakeRO {
      constructor(cb: () => void) {
        fire = cb
      }
      observe() {}
      disconnect() {}
    }
    vi.stubGlobal('ResizeObserver', FakeRO as unknown as typeof ResizeObserver)
    render(<Host draft="" />)
    const el = document.querySelector('[data-testid="grown"]') as HTMLTextAreaElement
    let width = 600
    el.getBoundingClientRect = () => ({ width }) as DOMRect
    scrollPx(el, COMPOSER_EMPTY_PX)
    expect(el.style.height).toBe(`${COMPOSER_EMPTY_PX}px`)

    // A narrower column: the same draft needs three lines, and nothing typed.
    width = 300
    scrollPx(el, 3 * COMPOSER_LINE_PX + COMPOSER_PADDING_PX)
    act(() => fire!())
    expect(el.style.height).toBe('68px')
  })

  it('does not need a ResizeObserver to size the field', () => {
    vi.stubGlobal('ResizeObserver', undefined)
    const warn = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    expect(() => render(<Host draft="hallo" />)).not.toThrow()
    expect(warn).not.toHaveBeenCalled()
    warn.mockRestore()
  })
})
