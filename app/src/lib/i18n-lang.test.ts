import { describe, it, expect } from 'vitest'
import i18n, { languageFrom } from '../i18n'

describe('boot language (first start)', () => {
  it('follows the browser when nothing is stored, and a stored choice wins', () => {
    expect(languageFrom(null, 'de-DE')).toBe('de')
    expect(languageFrom('', 'de-DE')).toBe('de')
    expect(languageFrom('en-US', 'de-DE')).toBe('en')
    expect(languageFrom(null, 'fr-FR')).toBe('en')
    expect(languageFrom('xx', 'de-DE')).toBe('en')
  })
})

// R36 regression: <html lang> must track the active UI language. The value in
// index.html is only the bootstrap default ('en' — the i18n fallback); without
// the languageChanged sync, screen readers announced the English UI with
// German pronunciation rules while the user had switched languages.
describe('document lang sync (R36)', () => {
  it('bootstrap default resolves to the fallback language', () => {
    expect(document.documentElement.lang).toBe('en')
  })

  it('follows languageChanged in both directions', async () => {
    await i18n.changeLanguage('de')
    expect(document.documentElement.lang).toBe('de')
    await i18n.changeLanguage('en')
    expect(document.documentElement.lang).toBe('en')
  })
})
