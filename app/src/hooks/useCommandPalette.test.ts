/**
 * F-03: the Cmd/Ctrl+K toggle detection (useCommandPalette)
 *
 * GIVEN  isPaletteToggle (a pure KeyboardEvent test)
 * WHEN   different key variants arrive
 * THEN   Cmd/Ctrl+K toggles — case-independent, with a KeyK code fallback;
 *        a bare K and any other letter do NOT toggle.
 */
import { describe, it, expect } from 'vitest'
import { isPaletteToggle } from './useCommandPalette'

function ev(partial: { key: string; code?: string; metaKey?: boolean; ctrlKey?: boolean }) {
  return partial
}

describe('isPaletteToggle (F-03)', () => {
  it('Cmd+K (klein) togglet', () => {
    expect(isPaletteToggle(ev({ key: 'k', metaKey: true }))).toBe(true)
  })

  it('Cmd+K bei CapsLock/Shift (groß "K") togglet — Regression: exakter === "k"-Vergleich', () => {
    expect(isPaletteToggle(ev({ key: 'K', metaKey: true }))).toBe(true)
  })

  it('Ctrl+K togglet (Windows/Linux)', () => {
    expect(isPaletteToggle(ev({ key: 'k', ctrlKey: true }))).toBe(true)
  })

  it('code "KeyK" togglet, falls key anomal ist', () => {
    expect(isPaletteToggle(ev({ key: 'Dead', code: 'KeyK', metaKey: true }))).toBe(true)
  })

  it('K ohne Modifier togglet NICHT (sonst tippt man kein k im Composer)', () => {
    expect(isPaletteToggle(ev({ key: 'k' }))).toBe(false)
    expect(isPaletteToggle(ev({ key: 'K' }))).toBe(false)
  })

  it('Cmd+andere Buchstaben toggleln NICHT', () => {
    expect(isPaletteToggle(ev({ key: 'p', metaKey: true }))).toBe(false)
  })
})
