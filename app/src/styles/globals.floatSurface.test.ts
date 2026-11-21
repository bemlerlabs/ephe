/**
 * The floating surface — one primitive, no second recipe.
 *
 * Two recipes had grown for the same role: `glass-float rounded-2xl
 * shadow-elevation-3` (16 sites) and a hand-rolled `bg-background/95
 * backdrop-blur-md rounded-xl shadow-elevation-2` (5). Radius, elevation and
 * material lived at the call sites, so they could drift. They live in
 * `.float-surface` now. This pins the primitive to the tokens and refuses a
 * call site that re-derives any of the three.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const css = readFileSync('src/styles/globals.css', 'utf8')
const code = css.replace(/\/\*[\s\S]*?\*\//g, '')
// the primitive's own rule (the shared group rule also names the selector)
const rules = [...code.matchAll(/\.float-surface\s*\{([^}]*)\}/g)].map((m) => m[1] ?? '')
const rule = rules.find((r) => r.includes('--glass-float-fill')) ?? ''
const level3 = /\.float-surface\[data-float="3"\]\s*\{([^}]*)\}/.exec(code)?.[1] ?? ''

const EXTS = ['.ts', '.tsx']
function walk(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry)
    if (statSync(p).isDirectory()) out.push(...walk(p))
    else if (EXTS.some((e) => p.endsWith(e)) && !/\.(test|spec)\./.test(p)) out.push(p)
  }
  return out
}
const files = walk('src').sort()
const source = new Map(
  files.map((f) => [f, readFileSync(f, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')]),
)

/** Class strings on lines that name the primitive. */
function floatClassLines(): { file: string; text: string }[] {
  const out: { file: string; text: string }[] = []
  for (const [file, text] of source)
    for (const line of text.split('\n'))
      if (/(?<![\w-])float-surface/.test(line)) out.push({ file, text: line })
  return out
}

describe('floating surface — one primitive', () => {
  it('takes radius and elevation from the sheet tokens', () => {
    expect(rule, '.float-surface rule missing').toBeTruthy()
    expect(rule).toContain('border-radius: var(--radius-xl)')
    expect(rule).toContain('var(--shadow-elevation-2)')
    expect(rule).toContain('--glass-float-fill')
  })

  it('leaves exactly one elevation axis, and it reads a sheet token', () => {
    expect(level3, 'the dialog step is gone').toContain('var(--shadow-elevation-3)')
    expect(code.match(/\.float-surface\[data-float=/g) ?? []).toHaveLength(1)
  })

  it('has call sites that do not re-derive material, radius or elevation', () => {
    const sites = floatClassLines()
    expect(sites.length).toBeGreaterThan(15)
    const drift = sites.flatMap(({ file, text }) => {
      const bad = [
        /rounded-(?!full)/,
        /shadow-elevation-/,
        /bg-background\//,
        /backdrop-blur-/,
      ].filter((re) => re.test(text))
      return bad.length ? [`${file}: ${text.trim().slice(0, 90)}`] : []
    })
    expect(drift).toEqual([])
  })

  it('keeps exactly one structural site on the raw material', () => {
    // agent/panel.tsx docks a full-height panel to an edge: a radius would be
    // wrong there, so its own material is allowed — and pinned, so a fourth
    // hand-rolled floating recipe cannot slip in beside it.
    const handRolled = [...source]
      .filter(([, text]) => text.includes('bg-background/95'))
      .map(([f]) => f.slice('src/components/'.length))
    expect(handRolled).toEqual(['dashboard/agent/panel.tsx'])
  })
})
