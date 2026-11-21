/**
 * Wave 10 · P0-6 — radius scale: one source, 4px grid.
 * Invariants against globals.css (static check, like P0-4).
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'

// Vitest's cwd is the app root (see the test block in vite.config.ts) — read relative.
const css = readFileSync('src/styles/globals.css', 'utf8')

describe('Wave 10 P0-6: the radius tokens', () => {
  it('defines the 5 steps plus full in the @theme block on the 4px grid', () => {
    const theme = css.match(/@theme\s*{([\s\S]*?)}\s*\n/)?.[1] ?? ''
    for (const [token, px] of [
      ['--radius-sm', '4px'],
      ['--radius-md', '8px'],
      ['--radius-lg', '12px'],
      ['--radius-xl', '16px'],
      ['--radius-2xl', '20px'],
    ] as const) {
      expect(theme, token).toContain(`${token}: ${px};`)
    }
  })

  it('holds no dead root duplicate block for radii any more', () => {
    // :root must not set the radius tokens a second time outside @theme
    const rootBlock = css.match(/:root\s*{([\s\S]*?)}/g) ?? []
    const withRadius = rootBlock.filter((b) => /--radius-/.test(b))
    expect(withRadius.length).toBe(0)
  })
})
