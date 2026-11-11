/**
 * The header at 320 px: the palette button gets the run bar's last pixels, so a
 * control that cannot follow it out of the way must step back first.
 *
 * Measured on the built dist at 320x568 (B13): `workbench-command` sat at
 * x=336..360, fully outside the viewport, and the run state's right edge was at
 * 328 in a 320 px window. The bar is `overflow: hidden`, so both were cut rather
 * than wrapped. The class contract held here names the two retreats: the
 * companion toggle leaves under 360 px, and the coarse-pointer rule gives the
 * toggle that stays a 44 px box.
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const here = dirname(fileURLToPath(import.meta.url))
const HEADER = readFileSync(join(here, 'index.tsx'), 'utf8')
const COMPANION_CSS = readFileSync(join(here, '../../shell/Companion.css'), 'utf8')

function line(anchor: string): string {
  const hits = HEADER.split('\n').filter((one) => one.includes(anchor))
  const [only] = hits
  if (only === undefined || hits.length !== 1) {
    throw new Error(`"${anchor}" must sit on exactly one source line, found ${hits.length}`)
  }
  return only
}

describe('header controls at 320 px', () => {
  it('moves the companion toggle out of the run bar below 360 px', () => {
    expect(line('header-companion-toggle focus-ring')).toContain('max-[359px]:hidden!')
  })

  it('keeps the toggle a 44 px target where it stays on a coarse pointer', () => {
    const coarse = COMPANION_CSS.slice(COMPANION_CSS.indexOf('@media (pointer: coarse)'))
    expect(coarse).toMatch(/\.header-companion-toggle\s*{[^}]*width:\s*2\.75rem/s)
    expect(coarse).toMatch(/\.header-companion-toggle\s*{[^}]*height:\s*2\.75rem/s)
  })
})
