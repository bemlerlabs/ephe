import { expect, test, type Page } from '@playwright/test'
import { readdirSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { ensureOnboarded } from './helpers'

/**
 * UI 4x work item #67 (U3) — the three glass layers measured where they render.
 *
 * `tests/test_r61_glass_contrast.py` computes the same 18 ratios from the stylesheet source on
 * every pytest run. This file reads them off `app/dist` in a browser, because the source and the
 * shipped sheet are two artefacts and only one of them is what a reader looks at: the build
 * rewrites every `hsla()` triple into an 8-digit hex, so `hsla(0 0% 26% / 0.20)` ships as
 * `#42424233`, and a step that shifted an alpha by one unit would move a ratio without moving a
 * line of the file the Python gate parses.
 *
 * The rule is section 8 of `docs/UI_4X_PROGRAM_2026-10-11.md`: three layers named by role, each
 * carrying its own fill, and every ink role at 4.5:1 or better against that fill composited on
 * the theme canvas. The compositing is what the browser paints, so a probe panel goes into
 * `document.body`, whose background is the canvas token, and two computed colours are asked for:
 * the panel's `background-color` with its alpha, and the ink resolved through a `var()` span the
 * way the sheet's own var() links resolve one.
 *
 * The canvas assumption bounds every figure here as it bounds the Python gate. Over a bright
 * content area the same veils read 2.50:1 to 3.21:1 for the muted role, which is wave 5's pixel
 * sampler and is still unwritten.
 *
 * The third case is the sweep's own guard: 74 occurrences moved off the two class names this
 * section replaced, and a surface left spelling a dead name loses its glass silently, because an
 * unmatched class paints nothing. The fourth case closes the retirement: the two rules are gone
 * from the sheet now, and `liquid-glass` does not start with `glass-`, so it would slip past the
 * third case while painting nothing. Both names are refused in the source and in the built chunks.
 */

const AA_NORMAL = 4.5
const LAYERS = ['glass-reading', 'glass-control', 'glass-float'] as const
const ROLES = ['color-ink', 'color-ink-soft', 'color-ink-faint'] as const

type Cell = {
  theme: 'forest'
  layer: string
  role: string
  ratio: number
  panel: string
  ink: string
}

function channel(c: number): number {
  const v = c / 255
  return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
}

function luminance(rgb: number[]): number {
  return 0.2126 * channel(rgb[0]) + 0.7152 * channel(rgb[1]) + 0.0722 * channel(rgb[2])
}

function contrast(a: number[], b: number[]): number {
  const l1 = luminance(a)
  const l2 = luminance(b)
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)
}

/** `rgb(66, 66, 66)` / `rgba(66, 66, 66, 0.2)` as the browser's computed style spells them. */
function parseColor(value: string): { rgb: number[]; alpha: number } {
  const match = value.match(/rgba?\(([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,/\s]+([\d.]+))?\)?/)
  if (!match) throw new Error(`computed colour arrived unparsable: ${value}`)
  return {
    rgb: [Number(match[1]), Number(match[2]), Number(match[3])],
    alpha: match[4] === undefined ? 1 : Number(match[4]),
  }
}

function composite(fill: number[], ground: number[], alpha: number): number[] {
  return fill.map((c, i) => c * alpha + ground[i] * (1 - alpha))
}

async function grid(page: Page): Promise<Cell[]> {
  const raw = await page.evaluate(
    ([layers, roles]: [string[], string[]]) => {
      const canvas = getComputedStyle(document.body).backgroundColor
      const rows: { layer: string; role: string; panel: string; ink: string; canvas: string }[] = []
      for (const layer of layers) {
        const panel = document.createElement('div')
        panel.className = layer
        document.body.append(panel)
        const fill = getComputedStyle(panel).backgroundColor
        for (const role of roles) {
          const label = document.createElement('span')
          label.style.color = `var(--${role})`
          panel.append(label)
          rows.push({ layer, role, panel: fill, ink: getComputedStyle(label).color, canvas })
          label.remove()
        }
        panel.remove()
      }
      return rows
    },
    [[...LAYERS], [...ROLES]] as [string[], string[]],
  )
  return raw.map((row) => {
    const fill = parseColor(row.panel)
    const ground = composite(fill.rgb, parseColor(row.canvas).rgb, fill.alpha)
    return {
      theme: 'forest',
      layer: `.${row.layer}`,
      role: `--${row.role}`,
      panel: row.panel,
      ink: row.ink,
      ratio: contrast(parseColor(row.ink).rgb, ground),
    }
  })
}

function table(rows: Cell[]): string {
  return rows
    .map(
      (r) =>
        `${r.theme.padEnd(5)} ${r.layer.padEnd(16)} ${r.role.padEnd(20)} ${r.ratio.toFixed(2)}:1`,
    )
    .join('\n')
}

test.describe('glass layers in the built bundle', () => {
  test.beforeEach(async ({ page }) => {
    ensureOnboarded(page)
    await page.goto('/', { waitUntil: 'load' })
  })

  test('every ink role holds AA behind every forest layer', async ({ page }) => {
    const rows = await grid(page)
    expect(rows, '3 layers x 3 ink roles on the one ground').toHaveLength(9)
    console.log(`U3 glass grid, forest ground, rendered from app/dist\n${table(rows)}`)
    for (const row of rows) {
      expect(
        row.ratio,
        `${row.theme} ${row.role} behind ${row.layer} (fill ${row.panel} on ${row.ink})`,
      ).toBeGreaterThanOrEqual(AA_NORMAL)
    }
  })

  test('the three layers are three veils, and every surface that names one paints it', async ({
    page,
  }) => {
    // The removal and the read happen in ONE synchronous `evaluate`. The app applies the theme
    // itself at module load (`main.tsx` → `lib/theme.ts`: `getStoredTheme()` returns light when
    // nothing is stored), and the class was measured absent right after `waitUntil: 'load'` and
    // present a beat later — so a removal in one round trip and a read in the next can straddle
    // that write. The read then lands in the LIGHT theme, where reading and control deliberately
    // share one fill (`.light` in the built sheet: `--glass-reading-fill:#ffffffe0` and
    // `--glass-control-fill:#ffffffe0`) and the count really is 2 — a red that blames the three
    // layers for a window this case never opened.
    const seen = await page.evaluate(() => {
      document.documentElement.classList.remove('light')
      const theme = document.documentElement.className
      const fills = ['glass-reading', 'glass-control', 'glass-float'].map((layer) => {
        const el = document.createElement('div')
        el.className = layer
        document.body.append(el)
        const value = getComputedStyle(el).backgroundColor
        el.remove()
        return value
      })
      const bare = Array.from(
        document.querySelectorAll(
          '[class*="glass-reading"], [class*="glass-control"], [class*="glass-float"]',
        ),
      )
        .map((el) => ({
          cls: String(el.className).slice(0, 60),
          bg: getComputedStyle(el).backgroundColor,
        }))
        .filter((entry) => /rgba\([^)]+,\s*0\)$/.test(entry.bg))
      return { fills, bare, theme }
    })
    // The window this case measures is the ink theme. Say so, rather than inferring it from a
    // removal nothing checked: when the app's own boot won the race, the fills below are the
    // light theme's and the failure is about the window, not about the three layers.
    expect(
      seen.theme,
      `the ink window closed before the read (html class "${seen.theme}")`,
    ).not.toContain('light')
    // A layer that lost its rule ships transparent, and two layers that share a value in this
    // theme are one layer doing two jobs: section 8 separates them in the ink theme by measurement.
    for (const fill of seen.fills) expect(fill).not.toBe('rgba(0, 0, 0, 0)')
    expect(
      new Set(seen.fills).size,
      `three ink-theme fills came back identical: ${seen.fills}`,
    ).toBe(3)
    expect(seen.bare, `glass surfaces painting no fill: ${JSON.stringify(seen.bare)}`).toEqual([])
  })

  test('every glass class a component spells has a rule in the built sheet', () => {
    // A rename that lands on a name no rule defines is invisible in a screenshot of a page that
    // does not show the surface, and the class string is the only thing a translucent panel has:
    // `glass-float-strong` was one such rename, produced by this lane's own sweep across 13 sites,
    // and every ratio in the world read green while the float layer painted nothing.
    const source = join(fileURLToPath(new URL('../../src', import.meta.url)))
    const used = new Set<string>()
    for (const name of readdirSync(source, { recursive: true })) {
      if (!/\.(ts|tsx)$/.test(name)) continue
      const text = readFileSync(join(source, name), 'utf8')
      for (const hit of text.matchAll(/(?<![-\w])(glass-[a-z][a-z-]*)/g)) used.add(hit[1])
    }
    expect(used.size, `no glass class found under ${source}`).toBeGreaterThanOrEqual(3)
    const assets = join(fileURLToPath(new URL('../../dist/assets', import.meta.url)))
    const sheets = readdirSync(assets).filter((name) => name.endsWith('.css'))
    expect(sheets.length, `no built stylesheet under ${assets}`).toBeGreaterThan(0)
    const sheet = sheets.map((name) => readFileSync(join(assets, name), 'utf8')).join('\n')
    const orphans = [...used].filter((token) => !sheet.includes(`.${token}`))
    expect(orphans, `classes with no rule in the built sheet: ${orphans.join(', ')}`).toEqual([])
  })

  test('the two retired class names match nothing, in the source and in the bundle', () => {
    // What the case above cannot see: `liquid-glass` does not start with `glass-`, so a surface that
    // reappeared under a retired name would pass it, and since globals.css no longer defines those
    // two rules such a surface paints nothing at all. Both halves are checked because the name can
    // come back through a component or through a stylesheet that grew the block again. `src` only,
    // since this file has to spell the names to refuse them.
    const source = join(fileURLToPath(new URL('../../src', import.meta.url)))
    const carriers: string[] = []
    for (const name of readdirSync(source, { recursive: true })) {
      if (!/\.(ts|tsx|css)$/.test(name)) continue
      if (readFileSync(join(source, name), 'utf8').includes('liquid-glass')) carriers.push(name)
    }
    expect(carriers, `sources spelling a retired glass class: ${carriers.join(', ')}`).toEqual([])
    const assets = join(fileURLToPath(new URL('../../dist/assets', import.meta.url)))
    const shipped = readdirSync(assets)
      .filter((name) => /\.(js|css)$/.test(name))
      .filter((name) => readFileSync(join(assets, name), 'utf8').includes('liquid-glass'))
    expect(shipped, `built chunks still carrying a retired class: ${shipped.join(', ')}`).toEqual(
      [],
    )
  })
})
