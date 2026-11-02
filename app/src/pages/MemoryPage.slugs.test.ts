/**
 * W-2 — the Knowledge sub-pages answer to German slugs under labels that translate.
 *
 * The four views of `/memory/:view` carry the slugs `bestand`, `korrekturen`, `papierkorb`
 * and `gehirne`, while the nav row renders each label in the reader's language. That split is
 * deliberate. The slug is the identifier — it travels in bookmarks, in the desktop shell's
 * parity probe (`tests/playwright/shell-parity.manifest.json`), in the theme baselines' shot
 * keys, in the deep-link tests and in the walkthrough evidence. The label is the text, and
 * text translates. Renaming one side alone breaks the other side's promise: a renamed slug
 * strands every bookmark and every pinned read, a translated slug would make the address
 * language-dependent.
 *
 * This lane's witnesses keep the pair from drifting apart quietly: the frozen slug set, the
 * label each catalog owes to each slug, and the manifest's probe of the `/memory/:view` route
 * must move together or fail here. The same convention holds for `/artifacts/:view` (`regal`,
 * `ablage`).
 */
import { describe, it, expect } from 'vitest'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'

/** The app directory, found from either run root (app/ or the repository root). */
function findApp(): string {
  for (const base of [process.cwd(), resolve(process.cwd(), 'app')]) {
    if (existsSync(resolve(base, 'src', 'locales', 'de.json'))) return base
  }
  throw new Error(`app directory not found below ${process.cwd()}`)
}

const APP = findApp()
const read = (rel: string) => JSON.parse(readFileSync(resolve(APP, rel), 'utf-8'))

const en = read('src/locales/en.json')
const de = read('src/locales/de.json')
const manifest = read('tests/playwright/shell-parity.manifest.json')

/** The frozen sub-page slugs of `/memory/:view` — the address-bar half of the contract. */
const MEMORY_SLUGS = ['bestand', 'korrekturen', 'papierkorb', 'gehirne']

describe('the memory sub-page slugs are the contract beside their labels', () => {
  it.each(MEMORY_SLUGS)('both catalogs name the view the address calls %s', (slug) => {
    expect(en.memory.view[slug]).toMatch(/\S/)
    expect(de.memory.view[slug]).toMatch(/\S/)
  })

  it('freezes exactly the four slugs, so a rename is a decision with witnesses', () => {
    expect(Object.keys(en.memory.view).sort()).toEqual([...MEMORY_SLUGS].sort())
    expect(Object.keys(de.memory.view).sort()).toEqual([...MEMORY_SLUGS].sort())
  })

  it('lets the desktop shell probe the :view route with one of the frozen slugs', () => {
    const entry = manifest.routes.find((r: { path: string }) => r.path === '/memory/:view')
    expect(entry).toBeTruthy()
    expect(MEMORY_SLUGS).toContain(String(entry.probe).replace(/^\/memory\//, ''))
  })
})
