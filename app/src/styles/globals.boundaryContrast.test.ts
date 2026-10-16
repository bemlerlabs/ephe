/**
 * Boundary contrast as a token rule — the control boundary clears WCAG 1.4.11
 * in both themes.
 *
 * The measured defect: no UI boundary reached 3:1. The 1-px hairline sits at
 * 1.21-1.42:1 and the louder hover step at 1.4-1.9:1, so six interactive
 * elements carried a boundary nobody with reduced contrast sensitivity can see
 * as an edge (WCAG 2.2 SC 1.4.11 asks 3:1 for exactly that). A per-component
 * fix cannot hold the floor — the next component re-derives a border from
 * whatever token is at hand. This file asserts the floor as a property of the
 * tokens: --border-control clears 3:1 against every background role the sheet
 * declares, in both themes, recomputed from the values in globals.css. No
 * figure here is a recorded number; change a token and this moves with it.
 *
 * It also pins the rest of the contract the same way: the semantic and
 * component layers exist, the elevation ladder carries four ordered steps, and
 * the boundary is reachable as a class (the --color-* namespace is the one
 * Tailwind v4 turns into utilities).
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const css = readFileSync('src/styles/globals.css', 'utf8')
const code = css.replace(/\/\*[\s\S]*?\*\//g, '')

/** The body of the first block whose selector matches `re`, brace-balanced. */
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

/** Every `--token: value;` declaration in `src`. */
function defs(src: string): Map<string, string> {
  const out = new Map<string, string>()
  for (const m of src.matchAll(/(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);/g))
    out.set(m[1] ?? '', (m[2] ?? '').trim())
  return out
}

const ink = defs(block(/@theme\s*\{/))
const paper = defs(block(/html\.light\s*\{/))
const THEMES: [string, Map<string, string>][] = [
  ['ink', ink],
  ['paper', new Map([...ink, ...paper])],
]

/** One hop of var() at a time, so a chain of roles still lands on a value. */
function resolve(theme: Map<string, string>, name: string, seen: string[] = []): string {
  const raw = theme.get(name)
  if (raw === undefined) throw new Error(`${name} is not declared in this theme`)
  const hop = /^var\(\s*(--[a-zA-Z0-9-]+)\s*\)$/.exec(raw)
  if (!hop) return raw
  if (seen.includes(name)) throw new Error(`${name} resolves in a cycle: ${seen.join(' -> ')}`)
  return resolve(theme, hop[1] as string, [...seen, name])
}

type Rgba = [number, number, number, number]

/** `hsl(H S% L%)` / `hsl(H S% L% / A)`, plus the bare hex the hero tokens use. */
function parseColor(value: string): Rgba {
  const hsl = /^hsla?\(\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*(?:\/\s*([\d.]+)\s*)?\)$/.exec(value)
  if (hsl) {
    const [h, s, l] = [Number(hsl[1]), Number(hsl[2]) / 100, Number(hsl[3]) / 100]
    const k = (n: number) => (n + h / 30) % 12
    const a = s * Math.min(l, 1 - l)
    const f = (n: number) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)))
    return [f(0) * 255, f(8) * 255, f(4) * 255, hsl[4] === undefined ? 1 : Number(hsl[4])]
  }
  const hex = /^#([0-9a-f]{6})$/i.exec(value)
  if (hex) {
    const n = parseInt(hex[1] as string, 16)
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255, 1]
  }
  throw new Error(`unparsable colour: ${value}`)
}

/** A translucent role is a veil over its own ground, which is what an eye sees. */
function over(fg: Rgba, bg: Rgba): Rgba {
  return [
    fg[0] * fg[3] + bg[0] * (1 - fg[3]),
    fg[1] * fg[3] + bg[1] * (1 - fg[3]),
    fg[2] * fg[3] + bg[2] * (1 - fg[3]),
    1,
  ]
}

function luminance([r, g, b]: Rgba): number {
  const lin = (c: number) => {
    const v = c / 255
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}

function ratio(a: Rgba, b: Rgba): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number]
  return (hi + 0.05) / (lo + 0.05)
}

/** Every ground the sheet lets a control sit on. The two veils lift a card, so they
 *  composite on the card role, not on the page. */
const GROUNDS = [
  '--color-canvas',
  '--color-surface',
  '--color-surface-raised',
  '--color-surface-interactive',
] as const

const BOUNDARY = '--border-control'
const FLOOR = 3

function ground(theme: Map<string, string>, name: string): Rgba {
  const value = parseColor(resolve(theme, name))
  if (value[3] === 1) return value
  return over(value, parseColor(resolve(theme, '--color-surface')))
}

describe('the control boundary clears 3:1 as a token rule (WCAG 1.4.11)', () => {
  it('declares the boundary role in both themes', () => {
    for (const [label, theme] of THEMES) {
      expect(theme.has(BOUNDARY), `${BOUNDARY} missing from the ${label} theme`).toBe(true)
      expect(resolve(theme, BOUNDARY)).toMatch(/^(hsla?\(|#)/)
    }
  })

  it(`holds ${FLOOR}:1 against every background role the sheet declares`, () => {
    const rows: string[] = []
    for (const [label, theme] of THEMES) {
      const edge = parseColor(resolve(theme, BOUNDARY))
      for (const name of GROUNDS) {
        const value = ratio(edge, ground(theme, name))
        rows.push(
          `${label.padEnd(5)} ${BOUNDARY.padEnd(17)} on ${name.padEnd(28)} ${value.toFixed(2)}:1`,
        )
        expect(
          value,
          `${label}: ${BOUNDARY} on ${name} = ${value.toFixed(2)}:1 < ${FLOOR}:1`,
        ).toBeGreaterThanOrEqual(FLOOR)
      }
    }
    // the measured grid, printed every run and carried in a failure message
    console.log(
      ['boundary grid — the control edge on each background role, floor 3:1', ...rows].join('\n'),
    )
    expect(rows.length).toBe(THEMES.length * GROUNDS.length)
  })

  it('is a distinct role, never the decorative hairline under another name', () => {
    for (const [label, theme] of THEMES) {
      expect(
        resolve(theme, BOUNDARY),
        `${label}: the boundary role was pointed back at the decorative 1.3:1 hairline`,
      ).not.toBe(resolve(theme, '--color-hairline'))
      expect(
        resolve(theme, '--color-control'),
        `${label}: --color-control (the class bridge) drifted from the boundary role`,
      ).toBe(resolve(theme, BOUNDARY))
    }
  })

  it('hands the boundary to the utility namespace, so a call site can name it', () => {
    const body = code.slice(code.indexOf(BOUNDARY))
    expect(body).toMatch(/var\(--border-control\)/)
    expect(ink.has('--color-control')).toBe(true)
  })
})

describe('the token taxonomy carries its three layers', () => {
  const NAMESPACES: [string, RegExp][] = [
    ['semantic surface', /--surface-[a-z-]+:/],
    ['semantic text role', /--text-role-[a-z-]+:/],
    ['semantic boundary', /--border-[a-z-]+:/],
    ['component panel', /--panel-[a-z-]+:/],
    ['component chip', /--chip-[a-z-]+:/],
  ]

  it('declares a semantic and a component namespace', () => {
    for (const [label, re] of NAMESPACES) {
      expect(re.test(code), `${label} namespace is missing`).toBe(true)
    }
  })

  it('names the four elevation steps in one ordered ladder', () => {
    const ladder = ['base', 'raised', 'overlay', 'elevated'].map((s) => `--elevation-${s}`)
    for (const step of ladder) expect(ink.has(step), `${step} missing`).toBe(true)
    expect(resolve(ink, '--elevation-base')).toBe('none')
    // each step above the base borrows the shadow family of the matching depth,
    // so the ladder cannot drift from the S3 steps it names
    expect(resolve(ink, '--elevation-raised')).toBe(resolve(ink, '--shadow-elevation-1'))
    expect(resolve(ink, '--elevation-overlay')).toBe(resolve(ink, '--shadow-elevation-2'))
    expect(resolve(ink, '--elevation-elevated')).toBe(resolve(ink, '--shadow-elevation-3'))
  })

  it('keeps the role-class landmines out of the components', () => {
    // --text-role-* lives in Tailwind v4's font-size namespace, so a matching
    // class would set font-size instead of a colour. Nothing may use one.
    const EXTS = ['.ts', '.tsx']
    const walk = (dir: string): string[] => {
      const out: string[] = []
      for (const entry of readdirSync(dir)) {
        const p = join(dir, entry)
        if (statSync(p).isDirectory()) out.push(...walk(p))
        else if (EXTS.some((e) => p.endsWith(e)) && !/\.(test|spec)\./.test(p)) out.push(p)
      }
      return out
    }
    const files = walk('src')
    const offenders = files.flatMap((f) =>
      [
        ...readFileSync(f, 'utf8')
          .replace(/\/\*[\s\S]*?\*\//g, '')
          .matchAll(/(?<![\w-])text-role-[a-z-]+/g),
      ].map((m) => `${f}: ${m[0]}`),
    )
    expect(offenders).toEqual([])
    expect(files.length).toBeGreaterThan(80)
  })
})
