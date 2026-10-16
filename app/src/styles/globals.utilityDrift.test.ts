/**
 * Utility drift — a class naming a token nobody declared renders nothing.
 *
 * text-ui-xxs (8x in sections-plugins) and text-ui-md (1x in readerView) emitted
 * no rule at all: the elements inherited their parent size and nothing failed.
 * globals.deadTokens walks var(--x) references and cannot see a class name;
 * globals.scale reads the sheet, not the call sites. This is the third side: a
 * class drawn from a namespace the @theme block owns must name a step that exists
 * there. The legal sets are derived from the sheet, never listed by hand.
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

const theme = new Set(
  [...block(/@theme\s*\{/).matchAll(/(--[a-zA-Z0-9-]+)\s*:/g)].map((m) => m[1] ?? ''),
)
/** The step names a namespace in @theme actually declares. */
const steps = (prefix: string) =>
  new Set(
    [...theme]
      .filter((t) => t.startsWith(prefix) && !t.endsWith('--line-height'))
      .map((t) => t.slice(prefix.length)),
  )

const LEGAL = {
  'text-ui-': steps('--text-ui-'),
  'shadow-elevation-': steps('--shadow-elevation-'),
  'z-index-': new Set([...steps('--z-index-'), 'auto']),
  'duration-': steps('--transition-duration-'),
  'ease-': steps('--ease-'),
  'color-surface': steps('--color-surface-').add(''),
}

/** Class tokens in `text` whose step is missing from its @theme namespace. */
export function unknownTokens(text: string): string[] {
  const out: string[] = []
  const scan = (re: RegExp, legal: Set<string>) => {
    for (const m of text.matchAll(re)) {
      const step = m[1] ?? ''
      if (!legal.has(step)) out.push(m[0])
    }
  }
  scan(/(?<![\w-])text-ui-([a-z0-9]+)/g, LEGAL['text-ui-'])
  scan(/(?<![\w-])shadow-elevation-([a-z0-9]+)/g, LEGAL['shadow-elevation-'])
  scan(/(?<![\w-])z-([a-z][a-z0-9-]*)/g, LEGAL['z-index-'])
  scan(/(?<![\w-])duration-([a-z][a-z0-9-]*)/g, LEGAL['duration-'])
  scan(/(?<![\w-])ease-([a-z][a-z0-9-]*)/g, LEGAL['ease-'])
  scan(/(?<![\w-])(?:bg|text|border|ring)-surface-([a-z][a-z0-9-]*)/g, LEGAL['color-surface'])
  return out
}

// call sites: src .ts/.tsx minus tests, block comments stripped
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

describe('utility drift — every class names a declared step', () => {
  it('detects an undeclared step (the gate has teeth)', () => {
    // the two names that shipped dead, plus a namespace miss on the same axis
    expect(
      unknownTokens('text-ui-xxs text-ui-md shadow-elevation-4 z-deep duration-quick'),
    ).toEqual(['text-ui-xxs', 'text-ui-md', 'shadow-elevation-4', 'z-deep', 'duration-quick'])
    // a declared step in the same shape stays quiet
    expect(unknownTokens('text-ui-2xs shadow-elevation-3 z-modal duration-fast')).toEqual([])
  })

  it('finds no class naming an undeclared @theme step', () => {
    const dead = files.flatMap((f) =>
      unknownTokens(readFileSync(f, 'utf8').replace(/\/\*[\s\S]*?\*\//g, '')).map(
        (t) => `${f}: ${t}`,
      ),
    )
    expect(dead).toEqual([])
  })

  it('scanned the tree (guards against a silently empty walk)', () => {
    expect(files.length).toBeGreaterThan(80)
    expect(LEGAL['text-ui-'].size).toBe(8)
  })
})
