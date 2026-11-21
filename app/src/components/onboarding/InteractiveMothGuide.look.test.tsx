/**
 * InteractiveMothGuide — the pointer the guide is dragged toward reaches both axes.
 *
 * GIVEN the live guide with its spring running
 * WHEN  the pointer moves away from the body
 * THEN  the body carries a horizontal look and a vertical one, because
 *       `InteractiveMothGuide.css` rolls on `--look-x` and nods on `--look-y`,
 *       and a write nobody reads is a style the frame pays for and the user
 *       never sees.
 */
import { describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'

vi.mock('@/lib/spiritAudio', () => ({
  playSparkChime: vi.fn(),
  playWingWhoosh: vi.fn(),
}))

import { InteractiveMothGuide } from './InteractiveMothGuide'

const rootOf = () => {
  const node = document.querySelector<HTMLElement>('.moth-guide')
  if (!node) throw new Error('the guide did not mount')
  return node
}

describe('InteractiveMothGuide', () => {
  it('writes both look axes when the pointer moves off the body', () => {
    render(<InteractiveMothGuide />)
    const root = rootOf()
    expect(root.style.getPropertyValue('--look-x')).toBe('')
    expect(root.style.getPropertyValue('--look-y')).toBe('')

    window.dispatchEvent(new PointerEvent('pointermove', { clientX: 300, clientY: 100 }))

    // The two are one normalised vector from the body to the pointer, and the body
    // sits wherever its spring has it, so the contract is the pair and not the values:
    // both set, both inside the unit range, together of length one. A write that
    // vanished would read back as an empty string and land as NaN.
    const x = Number(root.style.getPropertyValue('--look-x'))
    const y = Number(root.style.getPropertyValue('--look-y'))
    expect(root.style.getPropertyValue('--look-x')).not.toBe('')
    expect(root.style.getPropertyValue('--look-y')).not.toBe('')
    expect(Number.isFinite(x) && Number.isFinite(y)).toBe(true)
    expect(Math.hypot(x, y)).toBeCloseTo(1, 2)
  })
})
