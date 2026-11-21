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
  it('Cmd+K (lowercase) toggles', () => {
    expect(isPaletteToggle(ev({ key: 'k', metaKey: true }))).toBe(true)
  })

  it('Cmd+K with CapsLock/Shift (uppercase K) toggles; a strict k check regressed', () => {
    expect(isPaletteToggle(ev({ key: 'K', metaKey: true }))).toBe(true)
  })

  it('Ctrl+K toggles (Windows/Linux)', () => {
    expect(isPaletteToggle(ev({ key: 'k', ctrlKey: true }))).toBe(true)
  })

  it('code KeyK toggles when key is anomalous', () => {
    expect(isPaletteToggle(ev({ key: 'Dead', code: 'KeyK', metaKey: true }))).toBe(true)
  })

  it('K without a modifier does not toggle, else the composer could not type k', () => {
    expect(isPaletteToggle(ev({ key: 'k' }))).toBe(false)
    expect(isPaletteToggle(ev({ key: 'K' }))).toBe(false)
  })

  it('Cmd plus any other letter does not toggle', () => {
    expect(isPaletteToggle(ev({ key: 'p', metaKey: true }))).toBe(false)
  })
})
