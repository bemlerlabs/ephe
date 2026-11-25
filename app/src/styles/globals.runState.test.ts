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

/**
 * A selector's presentation is not its meaning: the formatter may quote an
 * attribute value either way and break one rule's selector list across lines,
 * so the two cases below read the sheet with attribute quotes removed and
 * whitespace collapsed. Class and attribute names keep their case — in CSS
 * that difference does mean something.
 */
function selectorForm(src: string): string {
  return src
    .replace(
      /\[\s*([\w-]+)\s*=\s*(?:"([^"]*)"|'([^']*)')\s*\]/g,
      (_all, name: string, double: string, single: string) => `[${name}=${double ?? single}]`,
    )
    .replace(/\s+/g, ' ')
    .trim()
}

const sheet = selectorForm(code)

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

  it('names the four states and the two chrome surfaces, quote style aside', () => {
    for (const state of ['ready', 'working', 'waiting', 'done']) {
      expect(sheet).toContain(`.ephe-run[data-state=${state}]`)
    }
    expect(sheet).toContain('.workbench-bar')
    expect(sheet).toContain('.ephe-run-progress')
    expect(sheet).toContain('.ephe-rail-mark[data-step=active]')
    expect(sheet).toContain('.ephe-rail-mark[data-step=failed]')
  })

  it('lands every state on the still under both switches, line breaks aside', () => {
    // The operating system's switch and the user's carry the same selectors.
    for (const prefix of ['', 'html.no-motion ']) {
      expect(sheet).toContain(`${prefix}.ephe-run[data-state=working] .ephe-run-mark`)
      expect(sheet).toContain(`${prefix}.ephe-rail-mark[data-step=active]`)
    }
    expect(sheet).toContain(
      'html.no-motion .ephe-run[data-state=working] .ephe-run-mark, html.no-motion .ephe-rail-mark[data-step=active]',
    )
    // The still keeps the live tone, so a stopped state is still readable.
    expect(sheet).toContain('opacity: 1 !important;')
  })
})
