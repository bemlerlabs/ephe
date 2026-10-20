/**
 * The register's phone strip and its save footer, held by contract.
 *
 * Measured 2026-10-10 at 390x844 on the dev surface: the section strip is a
 * 2637 px `overflow-x-auto` row that shows 4 of its 23 chips, and the four group
 * headings that would tell a reader which quarter of the register they are in were
 * `max-md:hidden`. Wrapping was rejected on the same measurement — 23 chips of
 * ~120 px need about 270 px of the 844 — so the strip keeps scrolling and gains the
 * two things scrolling needs to be usable: it settles on a whole chip, and it names
 * the group each run belongs to.
 *
 * This is a static convention scan (the style of `../focusRing.parity.test.ts`),
 * not a layout proof: jsdom computes no widths, so the 4-of-23 and the snap
 * behaviour are proven by the Playwright run in `out/ux-fix-2026-10-10/`. What is
 * held here is the class contract a later edit could silently drop. Each class list
 * sits on one source line, so the anchors are lines, not tags — an opening tag
 * cannot be cut out at the first `>` because its handlers contain one.
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

// Not `new URL('./index.tsx', import.meta.url)`: Vite rewrites that shape into a
// built-asset URL and the read then fails on the scheme.
const SOURCE = [
  readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'index.tsx'), 'utf8'),
  // The chip and the group heading left the page when the nav column became its
  // own module (index.tsx stood at 453 lines against the 400-line wall). The
  // strip and its footer stayed; this contract is about the whole surface.
  readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'registerNav.tsx'), 'utf8'),
].join('\n')

/** The one source line holding `anchor`; a missing or doubled anchor fails naming it. */
function line(anchor: string): string {
  const hits = SOURCE.split('\n').filter((l) => l.includes(anchor))
  const [only] = hits
  if (only === undefined || hits.length !== 1) {
    throw new Error(`"${anchor}" must sit on exactly one source line, found ${hits.length}`)
  }
  return only
}

/** Every chip line: the four groups and the dashed About card share the strip. */
function lines(anchor: string): string[] {
  const hits = SOURCE.split('\n').filter((l) => l.includes(anchor))
  if (hits.length === 0) throw new Error(`"${anchor}" appears on no source line`)
  return hits
}

const nav = line('max-md:[scrollbar-width:none]')
const chips = lines('max-md:whitespace-nowrap')
const groupHeading = line('max-md:self-center')
const title = line('text-ui-lg font-semibold text-foreground/90 truncate max-md:sr-only')
const footer = line('pb-[calc(1rem+env(safe-area-inset-bottom))]')
const scrollColumn = line('pb-[calc(1.5rem+env(safe-area-inset-bottom))]')

describe('register strip at phone width', () => {
  it('scrolls to a whole chip instead of stopping inside a label', () => {
    expect(nav).toMatch(/max-md:snap-x/)
    expect(nav).toMatch(/max-md:snap-mandatory/)
    for (const chip of chips) expect(chip).toMatch(/max-md:snap-start/)
  })

  it('keeps the group heading beside the chips it introduces', () => {
    expect(groupHeading).not.toMatch(/max-md:hidden/)
    expect(groupHeading).toMatch(/uppercase/)
  })

  it('gives the strip no fixed width of its own', () => {
    expect(nav).toMatch(/max-md:w-full/)
    expect(nav).not.toMatch(/max-md:w-\[\d{3,}px\]/)
    for (const chip of chips) expect(chip).toMatch(/max-md:w-auto/)
  })

  it('scrolls the active section into view when the register opens on it', () => {
    expect(SOURCE).toMatch(/scrollIntoView\?\.\(\{[^}]*inline:\s*'start'/)
  })

  it('paints the section name once at phone width', () => {
    // The H1 and the active chip render the same key (`settings.${activeTab}`), so
    // the heading is a second copy of the chip two lines below it. It stays in the
    // a11y tree through `sr-only`, and the detail column keeps its own aria-label.
    expect(title).toMatch(/max-md:sr-only/)
    expect(SOURCE).toMatch(/aria-label=\{t\(`settings\.\$\{activeTab\}`\)\}/)
  })
})

describe('register save footer', () => {
  it('clears the home-indicator band at the end of a notched phone', () => {
    expect(footer).toMatch(/env\(safe-area-inset-bottom\)/)
    expect(scrollColumn).toMatch(/env\(safe-area-inset-bottom\)/)
  })

  it('stays a static flex sibling, so it can never cover the scroll column', () => {
    expect(footer).not.toMatch(/\b(fixed|sticky)\b/)
  })
})
