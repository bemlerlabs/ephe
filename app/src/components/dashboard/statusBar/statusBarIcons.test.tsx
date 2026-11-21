/**
 * W13 — the status bar's chip groups carry one glyph size.
 *
 * GIVEN the connection pill and the cost/cache chips, which share the status row
 * WHEN each glyph's size class is read
 * THEN all of them name the same fixed 14 px.
 *
 * Measured before the change, Chromium at 1440x900 against the dev server on :5173: the pill's
 * `Wifi` at `h-[0.875em]` resolved to 14x14 and the cache chip's `Recycle` at `h-3 w-3` to 12x12,
 * so the row carried two sizes — `a11y.json`, row `[288,851,732x49]`, distinctSizesInRow
 * `12x12` + `14x14`.
 *
 * `0.875em` is the font size of whatever surrounds the glyph, so it reads 14 px only while the
 * inherited context stays at 16 px; the fixed token cannot drift with it. The row's inline glyph
 * size is `h-3.5 w-3.5` (14 px).
 *
 * jsdom measures no box, so this pins the class contract; the px values come from the live
 * measurement above.
 */
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: { language: 'en' },
  }),
}))

import { ConnectionPill } from './ConnectionPill'
import { CostChips } from './CostChips'

/** 14 px in the app's spacing scale — the inline glyph size of the status row. */
const GLYPH = 'h-3.5 w-3.5'

/** The class tokens this repo reads as a 24 px-or-larger box on each axis. */
const FLOOR = {
  h: ['min-h-6', 'h-6', 'h-7', 'h-8', 'h-9', 'h-10', 'h-11', 'min-h-9', 'min-h-11'],
  w: ['min-w-6', 'w-6', 'w-7', 'w-8', 'w-9', 'w-10', 'w-11', 'min-w-9', 'min-w-11'],
}

/** The `h-*`/`w-*` pair a glyph carries, as `"<height> <width>"`. */
function glyphSizes(container: HTMLElement): string[] {
  return [...container.querySelectorAll('svg')].map((svg) => {
    const cls = svg.getAttribute('class') ?? ''
    const height = cls.match(/(?:^|\s)h-(\S+)/)?.[1] ?? 'none'
    const width = cls.match(/(?:^|\s)w-(\S+)/)?.[1] ?? 'none'
    return `${height} ${width}`
  })
}

function renderedGlyphs(): Record<string, { size: string; cls: string }> {
  const pills = {
    wifi: render(<ConnectionPill backendOnline engineOnline />),
    wifiOff: render(<ConnectionPill backendOnline={false} />),
  }
  const chips = render(
    <CostChips
      usageTotals={{ in: 120_000, out: 4_000, cached: 30_000 }}
      enginePricing={{ in_per_m: 3, out_per_m: 15 }}
      sessionCost={0.42}
      cachePercent={25}
    />,
  )
  const out: Record<string, { size: string; cls: string }> = {}
  for (const [name, view] of Object.entries({ ...pills, cache: chips })) {
    const svg = view.container.querySelector('svg')
    expect(svg, `${name} renders a glyph`).not.toBeNull()
    out[name] = {
      size: glyphSizes(view.container)[0] ?? 'none',
      cls: svg?.getAttribute('class') ?? '',
    }
  }
  return out
}

describe('status-bar chips — one glyph size (W13)', () => {
  it('every glyph names the same size', () => {
    const glyphs = renderedGlyphs()
    const sizes = Object.entries(glyphs).map(([name, g]) => `${name}=${g.size}`)
    const distinct = [...new Set(Object.values(glyphs).map((g) => g.size))]
    expect(distinct, sizes.join(' ')).toHaveLength(1)
  })

  it('that size is the fixed 14 px token', () => {
    const glyphs = renderedGlyphs()
    for (const [name, glyph] of Object.entries(glyphs)) {
      expect(glyph.cls, `${name} glyph`).toContain(GLYPH)
      expect(glyph.cls, `${name} is a font-relative glyph size`).not.toMatch(/\d(?:\.\d+)?em/)
    }
  })

  it('the size is not scoped to phone widths', () => {
    // The desktop row is the one that was measured mixed; a `max-lg:` size would leave 1440 px
    // on a different glyph size than the phone (the shape the W10 touch-floor pass had).
    const glyphs = renderedGlyphs()
    for (const [name, glyph] of Object.entries(glyphs)) {
      expect(glyph.cls, `${name} glyph`).not.toMatch(/(?:^|\s)(?:max-)?lg:(?:h|w)-/)
    }
  })

  it('any control added to the chip groups has to clear the 24 px floor', () => {
    // Guard, not a finding: measured 2026-10-13, neither group renders an interactive element —
    // the census' 17 real desktop 2.5.8 violations all sit in other files. A control added here
    // later has to bring the floor with it.
    const views = [
      render(<ConnectionPill backendOnline />),
      render(
        <CostChips
          usageTotals={{ in: 1, out: 1, cached: 1 }}
          enginePricing={{ in_per_m: 1, out_per_m: 1 }}
          sessionCost={1}
          cachePercent={1}
        />,
      ),
    ]
    for (const view of views) {
      const targets = view.container.querySelectorAll(
        'button, a[href], input, select, textarea, [role="button"], [tabindex]',
      )
      for (const target of targets) {
        const cls = (target.getAttribute('class') ?? '').split(/\s+/)
        expect(
          cls.some((c) => FLOOR.h.includes(c)),
          `${target.tagName} height`,
        ).toBe(true)
        expect(
          cls.some((c) => FLOOR.w.includes(c)),
          `${target.tagName} width`,
        ).toBe(true)
      }
    }
  })
})
