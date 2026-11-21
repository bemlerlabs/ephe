/**
 * P1-16 (parity audit 2026-10-13): the shortcut table is the one source.
 *
 * The evidence: 12 entries, but 11 of the 12 ids had zero references outside this
 * file — the table could name a key nobody handled. These tests pin the two halves
 * that make the table binding rather than decorative:
 *   1. every entry resolves from a real KeyboardEvent shape (`matchShortcut`),
 *   2. the rendered glyph is *derived* from that binding, so a glyph cannot drift
 *      away from the key the matcher accepts.
 */
import { describe, it, expect } from 'vitest'
import { SHORTCUTS, SHORTCUTS_BY_ID, matchShortcut, renderKeys, type KeyLike } from './shortcuts'

const press = (o: Partial<KeyLike> & { key: string }): KeyLike => ({
  metaKey: false,
  ctrlKey: false,
  shiftKey: false,
  altKey: false,
  ...o,
})

describe('the shortcut table', () => {
  it('has unique ids', () => {
    const ids = SHORTCUTS.map((s) => s.id)
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('indexes every row under its own id', () => {
    for (const s of SHORTCUTS) expect(SHORTCUTS_BY_ID[s.id]).toBe(s)
  })

  it('carries the panel focus binding (⌘O) that only the palette listener knew', () => {
    // useCommandPalette.ts:82 handled ⌘O with no row in the table.
    const focus = SHORTCUTS_BY_ID.panelFocus
    expect(focus).toBeTruthy()
    expect(matchShortcut(press({ key: 'o', metaKey: true }))?.id).toBe('panelFocus')
  })

  it('marks the composing keys as field-local, never as global dispatch', () => {
    for (const id of ['send', 'close'] as const) {
      expect(SHORTCUTS_BY_ID[id]?.scope).toBe('field')
    }
    expect(
      SHORTCUTS.filter((s) => s.scope === 'field')
        .map((s) => s.id)
        .sort(),
    ).toEqual(['close', 'send'])
  })
})

describe('matchShortcut — the one key-to-id resolution', () => {
  it('resolves every global row from its own binding', () => {
    for (const s of SHORTCUTS.filter((x) => x.scope === 'global')) {
      const b = s.binding
      const key = b.key === 'digit' ? '1' : b.key
      const hit = matchShortcut(press({ key, metaKey: b.mod, shiftKey: b.shift, altKey: b.alt }))
      expect(hit?.id, `binding of ${s.id} must resolve back to ${s.id}`).toBe(s.id)
    }
  })

  it('accepts Ctrl where the Mac form is Cmd (Windows/Linux parity)', () => {
    expect(matchShortcut(press({ key: 'b', ctrlKey: true }))?.id).toBe('sidebar')
    expect(matchShortcut(press({ key: 'B', ctrlKey: true }))?.id).toBe('sidebar')
  })

  it('covers the tenth panel tab (⌘0) and rejects digits with Shift', () => {
    expect(matchShortcut(press({ key: '0', metaKey: true }))?.id).toBe('panelTabs')
    expect(matchShortcut(press({ key: '9', metaKey: true }))?.id).toBe('panelTabs')
    expect(matchShortcut(press({ key: '1', metaKey: true, shiftKey: true }))).toBeNull()
  })

  it('keeps the Shift collision rule: ⌘F is native find, ⌘⇧F is composer focus', () => {
    expect(matchShortcut(press({ key: 'f', metaKey: true }))).toBeNull()
    expect(matchShortcut(press({ key: 'f', metaKey: true, shiftKey: true }))?.id).toBe(
      'focusComposer',
    )
  })

  it('keeps ⌘B and ⌥⌘B apart', () => {
    expect(matchShortcut(press({ key: 'b', metaKey: true }))?.id).toBe('sidebar')
    expect(matchShortcut(press({ key: 'b', metaKey: true, altKey: true }))?.id).toBe('panelToggle')
  })

  it('returns null for keys the table does not carry', () => {
    expect(matchShortcut(press({ key: 'q', metaKey: true }))).toBeNull()
    expect(matchShortcut(press({ key: 'b' }))).toBeNull()
    expect(matchShortcut(press({ key: 'ArrowLeft', metaKey: true }))).toBeNull()
  })
})

describe('the glyph is derived from the binding', () => {
  it('renders mod+letter rows as one Mac glyph', () => {
    for (const s of SHORTCUTS) {
      const b = s.binding
      expect(s.keys.startsWith('⌘') || !b.mod, `${s.id}: mod must lead the glyph`).toBe(true)
      if (b.key.length === 1) expect(s.keys.endsWith(b.key.toUpperCase())).toBe(true)
    }
  })

  it('swaps the Mac glyphs for the Ctrl variant off-Mac', () => {
    const bar = SHORTCUTS_BY_ID.sidebar
    expect(renderKeys(bar.keys, true)).toBe('⌘ B')
    expect(renderKeys(bar.keys, false)).toBe('Ctrl B')
  })
})
