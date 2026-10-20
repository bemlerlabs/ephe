/**
 * Curated accents — layer 1 only, measured on the one ground.
 *
 * The three preset blocks may bend exactly the four brand roles; the ground,
 * status tones, selection steps and the terminal palette must stay the base
 * sheet's. Every pair below is computed from the shipped literals, so changing
 * an accent without its measurement fails here.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'

const css = readFileSync('src/styles/globals.css', 'utf8')
const code = css.replace(/\/\*[\s\S]*?\*\//g, '')

function block(re: RegExp): string {
  const m = re.exec(code)
  if (!m) return ''
  const open = code.indexOf('{', m.index)
  let depth = 0
  for (let i = open; i < code.length; i++) {
    if (code[i] === '{') depth++
    else if (code[i] === '}' && --depth === 0) return code.slice(open + 1, i)
  }
  return code.slice(open + 1)
}

function defs(src: string): Map<string, string> {
  const out = new Map<string, string>()
  for (const m of src.matchAll(/(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);/g))
    out.set(m[1] ?? '', (m[2] ?? '').trim())
  return out
}

type Rgba = [number, number, number, number]

function hsl(value: string): Rgba {
  const m = /hsl\(\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%(?:\s*\/\s*([\d.]+))?\s*\)/.exec(value)
  if (!m) throw new Error(`not an hsl() value: ${value}`)
  const h = Number(m[1]) / 360
  const s = Number(m[2]) / 100
  const l = Number(m[3]) / 100
  const a = m[4] === undefined ? 1 : Number(m[4])
  const f = (n: number) => {
    const k = (n + h * 12) % 12
    const amp = s * Math.min(l, 1 - l)
    return Math.round((l - amp * Math.max(-1, Math.min(k - 3, 9 - k, 1))) * 255)
  }
  return [f(0), f(8), f(4), a]
}

function luminance([r, g, b]: Rgba): number {
  const f = (channel: number) => {
    const c = channel / 255
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
}

function ratio(a: Rgba, b: Rgba): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number]
  return (hi + 0.05) / (lo + 0.05)
}

function over(fg: Rgba, bg: Rgba): Rgba {
  return [
    Math.round(fg[0] * fg[3] + bg[0] * (1 - fg[3])),
    Math.round(fg[1] * fg[3] + bg[1] * (1 - fg[3])),
    Math.round(fg[2] * fg[3] + bg[2] * (1 - fg[3])),
    1,
  ]
}

const theme = defs(block(/@theme\s*\{/))
const canvas = hsl(theme.get('--color-canvas') as string)
const surface = hsl(theme.get('--color-surface') as string)
const ink = hsl(theme.get('--color-ink') as string)
const black: Rgba = [0, 0, 0, 1]

const BRAND_KEYS = [
  '--color-brand',
  '--color-brand-deep',
  '--color-brand-glow',
  '--color-brand-tint',
] as const

const baseBrand = hsl(theme.get('--color-brand') as string)
const baseGlow = hsl(theme.get('--color-brand-glow') as string)
const baseTint = hsl(theme.get('--color-brand-tint') as string)

const ACCENTS = ['indigo', 'plum', 'mono'] as const

describe('curated accents', () => {
  it('each preset declares only the four brand roles', () => {
    for (const accent of ACCENTS) {
      const preset = defs(block(new RegExp(`html\\[data-accent='${accent}'\\]\\s*\\{`)))
      expect([...preset.keys()].sort()).toEqual([...BRAND_KEYS].sort())
    }
  })

  const cases: [string, Rgba, Rgba, Rgba][] = [
    ['ember', baseBrand, baseGlow, baseTint],
    ...ACCENTS.map((accent): [string, Rgba, Rgba, Rgba] => {
      const preset = defs(block(new RegExp(`html\\[data-accent='${accent}'\\]\\s*\\{`)))
      return [
        accent,
        hsl(preset.get('--color-brand') as string),
        hsl(preset.get('--color-brand-glow') as string),
        hsl(preset.get('--color-brand-tint') as string),
      ]
    }),
  ]

  it.each(cases)('%s keeps text, fill and ring on the floors', (_name, brand, glow, tint) => {
    expect(ratio(brand, canvas)).toBeGreaterThanOrEqual(4.5)
    expect(ratio(brand, surface)).toBeGreaterThanOrEqual(4.5)
    expect(ratio(black, brand)).toBeGreaterThanOrEqual(4.5)
    expect(ratio(brand, canvas)).toBeGreaterThanOrEqual(3)
    expect(ratio(glow, canvas)).toBeGreaterThanOrEqual(3)
    expect(ratio(ink, over(tint, surface))).toBeGreaterThanOrEqual(4.5)
  })
})
