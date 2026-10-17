/**
 * WD-33: the inactive language is not in the first paint.
 *
 * `src/i18n.ts` used to import both catalogs statically, which put every German byte on
 * an English user's first paint and vice versa. The split is only real while two things
 * hold, and neither of them is visible from the rendered app:
 *
 *  1. no catalog is imported statically again — the entry chunk would swallow it back
 *     (the static-import test below reads the module's own source);
 *  2. the language a user did not choose is not in memory after boot, and the switch
 *     fetches it *before* it is announced.
 *
 * The second half is the flash: `changeLanguage` resolving is not enough, the catalog has
 * to be in the store by the time `languageChanged` is emitted, or the first frames of the
 * switch render key paths. Each case builds its own i18n instance (a fresh module
 * registry), because the language is decided once, at import time.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import type { i18n as I18n } from 'i18next'

const I18N_SOURCE = readFileSync(resolve(process.cwd(), 'src', 'i18n.ts'), 'utf8')

/** A fresh i18n, decided by whatever is in `localStorage` at import time. */
async function bootWith(stored: string | null): Promise<I18n> {
  vi.resetModules()
  localStorage.clear()
  if (stored !== null) localStorage.setItem('i18nextLng', stored)
  const module = await import('./i18n')
  return module.default
}

describe('the locale catalogs stay split per language', () => {
  let instance: I18n | undefined

  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(async () => {
    if (instance) await instance.changeLanguage('en')
    instance = undefined
    localStorage.clear()
    vi.resetModules()
  })

  it('imports no catalog statically', () => {
    expect(I18N_SOURCE).not.toMatch(/^import .*from '\.\/locales\/[a-z]{2}\.json'$/m)
    expect(I18N_SOURCE).toContain('import(`./locales/${')
  })

  it('boots with the stored language and leaves the other catalog out of memory', async () => {
    instance = await bootWith('de')

    expect(instance.language).toBe('de')
    expect(instance.hasResourceBundle('de', 'translation')).toBe(true)
    expect(instance.hasResourceBundle('en', 'translation')).toBe(false)
    // The first paint has sentences, not key paths: the awaited preload is what keeps
    // German out of the "not in memory yet" window.
    expect(instance.t('workspaces.title')).toBe('Arbeitsbereiche')
  })

  it('reads English without a stored choice and holds no German', async () => {
    instance = await bootWith(null)

    expect(instance.language).toBe('en')
    expect(instance.hasResourceBundle('en', 'translation')).toBe(true)
    expect(instance.hasResourceBundle('de', 'translation')).toBe(false)
  })

  it('fetches the other catalog when it is chosen', async () => {
    instance = await bootWith('en')
    expect(instance.hasResourceBundle('de', 'translation')).toBe(false)

    await instance.changeLanguage('de')

    expect(instance.hasResourceBundle('de', 'translation')).toBe(true)
    expect(instance.t('workspaces.title')).toBe('Arbeitsbereiche')
  })

  it('holds the catalog in memory before it announces the language', async () => {
    const booted = await bootWith('en')
    instance = booted
    const readyWhenAnnounced: boolean[] = []
    booted.on('languageChanged', (lng: string) => {
      readyWhenAnnounced.push(booted.hasResourceBundle(lng, 'translation'))
    })

    await booted.changeLanguage('de')

    expect(readyWhenAnnounced).toEqual([true])
  })

  it('lands in the new language with no catalog behind it when its chunk never arrives', async () => {
    // The shape, measured — not a promise. i18next announces the language it was asked for
    // even when the backend reported an error for it (`changeLanguage`'s `done(err, l)`
    // passes `l` regardless of the error), and nothing here keeps the language the user was
    // reading: its catalog stays in the store, unused, while the new language paints key
    // paths. Closing that means promising the old language stays, which `i18n.ts` does not,
    // so this case holds the measured behaviour still instead.
    instance = await bootWith('de')
    expect(instance.hasResourceBundle('de', 'translation')).toBe(true)
    vi.doMock('./locales/en.json', () => {
      throw new Error('offline: the en chunk could not be fetched')
    })
    try {
      const announced: string[] = []
      instance.on('languageChanged', (lng: string) => announced.push(lng))

      await instance.changeLanguage('en')

      expect(announced).toEqual(['en'])
      expect(instance.language).toBe('en')
      expect(instance.hasResourceBundle('en', 'translation')).toBe(false)
      expect(instance.t('workspaces.title')).toBe('workspaces.title')
    } finally {
      vi.doUnmock('./locales/en.json')
      vi.resetModules()
    }
  })
})
