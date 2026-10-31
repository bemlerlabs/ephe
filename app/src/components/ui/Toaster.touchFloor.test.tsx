/**
 * The toaster at phone width — the 24px floor, and where the stack may sit.
 *
 * Measured 2026-10-13 at 390x844 on the live surface: the toast rectangle was
 * [16,720,358x44] while the composer's bottom row sits at y=739, so the stack
 * covered the model chip and the send button (both 44x44 at y=739 — a 25px
 * overlap). The dismiss control measured 14x14 at that width and at 1440, under
 * the WCAG 2.5.8 24px floor.
 *
 * jsdom computes no layout, so what is held here is the class contract the
 * breakpoints encode: at phone width the stack hangs under the header instead of
 * over the composer, and the dismiss target carries a 24px minimum. The
 * rectangles themselves are measured in the Playwright run.
 *
 * The header measures 53px at every width below lg, which is why the phone
 * anchor may not sit higher than 56px: the toast paints above the header
 * (z-modal over z-sticky), so a smaller offset would cover the menu toggle.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k: string) => k }) }))

import { toastBus } from '@/lib/toast'
import { Toaster } from './Toaster'

const tokens = (el: Element | null): string[] => (el?.getAttribute('class') ?? '').split(/\s+/)
const has = (el: Element | null, token: string): boolean => tokens(el).includes(token)

/** The toast stack: the fixed container wrapping the single raised toast. */
function stack(): HTMLElement {
  render(<Toaster />)
  act(() => {
    toastBus.error('Backend getrennt')
  })
  const close = screen.getByRole('button', { name: 'toast.close' })
  return close.closest('[role="status"]')!.parentElement as HTMLElement
}

describe('the toaster at phone width', () => {
  it('the dismiss control reaches the 24px floor', () => {
    render(<Toaster />)
    act(() => {
      toastBus.error('Backend getrennt')
    })
    const close = screen.getByRole('button', { name: 'toast.close' })
    expect(has(close, 'min-h-6'), 'dismiss 24px height').toBe(true)
    expect(has(close, 'min-w-6'), 'dismiss 24px width').toBe(true)
    expect(close.querySelector('svg'), 'the glyph stays inline, not the target').not.toBeNull()
  })

  it('hangs the stack under the header instead of over the composer', () => {
    const el = stack()
    const phoneAnchor = tokens(el).find((t) => /^max-lg:top-\[/.test(t))
    expect(phoneAnchor, 'a phone-width top anchor').toBeTruthy()
    expect(tokens(el), 'no bottom anchor at any width').not.toContain('bottom-20')
    expect(
      tokens(el).some((t) => t === 'lg:top-[calc(env(safe-area-inset-top)+3.75rem)]'),
      'desktop anchors under the top bar',
    ).toBe(true)
  })

  it('clears the measured 53px header with its phone offset', () => {
    const phoneAnchor = tokens(stack()).find((t) => /^max-lg:top-\[/.test(t))!
    // `top-[calc(env(safe-area-inset-top)+Nrem)]` — the offset is the rem step.
    const rem = Number(/\+(\d+(?:\.\d+)?)rem\)?\]/.exec(phoneAnchor)?.[1])
    expect(Number.isFinite(rem), `a readable rem offset in "${phoneAnchor}"`).toBe(true)
    expect(rem * 16, 'offset clears the 53px header').toBeGreaterThanOrEqual(56)
  })
})
