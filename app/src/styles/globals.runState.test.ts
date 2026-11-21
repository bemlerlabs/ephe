/**
 * The run-state layer of the sheet: the four states the agentic workbench chrome
 * moves through, held to the vocabulary the first-open scene already set.
 *
 * Static, like globals.motion.test.ts. The three claims: the durations are the
 * scene's own (no second budget), only compositor properties move, and both switches
 * (the operating system's and the user's) land every state on the still.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'

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

describe('run state — one vocabulary, the scene’s own clock', () => {
  it('takes its durations from the scene tokens, not from a second budget', () => {
    expect(code).toContain('--ephe-run-enter-duration: var(--ephe-condense-duration)')
    expect(code).toContain('--ephe-run-done-duration: var(--ephe-decay-duration)')
    expect(code).toContain('--ephe-run-work-period: var(--ephe-mark-work-period)')
  })

  it('moves only transform, opacity and filter', () => {
    for (const name of ['ephe-run-enter', 'ephe-run-done', 'ephe-run-work']) {
      const kf = block(new RegExp(`@keyframes\\s+${name}\\s*\\{`))
      expect(kf.length, name).toBeGreaterThan(0)
      for (const prop of kf.matchAll(/([\w-]+)\s*:/g)) {
        expect(['transform', 'opacity', 'filter'], `${name} ${prop[1]}`).toContain(prop[1])
      }
    }
  })

  it('names the four states and the two chrome surfaces', () => {
    for (const state of ['ready', 'working', 'waiting', 'done']) {
      expect(code).toContain(`.ephe-run[data-state="${state}"]`)
    }
    expect(code).toContain('.workbench-bar')
    expect(code).toContain('.ephe-run-progress')
    expect(code).toContain('.ephe-rail-mark[data-step="active"]')
    expect(code).toContain('.ephe-rail-mark[data-step="failed"]')
  })

  it('lands every state on the still under both switches', () => {
    // The operating system's switch and the user's carry the same selectors.
    for (const prefix of ['', 'html.no-motion ']) {
      expect(code).toContain(`${prefix}.ephe-run[data-state="working"] .ephe-run-mark`)
      expect(code).toContain(`${prefix}.ephe-rail-mark[data-step="active"]`)
    }
    expect(code).toContain(
      'html.no-motion .ephe-run[data-state="working"] .ephe-run-mark,\nhtml.no-motion .ephe-rail-mark[data-step="active"]',
    )
    // The still keeps the live tone, so a stopped state is still readable.
    expect(code).toContain('opacity: 1 !important;')
  })
})
