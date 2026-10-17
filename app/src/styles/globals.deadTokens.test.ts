/**
 * Dead-token scan — every var() reference resolves somewhere in src/.
 *
 * WD-26: ForestBackground carried `var(--background)`, a name no stylesheet
 * defines (the token is `--color-background`); it rendered nothing and nothing
 * noticed. globals.tokens.test.ts only scans globals.css, so a dangling
 * reference in component code stayed invisible. This walks the whole tree:
 * a custom property counts as defined when a CSS/JS declaration or a quoted
 * key sets it, and every `var(--x)` must point at one.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

const SRC = 'src'
const EXTS = ['.ts', '.tsx', '.css']

function walk(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry)
    if (statSync(p).isDirectory()) out.push(...walk(p))
    else if (EXTS.some((e) => p.endsWith(e)) && !/\.(test|spec)\./.test(p)) out.push(p)
  }
  return out
}

const files = walk(SRC).sort()

/** Custom-property names a file *defines*: CSS/JS `--x: …`, `@property --x`,
 *  or a quoted object key `'--x':` / `'--x' as string]:`. */
function definedTokens(src: string): string[] {
  const out: string[] = []
  for (const m of src.matchAll(/@property\s+(--[a-zA-Z0-9-]+)/g)) out.push(m[1]!)
  for (const m of src.matchAll(/['"](--[a-zA-Z0-9-]+)['"]/g)) out.push(m[1]!)
  for (const m of src.matchAll(/(?:^|[\s;{,])(--[a-zA-Z0-9-]+)\s*:/gm)) out.push(m[1]!)
  return out
}

/** var() references; block comments stripped so prose tokens do not count. */
function referencedTokens(src: string): string[] {
  const code = src.replace(/\/\*[\s\S]*?\*\//g, '')
  return [...code.matchAll(/var\(\s*(--[a-zA-Z0-9-]+)/g)].map((m) => m[1]!)
}

const defined = new Set<string>()
const refs: { file: string; token: string }[] = []
for (const f of files) {
  const text = readFileSync(f, 'utf8')
  for (const t of definedTokens(text)) defined.add(t)
  for (const t of referencedTokens(text)) refs.push({ file: relative('.', f), token: t })
}

describe('dead-token scan — every var() reference resolves (WD-26)', () => {
  it('finds no var() reference to an undefined custom property', () => {
    const dead = refs.filter((r) => !defined.has(r.token)).map((r) => `${r.file}: var(${r.token})`)
    expect(dead).toEqual([])
  })

  it('scanned the tree (guards against a silently empty walk)', () => {
    expect(files.length).toBeGreaterThan(50)
    expect(refs.length).toBeGreaterThan(20)
  })
})
