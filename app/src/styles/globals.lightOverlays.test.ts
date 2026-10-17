/**
 * Light-mode overlays — one theme-aware pair, and a ban on the raw veil.
 *
 * 62 bg-white/[0.03–0.12] utilities lifted chips, rows and hovers out of the ink
 * ground. On the paper theme the same utility is a ~1% luminance delta against
 * hsl(60 25% 92%): hover and selection simply vanished. Those call sites now read
 * bg-surface-raised / bg-surface-interactive, names the @theme block declares as a
 * white lift and html.light re-points at an ink tint. Two invariants hold it
 * together: the pair must exist in BOTH blocks and must not be the same colour,
 * and the raw bg-white/<alpha> form must not come back.
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

function defs(src: string): Map<string, string> {
  const out = new Map<string, string>()
  for (const m of src.matchAll(/(--[a-zA-Z0-9-]+)\s*:\s*([^;]+);/g))
    out.set(m[1] ?? '', (m[2] ?? '').trim())
  return out
}

const ink = defs(block(/@theme\s*\{/))
const paper = defs(block(/html\.light\s*\{/))
const PAIR = ['--color-surface-raised', '--color-surface-interactive']

// call sites: src .ts/.tsx minus tests, block comments stripped (prose may name
// the old class while explaining why it left).
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

// w10-22 owns this file in the same wave; its two overlays move with their edit.
const PENDING = new Set(['src/components/dashboard/settings/model/sections-mcp.tsx'])

describe('light-mode overlays — one pair, no raw veil', () => {
  it('declares the pair in @theme and in html.light', () => {
    for (const name of PAIR) {
      expect(ink.get(name), `${name} missing from @theme`).toBeTruthy()
      expect(paper.get(name), `${name} missing from html.light`).toBeTruthy()
    }
  })

  it('gives paper a different value, not a white veil', () => {
    for (const name of PAIR) {
      const light = paper.get(name) ?? ''
      expect(light, `${name} is still a white overlay`).not.toBe(ink.get(name))
      expect(/0 0% 100%/.test(light), `${name} lifted by white on paper`).toBe(false)
    }
  })

  it('leaves no raw bg-white/<alpha> overlay outside the pending file', () => {
    const files = walk('src')
    const offenders = files
      .filter((f) => !PENDING.has(f))
      .flatMap((f) =>
        [
          ...readFileSync(f, 'utf8')
            .replace(/\/\*[\s\S]*?\*\//g, '')
            .matchAll(/(?:bg|border)-white\/[0-9.[\]]+/g),
        ].map((m) => `${f}: ${m[0]}`),
      )
    expect(offenders).toEqual([])
    expect(files.length).toBeGreaterThan(80)
  })

  it('keeps the pending file honest (the entry leaves with w10-22)', () => {
    for (const f of PENDING) {
      const raw = readFileSync(f, 'utf8')
      expect(/bg-white\//.test(raw), `${f} no longer holds an overlay`).toBe(true)
    }
  })
})
