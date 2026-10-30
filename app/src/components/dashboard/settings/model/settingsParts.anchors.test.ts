/**
 * A nav row that scrolls to nothing is worse than no nav row.
 *
 * TAB_PARTS names blocks the section modules render by hand, so nothing at run
 * time proves the anchor exists — this reads the sources and refuses an entry
 * whose id is not rendered somewhere in the register, or whose label is a word
 * one of the bundles does not carry.
 */
import { readFileSync, readdirSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { TAB_PARTS } from './settingsParts'
import { DEEP_PREFIX } from './deepRegister'

// Vitest rewrites import.meta.url to an http URL, so the register is read from
// the run's working directory, the same way the style and locale source tests do.
const SETTINGS_DIR = 'src/components/dashboard/settings'
const LOCALE_DIR = 'src/locales'

function sources(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = `${dir}/${entry.name}`
    if (entry.isDirectory()) sources(path, out)
    else if (/\.(tsx|ts)$/.test(entry.name) && !entry.name.includes('.test.')) out.push(path)
  }
  return out
}

const corpus = sources(SETTINGS_DIR)
  .map((path) => readFileSync(path, 'utf8'))
  .join('\n')

/** The bundles nest: `settings.deepSection.network` is three objects deep. */
function lookup(bundle: unknown, key: string): string | undefined {
  const steps = key.split('.')
  let node = bundle
  for (let i = 0; i < steps.length; i++) {
    if (typeof node !== 'object' || node === null) return undefined
    const table = node as Record<string, unknown>
    // Some entries keep the dot in the key itself: `shortcutsGroup.global`.
    const flat = table[steps.slice(i).join('.')]
    if (typeof flat === 'string') return flat
    node = table[steps[i] as string]
  }
  return typeof node === 'string' ? node : undefined
}

const bundles = ['en', 'de'].map((tag) =>
  JSON.parse(readFileSync(`${LOCALE_DIR}/${tag}.json`, 'utf8')),
)

const parts = Object.entries(TAB_PARTS).flatMap(([tab, subs]) =>
  (subs ?? []).filter((sub) => !sub.id.startsWith(DEEP_PREFIX)).map((sub) => ({ tab, ...sub })),
)

describe('settings page parts', () => {
  it('names a block the register renders', () => {
    const missing = parts.filter((one) => !corpus.includes(`testid="${one.id}"`))
    expect(missing.map((one) => `${one.tab}/${one.id}`)).toEqual([])
  })

  it('labels each block with a word both bundles carry', () => {
    const unheld = parts.filter(
      (one) => bundles.some((bundle) => lookup(bundle, one.labelKey) === undefined),
    )
    expect(unheld.map((one) => `${one.tab}/${one.labelKey}`)).toEqual([])
  })

  it('expands the areas the schema alone could not reach', () => {
    // The register blocks come from the server; these are the hand-built ones.
    expect(parts.length).toBeGreaterThanOrEqual(30)
    expect(new Set(parts.map((one) => one.tab)).size).toBeGreaterThanOrEqual(12)
  })
})
