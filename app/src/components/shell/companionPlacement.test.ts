/**
 * QD-005 — where the companion is allowed to sit.
 *
 * The figure lives in a stylesheet, so no component test can see the one thing
 * the owner complained about: it leaned into the reading column while the
 * engine wrote. This reads the rule where it is written and refuses both the
 * old offset and the old inset, so a later wave has to raise the issue on
 * purpose instead of rediscovering it in the app.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const css = readFileSync(resolve(process.cwd(), 'src/components/shell/Companion.css'), 'utf8')

function rule(selector: string): string {
  // The bare rule only: `.workspace-companion .companion-turn` and friends are
  // descendant selectors, and the first match in the file is one of those.
  const match = new RegExp(`^\\s*${selector}\\s*\\{`, 'm').exec(css)
  expect(match, `${selector} is missing from Companion.css`).toBeTruthy()
  const open = css.indexOf('{', match!.index)
  return css.slice(open, css.indexOf('}', open))
}

describe('companion placement', () => {
  it('parks the composer companion in the right outer gutter', () => {
    expect(rule('.workspace-companion')).toContain('right: clamp(0.75rem, 1.8vw, 1.5rem)')
  })

  it('never pulls it toward the text while the engine streams', () => {
    expect(css).not.toMatch(/translate\(\s*-4\.5rem/)
    expect(css).not.toMatch(/right:\s*clamp\(\s*1\.2rem\s*,\s*30vw/)
  })
})
