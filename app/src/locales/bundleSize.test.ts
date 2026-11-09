/**
 * WD-33 — what each locale catalog weighs.
 *
 * `src/i18n.ts` used to import `./locales/en.json` and `./locales/de.json` at the top of
 * the module, which put both files in the entry chunk: every byte here was downloaded by
 * every user before the first paint, in both languages. Since the WD-33 split each catalog
 * is a chunk of its own and is fetched when its language is chosen, so a file's size is
 * what one reader of that language pays. (`src/i18n.lazySplit.test.ts` guards the split
 * itself; this file weighs the bytes.)
 *
 * There is no weight budget. The owner lifted it on 2026-11-05. A ceiling never
 * distinguished a copy block that should have been shorter from a feature that simply needed
 * words, so what it produced in practice was a two-step tax on every wave: write the German
 * in as few bytes as possible, then raise a number in a separate commit and measure the same
 * bytes again. Its last entry priced sixty-seven leaves "for the whole remaining programme" —
 * by then the mechanism was a forecast to defend, not a bound to respect. The ledger of
 * forty-two raises that recorded lived in this file; the history stays in git, where it is
 * readable without taxing the next feature.
 *
 * What is kept is the measurement, plus the one thing a size number can still detect: a
 * catalog that has stopped being a translation. Key parity and placeholder correctness live
 * in the neighbour gates (`completeness.test.ts`, `../lib/locales.test.ts`), and a German
 * leaf that only repeats its English twin in `germanSurface.test.ts`.
 */
import { describe, it, expect } from 'vitest'
import { existsSync, statSync } from 'node:fs'
import { resolve } from 'node:path'

/** app/src, found from the run's cwd (vitest runs at the app or the repo root). */
function findLocales(): string {
  for (const base of [process.cwd(), resolve(process.cwd(), 'app')]) {
    const candidate = resolve(base, 'src', 'locales')
    if (existsSync(resolve(candidate, 'de.json'))) return candidate
  }
  throw new Error(`app/src/locales not found below ${process.cwd()}`)
}
const LOCALES = findLocales()
const size = (name: string) => statSync(resolve(LOCALES, name)).size

// The ledger of ceiling raises that filled this space is in git, which is where the
// header says it belongs. The budget itself was dissolved on 2026-11-05, so no ceiling
// is asserted here any more: a copy block used to pay for its bytes twice, once in the
// catalog and once in a second commit that raised a number and measured the same bytes
// again. What the file still reports is the weight, and what it still refuses is the
// inflation ratio below.

// German runs 1.07x English here (96,075 / 89,756). A pair far outside that range
// is a defect rather than a translation: a duplicated block, or English pasted into
// the German file and left half-migrated.
const MAX_INFLATION = 1.4

describe('locale weight', () => {
  const en = size('en.json')
  const de = size('de.json')

  it('reports what the pair weighs', () => {
    console.log(`locale weight: en ${en} B, de ${de} B, both ${en + de} B`)
    expect(en).toBeGreaterThan(0)
    expect(de).toBeGreaterThan(0)
  })

  it('keeps German in a plausible range of English', () => {
    expect(de / en, `de/en = ${(de / en).toFixed(3)} exceeds ${MAX_INFLATION}`).toBeLessThanOrEqual(
      MAX_INFLATION,
    )
  })
})
