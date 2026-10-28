/**
 * H2 — the icon raster.
 *
 * Lucide draws every glyph with stroke-width="2" unless a call site overrides it.
 * The constitution asks for one optical stroke across the product, so the sheet
 * carries the rule and the attribute stays what a component may override inline.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'

const css = readFileSync('src/styles/globals.css', 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')

describe('icon raster', () => {
  it('draws every Lucide glyph on the 1.5 px stroke', () => {
    expect(css).toMatch(/svg\.lucide\s*\{[^}]*stroke-width:\s*1\.5\s*;/)
  })

  it('keeps the three documented size steps', async () => {
    const { ICON_SIZE, ICON_STROKE_WIDTH } = await import('@/components/ui/iconScale')
    expect(ICON_STROKE_WIDTH).toBe(1.5)
    expect(ICON_SIZE).toEqual({ inline: 16, navigation: 18, section: 20 })
  })
})
