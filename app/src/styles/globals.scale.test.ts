/**
 * W3-56 — design tokens: one scale, no orphans.
 *
 * One scale: every axis carries exactly one ordered step set, declared once in
 * @theme (type S1, radius S6, shadow S3, z S4, tracking). The duplicate layers
 * that once shadowed those axes are gone — a --space-* token scale next to the
 * documented spacing raster, and the --surface-, --text- and --border- trio
 * while it renamed concepts the role layer (--color-) already names *with its
 * own literals*: two names for one value is how the two drift apart.
 *
 * The trio is back as the middle rung of a three-layer taxonomy (semantic roles
 * over the role layer, component roles over that), and the invariant moved from
 * the name to the value: a layer-2 or layer-3 token may only be a single var()
 * onto the layer underneath, never a literal. That is a stronger rule than the
 * old name ban — a renamed literal was legal while it agreed, a var() cannot
 * disagree — and it is checked below.
 *
 * No orphans: every token the sheet defines is consumed somewhere in src/ — by
 * a var() reference or by a generated utility class. The only survivors are a
 * frozen allowlist (ALLOW) of literal compat: the legacy brand aliases the
 * sheet keeps on purpose, the guardian literals test_sprint2_f2/test_r48 read
 * raw, and the two scale steps test_r48 pins. A new dead token fails here.
 *
 * Static, like globals.tokens.test.ts and globals.radius.test.ts.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const css = readFileSync('src/styles/globals.css', 'utf8')
const code = css.replace(/\/\*[\s\S]*?\*\//g, '') // comments carry fake tokens

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

/** Every `--token: value;` declaration in `src`. */
function defs(src: string): Map<string, string> {
  const out = new Map<string, string>()
  for (const m of src.matchAll(/(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);/g))
    out.set(m[1] ?? '', (m[2] ?? '').trim())
  return out
}

const [ts, te] = span(/@theme\s*\{/)
const theme = defs(code.slice(ts, te))
const themeNames = [...theme.keys()]

// consumers: src/ minus tests, comments stripped. `.svg` counts: an asset under
// src/assets/ is inlined into the tree (`?raw` + dangerouslySetInnerHTML), so a
// `var()` in one resolves against the sheet exactly like a var() in a stylesheet.

const EXTS = ['.ts', '.tsx', '.css', '.svg']
function walk(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry)
    if (statSync(p).isDirectory()) out.push(...walk(p))
    else if (EXTS.some((e) => p.endsWith(e)) && !/\.(test|spec)\./.test(p)) out.push(p)
  }
  return out
}
const src = walk('src')
  .map((f) => readFileSync(f, 'utf8').replace(/\/\*[\s\S]*?\*\//g, ''))
  .join('\n')

/** Tailwind v4 utility prefixes that name a --color-* token. */
const COLOR_UTILS =
  'bg|text|border|ring|fill|stroke|from|via|to|outline|shadow|divide|accent|caret|decoration|placeholder|scrollbar|inset-shadow|drop-shadow|selection'

/** The class name that consumes `token`, or null when the namespace is var()-only. */
function utilFor(token: string): string | null {
  if (token.startsWith('--color-')) return `(${COLOR_UTILS})-${token.slice(8)}`
  if (token.startsWith('--radius-')) return `rounded(?:-[a-z]+)*-${token.slice(9)}`
  if (token.startsWith('--shadow-')) return `shadow-${token.slice(9)}`
  if (token.startsWith('--tracking-')) return `tracking-${token.slice(11)}`
  if (token.startsWith('--font-')) return `font-${token.slice(7)}`
  if (token.startsWith('--z-index-')) return `z-${token.slice(10)}`
  if (token.startsWith('--text-') && !token.endsWith('--line-height'))
    return `text-${token.slice(7)}`
  return null
}

/** Is `token` read anywhere in src/? A `--text-x--line-height` rides on `--text-x`. */
function consumed(token: string): boolean {
  const base = token.endsWith('--line-height') ? token.slice(0, -'--line-height'.length) : token
  if (new RegExp(`var\\(\\s*${base}\\s*[,)]`).test(src)) return true
  const util = utilFor(base)
  return util !== null && new RegExp(`(?<![\\w-])${util}(?![\\w-])`).test(src)
}

// one scale: the step set per axis

const stepsOf = (prefix: string) =>
  themeNames
    .filter((n) => n.startsWith(prefix) && !n.endsWith('--line-height'))
    .map((n) => n.slice(prefix.length))
    .sort()

describe('W3-56 — one scale per axis', () => {
  it('type: the 7 documented steps + the fixed input size', () => {
    expect(stepsOf('--text-ui-')).toEqual([
      '2xs',
      'base',
      'caption',
      'input',
      'lg',
      'sm',
      'xl',
      'xs',
    ])
    // every step carries its line-height, and only those (one scale, no stray size)
    for (const step of stepsOf('--text-ui-'))
      expect(theme.has(`--text-ui-${step}--line-height`), `${step} line-height`).toBe(true)
  })

  it('radius: 5 steps + full, on the 4px raster', () => {
    expect(stepsOf('--radius-')).toEqual(['2xl', 'full', 'lg', 'md', 'sm', 'xl'])
    for (const [step, px] of [
      ['sm', '4px'],
      ['md', '8px'],
      ['lg', '12px'],
      ['xl', '16px'],
      ['2xl', '20px'],
    ] as const)
      expect(theme.get(`--radius-${step}`), step).toBe(px)
  })

  it('shadow: exactly three shadow steps, no fourth family', () => {
    // The four-rung --elevation-* ladder names these three by height plus the
    // flat base; it introduces no fourth shadow (globals.boundaryContrast.test.ts
    // pins that mapping).
    const shadows = themeNames.filter((n) => n.startsWith('--shadow-')).sort()
    expect(shadows).toEqual([
      '--shadow-elevation-1',
      '--shadow-elevation-2',
      '--shadow-elevation-3',
    ])
  })

  it('z: the 4-step overlay ladder', () => {
    expect(stepsOf('--z-index-')).toEqual(['base', 'modal', 'overlay', 'sticky'])
    expect(theme.get('--z-index-base')).toBe('0')
    expect(theme.get('--z-index-modal')).toBe('30')
  })
})

describe('W3-56 — no orphan layers', () => {
  it('the dead duplicate scales are gone from the whole sheet', () => {
    const dead = [
      /--space-[a-z-]+/, // a token spacing scale beside the documented raster
      /--text-(primary|secondary|muted)(?![\w-])/, // renamed --color-ink/-soft/-faint
      /--border-(subtle|strong)(?![\w-])/, // renamed --color-hairline[-strong]
      /--color-(primary|accent|popover)(?![\w-])/, // shadcn names nothing here consumes
      /--color-destructive-foreground(?![\w-])/,
    ]
    for (const re of dead) expect(code.match(re), `${re} still defined`).toBeNull()
  })

  it('keeps the semantic layer one var() hop above the role layer', () => {
    // --surface-* was in the list above while it carried its own literals; the
    // ban was right then and the invariant it protected is now stated on the
    // value. A layer-2 token that stops resolving fails here, in
    // globals.tokens.test.ts and in every consumer that reads it.
    const LAYER2 = /^--(surface|text-role|border)-/
    const names = themeNames.filter((n) => LAYER2.test(n))
    expect(names.length).toBeGreaterThanOrEqual(9)
    const literals = names.filter((n) => !/^var\(--[a-zA-Z0-9-]+\)$/.test(theme.get(n) ?? ''))
    expect(literals).toEqual([])
  })

  it('keeps the component layer one var() hop above the semantic layer', () => {
    const LAYER3 = /^--(panel|chip)-/
    const names = themeNames.filter((n) => LAYER3.test(n))
    expect(names.length).toBeGreaterThan(5)
    const bad = names.filter(
      (n) => !/^var\(--(surface|text-role|border)-[a-z-]+\)$/.test(theme.get(n) ?? ''),
    )
    expect(bad).toEqual([])
  })

  it('every token is consumed, or on the frozen compat allowlist', () => {
    // Literal contract survivors — each has a reason, none is a usable scale step:
    //  legacy brand aliases the sheet keeps for utility compatibility
    //  guardian literals the python tests compute raw
    //  the two S1 steps test_r48 pins even while no surface uses them
    const ALLOW = new Set([
      '--color-black-forest',
      '--color-black-midnight',
      '--color-moss',
      '--color-moss-deep',
      '--color-forest-dark',
      '--color-lichen',
      '--color-firefly-glow',
      '--color-stone',
      '--color-card-foreground',
      '--color-secondary-foreground',
      '--color-brand-tint',
      '--color-status-success-hover',
      '--text-ui-xl',
      '--text-ui-caption',
      '--color-figure-plate',
      '--color-figure-wing-root',
      '--color-figure-wing-mid',
      '--color-figure-wing-tip',
      // The constitution's role names: a surface asks for the role, and the
      // palette answers with the signal steps it already had.
      '--color-elevated',
      '--color-ok',
      '--color-warn',
      '--color-error',
    ])
    const bare = (n: string) =>
      n.endsWith('--line-height') ? n.slice(0, -'--line-height'.length) : n
    const orphans = themeNames.filter((n) => !consumed(n) && !ALLOW.has(bare(n)))
    expect(orphans).toEqual([])
  })

  it('the allowlist names live tokens only (no stale entries)', () => {
    const ALLOW = [
      '--color-black-forest',
      '--color-black-midnight',
      '--color-moss',
      '--color-moss-deep',
      '--color-forest-dark',
      '--color-lichen',
      '--color-firefly-glow',
      '--color-stone',
      '--color-card-foreground',
      '--color-secondary-foreground',
      '--color-brand-tint',
      '--color-status-success-hover',
      '--text-ui-xl',
      '--text-ui-caption',
      '--color-figure-plate',
      '--color-figure-wing-root',
      '--color-figure-wing-mid',
      '--color-figure-wing-tip',
    ]
    const missing = ALLOW.filter((n) => !theme.has(n))
    expect(missing).toEqual([])
    // the allowlist cannot grow silently past the documented set
    expect(ALLOW.length).toBe(18)
  })
})
