/**
 * The composer model chip at desktop width — the 24px floor and one glyph size.
 *
 * jsdom measures no layout, so what is held here is the class contract the
 * breakpoints encode: at desktop (lg and up) the chip reaches 24x24 (both axes,
 * the width guard promoted from the mobile one) and its row carries a single
 * glyph size (14px, the inline chevron), while the 44px touch guard below lg
 * stays exactly as it was.
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

import ComposerModelChip from './chat/ComposerModelChip'

const tokens = (el: Element | null): string[] => (el?.getAttribute('class') ?? '').split(/\s+/)
const has = (el: Element | null, token: string): boolean => tokens(el).includes(token)

function renderChip() {
  function Host() {
    const ref = useRef<HTMLButtonElement>(null)
    return (
      <ComposerModelChip
        open={false}
        onToggle={() => undefined}
        onClose={() => undefined}
        anchorRef={ref}
        menuPos={null}
        needsSetup={false}
        model="gemma4:12b"
        providers={[]}
        activeP="local_ollama"
        onPick={() => undefined}
        onSetup={() => undefined}
      />
    )
  }
  return render(<Host />)
}

describe('the composer model chip at desktop width', () => {
  it('reaches 24x24 and keeps the 44px mobile guard on both axes', () => {
    renderChip()
    const chip = screen.getByTestId('model-chip')
    // Unconditional floors: 24px from lg up.
    expect(has(chip, 'min-h-6'), 'desktop 24px height').toBe(true)
    expect(has(chip, 'min-w-6'), 'desktop 24px width').toBe(true)
    // The mobile guards are untouched: 44px below lg.
    expect(has(chip, 'max-lg:min-h-11'), 'mobile 44px height guard kept').toBe(true)
    expect(has(chip, 'max-lg:min-w-11'), 'mobile 44px width guard kept').toBe(true)
  })

  it('carries one glyph size in the chip row — the 14px inline chevron', () => {
    renderChip()
    const chip = screen.getByTestId('model-chip')
    const glyphs = chip.querySelectorAll('svg')
    expect(glyphs.length, 'exactly one glyph in the chip').toBe(1)
    const chevron = glyphs[0]!
    expect(has(chevron, 'h-3.5') && has(chevron, 'w-3.5'), '14px inline chevron').toBe(true)
    expect(has(chevron, 'h-2.5'), 'no 10px glyph left in the row').toBe(false)
  })
})
