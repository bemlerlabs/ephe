/**
 * I5-5 — the focus outline has a single source.
 *
 * Finding of the day: `*:focus-visible { outline: 2px solid hsl(0 72% 51%) }` sat
 * outside every @layer rule. In the cascade model an unlayered rule still beats
 * EVERY layered one — so the .focus-ring class in the component layer had no
 * effect and the whole interface showed a red focus ring. A sweep of the
 * outline-firefly classes (I5-1) could not see this one finding, because it is
 * not written as a class in the TSX.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'

const css = readFileSync('src/styles/globals.css', 'utf8')

function ruleFor(selector: string): string {
  const i = css.indexOf(selector)
  if (i < 0) return ''
  const open = css.indexOf('{', i)
  return css.slice(open + 1, css.indexOf('}', open))
}

describe('I5-5 — Fokus-Kontur', () => {
  it('die globale Kontur folgt dem Token, nicht einem Farbwort', () => {
    const rule = ruleFor('*:focus-visible')
    expect(rule).toContain('outline: 2px solid var(--color-ring)')
    expect(rule).not.toMatch(/outline:[^;]*(hsl\(|#[0-9a-f]{3,8}|rgb\()/i)
  })

  it('keine hartcodierte Outline-Farbe im ganzen Blatt', () => {
    const offenders = [
      ...css.matchAll(/outline:\s*[^;{}]*?(hsl\([^)]*\)|#[0-9a-fA-F]{3,8}|rgba?\([^)]*\))/g),
    ]
    expect(offenders.map((m) => m[0])).toEqual([])
  })

  it('.focus-ring und die globale Kontur nutzen denselben Ton', () => {
    expect(ruleFor('.focus-ring:focus-visible')).toContain('var(--color-ring)')
  })

  // border-radius on :focus changes the element shape itself, not only the
  // frame: a rounded pill turned square when focused.
  it('die globale Kontur verbiegt keine Elementform', () => {
    expect(ruleFor('*:focus-visible')).not.toContain('border-radius')
  })
})
