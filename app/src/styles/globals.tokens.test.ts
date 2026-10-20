/**
 * Token consistency — one stylesheet, one ground.
 *
 * The @theme block carries the forest role literals and :root holds the
 * theme-neutral defaults; there is no second block to bend them (owner decision
 * 2026-10-19). The structure is fine until a guardian literal no longer equals
 * the role it duplicates or a var() reference resolves to nothing — both fail
 * silently at build time and show up only as a wrong colour. One case below
 * refuses a second ground outright, because a `html.light` block returning here
 * would make every other read of this file pass against a map nobody fills.
 * These invariants read the sheet statically, like globals.radius.test.ts.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'

const css = readFileSync('src/styles/globals.css', 'utf8')
const code = css.replace(/\/\*[\s\S]*?\*\//g, '') // comments carry fake tokens (var(--color-*))

/** [start, end) of the first block whose selector matches `re`, brace-balanced. */
function span(re: RegExp): [number, number] {
  const m = re.exec(code)
  if (!m) return [0, 0]
  const open = code.indexOf('{', m.index)
  let depth = 0
  for (let i = open; i < code.length; i++) {
    if (code[i] === '{') depth++
    else if (code[i] === '}' && --depth === 0) return [open + 1, i]
  }
  return [open + 1, code.length]
}

/** The body of the first block whose selector matches `re`. */
function block(re: RegExp): string {
  const [a, b] = span(re)
  return code.slice(a, b)
}

/** Every `--token: value;` declaration in `src`. */
function defs(src: string): Map<string, string> {
  const out = new Map<string, string>()
  for (const m of src.matchAll(/(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);/g))
    out.set(m[1] ?? '', (m[2] ?? '').trim())
  return out
}

const theme = defs(block(/@theme\s*\{/))

describe('theme tokens — one stylesheet, one ground', () => {
  it('declares no second ground', () => {
    expect(code).not.toMatch(/(^|\n)\s*html\.light\s*\{/)
    expect(css).not.toContain('html.light')
  })

  it('every var() reference resolves in the sheet', () => {
    const defined = new Set([...code.matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)].map((m) => m[1]))
    const registered = new Set(
      [...code.matchAll(/@property\s+(--[a-zA-Z0-9-]+)/g)].map((m) => m[1]),
    )
    const withFallback = new Set(
      [...code.matchAll(/var\(\s*(--[a-zA-Z0-9-]+)\s*,/g)].map((m) => m[1]),
    )
    const refs = new Set([...code.matchAll(/var\(\s*(--[a-zA-Z0-9-]+)/g)].map((m) => m[1]))
    const dangling = [...refs].filter(
      (t) => !defined.has(t) && !registered.has(t) && !withFallback.has(t),
    )
    expect(dangling).toEqual([])
  })

  it('keeps every guardian literal equal to the role it duplicates', () => {
    // Legacy token -> the role token whose @theme literal it mirrors. test_sprint2_f2
    // and test_r48 read these raw, so the two copies must not drift apart.
    const pairs: [string, string][] = [
      ['--color-firefly', '--color-brand'],
      ['--color-firefly-glow', '--color-brand-glow'],
      ['--color-stone', '--color-ink'],
      ['--color-mist', '--color-ink-soft'],
      ['--color-background', '--color-canvas'],
      ['--color-foreground', '--color-ink'],
      ['--color-card', '--color-surface'],
      ['--color-card-foreground', '--color-ink'],
      ['--color-secondary', '--color-muted'],
      ['--color-secondary-foreground', '--color-ink'],
      ['--color-muted-foreground', '--color-ink-faint'],
    ]
    for (const [legacy, role] of pairs) {
      expect(theme.get(legacy), `${legacy} fehlt im @theme`).toBeTruthy()
      expect(theme.get(role), `${role} fehlt im @theme`).toBeTruthy()
      expect(theme.get(legacy), `${legacy} != ${role}`).toBe(theme.get(role))
    }
  })

  it('names the radius steps the S6 comment actually defines', () => {
    const comment = /S6 \(R48\): radius nesting convention[\s\S]*?\*\//.exec(css)?.[0] ?? ''
    expect(comment).toContain('5 steps')
    expect(comment).toContain('sm 4')
    expect(comment).not.toContain('sm 6')
    expect(theme.get('--radius-sm')).toBe('4px')
    expect(theme.get('--radius-2xl')).toBe('20px')
  })
})
