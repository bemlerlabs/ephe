/**
 * The motion budget has consumers now.
 *
 * globals.css declared seven motion tokens in :root and no .tsx ever read them:
 * 14 sites hardcoded duration-200, so the budget was documentation. The tokens
 * moved into @theme where the v4 namespaces emit the duration- and ease-
 * utilities, and the components read those. This pins both halves: the tokens
 * must keep their @theme names, and the budget must not fall back to a number.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

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
const theme = block(/@theme\s*\{/)

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
const source = walk('src')
  .map((f) => readFileSync(f, 'utf8').replace(/\/\*[\s\S]*?\*\//g, ''))
  .join('\n')

describe('motion budget — tokens the components read', () => {
  it('declares the steps in the namespaces that emit the utilities', () => {
    for (const t of [
      '--transition-duration-fast',
      '--transition-duration-base',
      '--transition-duration-slow',
    ])
      expect(theme, t).toContain(`${t}:`)
    for (const t of ['--ease-out-soft', '--ease-organic', '--ease-settle'])
      expect(theme, t).toContain(`${t}:`)
  })

  it('keeps the --motion-* aliases the animation rules read', () => {
    for (const t of ['--motion-fast', '--motion-base', '--motion-slow'])
      expect(code, t).toContain(`${t}: var(--transition-duration-`)
  })

  it('has a component consuming every duration step', () => {
    for (const util of ['duration-fast', 'duration-base', 'duration-slow'])
      expect(new RegExp(`(?<![\\w-])${util}(?![\\w-])`).test(source), util).toBe(true)
    expect(/(?<![\w-])ease-(?:out-soft|organic|settle)(?![\w-])/.test(source)).toBe(true)
  })

  it('no site falls back to the hardcoded duration it replaced', () => {
    expect(source.includes('duration-200'), 'duration-200 came back').toBe(false)
    expect(source.includes('ease-[var(--ease-'), 'arbitrary ease came back').toBe(false)
  })
})
