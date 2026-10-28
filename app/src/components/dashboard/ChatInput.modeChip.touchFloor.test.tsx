/**
 * The composer mode chip at desktop width — the 24px floor and one glyph size.
 *
 * jsdom measures no layout, so what is held here is the class contract the
 * breakpoints encode, the same contract the pixel runs measure: at desktop (lg
 * and up) the control reaches 24px and its row carries a single glyph size
 * (14px, the inline chevron), while the 44px touch guard below lg stays exactly
 * as it was.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { useRef } from 'react'

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: () => undefined },
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string, opts?: { defaultValue?: string }) => opts?.defaultValue ?? key,
  }),
}))

import ComposerModeChip from './chat/ComposerModeChip'

const tokens = (el: Element | null): string[] => (el?.getAttribute('class') ?? '').split(/\s+/)
const has = (el: Element | null, token: string): boolean => tokens(el).includes(token)

function renderChip() {
  function Host() {
    const ref = useRef<HTMLButtonElement>(null)
    return (
      <ComposerModeChip
        open={false}
        mode="plan"
        approval="strict"
        anchorRef={ref}
        menuPos={null}
        onToggle={() => undefined}
        onClose={() => undefined}
        onPick={() => undefined}
      />
    )
  }
  return render(<Host />)
}

describe('the composer mode chip at desktop width', () => {
  it('reaches the 24px floor and keeps the 44px mobile guard', () => {
    renderChip()
    const chip = screen.getByTestId('composer-mode-selector')
    // Unconditional min-height: 24px from lg up.
    expect(has(chip, 'min-h-6'), 'desktop 24px height').toBe(true)
    // The mobile guard is untouched: 44px below lg.
    expect(has(chip, 'max-lg:min-h-11'), 'mobile 44px guard kept').toBe(true)
  })

  it('carries one glyph size in the chip row — the 14px inline chevron', () => {
    renderChip()
    const chip = screen.getByTestId('composer-mode-selector')
    const glyphs = chip.querySelectorAll('svg')
    expect(glyphs.length, 'exactly one glyph in the chip').toBe(1)
    const chevron = glyphs[0]!
    expect(has(chevron, 'h-3.5') && has(chevron, 'w-3.5'), '14px inline chevron').toBe(true)
    expect(has(chevron, 'h-2.5'), 'no 10px glyph left in the row').toBe(false)
  })
})
