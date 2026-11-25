/**
 * LS-1: the register's copy is a lazy read, and it is complete when it arrives.
 *
 * Three things hold the split together, and none of them shows in a rendered panel:
 *
 *  1. the copy is reached through `import()`, so the bundler emits a chunk of its own —
 *     a static import would fold it back into the chunk that opens the register and the
 *     bytes would be on the first paint again. This reads the module's own source for
 *     exactly that reason; the byte proof is `scripts/bundle_budget.py` on `app/dist`.
 *  2. both languages are named, so a German visitor fetches the German half alone.
 *  3. the leaves that arrive are the leaves the register asks for, in the language the
 *     user reads. A missing leaf would show as a key path inside a row, which is the
 *     defect this file exists to keep out.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

import copyDe from './settingsCopy.de.json'
import copyEn from './settingsCopy.en.json'

const SOURCE = readFileSync(resolve(process.cwd(), 'src', 'lib', 'settingsCopy.ts'), 'utf8')

/** A field that carries a hint, spelled the way `core/settings_hints.py` names it. */
const HINT_KEY = 'settings.shortcutsGlobalEnabledHint'
/** A row title, spelled the way `core/settings_schema.py` labels it. */
const TITLE_KEY = 'settings.advancedFilmSfxDir'

async function load(language: string) {
  vi.resetModules()
  const [{ default: i18n }, copy] = await Promise.all([import('../i18n'), import('./settingsCopy')])
  copy.resetSettingsCopy()
  await copy.ensureSettingsCopy(language)
  return { i18n, copy }
}

describe('the register copy is loaded on demand', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('reaches both language files through a dynamic import', () => {
    expect(SOURCE).toContain("import('./settingsCopy.de.json')")
    expect(SOURCE).toContain("import('./settingsCopy.en.json')")
    expect(SOURCE).not.toMatch(/^import\s+\w+\s+from\s+'\.\/settingsCopy\.(de|en)\.json'/m)
  })

  it('names each language separately so one visit fetches one half', async () => {
    const { i18n, copy } = await load('de')
    expect(copy.settingsCopyLanguage()).toBe('de')
    expect(i18n.getFixedT('de')(HINT_KEY)).toBe(copyDe.settings.shortcutsGlobalEnabledHint)
    expect(i18n.getFixedT('de')(HINT_KEY)).not.toBe(copyEn.settings.shortcutsGlobalEnabledHint)
  })

  it('brings the German sentence the register row asks for', async () => {
    const { i18n } = await load('de')
    const text = i18n.getFixedT('de')(HINT_KEY)
    expect(typeof text).toBe('string')
    expect(text).not.toBe(HINT_KEY)
    expect(text.length).toBeGreaterThan(20)
  })

  it('brings the row title beside the hint', async () => {
    const { i18n } = await load('en')
    expect(i18n.getFixedT('en')(TITLE_KEY)).toBe(copyEn.settings.advancedFilmSfxDir)
  })

  it('reads again after a language switch instead of serving the old half', async () => {
    const { i18n, copy } = await load('de')
    copy.resetSettingsCopy()
    await copy.ensureSettingsCopy('en')
    expect(copy.settingsCopyLanguage()).toBe('en')
    expect(i18n.getFixedT('en')(HINT_KEY)).toBe(copyEn.settings.shortcutsGlobalEnabledHint)
  })

  it('holds every leaf the register ships, in both languages', () => {
    expect(Object.keys(copyDe.settings).sort()).toEqual(Object.keys(copyEn.settings).sort())
    expect(Object.keys(copyDe.settings).length).toBeGreaterThanOrEqual(100)
  })

  // The other half of the promise: nobody who never opens the register loads these words.
  // The catalogs stopped carrying them on 2026-11-24; the case is the proof, so it runs.
  // Read from disk, not by import: `addResourceBundle` merges into the very object
  // `i18n.ts` took from the boot catalog, so an imported catalog would show the leaves this
  // file's own cases just loaded and say nothing about what the bundler ships.
  it('the start bundle carries none of the register copy', () => {
    const catalog = (language: string) =>
      JSON.parse(readFileSync(resolve(process.cwd(), 'src', 'locales', `${language}.json`), 'utf8'))
        .settings as Record<string, unknown>
    const de = catalog('de')
    const en = catalog('en')
    expect(Object.keys(de).length).toBeGreaterThan(800)
    expect(Object.keys(en).length).toBeGreaterThan(800)
    const overlap = Object.keys(copyDe.settings).filter((leaf) => leaf in de || leaf in en)
    expect(overlap).toEqual([])
  })
})
